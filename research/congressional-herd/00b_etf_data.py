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
END   = "2024-12-31"

# Expense ratios (annualised), used in the report for fee-drag annotation
EXPENSE_RATIOS = {"NANC": 0.0075, "KRUZ": 0.0075, "SPY": 0.000945}


def pull_from_wrds():
    import wrds
    print("Connecting to WRDS...")
    db = wrds.Connection(wrds_username=_u)

    print(f"Looking up permnos for {TICKERS}...")
    df_map = db.raw_sql(
        "SELECT DISTINCT ticker, permno, comnam, namedt, nameenddt "
        "FROM crsp.stocknames "
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
        "SELECT date, permno, prc, ret "
        "FROM crsp.dsf "
        "WHERE permno IN %(permnos)s AND date BETWEEN %(s)s AND %(e)s",
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
        "SELECT DISTINCT gvkey, iid, tic, conm "
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


def pull_from_stooq():
    """Direct HTTP fetch from stooq -- bypasses pandas_datareader parser issues."""
    import requests
    from io import StringIO
    d1 = START.replace("-", "")
    d2 = END.replace("-", "")
    headers = {"User-Agent": "Mozilla/5.0"}
    frames = []
    for t in TICKERS:
        print(f"Pulling {t} from stooq...")
        url = f"https://stooq.com/q/d/l/?s={t.lower()}.us&i=d&d1={d1}&d2={d2}"
        try:
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            text = r.text.strip()
            if text.startswith("<") or "No data" in text or len(text) < 50:
                print(f"  {t}: no data ({text[:80]!r})")
                continue
            hist = pd.read_csv(StringIO(text))
            if "Close" not in hist.columns or "Date" not in hist.columns:
                print(f"  {t}: unexpected columns {list(hist.columns)}")
                continue
            hist = hist.dropna(subset=["Close", "Date"]).sort_values("Date").reset_index(drop=True)
            s = pd.DataFrame({
                "date": pd.to_datetime(hist["Date"]),
                "ticker": t,
                "prc": hist["Close"].values,
            })
            s["ret"] = s["prc"].pct_change()
            frames.append(s)
            print(f"  ok: {len(s)} rows, {s['date'].min().date()} to {s['date'].max().date()}")
        except Exception as e:
            print(f"  failed: {e}")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def pull_from_yfinance():
    import yfinance as yf
    import time
    frames = []
    for t in TICKERS:
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


def main():
    if OUT.exists():
        print(f"{OUT.name} already exists -- re-pulling.")

    df = None
    try:
        df = pull_from_wrds()
    except Exception as e:
        print(f"WRDS pull failed: {e}")
        df = None

    # CRSP daily often has sparse coverage for newer ETFs (NANC and KRUZ launched 2023).
    # If any ticker has <100 days of data, fall back to yfinance entirely for consistency.
    if df is not None and not df.empty:
        counts = df.groupby("ticker").size()
        thin = counts[counts < 100]
        if not thin.empty:
            print(f"\nCRSP coverage too thin for: {thin.to_dict()} -- falling back to yfinance")
            df = None

    if df is None or df.empty:
        print("\nTrying Compustat (WRDS)...")
        try:
            df = pull_from_compustat()
        except Exception as e:
            print(f"Compustat pull failed: {e}")
            df = None

    if df is not None and not df.empty:
        counts = df.groupby("ticker").size()
        thin = counts[counts < 100]
        if not thin.empty:
            print(f"\nCompustat coverage too thin for: {thin.to_dict()} -- trying stooq")
            df = None

    if df is None or df.empty:
        print("\nTrying stooq...")
        df = pull_from_stooq()

    if df is None or df.empty:
        print("\nFalling back to yfinance...")
        df = pull_from_yfinance()

    if df is None or df.empty:
        print("FATAL: no data from any source")
        return

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
