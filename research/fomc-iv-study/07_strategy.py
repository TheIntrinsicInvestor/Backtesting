"""
07_strategy.py
--------------
Backtest both straddle strategies and compute full performance metrics.

Strategy A — Pre-Meeting Straddle Sell:
  Enter: Sell ATM SPY straddle at T-1 close
  Exit : Buy back at T+1 close
  Hypothesis: IV crush on announcement day makes short straddle profitable

Strategy B — Post-Announcement Straddle Sell:
  Enter: Sell ATM SPY straddle at T+1 close
  Exit : Buy back at T+2, T+3, T+5, T+10 (sensitivity table)
  Hypothesis: Continued vol mean-reversion after uncertainty is resolved

Metrics per strategy:
  - Win rate (% of trades with P&L > 0)
  - Avg P&L per trade ($, per 1 contract = 100 shares)
  - Total cumulative P&L
  - Per-trade return (P&L / entry_straddle × 100%)
  - Annualised Sharpe = mean(return) / std(return) × sqrt(8)
    [sqrt(8): ~8 FOMC meetings/year; wide CI at n=55, disclosed in report]
  - Max drawdown on cumulative P&L curve
  - Split by decision_type and comm_surprise

Outputs:
  data/strategy_pre.parquet
  data/strategy_post.parquet
  data/sensitivity.parquet
  charts/data_pre_pnl.json
  charts/data_post_pnl.json
  charts/data_sensitivity.json
"""

import os
import json
import numpy as np
import pandas as pd

os.makedirs("data", exist_ok=True)
os.makedirs("charts", exist_ok=True)

MEETINGS_PER_YEAR = 8  # approx; used for Sharpe annualisation

# ── Load data ─────────────────────────────────────────────────────────────────
straddles = pd.read_parquet("data/spy_straddles.parquet")
events    = pd.read_parquet("data/fomc_events.parquet")

straddles["fomc_date"] = pd.to_datetime(straddles["fomc_date"])
events["date"]         = pd.to_datetime(events["date"])

# Merge event metadata into straddles
meta_cols = ["date", "decision_type", "comm_surprise", "is_outlier",
             "actual_change_bps", "surprise_bps"]
straddles = straddles.merge(
    events[meta_cols].rename(columns={"date": "fomc_date"}),
    on="fomc_date", how="left"
)

# Per-trade return as % of capital at risk (entry straddle value)
straddles["return_pct"] = straddles["pnl_per_contract"] / (straddles["straddle_entry"] * 100) * 100

def max_drawdown(cumulative):
    """Peak-to-trough max drawdown on a cumulative P&L series."""
    peak = cumulative.cummax()
    dd   = cumulative - peak
    return float(dd.min())

def compute_metrics(df, label=""):
    """Compute strategy metrics for a subset of straddle records."""
    if len(df) == 0:
        return {}
    n         = len(df)
    win_rate  = (df["pnl_per_contract"] > 0).mean()
    avg_pnl   = df["pnl_per_contract"].mean()
    total_pnl = df["pnl_per_contract"].sum()
    cum_pnl   = df.sort_values("fomc_date")["pnl_per_contract"].cumsum()
    mdd       = max_drawdown(cum_pnl)
    ret_mean  = df["return_pct"].mean()
    ret_std   = df["return_pct"].std()
    sharpe    = (ret_mean / ret_std * np.sqrt(MEETINGS_PER_YEAR)) if ret_std > 0 else np.nan
    return {
        "label"    : label,
        "n"        : n,
        "win_rate" : round(win_rate, 4),
        "avg_pnl"  : round(avg_pnl, 2),
        "total_pnl": round(total_pnl, 2),
        "max_dd"   : round(mdd, 2),
        "sharpe"   : round(sharpe, 3) if not np.isnan(sharpe) else None,
        "avg_entry": round(df["straddle_entry"].mean(), 2),
    }

# ── Strategy A: Pre-Meeting ────────────────────────────────────────────────────
pre = straddles[
    (straddles["strategy"] == "pre_meeting") &
    (straddles["exit_offset"] == 1)
].copy().sort_values("fomc_date").reset_index(drop=True)

pre["cum_pnl"] = pre["pnl_per_contract"].cumsum()

pre.to_parquet("data/strategy_pre.parquet", index=False)
print(f"Strategy A: {len(pre)} trades")

# Overall metrics
pre_metrics = compute_metrics(pre, "All meetings")
print(f"  Win rate: {pre_metrics['win_rate']:.0%}  "
      f"Avg P&L: ${pre_metrics['avg_pnl']:+.0f}  "
      f"Sharpe: {pre_metrics['sharpe']}  "
      f"Max DD: ${pre_metrics['max_dd']:.0f}")

# By decision_type
pre_by_dtype = {}
for dtype in ["Hike", "Hold", "Cut"]:
    sub = pre[pre["decision_type"] == dtype]
    pre_by_dtype[dtype] = compute_metrics(sub, dtype)

# By comm_surprise (all meetings)
pre_by_comm = {}
for cs in ["Hawkish", "Neutral", "Dovish"]:
    sub = pre[pre["comm_surprise"] == cs]
    pre_by_comm[cs] = compute_metrics(sub, cs)

# ── Strategy B: Post-Announcement ─────────────────────────────────────────────
post_all = straddles[straddles["strategy"] == "post_announcement"].copy()
post_all = post_all.sort_values(["fomc_date", "exit_offset"]).reset_index(drop=True)

