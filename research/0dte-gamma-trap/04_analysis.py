# ruff: noqa
"""
04_analysis.py
--------------
Merge GEX + intraday RVol, classify GEX regimes, compute stats and regression.

Regime classification (based on positive-day GEX distribution):
  - Negative GEX  : gex_bn < 0              → dealers short gamma, vol amplifying
  - Low GEX       : 0 ≤ gex_bn < median     → weakly long gamma, mild suppression
  - High GEX      : gex_bn ≥ median          → strongly long gamma, vol suppressing

Output: data/combined.parquet
"""

import os
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

os.makedirs("data", exist_ok=True)

CACHE = "data/combined.parquet"

# ── Load ──────────────────────────────────────────────────────────────────────
gex     = pd.read_parquet("data/gex_daily.parquet")
rvol    = pd.read_parquet("data/rvol_daily.parquet")
profile = pd.read_parquet("data/rvol_profile.parquet")

gex["date"]  = pd.to_datetime(gex["date"])
rvol["date"] = pd.to_datetime(rvol["date"])

merged = gex.merge(rvol, on="date", how="inner")
merged = merged.dropna(subset=["gex_bn", "rvol_ann"]).sort_values("date").reset_index(drop=True)
print(f"Merged dataset: {len(merged):,} days")

# ── Regime classification ─────────────────────────────────────────────────────
positive_days = merged[merged["gex_bn"] >= 0]["gex_bn"]
p50 = float(positive_days.quantile(0.50))

def classify(g):
    if g < 0:
        return "Negative GEX"
    elif g < p50:
        return "Low GEX"
    else:
        return "High GEX"

merged["regime"] = merged["gex_bn"].apply(classify)
merged["regime_ord"] = merged["regime"].map({"Negative GEX": 0, "Low GEX": 1, "High GEX": 2})

print(f"\nRegime thresholds: Negative < 0 < Low < {p50:.2f} (median) <= High")
print(merged["regime"].value_counts().to_string())

# ── Per-regime stats ──────────────────────────────────────────────────────────
def regime_stats(df):
    return pd.Series({
        "n_days":      len(df),
        "mean_rvol":   df["rvol_ann"].mean(),
        "median_rvol": df["rvol_ann"].median(),
        "std_rvol":    df["rvol_ann"].std(),
        "p10_rvol":    df["rvol_ann"].quantile(0.10),
        "p25_rvol":    df["rvol_ann"].quantile(0.25),
        "p75_rvol":    df["rvol_ann"].quantile(0.75),
        "p90_rvol":    df["rvol_ann"].quantile(0.90),
    })

regime_df = (
    merged.groupby("regime", sort=False)
    .apply(regime_stats)
    .loc[["Negative GEX", "Low GEX", "High GEX"]]
)
print("\n=== Per-regime realized vol stats ===")
print(regime_df.round(4).to_string())

# ── Statistical tests ─────────────────────────────────────────────────────────
neg  = merged.loc[merged["regime"] == "Negative GEX", "rvol_ann"]
low  = merged.loc[merged["regime"] == "Low GEX",      "rvol_ann"]
high = merged.loc[merged["regime"] == "High GEX",     "rvol_ann"]

t_stat, p_val = scipy_stats.ttest_ind(neg, high, equal_var=False)
kw_stat, kw_p = scipy_stats.kruskal(neg, low, high)

print(f"\n=== Welch t-test: Negative GEX vs High GEX ===")
print(f"t={t_stat:.3f}, p={p_val:.4f}  ({'significant' if p_val < 0.05 else 'NOT significant'} at 5%)")
print(f"\n=== Kruskal-Wallis (all 3 regimes) ===")
print(f"H={kw_stat:.3f}, p={kw_p:.4f}")

# ── OLS regression: rvol ~ gex_bn ────────────────────────────────────────────
slope, intercept, r, p_reg, se = scipy_stats.linregress(merged["gex_bn"], merged["rvol_ann"])
r2 = r ** 2
print(f"\n=== OLS: rvol ~ gex_bn ===")
print(f"slope={slope:.6f}, intercept={intercept:.4f}")
print(f"R²={r2:.4f}, p={p_reg:.4f}")

# Compute lowess for scatter chart
try:
    from statsmodels.nonparametric.smoothers_lowess import lowess as sm_lowess
    sorted_idx = merged["gex_bn"].argsort()
    lx = merged["gex_bn"].values[sorted_idx]
    ly = merged["rvol_ann"].values[sorted_idx]
    smoothed = sm_lowess(ly, lx, frac=0.3, return_sorted=True)
    merged["lowess_x"] = np.nan
    merged["lowess_y"] = np.nan
    lowess_pts = [{"x": round(float(x), 4), "y": round(float(y), 6)} for x, y in smoothed]
except ImportError:
    lowess_pts = []
    print("statsmodels not available — skipping lowess.")

# Store regression + test results for use in charts/report
merged["regression_slope"]     = slope
merged["regression_intercept"] = intercept
merged["regression_r2"]        = r2
merged["regression_p"]         = p_reg
merged["t_stat_neg_vs_high"]   = t_stat
merged["p_val_neg_vs_high"]    = p_val
merged["gex_p50_threshold"]    = p50

# ── Pre/post structural break: May 2022 (daily 0DTE introduced) ───────────────
# Before May 2022: Mon/Wed/Fri only had 0DTE. After: every day.
MAY_2022 = pd.Timestamp("2022-05-23")   # CBOE expanded to daily SPX 0DTE
pre  = merged[merged["date"] <  MAY_2022]
post = merged[merged["date"] >= MAY_2022]

print(f"\n=== Pre vs Post daily-0DTE (split: {MAY_2022.date()}) ===")
print(f"Pre  ({len(pre):3d} days): mean GEX={pre['gex_bn'].mean():.2f}bn, mean rvol={pre['rvol_ann'].mean():.1%}")
print(f"Post ({len(post):3d} days): mean GEX={post['gex_bn'].mean():.2f}bn, mean rvol={post['rvol_ann'].mean():.1%}")

# ── Merge vol profile bucket data ─────────────────────────────────────────────
profile["date"] = pd.to_datetime(profile["date"])
combined_profile = profile.merge(
    merged[["date", "regime"]],
    on="date", how="inner"
)

# Average bucket vol by regime — exported separately for chart 3
bucket_by_regime = (
    combined_profile.dropna(subset=["bucket_rvol"])
    .groupby(["regime", "bucket"])["bucket_rvol"]
    .mean()
    .unstack("bucket")
    .loc[["Negative GEX", "Low GEX", "High GEX"]]
)

# ── Save ──────────────────────────────────────────────────────────────────────
merged.to_parquet(CACHE, index=False)
bucket_by_regime.to_parquet("data/bucket_by_regime.parquet")

# Also pickle lowess for charts script
import json
with open("data/lowess_pts.json", "w") as f:
    json.dump(lowess_pts, f)

print(f"\nSaved combined.parquet ({len(merged):,} rows)")
print(f"Saved bucket_by_regime.parquet")

# ── Summary for report ────────────────────────────────────────────────────────
vol_premium = float((neg.mean() - high.mean()) / high.mean())
print(f"\n=== KEY NUMBERS FOR REPORT ===")
print(f"Negative GEX mean rvol : {neg.mean():.1%}")
print(f"High GEX mean rvol     : {high.mean():.1%}")
print(f"Vol premium (neg/high) : {vol_premium:+.1%}")
print(f"R² (GEX vs RVol)       : {r2:.3f}")
print(f"p-value (t-test)       : {p_val:.4f}")
