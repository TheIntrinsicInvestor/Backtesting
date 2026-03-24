"""
03_strategy.py
--------------
Compute per-event and per-ticker performance metrics from straddle prices.

Margin assumption: 20% of notional (spot * 100 shares) per contract.
Position size: 1 contract per event.

Outputs:
  data/event_results.parquet     per-event P&L and edge metrics
  data/ticker_summary.parquet    per-ticker aggregated metrics
  data/annual_pnl.parquet        annual P&L per ticker (2019-2024)
"""

import pandas as pd
import numpy as np
import os
from scipy import stats

DATA_DIR = "data"

# ── Load straddle prices ───────────────────────────────────────────────────────
df = pd.read_parquet(os.path.join(DATA_DIR, "straddle_prices.parquet"))
df["ann_date"]  = pd.to_datetime(df["ann_date"])
df["year"]      = df["ann_date"].dt.year
df["win"]       = (df["pnl_per_contract"] > 0).astype(int)
df["edge_pct"]  = df["implied_move_pct"] - df["realised_move_pct"]

# Margin: 20% of notional at entry
df["margin"]    = df["spot_entry"] * 100 * 0.20
df["return_on_margin"] = df["pnl_per_contract"] / df["margin"]

# ── Per-ticker metrics ────────────────────────────────────────────────────────
def ticker_metrics(group):
    pnl = group["pnl_per_contract"]
    rom = group["return_on_margin"]
    n   = len(pnl)

    total_pnl    = pnl.sum()
    win_rate     = group["win"].mean()
    avg_edge     = group["edge_pct"].mean()
    avg_implied  = group["implied_move_pct"].mean()
    avg_realised = group["realised_move_pct"].mean()

    wins   = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    payoff = wins.mean() / abs(losses.mean()) if len(losses) > 0 else np.nan

    # Risk-adjusted metrics (based on return_on_margin series)
    sharpe  = rom.mean() / rom.std() * np.sqrt(n) if rom.std() > 0 else np.nan
    sortino_denom = rom[rom < 0].std()
    sortino = rom.mean() / sortino_denom * np.sqrt(n) if sortino_denom > 0 else np.nan

    cum_rom  = rom.cumsum()
    max_pnl  = pnl.cumsum().cummax()
    drawdown = pnl.cumsum() - max_pnl
    max_dd   = drawdown.min()

    ann_return = total_pnl / (n / 4)  # n events / 4 per year
    calmar     = ann_return / abs(max_dd) if max_dd != 0 else np.nan

    skewness   = stats.skew(pnl)
    kurtosis   = stats.kurtosis(pnl)  # excess kurtosis

    avg_rom = rom.mean() * 100

    return pd.Series({
        "n_events"        : n,
        "total_pnl"       : round(total_pnl, 0),
        "win_rate"        : round(win_rate * 100, 1),
        "avg_edge_pct"    : round(avg_edge, 2),
        "avg_implied_pct" : round(avg_implied, 2),
        "avg_realised_pct": round(avg_realised, 2),
        "payoff_ratio"    : round(payoff, 3),
        "sharpe"          : round(sharpe, 3),
        "sortino"         : round(sortino, 3),
        "calmar"          : round(calmar, 3),
        "max_dd"          : round(max_dd, 0),
        "skewness"        : round(skewness, 3),
        "excess_kurtosis" : round(kurtosis, 3),
        "avg_rom_pct"     : round(avg_rom, 2),
    })

summary = df.groupby("ticker").apply(ticker_metrics).reset_index()

print("PER-TICKER SUMMARY")
print("=" * 90)
print(summary.to_string(index=False))

# ── Annual P&L breakdown ──────────────────────────────────────────────────────
annual = df.groupby(["ticker", "year"])["pnl_per_contract"].sum().unstack("year")
annual["total"] = annual.sum(axis=1)

print("\nANNUAL P&L BY TICKER")
print("=" * 70)
print(annual.round(1).to_string())

# ── Cross-ticker total ────────────────────────────────────────────────────────
total_pnl = df["pnl_per_contract"].sum()
print(f"\nCOMBINED TOTAL P&L (all tickers, all events): ${total_pnl:,.0f}")

# ── Save ──────────────────────────────────────────────────────────────────────
df.to_parquet(os.path.join(DATA_DIR, "event_results.parquet"), index=False)
summary.to_parquet(os.path.join(DATA_DIR, "ticker_summary.parquet"), index=False)
annual.to_parquet(os.path.join(DATA_DIR, "annual_pnl.parquet"))
print(f"\nSaved event_results, ticker_summary, annual_pnl to {DATA_DIR}/")
