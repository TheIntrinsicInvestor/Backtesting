"""
06_event_returns.py  —  Per-event market-adjusted returns vs SPY
Pulls SPY (permno 84398) if not cached; reuses mktcap_by_year price panel.
car_reaction  = stock(T-1 -> T+1)  - SPY(T-1 -> T+1)
car_drift_60  = stock(T+1 -> T+60) - SPY(T+1 -> T+60)
T = first trading day on or after anndats.
Returns are price-only (no dividends); disclose in methodology.
Output: data/spy_prices.parquet, data/event_returns.parquet
"""

import os, builtins, getpass
import wrds
import pandas as pd
import numpy as np
from pathlib import Path

_u = os.environ.get("WRDS_USERNAME", "hoovyalert")
_p = os.environ.get("PGPASSWORD", "")
def _ai(p=""):
    if "username" in p.lower(): v = _u
    elif "y/n" in p.lower(): v = "n"
    else: v = ""
    print(p + v); return v
builtins.input = _ai
getpass.getpass = lambda p="": _p

OUT       = Path("data/event_returns.parquet")
SPY_CACHE = Path("data/spy_prices.parquet")
PRICE_DIR = Path("data/mktcap_by_year")

if OUT.exists():
    df = pd.read_parquet(OUT)
    print(f"Cache hit — {len(df):,} rows  censored: {df['censored_drift'].sum()}")
    for cls in ["genuine_beat", "manufactured_beat", "miss"]:
        sub  = df[df["classification"] == cls]
        nd   = (~sub["censored_drift"]).sum()
        r    = sub["car_reaction"].dropna()
        dr   = sub.loc[~sub["censored_drift"], "car_drift_60"].dropna()
        print(f"  {cls:25s}  reaction n={len(r):4d} median={r.median():+.3%}"
              f"  drift n={nd:4d} median={dr.median():+.3%}")
    raise SystemExit(0)

# ── 1. SPY prices ─────────────────────────────────────────────────────────────
if SPY_CACHE.exists():
    spy = pd.read_parquet(SPY_CACHE)
    print(f"SPY cache hit — {len(spy):,} rows  ({spy['date'].min()} to {spy['date'].max()})")
else:
    db = wrds.Connection(wrds_username=_u)
    print("Pulling SPY (permno 84398) from crsp.dsf_v2 ...")
    spy = db.raw_sql("""
        SELECT dlycaldt AS date, dlyprc AS prc
        FROM crsp.dsf_v2
        WHERE permno = 84398
          AND dlycaldt BETWEEN '2014-01-01' AND '2025-12-31'
          AND dlyprc IS NOT NULL
        ORDER BY dlycaldt
    """, date_cols=["date"])
    db.close()
    spy["prc"] = spy["prc"].abs()
    spy.to_parquet(SPY_CACHE, index=False)
    print(f"SPY saved — {len(spy):,} rows  ({spy['date'].min()} to {spy['date'].max()})")

spy = spy.sort_values("date").reset_index(drop=True)
spy_by_date = {pd.Timestamp(d): float(p) for d, p in zip(spy["date"], spy["prc"])}

# ── 2. Universe price panel ────────────────────────────────────────────────────
print("Loading mktcap_by_year price panels ...")
chunks = [pd.read_parquet(f) for f in sorted(PRICE_DIR.glob("prices_*.parquet"))]
prices = pd.concat(chunks, ignore_index=True)
prices["date"] = pd.to_datetime(prices["date"])
prices["prc"]  = prices["prc"].abs()
prices = prices.sort_values(["permno", "date"]).reset_index(drop=True)
print(f"Price panel: {len(prices):,} rows, {prices['permno'].nunique():,} permnos")

price_by_permno = {
    int(p): grp[["date", "prc"]].reset_index(drop=True)
    for p, grp in prices.groupby("permno")
}
del prices

# ── 3. Load included events ────────────────────────────────────────────────────
events = pd.read_parquet("data/walkdown_events.parquet")
events["anndats"] = pd.to_datetime(events["anndats"])
events = events[events["included"]].copy()
print(f"Included events: {len(events):,}")

# ── 4. Per-event returns ───────────────────────────────────────────────────────
def spy_prc(ts):
    return spy_by_date.get(pd.Timestamp(ts), np.nan)

records = []
skipped = 0

for _, row in events.iterrows():
    permno  = int(row["permno"])
    anndats = row["anndats"]
    df      = price_by_permno.get(permno)

    if df is None or len(df) < 4:
        skipped += 1
        continue

    # T = first trading day on or after anndats
    dates_np = df["date"].values
    hits = np.where(dates_np >= np.datetime64(anndats))[0]
    if len(hits) == 0 or hits[0] < 1:
        skipped += 1
        continue
    idx_T = int(hits[0])

    if idx_T + 1 >= len(df):
        skipped += 1
        continue

    # Prices at T-1 and T+1
    d_tm1 = pd.Timestamp(df["date"].iloc[idx_T - 1])
    d_tp1 = pd.Timestamp(df["date"].iloc[idx_T + 1])
    p_tm1 = float(df["prc"].iloc[idx_T - 1])
    p_tp1 = float(df["prc"].iloc[idx_T + 1])

    if pd.isna(p_tm1) or pd.isna(p_tp1) or p_tm1 <= 0:
        skipped += 1
        continue

    s_tm1 = spy_prc(d_tm1)
    s_tp1 = spy_prc(d_tp1)
    car_reaction = (
        np.nan if (np.isnan(s_tm1) or np.isnan(s_tp1) or s_tm1 <= 0)
        else (p_tp1 / p_tm1 - 1) - (s_tp1 / s_tm1 - 1)
    )

    # Drift: T+1 → T+60
    idx_T60      = idx_T + 60
    censored     = idx_T60 >= len(df)
    car_drift_60 = np.nan

    if not censored:
        d_t60 = pd.Timestamp(df["date"].iloc[idx_T60])
        p_t60 = float(df["prc"].iloc[idx_T60])
        s_t60 = spy_prc(d_t60)
        if np.isnan(p_t60) or np.isnan(s_t60) or p_tp1 <= 0 or s_tp1 <= 0:
            censored = True
        else:
            car_drift_60 = (p_t60 / p_tp1 - 1) - (s_t60 / s_tp1 - 1)

    records.append({
        "permno":         permno,
        "anndats":        anndats,
        "classification": row["classification"],
        "car_reaction":   car_reaction,
        "car_drift_60":   car_drift_60,
        "censored_drift": censored,
    })

result = pd.DataFrame(records)
result.to_parquet(OUT, index=False)

print(f"\nSaved {len(result):,} rows  |  skipped: {skipped}  |  censored drift: {result['censored_drift'].sum()}")
print("\ncar_reaction by cohort:")
for cls in ["genuine_beat", "manufactured_beat", "miss"]:
    s = result[result["classification"] == cls]["car_reaction"].dropna()
    print(f"  {cls:25s}  n={len(s):4d}  median={s.median():+.3%}  mean={s.mean():+.3%}")
print("\ncar_drift_60 by cohort (non-censored only):")
for cls in ["genuine_beat", "manufactured_beat", "miss"]:
    s = result[(result["classification"] == cls) & (~result["censored_drift"])]["car_drift_60"].dropna()
    print(f"  {cls:25s}  n={len(s):4d}  median={s.median():+.3%}  mean={s.mean():+.3%}")
