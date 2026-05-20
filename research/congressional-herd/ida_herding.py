"""
IDA: Congressional Herding Events
Pulls Senate + House trade disclosures and counts herding events
at different thresholds and window sizes before committing to full study.
"""

import requests
import pandas as pd
from datetime import datetime, timedelta

SENATE_URLS = [
    "https://raw.githubusercontent.com/timothycarambat/senate-stock-watcher-data/master/aggregate/all_transactions.json",
]

def fetch_json(urls, label):
    for url in urls:
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                data = r.json()
                print(f"  {label}: {len(data):,} raw records")
                return data
            print(f"  {label}: HTTP {r.status_code}")
        except Exception as e:
            print(f"  {label}: error - {e}")
    print(f"  {label}: all sources failed")
    return []

def parse_trades(raw, chamber):
    rows = []
    for t in raw:
        ticker = str(t.get("ticker") or "").strip().upper()
        if not ticker or ticker in {"N/A", "--", "", "NONE"}:
            continue
        if " " in ticker or "/" in ticker or len(ticker) > 5:
            continue

        date_str = (t.get("transaction_date") or t.get("disclosure_date") or "")[:10]
        date = None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                date = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue
        if date is None:
            continue

        tx = str(t.get("type") or "").lower()
        if any(w in tx for w in ["purchase", "buy"]):
            direction = "buy"
        elif any(w in tx for w in ["sale", "sell", "exchange"]):
            direction = "sell"
        else:
            continue

        name = (
            t.get("senator") or t.get("representative") or t.get("politician") or ""
        ).strip()
        if not name:
            continue

        rows.append({
            "chamber": chamber,
            "name": name,
            "ticker": ticker,
            "date": date,
            "direction": direction,
        })
    return rows

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

    all_trades = []
    senate_raw = fetch_json(SENATE_URLS, "Senate")
    all_trades.extend(parse_trades(senate_raw, "Senate"))

    if not all_trades:
        print("\nNo data retrieved.")
        return

    df = pd.DataFrame(all_trades)
    df = df[df["date"] >= datetime(2012, 1, 1)]

    print()
    print("--- Dataset Overview ---")
    print(f"Total clean trades : {len(df):,}")
    print(f"Date range         : {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"Unique politicians : {df['name'].nunique()}")
    print(f"Unique tickers     : {df['ticker'].nunique()}")

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
