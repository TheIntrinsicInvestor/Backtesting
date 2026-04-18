# ruff: noqa
"""
05_charts.py
------------
Build the 5 chart JSON files used by 06_build_report.py.

Charts:
  1. data_gex_timeseries.json  — daily GEX time series with regime colouring
  2. data_scatter.json         — GEX vs realized vol scatter + regression + lowess
  3. data_intraday_profile.json — vol-by-time-bucket by regime
  4. data_regimes.json         — box-plot data (p10/p25/median/p75/p90) per regime
  5. data_backtest.json        — rolling 60-day rvol with GEX regime shading
"""

import json
import os
import numpy as np
import pandas as pd

os.makedirs("charts", exist_ok=True)

# ── Load ──────────────────────────────────────────────────────────────────────
df      = pd.read_parquet("data/combined.parquet")
bucket  = pd.read_parquet("data/bucket_by_regime.parquet")
df["date"] = pd.to_datetime(df["date"])

with open("data/lowess_pts.json") as f:
    lowess_pts = json.load(f)

REGIME_ORDER = ["Negative GEX", "Low GEX", "High GEX"]
REGIME_COLORS = {
    "Negative GEX": "#dc2626",   # red
    "Low GEX":      "#f59e0b",   # amber
    "High GEX":     "#059669",   # green
}

def fmt_date(ts):
    return ts.strftime("%Y-%m-%d")

# ── Chart 1: GEX time series ──────────────────────────────────────────────────
gex_ts = {
    "dates":      [fmt_date(d) for d in df["date"]],
    "gex_bn":     [round(float(v), 3) for v in df["gex_bn"]],
    "bar_colors": [REGIME_COLORS[r] for r in df["regime"]],
    "zero_line":  0,
    "stats": {
        "n_total":         int(len(df)),
        "n_positive":      int((df["gex_bn"] >= 0).sum()),
        "n_negative":      int((df["gex_bn"] <  0).sum()),
        "mean_gex":        round(float(df["gex_bn"].mean()), 3),
        "pct_positive":    round(float((df["gex_bn"] >= 0).mean()), 4),
        "p25":             round(float(df["gex_bn"].quantile(0.25)), 3),
        "p75":             round(float(df["gex_bn"].quantile(0.75)), 3),
        "min_gex":         round(float(df["gex_bn"].min()), 3),
        "max_gex":         round(float(df["gex_bn"].max()), 3),
    }
}

with open("charts/data_gex_timeseries.json", "w") as f:
    json.dump(gex_ts, f)
print("Wrote data_gex_timeseries.json")

# ── Chart 2: Scatter GEX vs RVol ─────────────────────────────────────────────
slope = float(df["regression_slope"].iloc[0])
intercept = float(df["regression_intercept"].iloc[0])
r2    = float(df["regression_r2"].iloc[0])
p_reg = float(df["regression_p"].iloc[0])
t_stat = float(df["t_stat_neg_vs_high"].iloc[0])
p_val  = float(df["p_val_neg_vs_high"].iloc[0])

# Regression line: evaluate at min/max GEX
gex_min = float(df["gex_bn"].min())
gex_max = float(df["gex_bn"].max())
reg_line = [
    {"x": round(gex_min, 3), "y": round(slope * gex_min + intercept, 6)},
    {"x": round(gex_max, 3), "y": round(slope * gex_max + intercept, 6)},
]

scatter = {
    "points": [
        {
            "gex":    round(float(row["gex_bn"]), 3),
            "rvol":   round(float(row["rvol_ann"]), 6),
            "date":   fmt_date(row["date"]),
            "regime": row["regime"],
            "color":  REGIME_COLORS[row["regime"]],
        }
        for _, row in df.iterrows()
    ],
    "regression": {
        "slope":     round(slope, 8),
        "intercept": round(intercept, 6),
        "r2":        round(r2, 4),
        "p":         round(p_reg, 6),
        "line":      reg_line,
    },
    "lowess": lowess_pts[:200],   # cap at 200 points for chart rendering
    "t_test": {
        "t_stat": round(t_stat, 3),
        "p_val":  round(p_val, 4),
    },
}

with open("charts/data_scatter.json", "w") as f:
    json.dump(scatter, f)
