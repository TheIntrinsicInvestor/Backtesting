import builtins, os
_u = os.environ.get("WRDS_USERNAME", "hoovyalert")
def _ai(p=""): v = _u if "username" in p.lower() else ""; print(p+v); return v
builtins.input = _ai

import pandas as pd
import numpy as np
import wrds
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
EVENTS_PATH = DATA_DIR / "events_buy.parquet"
TICKER_MAP_PATH = DATA_DIR / "ticker_permno_map.parquet"
PRICES_PATH = DATA_DIR / "crsp_prices.parquet"


def map_tickers(db, tickers):
    chunks = [tickers[i:i+500] for i in range(0, len(tickers), 500)]
    frames = []
    for chunk in chunks:
        df = db.raw_sql(
            "SELECT DISTINCT ticker, permno, issuernm AS comnam, siccd, namedt, nameenddt "
            "FROM crsp.stocknames_v2 "
            "WHERE ticker IN %(tickers)s",
            params={"tickers": tuple(chunk)},
        )
        frames.append(df)
    result = pd.concat(frames, ignore_index=True)
    result["namedt"] = pd.to_datetime(result["namedt"])
    result = (
        result.sort_values("namedt")
        .drop_duplicates(subset=["ticker"], keep="last")
        .drop(columns=["namedt", "nameenddt"])
        .reset_index(drop=True)
    )
    return result


def pull_prices(db, permnos, start_date, end_date):
    df = db.raw_sql(
        "SELECT dlycaldt AS date, permno, dlyprc AS prc, dlyret AS ret, dlycumfacpr AS cfacpr, dlyvol AS vol, shrout "
        "FROM crsp.dsf_v2 "
        "WHERE permno IN %(permnos)s AND dlycaldt BETWEEN %(start)s AND %(end)s",
        params={"permnos": tuple(permnos), "start": start_date, "end": end_date},
    )
    df["prc"] = df["prc"].abs()
    df["date"] = pd.to_datetime(df["date"])
    return df


def main():
    if TICKER_MAP_PATH.exists() and PRICES_PATH.exists():
        print("Cache exists — skipping WRDS pull")
        return

    events = pd.read_parquet(EVENTS_PATH)
    events["entry_disclosure_date"] = pd.to_datetime(events["entry_disclosure_date"])

    tickers = sorted(set(events["ticker"].dropna().unique().tolist()) | {"SPY"})

    start_date = (events["entry_disclosure_date"].min() - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    end_date = (events["entry_disclosure_date"].max() + pd.Timedelta(days=300)).strftime("%Y-%m-%d")

    db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME", "hoovyalert"))

    print(f"Mapping {len(tickers)} tickers to permno...")
    ticker_map = map_tickers(db, tickers)

    spy_mapped = "SPY" in ticker_map["ticker"].values
    if not spy_mapped:
        spy_row = pd.DataFrame([{"ticker": "SPY", "permno": 84398, "comnam": "SPDR S&P 500 ETF", "siccd": np.nan}])
        ticker_map = pd.concat([ticker_map, spy_row], ignore_index=True)

    mapped_tickers = set(ticker_map["ticker"].values)
    unmapped = [t for t in tickers if t not in mapped_tickers]
    print(f"Total unique tickers : {len(tickers)}")
    print(f"Mapped               : {len(mapped_tickers)}")
    print(f"Unmapped             : {len(unmapped)}")
    if unmapped:
        print(f"Unmapped tickers     : {unmapped}")

    ticker_map.to_parquet(TICKER_MAP_PATH, index=False)
    print(f"Saved {TICKER_MAP_PATH.name}")

    permnos = ticker_map["permno"].dropna().astype(int).tolist()
    print(f"Pulling CRSP prices for {len(permnos)} permnos, {start_date} to {end_date}...")
    prices = pull_prices(db, permnos, start_date, end_date)

    import concurrent.futures
    import yfinance as yf
    
    max_crsp_date = prices['date'].max() if not prices.empty else pd.to_datetime("2023-01-01")
    target_end_date = pd.to_datetime(end_date)
    
    if max_crsp_date < target_end_date:
        print(f"CRSP data only goes up to {max_crsp_date.date()}. Falling back to yfinance for the gap up to {target_end_date.date()}...")
        gap_start = (max_crsp_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        gap_end = (target_end_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        
        permno_to_ticker = dict(zip(ticker_map["permno"], ticker_map["ticker"]))
        tickers_to_pull = [permno_to_ticker[p] for p in permnos if p in permno_to_ticker]
        ticker_to_permno = {v: k for k, v in permno_to_ticker.items()}
        
        def pull_ticker(t):
            try:
                tk = yf.Ticker(t)
                hist = tk.history(start=gap_start, end=gap_end, auto_adjust=True)
                return t, hist
            except Exception:
                return t, None
                
        print(f"Batch pulling {len(tickers_to_pull)} tickers from yfinance...")
        yf_frames = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            for t, hist in executor.map(pull_ticker, tickers_to_pull):
                if hist is None or hist.empty: continue
                permno = ticker_to_permno[t]
                hist = hist.reset_index()
                sub_crsp = prices[prices['permno'] == permno]
                last_known_shrout = np.nan
                last_prc = np.nan
                if not sub_crsp.empty:
                    last_row = sub_crsp.sort_values('date').iloc[-1]
                    last_known_shrout = last_row['shrout']
                    last_prc = last_row['prc']
                
                s = pd.DataFrame({
                    "date": pd.to_datetime(hist["Date"]).dt.tz_localize(None),
                    "permno": permno,
                    "prc": hist["Close"].values,
                    "ret": np.nan,
                    "cfacpr": 1.0,
                    "vol": hist["Volume"].values,
                    "shrout": last_known_shrout
                })
                s = s.sort_values("date").reset_index(drop=True)
                s["ret"] = s["prc"].pct_change()
                if pd.notna(last_prc):
                    s.loc[0, "ret"] = (s.loc[0, "prc"] - last_prc) / last_prc
                yf_frames.append(s)
                
        if yf_frames:
            yf_prices = pd.concat(yf_frames, ignore_index=True)
            prices = pd.concat([prices, yf_prices], ignore_index=True)
            prices = prices.sort_values(["permno", "date"]).reset_index(drop=True)
            print(f"Appended {len(yf_prices)} rows from yfinance.")

    prices.to_parquet(PRICES_PATH, index=False)
    print(f"Saved {PRICES_PATH.name}")
    print(f"Date range pulled    : {prices['date'].min().date()} to {prices['date'].max().date()}")
    print(f"Total rows           : {len(prices):,}")
    print(f"Unique permnos       : {prices['permno'].nunique()}")

    db.close()


if __name__ == "__main__":
    main()
