"""
Pull NANC, KRUZ, SPY daily prices. Try CRSP via WRDS first, fallback to yfinance.

Output: data/etf_prices.parquet with columns: date, ticker, prc, ret
"""

import builtins, os
_u = os.environ.get("WRDS_USERNAME", "hoovyalert")
def _ai(p=""):
    v = _u if "username" in p.lower() else ""
    print(p + v)
    return v
builtins.input = _ai

import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
OUT = DATA_DIR / "etf_prices.parquet"

TICKERS = ["NANC", "KRUZ", "SPY"]
START = "2023-02-01"
END   = pd.Timestamp.today().strftime("%Y-%m-%d")

# Expense ratios (annualised), used in the report for fee-drag annotation
EXPENSE_RATIOS = {"NANC": 0.0075, "KRUZ": 0.0075, "SPY": 0.000945}


def pull_from_wrds():
    import wrds
    print("Connecting to WRDS...")
    db = wrds.Connection(wrds_username=_u)

    print(f"Looking up permnos for {TICKERS}...")
    df_map = db.raw_sql(
        "SELECT DISTINCT ticker, permno, issuernm AS comnam, namedt, nameenddt "
        "FROM crsp.stocknames_v2 "
        "WHERE ticker IN %(tickers)s",
        params={"tickers": tuple(TICKERS)},
    )
    if df_map.empty:
        print("No CRSP matches found.")
        db.close()
        return None

    df_map["namedt"] = pd.to_datetime(df_map["namedt"])
    df_map = df_map.sort_values("namedt").drop_duplicates("ticker", keep="last")
    print(df_map[["ticker", "permno", "comnam"]].to_string(index=False))

    if not set(TICKERS).issubset(set(df_map["ticker"].values)):
        missing = set(TICKERS) - set(df_map["ticker"].values)
        print(f"CRSP missing: {missing} -- will fall back to yfinance")
        db.close()
        return None

    permnos = df_map["permno"].astype(int).tolist()
    print(f"Pulling prices for permnos {permnos}, {START} to {END}...")
    prices = db.raw_sql(
        "SELECT dlycaldt AS date, permno, dlyprc AS prc, dlyret AS ret "
        "FROM crsp.dsf_v2 "
        "WHERE permno IN %(permnos)s AND dlycaldt BETWEEN %(s)s AND %(e)s",
        params={"permnos": tuple(permnos), "s": START, "e": END},
    )
    db.close()

    prices["prc"] = prices["prc"].abs()
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.merge(df_map[["ticker", "permno"]], on="permno", how="left")
    return prices[["date", "ticker", "prc", "ret"]]


def pull_from_compustat():
    """Compustat secd (securities daily) via WRDS -- alternative to CRSP for ETF coverage."""
    import wrds
    print("Connecting to WRDS (Compustat)...")
    db = wrds.Connection(wrds_username=_u)

    # Compustat security identifier lookup
    print("Looking up Compustat gvkey/iid for tickers...")
    sec = db.raw_sql(
        "SELECT DISTINCT gvkey, iid, tic "
        "FROM comp.security "
        "WHERE tic IN %(tickers)s",
        params={"tickers": tuple(TICKERS)},
    )
    print(sec.to_string(index=False) if not sec.empty else "  (no matches)")

    if sec.empty:
        db.close()
        return None

    # Pull daily prices from comp.secd
    print("Pulling daily prices from comp.secd...")
    pairs = list(zip(sec["gvkey"].tolist(), sec["iid"].tolist()))
    where_clauses = " OR ".join([f"(gvkey='{g}' AND iid='{i}')" for g, i in pairs])
    prices = db.raw_sql(
        f"SELECT datadate, gvkey, iid, prccd, ajexdi, trfd "
        f"FROM comp.secd "
        f"WHERE ({where_clauses}) AND datadate BETWEEN %(s)s AND %(e)s",
        params={"s": START, "e": END},
    )
    db.close()

    if prices.empty:
        return None

    prices = prices.merge(sec[["gvkey", "iid", "tic"]], on=["gvkey", "iid"], how="left")
    prices = prices.rename(columns={"datadate": "date", "tic": "ticker", "prccd": "prc"})
    prices["date"] = pd.to_datetime(prices["date"])
    # Total return = (price / split-adjust) * total-return-factor; use trfd for adjusted return
    prices = prices.sort_values(["ticker", "date"]).reset_index(drop=True)
    prices["adj_prc"] = prices["prc"] / prices["ajexdi"] * prices["trfd"]
    prices["ret"] = prices.groupby("ticker")["adj_prc"].pct_change()
    return prices[["date", "ticker", "prc", "ret"]]