print("Wrote data_scatter.json")

# ── Chart 3: Intraday vol profile by regime ───────────────────────────────────
BUCKET_LABELS = [
    "09:30","10:00","10:30","11:00","11:30","12:00","12:30",
    "13:00","13:30","14:00","14:30","15:00","15:30",
]

profile_data = {"buckets": BUCKET_LABELS, "regimes": {}}
for regime in REGIME_ORDER:
    if regime in bucket.index:
        row = bucket.loc[regime]
        profile_data["regimes"][regime] = [
            round(float(row.get(b, np.nan)), 6) if not pd.isna(row.get(b, np.nan)) else None
            for b in BUCKET_LABELS
        ]
    else:
        profile_data["regimes"][regime] = [None] * len(BUCKET_LABELS)

with open("charts/data_intraday_profile.json", "w") as f:
    json.dump(profile_data, f)
print("Wrote data_intraday_profile.json")

# ── Chart 4: Regime distribution (box plot data) ─────────────────────────────
def box_stats(vals):
    v = vals.dropna()
    return {
        "p10":    round(float(v.quantile(0.10)), 6),
        "p25":    round(float(v.quantile(0.25)), 6),
        "median": round(float(v.quantile(0.50)), 6),
        "p75":    round(float(v.quantile(0.75)), 6),
        "p90":    round(float(v.quantile(0.90)), 6),
        "mean":   round(float(v.mean()), 6),
        "n":      int(len(v)),
    }

regime_boxes = {
    "regimes": REGIME_ORDER,
    "colors":  [REGIME_COLORS[r] for r in REGIME_ORDER],
    "data":    {r: box_stats(df[df["regime"] == r]["rvol_ann"]) for r in REGIME_ORDER},
    "t_test":  {
        "t_stat": round(t_stat, 3),
        "p_val":  round(p_val, 4),
        "label":  "Negative GEX vs High GEX",
    },
    "vol_premium": round(
        float(
            (df[df["regime"]=="Negative GEX"]["rvol_ann"].mean()
             - df[df["regime"]=="High GEX"]["rvol_ann"].mean())
            / df[df["regime"]=="High GEX"]["rvol_ann"].mean()
        ), 4
    ),
}

with open("charts/data_regimes.json", "w") as f:
    json.dump(regime_boxes, f)
print("Wrote data_regimes.json")

# ── Chart 5: Rolling 60-day realized vol + regime shading ────────────────────
df_sorted = df.sort_values("date").copy()
df_sorted["rvol_rolling60"] = df_sorted["rvol_ann"].rolling(60, min_periods=20).mean()
df_sorted["gex_positive"]   = (df_sorted["gex_bn"] >= 0).astype(int)

backtest = {
    "dates":            [fmt_date(d) for d in df_sorted["date"]],
    "rvol_ann":         [round(float(v), 6) if not pd.isna(v) else None for v in df_sorted["rvol_ann"]],
    "rvol_rolling60":   [round(float(v), 6) if not pd.isna(v) else None for v in df_sorted["rvol_rolling60"]],
    "regime":           list(df_sorted["regime"]),
    "bar_colors":       [REGIME_COLORS[r] for r in df_sorted["regime"]],
    "gex_bn":           [round(float(v), 3) for v in df_sorted["gex_bn"]],
    "summary": {
        "neg_gex_mean_rvol":  round(float(df[df["regime"]=="Negative GEX"]["rvol_ann"].mean()), 6),
        "low_gex_mean_rvol":  round(float(df[df["regime"]=="Low GEX"]["rvol_ann"].mean()), 6),
        "high_gex_mean_rvol": round(float(df[df["regime"]=="High GEX"]["rvol_ann"].mean()), 6),
        "vol_premium_pct":    round(
            float(
                (df[df["regime"]=="Negative GEX"]["rvol_ann"].mean()
                 - df[df["regime"]=="High GEX"]["rvol_ann"].mean())
                / df[df["regime"]=="High GEX"]["rvol_ann"].mean() * 100
            ), 1
        ),
    }
}

with open("charts/data_backtest.json", "w") as f:
    json.dump(backtest, f)
print("Wrote data_backtest.json")

print("\nAll 5 chart JSON files written to charts/")
