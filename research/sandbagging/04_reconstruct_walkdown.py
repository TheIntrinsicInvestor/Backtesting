"""
04_reconstruct_walkdown.py  —  PIT consensus reconstruction + walk-down classification
Reads det_epsus_raw.parquet and earnings_dates.parquet; builds the daily consensus curve
for each event over the T-90..T-2 window, then classifies each event.

Outputs:
  data/walkdown_curve.parquet   — long: permno, ticker, anndats, pends, offset, consensus_eps, n_analysts
  data/walkdown_events.parquet  — wide: one row per event with orig/final snap + classification
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path

STALE_DAYS   = 365   # annual estimates remain active for up to a year
ORIG_WINDOW  = (-280, -260)  # offsets acceptable as the T-270 "original" consensus
FINAL_WINDOW = (-7,   -2)    # offsets acceptable as the T-2 "final" consensus
ANALYST_FLOOR = 3            # min active analysts (annual events skew smaller analyst pools early)
SMALL_BASE    = 0.10         # min |orig_consensus| in dollars (higher bar for annual EPS)

CURVE_CACHE  = Path("data/walkdown_curve.parquet")
EVENTS_CACHE = Path("data/walkdown_events.parquet")

if CURVE_CACHE.exists() and EVENTS_CACHE.exists():
    curve  = pd.read_parquet(CURVE_CACHE)
    events = pd.read_parquet(EVENTS_CACHE)
    print(f"Cache hit — curve: {len(curve):,} rows, events: {len(events):,} rows")
    inc = events["included"].sum()
    print(f"Included events: {inc:,} / {len(events):,}")
    print(events["classification"].value_counts().to_string())
    raise SystemExit(0)

Path("data").mkdir(exist_ok=True)

# ── Load inputs ───────────────────────────────────────────────────────────────
print("Loading earnings_dates...")
earnings = pd.read_parquet("data/earnings_dates.parquet")
earnings["anndats"] = pd.to_datetime(earnings["anndats"])
earnings["pends"]   = pd.to_datetime(earnings["pends"])
print(f"  {len(earnings):,} events, {earnings['permno'].nunique():,} permnos")

print("Loading det_epsus_raw...")
det = pd.read_parquet("data/det_epsus_raw.parquet")
det["anndats"]  = pd.to_datetime(det["anndats"])
det["fpedats"]  = pd.to_datetime(det["fpedats"])
det["revdats"]  = pd.to_datetime(det["revdats"])
print(f"  {len(det):,} detail rows, {det['ticker'].nunique():,} tickers")

# ── Merge det to events on ticker + fpedats==pends ────────────────────────────
# Build a (ticker, fpedats) -> (permno, anndats) lookup from earnings
print("\nJoining det rows to events...")
event_key = (
    earnings[["ticker", "pends", "permno", "anndats", "actual_eps"]]
    .rename(columns={"pends": "fpedats", "anndats": "event_anndats"})
    .drop_duplicates(subset=["ticker", "fpedats"])
)

det_merged = det.merge(event_key, on=["ticker", "fpedats"], how="inner")
print(f"  Det rows matched to events: {len(det_merged):,} "
      f"({len(det_merged)/len(det)*100:.1f}% of raw det)")
print(f"  Events with at least one det row: {det_merged.groupby(['permno','event_anndats']).ngroups:,}")

# ── PIT consensus reconstruction ──────────────────────────────────────────────
# On each offset day D (T-90..T-2), an analyst's estimate is active iff:
#   1. issued on/before D (anndats <= D)
#   2. it is the most recent estimate for (ticker, fpedats, estimator, analys) as of D
#   3. (D - anndats) <= STALE_DAYS
#
# Vectorized approach:
#   a. For each (event, estimator, analys), sort by anndats → forward-fill onto daily grid
#   b. Mask stale rows, compute mean per offset

OFFSETS     = np.arange(-270, -1, dtype=np.int64)  # T-270 to T-2, 269 values
STALE_NS    = np.int64(STALE_DAYS * 86_400 * 1_000_000_000)  # nanoseconds
NS_PER_DAY  = np.int64(86_400 * 1_000_000_000)

print(f"\nBuilding offset grid ({len(OFFSETS)} offsets per event, T-270..T-2, vectorized)...")

# Keep only the most recent estimate per (event, estimator, analys) on each issue date
det_merged = (
    det_merged
    .sort_values(["permno", "event_anndats", "estimator", "analys", "anndats"])
    .drop_duplicates(subset=["permno", "event_anndats", "estimator", "analys", "anndats"],
                     keep="last")
)

curve_rows  = []
event_rows  = []

total_events = det_merged.groupby(["permno", "event_anndats"]).ngroups
processed    = 0

for (permno, event_ann), ev_det in det_merged.groupby(["permno", "event_anndats"]):
    processed += 1
    if processed % 1000 == 0:
        print(f"  {processed:,}/{total_events:,} events processed...")

    event_ann  = pd.Timestamp(event_ann)
    actual_eps = ev_det["actual_eps"].iloc[0]
    ticker     = ev_det["ticker"].iloc[0]
    fpedats    = ev_det["fpedats"].iloc[0]

    # as-of timestamps for all 89 offsets (int64 ns)
    event_ns  = np.int64(event_ann.value)
    as_of_ns  = event_ns + OFFSETS * NS_PER_DAY   # shape (89,)

    # Sort within event by (analyst, anndats) for searchsorted
    ev_det = ev_det.sort_values(["estimator", "analys", "anndats"])

    # Factorize analyst pairs -> integer IDs
    analyst_keys = ev_det["estimator"].astype(str) + "|" + ev_det["analys"].astype(str)
    analyst_ids, _ = pd.factorize(analyst_keys.values)
    anndats_ns     = ev_det["anndats"].values.astype(np.int64)
    values_arr     = ev_det["value"].values.astype(np.float64)

    n_unique = int(analyst_ids.max()) + 1
    n_off    = len(OFFSETS)

    # Accumulators for each offset
    total_value = np.zeros(n_off, dtype=np.float64)
    total_count = np.zeros(n_off, dtype=np.int32)

    for a_id in range(n_unique):
        mask    = analyst_ids == a_id
        a_dates = anndats_ns[mask]   # sorted ascending (guaranteed by sort above)
        a_vals  = values_arr[mask]

        # For each offset: index of last estimate issued on/before as_of
        idx = np.searchsorted(a_dates, as_of_ns, side="right") - 1  # (89,)

        valid     = idx >= 0
        safe_idx  = np.where(valid, idx, 0)
        not_stale = np.where(valid, as_of_ns - a_dates[safe_idx] <= STALE_NS, False)
        active    = valid & not_stale                                 # (89,) bool

        total_value += np.where(active, a_vals[safe_idx], 0.0)
        total_count += active.astype(np.int32)

    # consensus per offset (nan where no active analysts)
    has_data       = total_count > 0
    consensus_arr  = np.where(has_data, total_value / total_count, np.nan)
    n_arr          = total_count

    if not has_data.any():
        continue

    # Build consensus_by_offset dict for snapping
    consensus_by_offset = {int(OFFSETS[i]): consensus_arr[i]
                           for i in range(n_off) if has_data[i]}
    n_by_offset         = {int(OFFSETS[i]): int(n_arr[i])
                           for i in range(n_off) if has_data[i]}

    # Append curve rows
    for i in range(n_off):
        if has_data[i]:
            curve_rows.append({
                "permno"        : permno,
                "ticker"        : ticker,
                "anndats"       : event_ann,
                "pends"         : fpedats,
                "offset"        : int(OFFSETS[i]),
                "consensus_eps" : consensus_arr[i],
                "n_analysts"    : int(n_arr[i]),
            })

    # Snap orig and final
    avail_offsets    = set(consensus_by_offset.keys())
    orig_candidates  = [o for o in avail_offsets if ORIG_WINDOW[0]  <= o <= ORIG_WINDOW[1]]
    final_candidates = [o for o in avail_offsets if FINAL_WINDOW[0] <= o <= FINAL_WINDOW[1]]

    if not orig_candidates or not final_candidates:
        continue

    orig_offset  = min(orig_candidates,  key=lambda o: abs(o - (-90)))
    final_offset = max(final_candidates)

    event_rows.append({
        "permno"           : permno,
        "ticker"           : ticker,
        "anndats"          : event_ann,
        "pends"            : fpedats,
        "actual_eps"       : actual_eps,
        "orig_consensus"   : consensus_by_offset[orig_offset],
        "orig_offset"      : orig_offset,
        "orig_n_analysts"  : n_by_offset[orig_offset],
        "final_consensus"  : consensus_by_offset[final_offset],
        "final_offset"     : final_offset,
        "final_n_analysts" : n_by_offset[final_offset],
    })

print(f"\nDone. {len(curve_rows):,} curve rows, {len(event_rows):,} events with orig+final")

# ── Build walkdown_events ─────────────────────────────────────────────────────
ev = pd.DataFrame(event_rows)

# Merge in year/quarter, sector, mktcap
earnings_meta = earnings[["permno", "anndats", "pends"]].copy()
earnings_meta["year"]    = earnings_meta["anndats"].dt.year
earnings_meta["quarter"] = earnings_meta["anndats"].dt.quarter

universe = pd.read_parquet("data/sp500_constituents.parquet")
uni_dedup = (universe.sort_values("end_date", ascending=False, na_position="first")
             .drop_duplicates("permno")[["permno", "sector"]])
mktcap_df = pd.read_parquet("data/mktcap.parquet")

ev = (ev
      .merge(earnings_meta[["permno", "anndats", "year", "quarter"]], on=["permno", "anndats"], how="left")
      .merge(uni_dedup, on="permno", how="left")
      .merge(mktcap_df[["permno", "anndats", "mktcap_m"]], on=["permno", "anndats"], how="left"))

# ── Walk-down metrics ─────────────────────────────────────────────────────────
ev["walkdown_abs"] = ev["final_consensus"] - ev["orig_consensus"]   # negative = walked down
ev["walkdown_pct"] = np.where(
    ev["orig_consensus"].abs() >= SMALL_BASE,
    ev["walkdown_abs"] / ev["orig_consensus"].abs() * 100,
    np.nan,
)
ev["beat_vs_orig"]  = ev["actual_eps"] > ev["orig_consensus"]
ev["beat_vs_final"] = ev["actual_eps"] > ev["final_consensus"]

# ── Exclusion flags ───────────────────────────────────────────────────────────
sign_flip = np.sign(ev["orig_consensus"]) != np.sign(ev["final_consensus"])

ev["included"] = (
    (ev["orig_consensus"]  > 0) &
    (ev["final_consensus"] > 0) &
    (ev["actual_eps"]      > 0) &
    (~sign_flip) &
    (ev["orig_consensus"].abs()  >= SMALL_BASE) &
    (ev["orig_n_analysts"]  >= ANALYST_FLOOR) &
    (ev["final_n_analysts"] >= ANALYST_FLOOR)
)

# ── Classification ────────────────────────────────────────────────────────────
def classify(row):
    if not row["included"]:
        return "excluded"
    if row["actual_eps"] > row["orig_consensus"]:
        return "genuine_beat"
    if row["actual_eps"] > row["final_consensus"]:
        return "manufactured_beat"
    return "miss"

ev["classification"] = ev.apply(classify, axis=1)

# ── Exclusion summary ─────────────────────────────────────────────────────────
total = len(ev)
included = ev["included"].sum()
print(f"\nEvent counts:")
print(f"  Total events with orig+final : {total:,}")
print(f"  Included (all filters pass)  : {included:,}")
print(f"  Excluded                     : {total - included:,}")
print(f"\nExclusion reasons (non-exclusive):")
print(f"  orig_consensus <= 0          : {(ev['orig_consensus'] <= 0).sum():,}")
print(f"  final_consensus <= 0         : {(ev['final_consensus'] <= 0).sum():,}")
print(f"  actual_eps <= 0              : {(ev['actual_eps'] <= 0).sum():,}")
print(f"  sign flip orig->final        : {sign_flip.sum():,}")
print(f"  orig |consensus| < {SMALL_BASE}      : {(ev['orig_consensus'].abs() < SMALL_BASE).sum():,}")
print(f"  orig_n_analysts < {ANALYST_FLOOR}           : {(ev['orig_n_analysts'] < ANALYST_FLOOR).sum():,}")
print(f"  final_n_analysts < {ANALYST_FLOOR}          : {(ev['final_n_analysts'] < ANALYST_FLOOR).sum():,}")

print(f"\nClassification (included only):")
print(ev.loc[ev["included"], "classification"].value_counts().to_string())

inc = ev[ev["included"]]
beats = inc["classification"].isin(["genuine_beat", "manufactured_beat"]).sum()
mfg   = (inc["classification"] == "manufactured_beat").sum()
if beats > 0:
    print(f"\nManufactured beat rate (mfg / all beats): {mfg/beats*100:.1f}%")
    print(f"Manufactured beat rate (mfg / all incl) : {mfg/len(inc)*100:.1f}%")

print(f"\nWalk-down (included): median {inc['walkdown_pct'].median():.1f}%  "
      f"mean {inc['walkdown_pct'].mean():.1f}%")

# ── Validation: compare reconstructed consensus vs statsum ────────────────────
print("\n--- Statsum cross-check ---")
# earnings has consensus_eps (from statsum, most recent before anndats)
# Compare to final_consensus from PIT reconstruction
check = ev.merge(
    earnings[["permno", "anndats", "consensus_eps"]].rename(columns={"consensus_eps": "statsum_consensus"}),
    on=["permno", "anndats"], how="inner"
)
check = check.dropna(subset=["statsum_consensus", "final_consensus"])
diff = (check["final_consensus"] - check["statsum_consensus"]).abs()
print(f"  Events compared    : {len(check):,}")
print(f"  Median abs diff    : ${diff.median():.4f}")
print(f"  Mean abs diff      : ${diff.mean():.4f}")
print(f"  Within $0.05       : {(diff <= 0.05).mean():.0%}")
print(f"  Within $0.10       : {(diff <= 0.10).mean():.0%}")

# ── Save ──────────────────────────────────────────────────────────────────────
curve_df = pd.DataFrame(curve_rows)
curve_df.to_parquet(CURVE_CACHE, index=False)
ev.to_parquet(EVENTS_CACHE, index=False)

print(f"\nSaved -> {CURVE_CACHE}  ({len(curve_df):,} rows)")
print(f"Saved -> {EVENTS_CACHE}  ({len(ev):,} rows)")