def pull_from_yahoo_direct(tickers=None):
    """Direct Yahoo Finance v8 API -- avoids yfinance library rate-limit."""
    import requests
    from datetime import datetime
    if tickers is None:
        tickers = TICKERS
    p1 = int(datetime.strptime(START, "%Y-%m-%d").timestamp())
    p2 = int(datetime.strptime(END, "%Y-%m-%d").timestamp()) + 86400
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    frames = []
    for t in tickers:
        print(f"Pulling {t} from Yahoo direct...")
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{t}"
               f"?interval=1d&period1={p1}&period2={p2}")
        try:
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            result = r.json()["chart"]["result"][0]
            timestamps = result["timestamp"]
            closes = result["indicators"]["quote"][0]["close"]
            s = pd.DataFrame({
                "date": pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(None),
                "ticker": t,
                "prc": closes,
            }).dropna(subset=["prc"])
            s["date"] = s["date"].dt.normalize()
            s["ret"] = s["prc"].pct_change()
            frames.append(s)
            print(f"  ok: {len(s)} rows, {s['date'].min().date()} to {s['date'].max().date()}")
        except Exception as e:
            print(f"  {t} failed: {e}")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def pull_from_yfinance(tickers=None):
    import yfinance as yf
    import time
    if tickers is None:
        tickers = TICKERS
    frames = []
    for t in tickers:
        print(f"Pulling {t} from yfinance...")
        for attempt in range(5):
            try:
                tk = yf.Ticker(t)
                hist = tk.history(start=START, end=END, auto_adjust=True)
                if hist.empty:
                    raise RuntimeError("empty history")
                hist = hist.reset_index()
                s = pd.DataFrame({
                    "date": pd.to_datetime(hist["Date"]).dt.tz_localize(None),
                    "ticker": t,
                    "prc": hist["Close"].values,
                })
                s["ret"] = s["prc"].pct_change()
                frames.append(s)
                print(f"  ok: {len(s)} rows, {s['date'].min().date()} to {s['date'].max().date()}")
                break
            except Exception as e:
                wait = 5 * (attempt + 1)
                print(f"  attempt {attempt+1} failed ({e}); waiting {wait}s")
                time.sleep(wait)
        else:
            print(f"  FAILED to pull {t} after 5 attempts")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _sufficient(sub, label):
    """Return True if sub has >=100 rows starting within 30 days of START."""
    start_dt = pd.Timestamp(START)
    if sub.empty or len(sub) < 100:
        return False
    if sub["date"].min() > start_dt + pd.Timedelta(days=30):
        print(f"  {label}: late start {sub['date'].min().date()} for {sub['ticker'].iloc[0]}")
        return False
    if pd.to_datetime(sub["date"].max()) < pd.to_datetime(END) - pd.Timedelta(days=14):
        print(f"  {label}: early end {sub['date'].max().date()} for {sub['ticker'].iloc[0]} (expected ~{END})")
        return False
    return True


def main():
    if OUT.exists():
        print(f"{OUT.name} already exists -- re-pulling.")

    collected = {}  # ticker -> DataFrame

    # --- CRSP ---
    try:
        crsp = pull_from_wrds()
    except Exception as e:
        print(f"CRSP failed: {e}")
        crsp = None

    if crsp is not None and not crsp.empty:
        for t in TICKERS:
            sub = crsp[crsp["ticker"] == t]
            if _sufficient(sub, "CRSP"):
                collected[t] = sub
                print(f"  CRSP ok: {t} {len(sub)} days {sub['date'].min().date()} to {sub['date'].max().date()}")

    missing = [t for t in TICKERS if t not in collected]

    # --- Compustat ---
    if missing:
        print(f"\nMissing after CRSP: {missing} -- trying Compustat")
        try:
            comp = pull_from_compustat()
        except Exception as e:
            print(f"Compustat failed: {e}")
            comp = None

        if comp is not None and not comp.empty:
            for t in list(missing):
                sub = comp[comp["ticker"] == t]
                if _sufficient(sub, "Compustat"):
                    collected[t] = sub
                    missing.remove(t)
                    print(f"  Compustat ok: {t} {len(sub)} days {sub['date'].min().date()} to {sub['date'].max().date()}")

    # --- Yahoo direct ---
    if missing:
        print(f"\nMissing after Compustat: {missing} -- trying Yahoo direct API")
        yf_df = pull_from_yahoo_direct(tickers=missing)
        if not yf_df.empty:
            for t in list(missing):
                sub = yf_df[yf_df["ticker"] == t]
                if not sub.empty:
                    collected[t] = sub
                    missing.remove(t)
                    print(f"  Yahoo direct ok: {t} {len(sub)} days")

    # --- yfinance (final fallback) ---
    if missing:
        print(f"\nMissing after Yahoo direct: {missing} -- trying yfinance")
        yf_df2 = pull_from_yfinance(tickers=missing)
        if not yf_df2.empty:
            for t in list(missing):
                sub = yf_df2[yf_df2["ticker"] == t]
                if not sub.empty:
                    collected[t] = sub
                    missing.remove(t)
                    print(f"  yfinance ok: {t} {len(sub)} days")

    if missing:
        print(f"WARNING: no data obtained for: {missing}")

    if not collected:
        print("FATAL: no data from any source")
        return

    df = pd.concat(list(collected.values()), ignore_index=True)
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    df.to_parquet(OUT, index=False)

    print(f"\nSaved {len(df):,} rows to {OUT.name}")
    print("\n--- Summary by ticker ---")
    for t in TICKERS:
        sub = df[df["ticker"] == t]
        if sub.empty:
            print(f"  {t}: NO DATA")
            continue
        first = sub.iloc[0]
        last = sub.iloc[-1]
        cum_ret = (1 + sub["ret"].dropna()).prod() - 1
        print(f"  {t}: {len(sub):>4} days | {first['date'].date()} to {last['date'].date()} | "
              f"prc {first['prc']:.2f} -> {last['prc']:.2f} | cum_ret {cum_ret:+.2%} | "
              f"expense ratio {EXPENSE_RATIOS[t]:.2%}")


if __name__ == "__main__":
    main()