# Primary exit: T+5 (determined after sensitivity; placeholder — update after running)
post = post_all[post_all["exit_offset"] == 5].copy().sort_values("fomc_date").reset_index(drop=True)
post["cum_pnl"] = post["pnl_per_contract"].cumsum()
post.to_parquet("data/strategy_post.parquet", index=False)

print(f"\nStrategy B (T+5 exit): {len(post)} trades")
post_metrics = compute_metrics(post, "All meetings")
print(f"  Win rate: {post_metrics['win_rate']:.0%}  "
      f"Avg P&L: ${post_metrics['avg_pnl']:+.0f}  "
      f"Sharpe: {post_metrics['sharpe']}  "
      f"Max DD: ${post_metrics['max_dd']:.0f}")

# ── Sensitivity table: Strategy B at each exit offset ─────────────────────────
sens_rows = []
for off in [2, 3, 5, 10]:  # T+1 = entry date for post_announcement; first valid exit is T+2
    sub = post_all[post_all["exit_offset"] == off]
    m   = compute_metrics(sub, f"T+{off}")
    m["exit_label"] = f"T+{off}"
    sens_rows.append(m)

sensitivity = pd.DataFrame(sens_rows)
sensitivity.to_parquet("data/sensitivity.parquet", index=False)

print("\n=== Sensitivity table (Strategy B) ===")
print(sensitivity[["exit_label", "n", "win_rate", "avg_pnl", "sharpe", "max_dd"]].to_string(index=False))

# Best exit by Sharpe
best_exit = sensitivity.loc[sensitivity["sharpe"].idxmax(), "exit_label"]
print(f"\nBest exit by Sharpe: {best_exit}")

# ── Chart: Pre-meeting P&L ────────────────────────────────────────────────────
COLOR_MAP = {
    ("Hike",  "Hawkish"): "#dc2626",
    ("Hike",  "Neutral"): "#ef4444",
    ("Hike",  "Dovish") : "#fca5a5",
    ("Hold",  "Hawkish"): "#2563eb",
    ("Hold",  "Neutral"): "#93c5fd",
    ("Hold",  "Dovish") : "#bfdbfe",
    ("Cut",   "Hawkish"): "#d97706",
    ("Cut",   "Neutral"): "#f59e0b",
    ("Cut",   "Dovish") : "#fde68a",
}
OUTLIER_COLOR = "#9ca3af"

def build_pnl_chart(df, label):
    df = df.sort_values("fomc_date").reset_index(drop=True)
    bars, cum_line, colors, labels = [], [], [], []
    for _, r in df.iterrows():
        pnl  = round(float(r["pnl_per_contract"]), 2)
        bars.append(pnl)
        cum_line.append(round(float(r["cum_pnl"]), 2))
        lbl = f"{r['fomc_date'].strftime('%b %Y')} ({r['decision_type'][0]})"
        labels.append(lbl)
        if r.get("is_outlier"):
            colors.append(OUTLIER_COLOR)
        elif pnl > 0:
            colors.append("#059669")  # green for wins
        else:
            colors.append("#dc2626")  # red for losses
    return {
        "labels"  : labels,
        "bars"    : bars,
        "colors"  : colors,
        "cum_line": cum_line,
        "metrics" : compute_metrics(df, label),
    }

pre_chart  = build_pnl_chart(pre,  "Pre-Meeting")
post_chart = build_pnl_chart(post, f"Post-Announcement ({best_exit})")

with open("charts/data_pre_pnl.json", "w") as f:
    json.dump(pre_chart, f, indent=2)
print("\nSaved charts/data_pre_pnl.json")

with open("charts/data_post_pnl.json", "w") as f:
    json.dump(post_chart, f, indent=2)
print("Saved charts/data_post_pnl.json")

# ── Sensitivity chart data ────────────────────────────────────────────────────
sens_chart = {
    "exits"     : list(sensitivity["exit_label"]),
    "win_rates" : [round(x * 100, 1) for x in sensitivity["win_rate"]],
    "avg_pnls"  : list(sensitivity["avg_pnl"]),
    "sharpes"   : list(sensitivity["sharpe"]),
    "max_dds"   : list(sensitivity["max_dd"]),
    "best_exit" : best_exit,
}
with open("charts/data_sensitivity.json", "w") as f:
    json.dump(sens_chart, f, indent=2)
print("Saved charts/data_sensitivity.json")

# ── Full summary print ─────────────────────────────────────────────────────────
print("\n=== STRATEGY A: Pre-Meeting — by decision_type ===")
for dtype, m in pre_by_dtype.items():
    print(f"  {dtype:4s} n={m.get('n',0):2d} | win={m.get('win_rate',0):.0%} "
          f"| avg=${m.get('avg_pnl',0):+.0f} | sharpe={m.get('sharpe')}")

print("\n=== STRATEGY A: Pre-Meeting — by comm_surprise ===")
for cs, m in pre_by_comm.items():
    print(f"  {cs:8s} n={m.get('n',0):2d} | win={m.get('win_rate',0):.0%} "
          f"| avg=${m.get('avg_pnl',0):+.0f} | sharpe={m.get('sharpe')}")

print("\n=== STRATEGY B: Post-Announcement — by decision_type ===")
for dtype in ["Hike", "Hold", "Cut"]:
    sub = post[post["decision_type"] == dtype]
    m   = compute_metrics(sub, dtype)
    print(f"  {dtype:4s} n={m.get('n',0):2d} | win={m.get('win_rate',0):.0%} "
          f"| avg=${m.get('avg_pnl',0):+.0f} | sharpe={m.get('sharpe')}")
