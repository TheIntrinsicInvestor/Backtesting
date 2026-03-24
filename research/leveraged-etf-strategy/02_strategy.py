"""
02_strategy.py
--------------
Construct the market-neutral carry trade:
  Long  $10,000 AVGO  (1x exposure)
  Short  $5,000 AVL   (2x leveraged ETF, hedges AVGO delta via 2:1 ratio)

Rebalancing: daily back to target notional (maintains delta neutrality).
Borrow cost for AVL short: 0.6% per annum.

Outputs:
  data/daily_pnl.parquet       daily P&L and cumulative equity curve
  data/monthly_summary.parquet monthly P&L, tracking error, regime labels
"""

import pandas as pd
import numpy as np
import os

DATA_DIR = "data"

# ── Load prices ───────────────────────────────────────────────────────────────
prices = pd.read_parquet(os.path.join(DATA_DIR, "prices.parquet"))

# ── Position parameters ───────────────────────────────────────────────────────
AVGO_NOTIONAL  = 10_000.0   # long notional
AVL_NOTIONAL   =  5_000.0   # short notional (half because 2x leverage = same AVGO delta exposure)
BORROW_RATE    = 0.006       # 0.6% p.a. borrow cost on AVL short
TRADING_DAYS   = 252

# ── Daily rebalancing simulation ──────────────────────────────────────────────
df = prices.copy()
df["avgo_ret"] = df["AVGO"].pct_change()
df["avl_ret"]  = df["AVL"].pct_change()
df = df.dropna()

# Daily borrow cost on AVL short position (charged daily)
daily_borrow = BORROW_RATE / TRADING_DAYS

# P&L each day:
#   Long AVGO leg:  notional * avgo_ret
#   Short AVL leg:  notional * (-avl_ret) - borrow cost
#   Net:            long_pnl + short_pnl
df["long_pnl"]   = AVGO_NOTIONAL * df["avgo_ret"]
df["short_pnl"]  = AVL_NOTIONAL  * (-df["avl_ret"]) - (AVL_NOTIONAL * daily_borrow)
df["daily_pnl"]  = df["long_pnl"] + df["short_pnl"]
df["cum_pnl"]    = df["daily_pnl"].cumsum()
df["cum_return"] = df["cum_pnl"] / (AVGO_NOTIONAL + AVL_NOTIONAL)  # as % of total capital deployed

# Tracking error: how much AVL drifted from 2x AVGO on a given day
df["expected_avl"] = 2 * df["avgo_ret"]
df["tracking_err"] = df["avl_ret"] - df["expected_avl"]

# Win/loss
df["win"] = (df["daily_pnl"] > 0).astype(int)

print("Daily strategy summary:")
print(f"  Total P&L:      ${df['daily_pnl'].sum():.2f}")
print(f"  Total return:   {df['cum_return'].iloc[-1]*100:.2f}%")
print(f"  Win rate:       {df['win'].mean()*100:.1f}%")
print(f"  Trading days:   {len(df)}")

# ── Monthly aggregation ───────────────────────────────────────────────────────
df["month"] = df.index.to_period("M")

monthly = df.groupby("month").agg(
    pnl          = ("daily_pnl",   "sum"),
    tracking_err = ("tracking_err","std"),   # monthly TE = std of daily tracking error * sqrt(days)
    avgo_ret     = ("avgo_ret",    lambda x: (1 + x).prod() - 1),
    days         = ("daily_pnl",   "count"),
).reset_index()

# Annualise monthly TE
monthly["tracking_err_pct"] = monthly["tracking_err"] * np.sqrt(monthly["days"] * TRADING_DAYS / monthly["days"]) * 100

# Regime labels
regime_map = {
    "2024-10": "AVGO bull run",
    "2024-11": "AVGO bull run",
    "2024-12": "AVGO bull run",
    "2025-01": "DeepSeek crash",
    "2025-02": "Post-DeepSeek recovery",
    "2025-03": "Liberation Day (Apr)",
    "2025-04": "Liberation Day",
    "2025-05": "Post-tariff recovery",
    "2025-06": "Summer consolidation",
    "2025-07": "Summer consolidation",
    "2025-08": "Summer consolidation",
    "2025-09": "AVGO earnings spike",
    "2025-10": "Post-earnings",
    "2025-11": "Pre-December",
    "2025-12": "December 2025 vol event",
    "2026-01": "2026 YTD",
    "2026-02": "2026 YTD",
    "2026-03": "2026 YTD",
}
monthly["regime"] = monthly["month"].astype(str).map(regime_map).fillna("Normal carry")

# ── Save ──────────────────────────────────────────────────────────────────────
df[["avgo_ret", "avl_ret", "long_pnl", "short_pnl", "daily_pnl", "cum_pnl",
    "cum_return", "tracking_err", "win"]].to_parquet(
    os.path.join(DATA_DIR, "daily_pnl.parquet"))

monthly.to_parquet(os.path.join(DATA_DIR, "monthly_summary.parquet"))

print(f"\nSaved daily_pnl.parquet and monthly_summary.parquet to {DATA_DIR}/")
print(monthly[["month", "pnl", "tracking_err_pct", "regime"]].to_string())
