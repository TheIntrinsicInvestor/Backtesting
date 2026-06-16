"""
06_regime_stats.py
-------------------
Per-regime return/risk stats for the equity index, FF industries, style
factors, and the rate/curve backbone. Regimes are the four buckets from
01_rate_regimes.py: Hiking, Cutting, Hold-Elevated, Hold-ZLB. The COVID-2020
emergency-cut stub (is_outlier=True) is excluded from main aggregates and
reported separately per feedback_covid_outliers.

Drawdown is computed per contiguous regime "spell" (a regime label can recur
across several non-adjacent date spans) so it never bridges a regime change.

Outputs:
  data/regime_panel.parquet   (merged daily panel reused by 07_transition_study.py)
  charts/data_regime_equity.json
  charts/data_regime_industries.json
  charts/data_regime_factors.json
  charts/data_regime_curve.json
"""
import os
import json
import numpy as np
import pandas as pd

os.makedirs("charts", exist_ok=True)

TRADING_DAYS_YEAR = 252
REGIME_ORDER = ["Hiking", "Cutting", "Hold-Elevated", "Hold-ZLB"]

# ── Load + merge ─────────────────────────────────────────────────────────────
regimes    = pd.read_parquet("data/regimes.parquet")
equity     = pd.read_parquet("data/equity.parquet")
factors    = pd.read_parquet("data/ff_factors.parquet")
industries = pd.read_parquet("data/ff_industries.parquet")
macro      = pd.read_parquet("data/macro.parquet")

for d in (regimes, equity, factors, industries, macro):
    d["date"] = pd.to_datetime(d["date"])

regimes = regimes.sort_values("date").reset_index(drop=True)
regimes["spell_id"] = (regimes["regime"] != regimes["regime"].shift()).cumsum()

panel = (equity.merge(regimes, on="date", how="inner")
                .merge(factors, on="date", how="left")
                .merge(industries, on="date", how="left")
                .merge(macro, on="date", how="left"))
panel = panel.sort_values("date").reset_index(drop=True)
panel.to_parquet("data/regime_panel.parquet", index=False)
print(f"Panel: {len(panel):,} trading days, "
      f"{panel['date'].min().date()} to {panel['date'].max().date()}")

INDUSTRY_COLS = [c for c in industries.columns if c != "date"]
FACTOR_COLS   = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"]

# ── Return/risk stats per regime ───────────────────────────────────────────
def regime_return_stats(df, ret_col):
    rets = df[ret_col].dropna()
    n = len(rets)
    if n < 5:
        return {"n_days": int(n), "ann_return": None, "ann_vol": None,
                "sharpe": None, "max_drawdown": None}
    ann_return = (1 + rets).prod() ** (TRADING_DAYS_YEAR / n) - 1
    ann_vol    = rets.std() * np.sqrt(TRADING_DAYS_YEAR)
    sharpe     = ann_return / ann_vol if ann_vol else None
    dd_worst = 0.0
    for _, spell in df.groupby("spell_id"):
        cum = (1 + spell[ret_col].fillna(0)).cumprod()
        dd = (cum / cum.cummax() - 1).min()
        dd_worst = min(dd_worst, dd)
    return {
        "n_days": int(n),
        "ann_return": round(float(ann_return) * 100, 2),
        "ann_vol": round(float(ann_vol) * 100, 2),
        "sharpe": round(float(sharpe), 2) if sharpe is not None else None,
        "max_drawdown": round(float(dd_worst) * 100, 2),
    }

def stats_by_regime(panel, ret_col):
    main = panel[~panel["is_outlier"]]
    out = {r: regime_return_stats(main[main["regime"] == r], ret_col) for r in REGIME_ORDER}
    covid = panel[panel["is_outlier"]]
    out["Cutting_covid_outlier"] = regime_return_stats(covid, ret_col) if len(covid) else None
    return out

# ── Chart 1: equity index by regime ─────────────────────────────────────────
equity_stats = {
    "spx":     stats_by_regime(panel, "sprtrn"),
    "crsp_vw": stats_by_regime(panel, "vwretd"),
}
with open("charts/data_regime_equity.json", "w") as f:
    json.dump(equity_stats, f, indent=2)
print("Saved charts/data_regime_equity.json")

# ── Chart 2: FF industries by regime ────────────────────────────────────────
industry_stats = {ind: stats_by_regime(panel, ind) for ind in INDUSTRY_COLS}
with open("charts/data_regime_industries.json", "w") as f:
    json.dump(industry_stats, f, indent=2)
print(f"Saved charts/data_regime_industries.json ({len(INDUSTRY_COLS)} industries)")

# ── Chart 3: style factors by regime ────────────────────────────────────────
factor_stats = {fac: stats_by_regime(panel, fac) for fac in FACTOR_COLS}
with open("charts/data_regime_factors.json", "w") as f:
    json.dump(factor_stats, f, indent=2)
print(f"Saved charts/data_regime_factors.json ({len(FACTOR_COLS)} factors)")

# ── Chart 4: rates & curve levels by regime (descriptive, not return-based) ──
def curve_levels(df):
    sub = df.dropna(subset=["dgs10"])
    if len(sub) < 5:
        return None
    return {
        "n_days": int(len(sub)),
        "avg_dgs10": round(float(sub["dgs10"].mean()), 2),
        "avg_dgs2": round(float(sub["dgs2"].mean()), 2),
        "avg_t10y2y": round(float(sub["t10y2y"].mean()), 2),
        "min_t10y2y": round(float(sub["t10y2y"].min()), 2),
        "max_t10y2y": round(float(sub["t10y2y"].max()), 2),
        "avg_vix": round(float(sub["vix"].mean()), 2) if sub["vix"].notna().any() else None,
        "max_vix": round(float(sub["vix"].max()), 2) if sub["vix"].notna().any() else None,
    }

main_panel  = panel[~panel["is_outlier"]]
curve_stats = {r: curve_levels(main_panel[main_panel["regime"] == r]) for r in REGIME_ORDER}
covid_panel = panel[panel["is_outlier"]]
curve_stats["Cutting_covid_outlier"] = curve_levels(covid_panel) if len(covid_panel) else None
with open("charts/data_regime_curve.json", "w") as f:
    json.dump(curve_stats, f, indent=2)
print("Saved charts/data_regime_curve.json")

# ── Print summary ────────────────────────────────────────────────────────
print("\n=== SPX by regime (main, ex-COVID) ===")
for r in REGIME_ORDER:
    s = equity_stats["spx"][r]
    print(f"  {r:14s} n={s['n_days']:5d}  ann_ret={s['ann_return']:+6.1f}%  "
          f"ann_vol={s['ann_vol']:5.1f}%  sharpe={s['sharpe']:+5.2f}  maxDD={s['max_drawdown']:6.1f}%")
covid = equity_stats["spx"]["Cutting_covid_outlier"]
if covid and covid["ann_return"] is not None:
    print(f"  {'COVID outlier':14s} n={covid['n_days']:5d}  ann_ret={covid['ann_return']:+6.1f}%  "
          f"ann_vol={covid['ann_vol']:5.1f}%  sharpe={covid['sharpe']:+5.2f}  maxDD={covid['max_drawdown']:6.1f}%")

print("\n=== Curve levels by regime ===")
for r in REGIME_ORDER:
    c = curve_stats[r]
    if c:
        print(f"  {r:14s} avg_dgs10={c['avg_dgs10']:5.2f}%  avg_dgs2={c['avg_dgs2']:5.2f}%  "
              f"avg_t10y2y={c['avg_t10y2y']:+5.2f}  avg_vix={c['avg_vix']}")
print("Done.")
