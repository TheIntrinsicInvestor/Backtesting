"""
IDA: Congressional Herding Events
Reads scraped Capitol Trades data and counts herding events
at different thresholds and window sizes before committing to full study.
"""

import pandas as pd
from pathlib import Path
from datetime import timedelta

DATA_PATH = Path(__file__).parent / "data" / "all_trades.parquet"


def load_trades():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Parquet not found: {DATA_PATH}\nRun scrape_capitol_trades.py first.")

    df = pd.read_parquet(DATA_PATH)
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    # Keep only buy/sell; drop exchange, receive, etc.
    df = df[df["tx_type"].isin(["buy", "sell"])].copy()
    df = df.rename(columns={"trade_date": "date", "tx_type": "direction"})

    # Drop rows missing ticker or name
    df = df[df["ticker"].notna() & (df["ticker"] != "")]
    df = df[df["name"].notna() & (df["name"] != "")]

    return df[["chamber", "name", "ticker", "date", "direction"]].reset_index(drop=True)


def find_herding_events(df, min_politicians, window_days, direction="buy"):
    trades = df[df["direction"] == direction].copy()
    trades = trades.sort_values("date")
    events = []

    for ticker, group in trades.groupby("ticker"):
        group = group.sort_values("date").reset_index(drop=True)
        i = 0
        while i < len(group):
            start = group.loc[i, "date"]
            end = start + timedelta(days=window_days)
            mask = (group["date"] >= start) & (group["date"] <= end)
            window = group[mask]
            unique = window["name"].nunique()
            if unique >= min_politicians:
                events.append({
                    "ticker": ticker,
                    "window_start": start,
                    "politician_count": unique,
                    "politicians": sorted(window["name"].unique()),
                })
                i = mask[mask].index[-1] + 1
            else:
                i += 1

    return pd.DataFrame(events) if events else pd.DataFrame(
        columns=["ticker", "window_start", "politician_count", "politicians"]
    )


def main():
    print("=" * 60)
    print("Congressional Herding IDA")
    print("=" * 60)

    df = load_trades()

    print()
    print("--- Dataset Overview ---")
    print(f"Total clean trades : {len(df):,}")
    print(f"Date range         : {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"Unique politicians : {df['name'].nunique()}")
    print(f"Unique tickers     : {df['ticker'].nunique()}")

    by_chamber = df["chamber"].value_counts()
    for ch, n in by_chamber.items():
        print(f"  {ch:<8}: {n:,}")

    by_dir = df["direction"].value_counts()
    print(f"Buys               : {by_dir.get('buy', 0):,}")
    print(f"Sells              : {by_dir.get('sell', 0):,}")

    print()
    print("--- Herding Events (BUY) - count by threshold x window ---")
    windows = [14, 30, 60]
    thresholds = [2, 3, 4, 5]
    header = f"{'Threshold':<20}" + "".join(f"{'  ' + str(w) + 'd window':<16}" for w in windows)
    print(header)
    print("-" * (20 + len(windows) * 16))

    results = {}
    for t in thresholds:
        row = f"{str(t) + '+ politicians':<20}"
        for w in windows:
            events = find_herding_events(df, min_politicians=t, window_days=w)
            n = len(events)
            results[(t, w)] = events
            row += f"{n:<16}"
        print(row)

    events_main = results.get((3, 30), pd.DataFrame())
    if not events_main.empty:
        print()
        print("--- Most-Herded Tickers (3+ politicians, 30-day window) ---")
        top = (
            events_main.groupby("ticker")
            .agg(events=("window_start", "count"), max_crowd=("politician_count", "max"))
            .sort_values("events", ascending=False)
            .head(25)
        )
        print(top.to_string())

        events_main = events_main.copy()
        events_main["year"] = events_main["window_start"].dt.year
        print()
        print("--- Herding Events by Year (3+, 30-day) ---")
        print(events_main.groupby("year").size().to_string())

        print()
        print("--- Largest single herding events ---")
        biggest = events_main.sort_values("politician_count", ascending=False).head(10)
        for _, row in biggest.iterrows():
            names = row["politicians"]
            names_str = ", ".join(names[:4]) + ("..." if len(names) > 4 else "")
            print(f"  {row['ticker']:<6} {row['window_start'].date()}  n={row['politician_count']}  {names_str}")

    print()
    print("--- Done ---")


if __name__ == "__main__":
    main()
