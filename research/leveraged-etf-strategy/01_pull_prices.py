"""
01_pull_prices.py
-----------------
Pull daily price data for AVGO and AVL from yfinance.
AVL = T-Rex 2X Long AVGO Daily Target ETF (short leg)
AVGO = Broadcom Inc (long leg)

Study period: October 10, 2024 – March 13, 2026
"""

import yfinance as yf
import pandas as pd
import os

# ── Config ────────────────────────────────────────────────────────────────────
TICKERS     = ["AVGO", "AVL"]
START_DATE  = "2024-10-10"
END_DATE    = "2026-03-14"
DATA_DIR    = "data"

os.makedirs(DATA_DIR, exist_ok=True)

# ── Pull prices ───────────────────────────────────────────────────────────────
print(f"Pulling daily prices for {TICKERS} from {START_DATE} to {END_DATE}...")

raw = yf.download(TICKERS, start=START_DATE, end=END_DATE, auto_adjust=True)

# Keep adjusted close only
closes = raw["Close"][TICKERS].dropna()
closes.index = pd.to_datetime(closes.index)
closes.index.name = "date"

print(f"  {len(closes)} trading days retrieved")
print(f"  First: {closes.index[0].date()}  Last: {closes.index[-1].date()}")
print(closes.tail())

# ── Save ──────────────────────────────────────────────────────────────────────
closes.to_parquet(os.path.join(DATA_DIR, "prices.parquet"))
print(f"\nSaved to {DATA_DIR}/prices.parquet")
