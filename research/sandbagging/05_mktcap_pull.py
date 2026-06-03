"""
05_mktcap_pull.py  —  CRSP market cap snapshot per earnings event
Pulls one abs(prc)*shrout value per event near anndats (NOT a full daily panel).
Runs year-by-year to keep memory low; caches per-year slices.
Output: data/mktcap.parquet
Columns: permno, anndats, mktcap_m
"""

import os
import builtins
import wrds
import pandas as pd
from pathlib import Path

_u = os.environ.get("WRDS_USERNAME", "hoovyalert")
def _ai(p=""):
    v = _u if "username" in p.lower() else ""
    print(p + v); return v
builtins.input = _ai

CACHE      = Path("data/mktcap.parquet")
CACHE_DIR  = Path("data/mktcap_by_year")

if CACHE.exists():
    df = pd.read_parquet(CACHE)
    print(f"Cache hit — {len(df):,} rows")
    print(f"Events with mktcap: {df['mktcap_m'].notna().sum():,}")
    print(df["mktcap_m"].describe().to_string())
    raise SystemExit(0)

Path("data").mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

# ── Load events ───────────────────────────────────────────────────────────────
earnings = pd.read_parquet("data/earnings_dates.parquet")
earnings["anndats"] = pd.to_datetime(earnings["anndats"])
permnos  = earnings["permno"].unique().tolist()
perm_sql = ", ".join(str(int(p)) for p in permnos)
years    = sorted(earnings["anndats"].dt.year.unique().astype(int).tolist())
print(f"Events: {len(earnings):,}  |  Permnos: {len(permnos):,}  |  Years: {years}")

db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))

price_chunks = []
for year in years:
    year_cache = CACHE_DIR / f"prices_{year}.parquet"
    if year_cache.exists():
        chunk = pd.read_parquet(year_cache)
        print(f"  {year}: cache hit — {len(chunk):,} rows")
    else:
        query = f"""
            SELECT permno, dlycaldt AS date, dlyprc AS prc, shrout
            FROM crsp.dsf_v2
            WHERE permno IN ({perm_sql})
              AND dlycaldt BETWEEN '{year}-01-01' AND '{year}-12-31'
              AND dlyprc IS NOT NULL
              AND shrout IS NOT NULL
        """
        print(f"  {year}: querying...", end=" ", flush=True)
        chunk = db.raw_sql(query, date_cols=["date"])
        chunk["permno"] = chunk["permno"].astype(int)
        chunk.to_parquet(year_cache, index=False)
        print(f"{len(chunk):,} rows")
    price_chunks.append(chunk)

db.close()

# ── Build price panel and snap to each event ──────────────────────────────────
prices = pd.concat(price_chunks, ignore_index=True)
prices["date"]    = pd.to_datetime(prices["date"])
prices["prc"]     = prices["prc"].abs()
prices["shrout"]  = pd.to_numeric(prices["shrout"], errors="coerce")
prices["mktcap_m"] = prices["prc"] * prices["shrout"] / 1_000
prices = prices.sort_values(["permno", "date"]).reset_index(drop=True)
print(f"\nPrice panel: {len(prices):,} rows")

# For each event, find the latest price on or before anndats (within 5 trading days)
# merge_asof requires globally sorted keys; loop per permno to avoid cross-group issues
events = earnings[["permno", "anndats"]].drop_duplicates()
events = events.rename(columns={"anndats": "event_date"})

price_by_permno = {p: grp[["date", "mktcap_m"]].sort_values("date") for p, grp in prices.groupby("permno")}

snaps = []
for permno, ev_grp in events.groupby("permno"):
    pr = price_by_permno.get(permno)
    if pr is None or len(pr) == 0:
        continue
    merged = pd.merge_asof(
        ev_grp.sort_values("event_date"),
        pr,
        left_on="event_date",
        right_on="date",
        direction="backward",
        tolerance=pd.Timedelta("5 days"),
    )
    snaps.append(merged)

snap = pd.concat(snaps, ignore_index=True)
snap = snap.rename(columns={"event_date": "anndats"})
snap = snap[["permno", "anndats", "mktcap_m"]].dropna(subset=["mktcap_m"])

snap.to_parquet(CACHE, index=False)
print(f"\nSaved -> {CACHE}  ({len(snap):,} rows)")
print(f"  Events with mktcap : {snap['mktcap_m'].notna().sum():,} / {len(events):,}")
print(f"\nMarket cap distribution ($M):")
print(snap["mktcap_m"].describe().to_string())
