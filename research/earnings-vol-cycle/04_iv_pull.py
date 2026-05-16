"""
04_iv_pull.py  —  Pull 30-day ATM (delta=50) IV from OptionMetrics vsurfd
Pulls year-by-year for all secids in the universe, 2009-2024.
Caches each year separately; final merge produces iv_panel.parquet.
Output: data/iv_panel.parquet
Columns: secid, date, impl_volatility
"""

import os
import wrds
import pandas as pd
from pathlib import Path

YEARS      = list(range(2009, 2025))
CACHE_DIR  = Path("data/iv_by_year")
FINAL_FILE = Path("data/iv_panel.parquet")

Path("data").mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

if FINAL_FILE.exists():
    df = pd.read_parquet(FINAL_FILE)
    print(f"Cache hit — {len(df):,} rows")
    print(f"Date range: {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"Unique secids: {df['secid'].nunique():,}")
    raise SystemExit(0)

# ── Load secid list ───────────────────────────────────────────────────────────
secid_map = pd.read_parquet("data/secid_map.parquet")
secids    = secid_map["secid"].unique().tolist()
secids_sql = ", ".join(str(int(s)) for s in secids)
print(f"Pulling IV for {len(secids):,} secids across {len(YEARS)} years...")

db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))

chunks = []
for year in YEARS:
    year_cache = CACHE_DIR / f"vsurfd_{year}.parquet"

    if year_cache.exists():
        chunk = pd.read_parquet(year_cache)
        print(f"  {year}: cache hit — {len(chunk):,} rows")
    else:
        table = f"optionm_all.vsurfd{year}"
        query = f"""
            SELECT secid, date, impl_volatility
            FROM {table}
            WHERE secid IN ({secids_sql})
              AND days  = 30
              AND delta = 50
              AND cp_flag = 'C'
              AND impl_volatility IS NOT NULL
        """
        print(f"  {year}: querying {table}...", end=" ", flush=True)
        chunk = db.raw_sql(query)
        chunk["date"]  = pd.to_datetime(chunk["date"])
        chunk["secid"] = chunk["secid"].astype(int)
        chunk.to_parquet(year_cache, index=False)
        print(f"{len(chunk):,} rows saved")

    chunks.append(chunk)

db.close()

# ── Concat and save ───────────────────────────────────────────────────────────
df = pd.concat(chunks, ignore_index=True)
df = df.sort_values(["secid", "date"]).reset_index(drop=True)
df.to_parquet(FINAL_FILE, index=False)

print(f"\nSaved -> {FINAL_FILE}  ({len(df):,} rows)")
print(f"Date range : {df['date'].min().date()} to {df['date'].max().date()}")
print(f"Unique secids : {df['secid'].nunique():,}")
print(f"Null IV rows  : {df['impl_volatility'].isna().sum():,}")

# Quick coverage check per year
df["year"] = df["date"].dt.year
print("\n=== Rows per year ===")
print(df.groupby("year").size().to_string())

