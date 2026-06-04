"""
07_analysis.py  —  Aggregate walkdown + returns into data/analysis.json
Single source of truth for all figures in the HTML report.
Reads: data/walkdown_events.parquet, data/walkdown_curve.parquet, data/event_returns.parquet
Output: data/analysis.json
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

OUT = Path("data/analysis.json")

if OUT.exists():
    with open(OUT) as f:
        d = json.load(f)
    print(f"Cache hit — {OUT}")
    print(f"KPIs: {json.dumps(d['kpis'], indent=2)}")
    raise SystemExit(0)

# ── Load data ─────────────────────────────────────────────────────────────────
events = pd.read_parquet("data/walkdown_events.parquet")
events["anndats"] = pd.to_datetime(events["anndats"])
curve_df = pd.read_parquet("data/walkdown_curve.parquet")
curve_df["anndats"] = pd.to_datetime(curve_df["anndats"])
returns = pd.read_parquet("data/event_returns.parquet")
returns["anndats"] = pd.to_datetime(returns["anndats"])

inc = events[events["included"]].copy()
n_gen  = (inc["classification"] == "genuine_beat").sum()
n_mfg  = (inc["classification"] == "manufactured_beat").sum()
n_miss = (inc["classification"] == "miss").sum()
n_beats = n_gen + n_mfg
print(f"Included: {len(inc):,}  genuine: {n_gen:,}  manufactured: {n_mfg:,}  miss: {n_miss:,}")

# Merge events with returns on (permno, anndats)
merged = inc.merge(
    returns[["permno", "anndats", "car_reaction", "car_drift_60", "censored_drift"]],
    on=["permno", "anndats"], how="left"
)
merged["censored_drift"] = merged["censored_drift"].fillna(True)
merged["year"] = merged["anndats"].dt.year

# ── 1. KPIs ───────────────────────────────────────────────────────────────────
mfg_rate_pct      = n_mfg / n_beats * 100
median_walk_mfg   = inc[inc["classification"] == "manufactured_beat"]["walkdown_pct"].median()

gen_rxn  = merged[merged["classification"] == "genuine_beat"]["car_reaction"].dropna()
mfg_rxn  = merged[merged["classification"] == "manufactured_beat"]["car_reaction"].dropna()
ls_rxn   = gen_rxn.mean() - mfg_rxn.mean()

kpis = {
    "manufactured_beat_rate_pct": round(float(mfg_rate_pct), 1),
    "n_manufactured":             int(n_mfg),
    "median_walkdown_mfg_pct":    round(float(median_walk_mfg), 1),
    "ls_reaction_spread_pct":     round(float(ls_rxn * 100), 2),
}

# ── 2. Walk-down distribution histogram ───────────────────────────────────────
wdp_all  = inc["walkdown_pct"].clip(-80, 80)
wdp_mfg  = inc[inc["classification"] == "manufactured_beat"]["walkdown_pct"].clip(-80, 80)
wdp_gen  = inc[inc["classification"] == "genuine_beat"]["walkdown_pct"].clip(-80, 80)
wdp_miss = inc[inc["classification"] == "miss"]["walkdown_pct"].clip(-80, 80)
bin_edges = np.linspace(-80, 80, 33).tolist()  # 32 bins of 5-pct width

def hist(series, edges):
    counts, _ = np.histogram(series, bins=edges)
    return counts.tolist()

walkdown_dist = {
    "bins":          [f"{(b1+b2)/2:.0f}" for b1, b2 in zip(bin_edges[:-1], bin_edges[1:])],
    "counts_total":  hist(wdp_all,  bin_edges),
    "counts_mfg":    hist(wdp_mfg,  bin_edges),
    "counts_gen":    hist(wdp_gen,  bin_edges),
    "counts_miss":   hist(wdp_miss, bin_edges),
    "bin_edges":     bin_edges,
    "regime_cutoffs": [-2.0, 2.0],
}

# ── 3. Hero two-cohort walk curves ────────────────────────────────────────────
inc_keys = inc[["permno", "anndats", "classification", "orig_consensus"]].copy()
curve_m  = curve_df.merge(inc_keys, on=["permno", "anndats"], how="inner")
curve_m  = curve_m[curve_m["orig_consensus"].abs() > 0.01].copy()
curve_m["norm"] = curve_m["consensus_eps"] / curve_m["orig_consensus"] * 100

avg = (curve_m.groupby(["classification", "offset"])["norm"]
       .mean().reset_index().set_index(["classification", "offset"])["norm"])

offsets = list(range(-270, -1))

def get_curve(cls):
    vals = []
    for o in offsets:
        try:
            vals.append(round(float(avg.loc[(cls, o)]), 4))
        except KeyError:
            vals.append(None)
    return vals

walk_curves = {
    "offsets":      offsets,
    "manufactured": get_curve("manufactured_beat"),
    "genuine":      get_curve("genuine_beat"),
}

# ── 4. Cross-tab: walk bin x classification ───────────────────────────────────
def walk_bin(pct):
    if pct < -2:  return "down"
    if pct <= 2:  return "flat"
    return "up"

inc["walk_bin"] = inc["walkdown_pct"].apply(walk_bin)
xtab = inc.groupby(["walk_bin", "classification"]).size().unstack(fill_value=0)
bins_ord = ["down", "flat", "up"]
cls_ord  = ["genuine_beat", "manufactured_beat", "miss"]

crosstab = {
    "bins":           bins_ord,
    "classifications": cls_ord,
    "counts": [
        [int(xtab.loc[b, c]) if (b in xtab.index and c in xtab.columns) else 0
         for c in cls_ord]
        for b in bins_ord
    ],
    "bin_totals": [int(inc["walk_bin"].eq(b).sum()) for b in bins_ord],
    "bin_pcts":   [round(float(inc["walk_bin"].eq(b).mean() * 100), 1) for b in bins_ord],
}

# ── 5. Cohort profile ─────────────────────────────────────────────────────────
def coverage(cls):
    s = inc[inc["classification"] == cls]["final_n_analysts"].dropna()
    return {"median": round(float(s.median()), 1), "mean": round(float(s.mean()), 1), "n": int(len(s))}

analyst_coverage = {
    "manufactured": coverage("manufactured_beat"),
    "genuine":      coverage("genuine_beat"),
    "miss":         coverage("miss"),
}

sectors_ord = sorted(inc["sector"].dropna().unique().tolist())
def sec_pcts(cls):
    sub   = inc[inc["classification"] == cls]
    total = max(len(sub), 1)
    return [round(float(sub["sector"].eq(s).sum() / total * 100), 1) for s in sectors_ord]

sector_tilt = {
    "sectors":          sectors_ord,
    "manufactured_pct": sec_pcts("manufactured_beat"),
    "genuine_pct":      sec_pcts("genuine_beat"),
    "universe_pct":     [round(float(inc["sector"].eq(s).mean() * 100), 1) for s in sectors_ord],
}

def size_bucket(m):
    if pd.isna(m): return "Unknown"
    if m < 5_000:  return "<$5B"
    if m < 20_000: return "$5B-$20B"
    if m < 50_000: return "$20B-$50B"
    return ">$50B"

inc = inc.copy()
inc["size_bucket"] = inc["mktcap_m"].apply(size_bucket)
size_ord = ["<$5B", "$5B-$20B", "$20B-$50B", ">$50B"]

def size_pcts(cls):
    sub   = inc[inc["classification"] == cls]
    total = max(len(sub), 1)
    return [round(float(sub["size_bucket"].eq(b).sum() / total * 100), 1) for b in size_ord]

size_profile = {
    "buckets":          size_ord,
    "manufactured_pct": size_pcts("manufactured_beat"),
    "genuine_pct":      size_pcts("genuine_beat"),
    "miss_pct":         size_pcts("miss"),
}

cohort_profile = {
    "analyst_coverage": analyst_coverage,
    "sector_tilt":      sector_tilt,
    "size_profile":     size_profile,
}

# ── 6. Strategy tables ────────────────────────────────────────────────────────
def strat_stats(series):
    s = series.dropna()
    if len(s) < 5:
        return {"n": int(len(s)), "mean_pct": None, "median_pct": None,
                "hit_rate_pct": None, "t_stat": None, "p_val": None}
    t, p = stats.ttest_1samp(s, 0)
    return {
        "n":            int(len(s)),
        "mean_pct":     round(float(s.mean() * 100), 3),
        "median_pct":   round(float(s.median() * 100), 3),
        "hit_rate_pct": round(float((s > 0).mean() * 100), 1),
        "t_stat":       round(float(t), 2),
        "p_val":        round(float(p), 4),
    }

rxn_stats = {cls: strat_stats(merged[merged["classification"] == cls]["car_reaction"])
             for cls in cls_ord}

nc = merged[~merged["censored_drift"]]
dft_stats = {cls: strat_stats(nc[nc["classification"] == cls]["car_drift_60"])
             for cls in cls_ord}

gen_dft = nc[nc["classification"] == "genuine_beat"]["car_drift_60"].dropna()
mfg_dft = nc[nc["classification"] == "manufactured_beat"]["car_drift_60"].dropna()
ls_dft  = gen_dft.mean() - mfg_dft.mean()

def annual_ls_sharpe(df, col, exclude_censored=False):
    """Year-by-year L/S return: mean genuine - mean manufactured per year."""
    if exclude_censored:
        df = df[~df["censored_drift"]]
    years = sorted(df["year"].dropna().unique())
    ann = []
    for yr in years:
        g = df[(df["year"] == yr) & (df["classification"] == "genuine_beat")][col].mean()
        m = df[(df["year"] == yr) & (df["classification"] == "manufactured_beat")][col].mean()
        if pd.notna(g) and pd.notna(m):
            ann.append(float(g - m))
    if len(ann) < 3:
        return None
    arr = np.array(ann)
    std = arr.std()
    sharpe = float(arr.mean() / std) if std > 0 else None
    return {
        "sharpe":              round(sharpe, 2) if sharpe is not None else None,
        "n_years":             len(ann),
        "annual_returns_pct":  [round(r * 100, 2) for r in ann],
        "mean_annual_pct":     round(float(arr.mean() * 100), 2),
        "std_annual_pct":      round(float(std * 100), 2),
    }

strategy = {
    "reaction": {
        **rxn_stats,
        "ls_spread_pct": round(float(ls_rxn * 100), 3),
        "ls_sharpe":     annual_ls_sharpe(merged, "car_reaction"),
    },
    "drift": {
        **dft_stats,
        "ls_spread_pct": round(float(ls_dft * 100), 3),
        "ls_sharpe":     annual_ls_sharpe(merged, "car_drift_60", exclude_censored=True),
    },
}

# ── 7. Meta ───────────────────────────────────────────────────────────────────
xt = crosstab["counts"]  # [bin][cls]
meta = {
    "n_events_total":       int(len(events)),
    "n_included":           int(len(inc)),
    "n_genuine":            int(n_gen),
    "n_manufactured":       int(n_mfg),
    "n_miss":               int(n_miss),
    "n_beats":              int(n_beats),
    "data_range":           "2015-2025",
    "n_censored_drift":     int(merged["censored_drift"].sum()),
    "median_walk_all_pct":  round(float(inc["walkdown_pct"].median()), 1),
    "median_walk_mfg_pct":  round(float(median_walk_mfg), 1),
    "mean_walk_mfg_pct":    round(float(inc[inc["classification"]=="manufactured_beat"]["walkdown_pct"].mean()), 1),
    "median_walk_gen_pct":  round(float(inc[inc["classification"]=="genuine_beat"]["walkdown_pct"].median()), 1),
    "mean_walk_gen_pct":    round(float(inc[inc["classification"]=="genuine_beat"]["walkdown_pct"].mean()), 1),
    "median_analysts_mfg":  round(float(inc[inc["classification"]=="manufactured_beat"]["final_n_analysts"].median()), 1),
    "median_analysts_gen":  round(float(inc[inc["classification"]=="genuine_beat"]["final_n_analysts"].median()), 1),
    "n_mfg_down":           xt[0][1],
    "n_mfg_flat":           xt[1][1],
    "n_mfg_up":             xt[2][1],
}
# Near-miss: % of manufactured beats within 5% / 10% of the original consensus
mfg_sub  = inc[inc["classification"] == "manufactured_beat"]
gap_pct  = (mfg_sub["orig_consensus"] - mfg_sub["actual_eps"]) / mfg_sub["orig_consensus"].abs()
meta["near_miss_5pct_of_mfg"]  = round(float((gap_pct < 0.05).mean() * 100), 1)
meta["near_miss_10pct_of_mfg"] = round(float((gap_pct < 0.10).mean() * 100), 1)

# ── Save ──────────────────────────────────────────────────────────────────────
data = {
    "kpis":           kpis,
    "walkdown_dist":  walkdown_dist,
    "walk_curves":    walk_curves,
    "crosstab":       crosstab,
    "cohort_profile": cohort_profile,
    "strategy":       strategy,
    "meta":           meta,
}

with open(OUT, "w") as f:
    json.dump(data, f, indent=2)

print(f"\nSaved {OUT}")
print(f"KPIs: {kpis}")
print(f"\nReaction L/S spread: {ls_rxn*100:+.2f}%  |  Drift L/S spread: {ls_dft*100:+.2f}%")
print(f"Reaction Sharpe: {strategy['reaction']['ls_sharpe']}")
print(f"Drift Sharpe:    {strategy['drift']['ls_sharpe']}")
print(f"\nCross-tab (manufactured by walk bin):"
      f" down={meta['n_mfg_down']}  flat={meta['n_mfg_flat']}  up={meta['n_mfg_up']}")
