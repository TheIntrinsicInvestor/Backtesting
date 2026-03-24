"""
01_pull_options.py
------------------
Pull daily SPY option chain data from OptionMetrics IvyDB via WRDS.

Covers January 2018 – December 2025 (8 full years).
Pulls all SPY options with:
  - DTE between 10 and 75 days (covers all tested parameter combos)
  - Delta between 0.05 and 0.55 (covers 10 to 50 delta)
  - Non-zero bid/ask
  - Standard options only (ss_flag = 0)

Underlying prices also pulled for assignment tracking.

Output: data/spy_options.parquet  (may be large — ~several GB before filtering)
        data/spy_prices.parquet   daily SPY closing prices
"""

import wrds
import pandas as pd
import os

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

SPY_SECID = 108105   # OptionMetrics secid for SPY
START_YEAR = 2018
END_YEAR   = 2025

print("Connecting to WRDS...")
db = wrds.Connection()

# ── Pull underlying prices ────────────────────────────────────────────────────
print("Pulling SPY underlying prices...")
price_frames = []
for year in range(START_YEAR, END_YEAR + 1):
    q = f"""
        SELECT date, close AS spy_close
        FROM optionm.secprd{year}
        WHERE secid = {SPY_SECID}
        ORDER BY date
    """
    price_frames.append(db.raw_sql(q, date_cols=["date"]))

spy_prices = pd.concat(price_frames, ignore_index=True)
spy_prices.to_parquet(os.path.join(DATA_DIR, "spy_prices.parquet"), index=False)
print(f"  SPY prices: {len(spy_prices)} days saved")

# ── Pull option chain by year ─────────────────────────────────────────────────
# Pull in yearly chunks to manage memory
option_frames = []

for year in range(START_YEAR, END_YEAR + 1):
    print(f"  Pulling {year} options...")
    q = f"""
        SELECT date, exdate, cp_flag, strike_price,
               best_bid, best_offer, impl_volatility, delta, volume, open_interest
        FROM optionm.opprcd{year}
        WHERE secid  = {SPY_SECID}
          AND ss_flag = 0
          AND best_bid > 0
          AND best_offer > 0
          AND delta IS NOT NULL
          AND ABS(delta) BETWEEN 0.05 AND 0.55
          AND (exdate - date) BETWEEN 10 AND 75
        ORDER BY date, cp_flag, exdate, strike_price
    """
    yr_df = db.raw_sql(q, date_cols=["date", "exdate"])
    yr_df["mid"] = (yr_df["best_bid"] + yr_df["best_offer"]) / 2
    yr_df["dte"] = (yr_df["exdate"] - yr_df["date"]).dt.days
    yr_df["strike"] = yr_df["strike_price"] / 1000
    option_frames.append(yr_df)
    print(f"    {len(yr_df):,} option records for {year}")

db.close()

# ── Combine and save ──────────────────────────────────────────────────────────
options = pd.concat(option_frames, ignore_index=True)
print(f"\nTotal option records: {len(options):,}")

options.to_parquet(os.path.join(DATA_DIR, "spy_options.parquet"), index=False)
print(f"Saved to {DATA_DIR}/spy_options.parquet")
