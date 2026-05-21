import argparse
import re
import pandas as pd
from pathlib import Path
from datetime import timedelta

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

INPUT = DATA_DIR / "all_trades.parquet"

ETF_TICKERS = {
    "SPY","QQQ","VTI","VOO","IWM","EEM","GLD","TLT","SLV","IAU","BND","AGG",
    "LQD","HYG","XLF","XLK","XLE","XLV","XLI","XLP","XLY","XLU","XLRE","XLB",
    "XLC","ARKK","ARKG","ARKF","GDX","GDXJ","SDS","TQQQ","SQQQ","UVXY","VXX",
}

ETF_ISSUER_KEYWORDS = ["fund", "etf", "trust", "index", "shares"]

THRESHOLDS = [2, 3, 4, 5]
WINDOWS = [14, 30, 60]


def parse_size_midpoint(s):
    if not isinstance(s, str):
        return 0.0
    s = s.strip()

    range_map = {
        "1K-15K": 8000, "15K-50K": 32500, "50K-100K": 75000,
        "100K-250K": 175000, "250K-500K": 375000, "500K-1M": 750000,
        "1M-5M": 3000000, "5M-25M": 15000000, "25M-50M": 37500000,
        ">50M": 75000000,
    }
    for key, val in range_map.items():
        if key in s:
            return float(val)

    m = re.search(r"[\$]?([\d.]+)\s*([KkMm]?)", s)
    if m:
        num = float(m.group(1))
        suffix = m.group(2).upper()
        if suffix == "K":
            return num * 1_000
        if suffix == "M":
            return num * 1_000_000
        return num

    return 0.0


def sum_sizes(size_list):
    return sum(parse_size_midpoint(s) for s in size_list)


def find_herding_events_extended(df, min_politicians, window_days):
    events = []
    for ticker, group in df.groupby("ticker"):
        group = group.sort_values("trade_date").reset_index(drop=True)
        i = 0
        while i < len(group):
            start = group.loc[i, "trade_date"]
            end = start + timedelta(days=window_days)
            mask = (group["trade_date"] >= start) & (group["trade_date"] <= end)
            window = group[mask]
            unique_names = window["name"].unique()
            if len(unique_names) >= min_politicians:
                window_sorted = window.sort_values(["trade_date", "name"]).reset_index(drop=True)
                nth = window_sorted.iloc[min_politicians - 1]
                parties = window["party"].dropna().unique().tolist()
                chambers = window["chamber"].dropna().unique().tolist()
                events.append({
                    "ticker": ticker,
                    "threshold": min_politicians,
                    "window_days": window_days,
                    "window_start": group.loc[i, "trade_date"],
                    "entry_trade_date": nth["trade_date"],
                    "entry_disclosure_date": nth["disclosure_date"],
                    "politician_count": int(len(unique_names)),
                    "politicians": sorted(unique_names.tolist()),
                    "parties_in_herd": parties,
                    "chambers_in_herd": chambers,
                    "is_bipartisan": ("Democrat" in parties and "Republican" in parties),
                    "total_dollar_size": sum_sizes(window["size"].tolist()),
                })
                i = int(mask[mask].index[-1]) + 1
            else:
                i += 1
    return events


def load_and_filter(tx_type):
    df = pd.read_parquet(INPUT)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["disclosure_date"] = pd.to_datetime(df["disclosure_date"])

    df = df[df["tx_type"] == tx_type].copy()
    df = df[df["ticker"].notna() & (df["ticker"] != "") & (df["ticker"] != "N/A")]

    ticker_mask = df["ticker"].isin(ETF_TICKERS)
    issuer_mask = df["issuer"].str.lower().str.contains("|".join(ETF_ISSUER_KEYWORDS), na=False)
    df = df[~(ticker_mask | issuer_mask)].copy()

    print(f"tx_type={tx_type} | Rows after filtering: {len(df):,}")
    print(f"Unique tickers: {df['ticker'].nunique()}")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tx-type", choices=["buy", "sell"], default="buy")
    args = ap.parse_args()

    output = DATA_DIR / f"events_{args.tx_type}.parquet"
    if output.exists():
        print(f"Notice: {output.name} already exists — re-running.")

    df = load_and_filter(args.tx_type)

    all_events = []
    for threshold in THRESHOLDS:
        for window in WINDOWS:
            events = find_herding_events_extended(df, threshold, window)
            all_events.extend(events)
            print(f"  threshold={threshold}, window={window}d -> {len(events)} events")

    result = pd.DataFrame(all_events)
    result.to_parquet(output, index=False)
    print(f"\nSaved {len(result):,} total event rows to {output.name}")

    print("\n--- Event count grid (threshold x window) ---")
    grid = result.groupby(["threshold", "window_days"]).size().unstack("window_days")
    print(grid.to_string())

    print("\n--- Top 20 most-herded tickers (threshold=3, window=30d) ---")
    subset = result[(result["threshold"] == 3) & (result["window_days"] == 30)]
    top20 = (
        subset.groupby("ticker")
        .size()
        .sort_values(ascending=False)
        .head(20)
        .rename("event_count")
    )
    print(top20.to_string())

    etf_check = set(ETF_TICKERS) & set(result["ticker"].unique())
    if etf_check:
        print(f"\nWARNING: ETF tickers found in output: {etf_check}")
    else:
        print("\nConfirmed: no ETF tickers (SPY/QQQ etc.) in output.")


if __name__ == "__main__":
    main()
