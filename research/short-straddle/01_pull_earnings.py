"""
01_pull_earnings.py
-------------------
Pull earnings announcement dates for the Magnificent Seven from IBES Actuals
(ibes.act_epsus) via WRDS.

Tickers: AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA
Period:  Q1 2019 – Q4 2024  (24 events per stock = 168 total)

IBES quirks handled:
  - Alphabet trades as GOOGL but IBES uses GOOG
  - Meta traded as FB/FBK until Jun 2022, then META

Output: data/earnings_dates.parquet
"""

import wrds
import pandas as pd
import os

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# IBES ticker mapping (IBES ticker -> display ticker)
TICKER_MAP = {
    "AAPL"  : "AAPL",
    "MSFT"  : "MSFT",
    "NVDA"  : "NVDA",
    "AMZN"  : "AMZN",
    "GOOG"  : "GOOGL",   # IBES uses GOOG for Alphabet
    "FBK"   : "META",    # IBES uses FBK for Meta (formerly FB)
    "TSLA"  : "TSLA",
}

IBES_TICKERS = list(TICKER_MAP.keys())
START_YEAR   = 2019
END_YEAR     = 2024

# ── Connect to WRDS ───────────────────────────────────────────────────────────
print("Connecting to WRDS...")
db = wrds.Connection()

# ── Pull IBES actual EPS announcement dates ───────────────────────────────────
tickers_str = ", ".join(f"'{t}'" for t in IBES_TICKERS)

query = f"""
    SELECT ticker, anndats, pends, pdicity
    FROM ibes.act_epsus
    WHERE ticker IN ({tickers_str})
      AND pdicity = 'QTR'
      AND anndats BETWEEN '2019-01-01' AND '2024-12-31'
    ORDER BY ticker, anndats
"""

print("Querying IBES earnings dates...")
raw = db.raw_sql(query, date_cols=["anndats", "pends"])
db.close()

print(f"  Raw rows returned: {len(raw)}")

# ── Clean & map tickers ───────────────────────────────────────────────────────
raw["display_ticker"] = raw["ticker"].map(TICKER_MAP)
raw = raw.dropna(subset=["display_ticker"])

# Drop duplicates (IBES can have multiple estimates per period)
earnings = (
    raw[["display_ticker", "anndats", "pends"]]
    .drop_duplicates(subset=["display_ticker", "anndats"])
    .rename(columns={
        "display_ticker" : "ticker",
        "anndats"        : "ann_date",
        "pends"          : "period_end",
    })
    .sort_values(["ticker", "ann_date"])
    .reset_index(drop=True)
)

# ── Validate: expect 24 events per ticker ────────────────────────────────────
counts = earnings.groupby("ticker").size()
print("\nEvents per ticker:")
print(counts.to_string())
print(f"\nTotal events: {len(earnings)}")

assert len(earnings) == 168, f"Expected 168 events, got {len(earnings)}"

# ── Save ──────────────────────────────────────────────────────────────────────
earnings.to_parquet(os.path.join(DATA_DIR, "earnings_dates.parquet"), index=False)
print(f"\nSaved to {DATA_DIR}/earnings_dates.parquet")
