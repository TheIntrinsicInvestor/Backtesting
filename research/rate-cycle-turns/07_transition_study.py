"""
07_transition_study.py
-----------------------
Event-window study around each rate-cycle "turn" (first hike / first cut),
trading days T-30 to T+90, mirroring fomc-iv-study/06_event_study.py.

Index, FF industries, and FF factors are normalised per-turn so the level on
the turn date (T0) = 100 (cumulative return from each daily return column).
VIX and curve levels are kept raw, with a delta-from-T0 column added for the
curve (level deltas, not normalised ratios, since 2s10s can cross zero).

Insurance cuts (1995, 2019) and the 2020 COVID emergency cut are excluded
from the main first_hike/first_cut aggregates and reported as separate single
-turn series (feedback_covid_outliers: isolated, not blended).

Requires data/regime_panel.parquet (built by 06_regime_stats.py).

Outputs:
  data/transition_panel.parquet
  charts/data_transition_index.json
  charts/data_transition_vix.json
  charts/data_transition_curve.json
  charts/data_transition_sectors.json
  charts/data_transition_factors.json
  charts/data_transition_heatmap.json
"""
import os
import json
import numpy as np
import pandas as pd

os.makedirs("charts", exist_ok=True)

WINDOW = list(range(-30, 91))   # T-30 to T+90
CHECKPOINTS = [-30, -5, 0, 5, 30, 60, 90]

panel = pd.read_parquet("data/regime_panel.parquet")
panel["date"] = pd.to_datetime(panel["date"])
panel = panel.sort_values("date").reset_index(drop=True)

turns = pd.read_parquet("data/turns.parquet")
turns["date"] = pd.to_datetime(turns["date"])

industries_cols = [c for c in pd.read_parquet("data/ff_industries.parquet").columns if c != "date"]
factor_cols     = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"]
ret_cols        = ["sprtrn"] + industries_cols + factor_cols
level_cols      = ["vix", "dgs10", "dgs2", "t10y2y"]

dates_idx = pd.DatetimeIndex(panel["date"])

# ── Build long event-window table ───────────────────────────────────────────
records = []
for _, turn in turns.iterrows():
    idx0 = int(dates_idx.searchsorted(turn["date"]))
    if idx0 >= len(panel):
        print(f"WARNING: turn {turn['date'].date()} is after data end, skipping")
        continue

    lo = max(0, idx0 + WINDOW[0])
    hi = min(len(panel) - 1, idx0 + WINDOW[-1])
    sl = panel.iloc[lo:hi + 1].reset_index(drop=True)
    pos0 = idx0 - lo
    offsets = np.arange(lo, hi + 1) - idx0

    cum = {}
    for col in ret_cols:
        c = (1 + sl[col].fillna(0)).cumprod()
        base = c.iloc[pos0]
        cum[col] = (c / base * 100).values

    for i, off in enumerate(offsets):
        row = {
            "turn_date": turn["date"], "turn_type": turn["turn_type"],
            "is_insurance": bool(turn["is_insurance"]), "is_outlier": bool(turn["is_outlier"]),
            "include_in_main": bool(turn["include_in_main"]), "t_day": int(off),
        }
        for col in ret_cols:
            row[col] = float(cum[col][i])
        for col in level_cols:
            v = sl[col].iloc[i]
            row[col] = float(v) if pd.notna(v) else None
        records.append(row)

df = pd.DataFrame(records)

# ── Curve deltas from T0 (level change, not normalised ratio) ───────────────
def add_delta(df, col):
    out = []
    for _, grp in df.groupby("turn_date"):
        base_row = grp[grp["t_day"] == 0]
        base = base_row[col].iloc[0] if len(base_row) and pd.notna(base_row[col].iloc[0]) else np.nan
        out.append(grp.assign(**{f"{col}_delta": grp[col] - base}))
    return pd.concat(out, ignore_index=True)

for col in ["dgs10", "dgs2", "t10y2y"]:
    df = add_delta(df, col)

df.to_parquet("data/transition_panel.parquet", index=False)
print(f"Saved {len(df):,} rows to data/transition_panel.parquet "
      f"({turns['date'].nunique()} turns)")

# ── Aggregation helper ───────────────────────────────────────────────────────
def series_for(subset, col):
    mean = subset.groupby("t_day")[col].mean()
    return [round(float(mean[t]), 2) if t in mean.index and pd.notna(mean[t]) else None for t in WINDOW]

main_hike = df[(df["turn_type"] == "first_hike") & (df["include_in_main"])]
main_cut  = df[(df["turn_type"] == "first_cut")  & (df["include_in_main"])]
ins_1995  = df[df["turn_date"] == pd.Timestamp("1995-07-06")]
ins_2019  = df[df["turn_date"] == pd.Timestamp("2019-07-31")]
covid     = df[df["turn_date"] == pd.Timestamp("2020-03-03")]

n_hike = main_hike["turn_date"].nunique()
n_cut  = main_cut["turn_date"].nunique()

# ── Chart 1: index ───────────────────────────────────────────────────────────
chart_index = {
    "labels": WINDOW,
    "first_hike_mean": series_for(main_hike, "sprtrn"), "first_hike_n": int(n_hike),
    "first_cut_mean":  series_for(main_cut,  "sprtrn"), "first_cut_n":  int(n_cut),
    "insurance_1995":     series_for(ins_1995, "sprtrn"),
    "insurance_2019":     series_for(ins_2019, "sprtrn"),
    "covid_2020_outlier": series_for(covid,    "sprtrn"),
}
with open("charts/data_transition_index.json", "w") as f:
    json.dump(chart_index, f, indent=2)
