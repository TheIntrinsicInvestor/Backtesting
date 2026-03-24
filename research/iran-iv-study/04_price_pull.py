"""
04_price_pull.py
----------------
Pull daily adjusted close prices for XLE, USO, XOM, CVX via yfinance.
Used downstream for the hybrid event filter (≥1.5% move on T0 or T+1).

OptionMetrics secprd only covers through 2024 — yfinance is used instead
as it covers the full study period (2003–2026) without gaps.

Output: data/prices_raw.parquet
Columns: date, ticker, close, return
"""

import os
import yfinance as yf
import pandas as pd

os.makedirs("data", exist_ok=True)

CACHE = "data/prices_raw.parquet"
TICKERS = ["XLE", "USO", "XOM", "CVX"]

# Cover T-20 before earliest event (2003-03-20) through today
START = "2002-12-01"
END = "2026-04-01"

if os.path.exists(CACHE):
    print(f"Cache found at {CACHE} — skipping download.")
    df = pd.read_parquet(CACHE)
    print(f"Loaded {len(df):,} rows. Date range: {df['date'].min()} to {df['date'].max()}")
else:
    print(f"Downloading prices for {TICKERS} from {START} to {END}...")
    raw = yf.download(
        TICKERS,
        start=START,
        end=END,
        auto_adjust=True,
        progress=False,
    )

    # yfinance returns MultiIndex columns: (field, ticker)
    close = raw["Close"].copy()
    close.index.name = "date"
    close = close.reset_index()
    close = close.melt(id_vars="date", var_name="ticker", value_name="close")
    close["date"] = pd.to_datetime(close["date"]).dt.tz_localize(None)
    close = close.dropna(subset=["close"])
    close = close.sort_values(["ticker", "date"]).reset_index(drop=True)

    # Compute daily return within each ticker
    close["return"] = close.groupby("ticker")["close"].pct_change()

    close.to_parquet(CACHE, index=False)
    print(f"Saved {len(close):,} rows to {CACHE}")
    df = close

print("\n=== Row counts per ticker ===")
print(df.groupby("ticker")["date"].agg(["count", "min", "max"]).rename(
    columns={"count": "rows", "min": "first_date", "max": "last_date"}
))

print("\n=== Null close check ===")
nulls = df[df["close"].isna()]
if nulls.empty:
    print("No nulls.")
else:
    print(f"WARNING: {len(nulls)} null close rows:")
    print(nulls.groupby("ticker").size())

print("\n=== Sample rows ===")
for ticker in TICKERS:
    sample = df[df["ticker"] == ticker].head(3)
    print(f"\n{ticker}:")
    print(sample.to_string(index=False))
