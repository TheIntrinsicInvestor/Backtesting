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
            "SELECT DISTINCT ticker, permno, comnam, siccd, namedt, nameendt "
            "FROM crsp.stocknames "
            "WHERE ticker IN %(tickers)s",
            params={"tickers": tuple(chunk)},
        )
        frames.append(df)
    result = pd.concat(frames, ignore_index=True)
    result["namedt"] = pd.to_datetime(result["namedt"])
    result = (
        result.sort_values("namedt")
        .drop_duplicates(subset=["ticker"], keep="last")
        .drop(columns=["namedt", "nameendt"])
        .reset_index(drop=True)
    )
    return result


def pull_prices(db, permnos, start_date, end_date):
    df = db.raw_sql(
        "SELECT date, permno, prc, ret, cfacpr, vol, shrout "
        "FROM crsp.dsf "
        "WHERE permno IN %(permnos)s AND date BETWEEN %(start)s AND %(end)s",
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

    prices.to_parquet(PRICES_PATH, index=False)
    print(f"Saved {PRICES_PATH.name}")
    print(f"Date range pulled    : {prices['date'].min().date()} to {prices['date'].max().date()}")
    print(f"Total rows           : {len(prices):,}")
    print(f"Unique permnos       : {prices['permno'].nunique()}")

    db.close()


if __name__ == "__main__":
    main()
