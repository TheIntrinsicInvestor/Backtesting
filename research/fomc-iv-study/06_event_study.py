"""
06_event_study.py
-----------------
Build normalised IV event profiles for all 58 FOMC meetings.

For each meeting × instrument, extract a T-20 to T+10 window of daily IV,
normalise so that mean(T-20 to T-15) = 100, then aggregate across meetings.

Profiles computed:
  1. All meetings — SPX mean + ±1 SD band
  2. All meetings — TLT mean
  3. All meetings — VIX mean
  4. By decision_type (Hike / Hold / Cut) — SPX mean
  5. By comm_surprise for Hold meetings only (Hawkish / Neutral / Dovish) — SPX mean

Key checkpoint data (for heatmap):
  T-5, T-1, T=0, T+1, T+5 — ΔIV vs baseline for each instrument per meeting

Outputs:
  data/event_profiles.parquet
  charts/data_iv_profile.json
  charts/data_iv_by_decision.json
  charts/data_iv_by_comm_hold.json
  charts/data_heatmap.json
"""

import os
import json
import numpy as np
import pandas as pd

os.makedirs("data", exist_ok=True)
os.makedirs("charts", exist_ok=True)

# ── Load data ─────────────────────────────────────────────────────────────────
events  = pd.read_parquet("data/fomc_events.parquet")
iv_raw  = pd.read_parquet("data/iv_raw.parquet")
vix_raw = pd.read_parquet("data/vix_raw.parquet")

events["date"]    = pd.to_datetime(events["date"])
iv_raw["date"]    = pd.to_datetime(iv_raw["date"])
vix_raw["date"]   = pd.to_datetime(vix_raw["date"])

# Build trading calendar from SPX data
trading_days = pd.DatetimeIndex(
    sorted(iv_raw[iv_raw["ticker"] == "SPX"]["date"].unique())
)

def find_tday(fomc_date, offset):
    ts = pd.Timestamp(fomc_date)
    idx = trading_days.searchsorted(ts)
    target = idx + offset
    if 0 <= target < len(trading_days):
        return trading_days[target]
    return None

# ── Build event window per meeting ────────────────────────────────────────────
WINDOW = list(range(-20, 11))   # T-20 to T+10
BASELINE_OFFSETS = list(range(-20, -14))  # T-20 to T-15 (6 days)

# Pivot IV data for fast lookup
spx_iv  = iv_raw[iv_raw["ticker"] == "SPX"].set_index("date")["impl_volatility"]
tlt_iv  = iv_raw[iv_raw["ticker"] == "TLT"].set_index("date")["impl_volatility"]
vix_ser = vix_raw.set_index("date")["vix"]

records = []

for _, ev in events.iterrows():
    fd = ev["date"]
    for off in WINDOW:
        td = find_tday(fd, off)
        if td is None:
            continue
        row = {
            "fomc_date"    : fd,
            "t_day"        : off,
            "trade_date"   : td,
            "decision_type": ev["decision_type"],
            "comm_surprise": ev["comm_surprise"],
            "is_outlier"   : ev["is_outlier"],
            "spx_iv"       : spx_iv.get(td, np.nan),
            "tlt_iv"       : tlt_iv.get(td, np.nan),
            "vix"          : vix_ser.get(td, np.nan),
        }
        records.append(row)

df = pd.DataFrame(records)

# ── Normalise per meeting × instrument ────────────────────────────────────────
def normalise_col(df, col):
    normed = []
    for fd, grp in df.groupby("fomc_date"):
        baseline = grp[grp["t_day"].isin(BASELINE_OFFSETS)][col].dropna()
        if len(baseline) < 3 or baseline.mean() == 0:
            grp = grp.copy()
            grp[f"{col}_norm"] = np.nan
        else:
            bm = baseline.mean()
            grp = grp.copy()
            grp[f"{col}_norm"] = grp[col] / bm * 100
        normed.append(grp)
    return pd.concat(normed, ignore_index=True)

df = normalise_col(df, "spx_iv")
df = normalise_col(df, "tlt_iv")
df = normalise_col(df, "vix")

df.to_parquet("data/event_profiles.parquet", index=False)
print(f"Saved {len(df):,} rows to data/event_profiles.parquet")

# ── Helper: aggregate profile for a subset ────────────────────────────────────
def agg_profile(subset, col):
    grp = subset.groupby("t_day")[col]
    mean = grp.mean()
    std  = grp.std()
    return mean, std

# ── Chart 1: All meetings — SPX + TLT + VIX profile ─────────────────────────
# Exclude degenerate Mar 18 2020 outlier for profile charts
clean = df[~df["is_outlier"]]

spx_mean, spx_std = agg_profile(clean, "spx_iv_norm")
tlt_mean, _       = agg_profile(clean, "tlt_iv_norm")
vix_mean, _       = agg_profile(clean, "vix_norm")

chart1 = {
    "labels"  : WINDOW,
    "spx_mean": [round(spx_mean.get(t, None), 2) if not np.isnan(spx_mean.get(t, np.nan)) else None for t in WINDOW],
    "spx_upper": [round((spx_mean.get(t, np.nan) + spx_std.get(t, np.nan)), 2)
                  if not np.isnan(spx_mean.get(t, np.nan)) else None for t in WINDOW],
    "spx_lower": [round((spx_mean.get(t, np.nan) - spx_std.get(t, np.nan)), 2)
                  if not np.isnan(spx_mean.get(t, np.nan)) else None for t in WINDOW],
    "tlt_mean": [round(tlt_mean.get(t, None), 2) if not np.isnan(tlt_mean.get(t, np.nan)) else None for t in WINDOW],
    "vix_mean": [round(vix_mean.get(t, None), 2) if not np.isnan(vix_mean.get(t, np.nan)) else None for t in WINDOW],
    "n_meetings": int((~clean["fomc_date"].duplicated()).sum()),
}