print("Saved charts/data_transition_index.json")

# ── Chart 2: VIX (raw level) ──────────────────────────────────────────────────
chart_vix = {
    "labels": WINDOW,
    "first_hike_mean": series_for(main_hike, "vix"), "first_hike_n": int(n_hike),
    "first_cut_mean":  series_for(main_cut,  "vix"), "first_cut_n":  int(n_cut),
    "insurance_1995":     series_for(ins_1995, "vix"),
    "insurance_2019":     series_for(ins_2019, "vix"),
    "covid_2020_outlier": series_for(covid,    "vix"),
}
with open("charts/data_transition_vix.json", "w") as f:
    json.dump(chart_vix, f, indent=2)
print("Saved charts/data_transition_vix.json")

# ── Chart 3: curve (level deltas from T0, main groups only) ──────────────────
chart_curve = {
    "labels": WINDOW,
    "first_hike_t10y2y_delta": series_for(main_hike, "t10y2y_delta"),
    "first_cut_t10y2y_delta":  series_for(main_cut,  "t10y2y_delta"),
    "first_hike_dgs10_delta":  series_for(main_hike, "dgs10_delta"),
    "first_cut_dgs10_delta":   series_for(main_cut,  "dgs10_delta"),
    "first_hike_n": int(n_hike), "first_cut_n": int(n_cut),
}
with open("charts/data_transition_curve.json", "w") as f:
    json.dump(chart_curve, f, indent=2)
print("Saved charts/data_transition_curve.json")

# ── Chart 4: sectors (FF industries, main groups only) ───────────────────────
chart_sectors = {
    "labels": WINDOW,
    "industries": {
        ind: {"first_hike": series_for(main_hike, ind), "first_cut": series_for(main_cut, ind)}
        for ind in industries_cols
    },
    "first_hike_n": int(n_hike), "first_cut_n": int(n_cut),
}
with open("charts/data_transition_sectors.json", "w") as f:
    json.dump(chart_sectors, f, indent=2)
print(f"Saved charts/data_transition_sectors.json ({len(industries_cols)} industries)")

# ── Chart 5: style factors (main groups only) ─────────────────────────────────
chart_factors = {
    "labels": WINDOW,
    "factors": {
        fac: {"first_hike": series_for(main_hike, fac), "first_cut": series_for(main_cut, fac)}
        for fac in factor_cols
    },
    "first_hike_n": int(n_hike), "first_cut_n": int(n_cut),
}
with open("charts/data_transition_factors.json", "w") as f:
    json.dump(chart_factors, f, indent=2)
print(f"Saved charts/data_transition_factors.json ({len(factor_cols)} factors)")

# ── Chart 6: per-turn checkpoint heatmap (honest small-sample, every turn) ───
heatmap_rows = []
for turn_date, grp in df.groupby("turn_date"):
    ev = turns[turns["date"] == turn_date].iloc[0]
    row = {
        "turn_date": turn_date.strftime("%Y-%m-%d"),
        "turn_type": ev["turn_type"],
        "is_insurance": bool(ev["is_insurance"]),
        "is_outlier": bool(ev["is_outlier"]),
        "notes": ev["notes"],
    }
    for cp in CHECKPOINTS:
        cp_row = grp[grp["t_day"] == cp]
        row[f"spx_T{cp:+d}"] = round(float(cp_row["sprtrn"].iloc[0]) - 100, 2) if len(cp_row) and pd.notna(cp_row["sprtrn"].iloc[0]) else None
        row[f"vix_T{cp:+d}"] = round(float(cp_row["vix"].iloc[0]), 1) if len(cp_row) and pd.notna(cp_row["vix"].iloc[0]) else None
        row[f"t10y2y_delta_T{cp:+d}"] = round(float(cp_row["t10y2y_delta"].iloc[0]), 2) if len(cp_row) and pd.notna(cp_row["t10y2y_delta"].iloc[0]) else None
    heatmap_rows.append(row)
heatmap_rows.sort(key=lambda r: r["turn_date"])

with open("charts/data_transition_heatmap.json", "w") as f:
    json.dump(heatmap_rows, f, indent=2)
print(f"Saved charts/data_transition_heatmap.json ({len(heatmap_rows)} turns)")

# ── Print summary ────────────────────────────────────────────────────────────
print(f"\n=== First-hike turns (main, n={n_hike}) ===")
for t in sorted(main_hike["turn_date"].unique()):
    print(f"  {pd.Timestamp(t).date()}")
print(f"\n=== First-cut turns (main, n={n_cut}) ===")
for t in sorted(main_cut["turn_date"].unique()):
    print(f"  {pd.Timestamp(t).date()}")

print("\n=== SPX cumulative level at T+90 vs T0=100 ===")
for label, sub in [("first_hike", main_hike), ("first_cut", main_cut),
                    ("insurance_1995", ins_1995), ("insurance_2019", ins_2019),
                    ("covid_2020_outlier", covid)]:
    v90 = sub[sub["t_day"] == 90]["sprtrn"]
    if len(v90):
        print(f"  {label:20s} T+90 = {v90.mean():6.1f}  (n_turns={sub['turn_date'].nunique()})")

print("\n=== VIX mean at T0 vs T+5 ===")
for label, sub in [("first_hike", main_hike), ("first_cut", main_cut)]:
    v0 = sub[sub["t_day"] == 0]["vix"].mean()
    v5 = sub[sub["t_day"] == 5]["vix"].mean()
    print(f"  {label:12s} T0={v0:.1f}  T+5={v5:.1f}")
print("Done.")