with open("charts/data_iv_profile.json", "w") as f:
    json.dump(chart1, f, indent=2)
print("Saved charts/data_iv_profile.json")

# ── Chart 2: By decision_type — SPX profile ───────────────────────────────────
chart2 = {"labels": WINDOW}
for dtype in ["Hike", "Hold", "Cut"]:
    sub = clean[clean["decision_type"] == dtype]
    mean, _ = agg_profile(sub, "spx_iv_norm")
    chart2[dtype] = [round(mean.get(t, None), 2) if not np.isnan(mean.get(t, np.nan)) else None for t in WINDOW]
    chart2[f"{dtype}_n"] = int(sub["fomc_date"].nunique())

with open("charts/data_iv_by_decision.json", "w") as f:
    json.dump(chart2, f, indent=2)
print("Saved charts/data_iv_by_decision.json")

# ── Chart 3: By comm_surprise — Hold meetings only ────────────────────────────
chart3 = {"labels": WINDOW}
holds = clean[clean["decision_type"] == "Hold"]
for cs in ["Hawkish", "Neutral", "Dovish"]:
    sub = holds[holds["comm_surprise"] == cs]
    mean, _ = agg_profile(sub, "spx_iv_norm")
    chart3[cs] = [round(mean.get(t, None), 2) if not np.isnan(mean.get(t, np.nan)) else None for t in WINDOW]
    chart3[f"{cs}_n"] = int(sub["fomc_date"].nunique())

with open("charts/data_iv_by_comm_hold.json", "w") as f:
    json.dump(chart3, f, indent=2)
print("Saved charts/data_iv_by_comm_hold.json")

# ── Chart 4: Heatmap — IV change at checkpoints per meeting ──────────────────
CHECKPOINTS = [-5, -1, 0, 1, 5]
heatmap_rows = []

for fd, grp in clean.groupby("fomc_date"):
    ev_row = events[events["date"] == fd].iloc[0]
    row = {
        "fomc_date"    : fd.strftime("%Y-%m-%d"),
        "decision_type": ev_row["decision_type"],
        "comm_surprise": ev_row["comm_surprise"],
        "actual_change": int(ev_row["actual_change_bps"]),
        "is_emergency" : bool(ev_row["is_emergency"]),
    }
    for cp in CHECKPOINTS:
        cp_row = grp[grp["t_day"] == cp]
        for col, label in [("spx_iv_norm", "SPX"), ("tlt_iv_norm", "TLT"), ("vix_norm", "VIX")]:
            key = f"{label}_T{cp:+d}"
            if len(cp_row) > 0 and not np.isnan(cp_row[col].values[0]):
                row[key] = round(float(cp_row[col].values[0]) - 100, 2)
            else:
                row[key] = None
    heatmap_rows.append(row)

with open("charts/data_heatmap.json", "w") as f:
    json.dump(heatmap_rows, f, indent=2)
print(f"Saved charts/data_heatmap.json ({len(heatmap_rows)} meetings)")

# ── Print key summary statistics ──────────────────────────────────────────────
print("\n=== Key IV crush statistics (T-1 to T+1, SPX, excl. outliers) ===")
t_minus1 = clean[clean["t_day"] == -1]["spx_iv_norm"].mean()
t_plus1  = clean[clean["t_day"] ==  1]["spx_iv_norm"].mean()
crush_pct = (t_plus1 - t_minus1) / t_minus1 * 100
print(f"  Mean SPX IV at T-1 : {t_minus1:.1f} (normalised)")
print(f"  Mean SPX IV at T+1 : {t_plus1:.1f} (normalised)")
print(f"  Avg IV crush T-1 to T+1: {crush_pct:+.1f}%")

print("\n=== IV crush by decision_type ===")
for dtype in ["Hike", "Hold", "Cut"]:
    sub = clean[clean["decision_type"] == dtype]
    m1 = sub[sub["t_day"] == -1]["spx_iv_norm"].mean()
    p1 = sub[sub["t_day"] ==  1]["spx_iv_norm"].mean()
    c  = (p1 - m1) / m1 * 100 if m1 else np.nan
    n  = sub["fomc_date"].nunique()
    print(f"  {dtype:4s} (n={n:2d}): T-1={m1:.1f}, T+1={p1:.1f}, crush={c:+.1f}%")

print("\n=== IV crush by comm_surprise (Hold meetings only) ===")
for cs in ["Hawkish", "Neutral", "Dovish"]:
    sub = holds[holds["comm_surprise"] == cs]
    m1 = sub[sub["t_day"] == -1]["spx_iv_norm"].mean()
    p1 = sub[sub["t_day"] ==  1]["spx_iv_norm"].mean()
    c  = (p1 - m1) / m1 * 100 if m1 else np.nan
    n  = sub["fomc_date"].nunique()
    print(f"  {cs:8s} (n={n:2d}): T-1={m1:.1f}, T+1={p1:.1f}, crush={c:+.1f}%")
