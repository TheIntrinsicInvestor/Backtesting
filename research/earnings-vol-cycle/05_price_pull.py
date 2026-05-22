"""
05_price_pull.py  —  CRSP daily prices, returns, and market cap
Pulls year-by-year for all permnos in the universe, 2009-2024.
Output: data/prices.parquet
Columns: permno, date, prc, ret, shrout, mktcap_m (market cap $M)
"""

import os
import builtins
import wrds
import pandas as pd
import numpy as np
from pathlib import Path

_u = os.environ.get("WRDS_USERNAME", "hoovyalert")
def _ai(p=""):
    v = _u if "username" in p.lower() else ""
    print(p + v); return v
builtins.input = _ai

YEARS      = list(range(2009, 2026))
CACHE_DIR  = Path("data/prices_by_year")
FINAL_FILE = Path("data/prices.parquet")

Path("data").mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

if FINAL_FILE.exists():
    df = pd.read_parquet(FINAL_FILE)
    print(f"Cache hit — {len(df):,} rows")
    print(f"Date range: {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"Unique permnos: {df['permno'].nunique():,}")
    raise SystemExit(0)

# ── Load permno list ──────────────────────────────────────────────────────────
universe  = pd.read_parquet("data/sp500_constituents.parquet")
permnos   = universe["permno"].unique().tolist()
perm_sql  = ", ".join(str(int(p)) for p in permnos)
print(f"Pulling prices for {len(permnos):,} permnos across {len(YEARS)} years...")

db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))

chunks = []
for year in YEARS:
    year_cache = CACHE_DIR / f"dsf_{year}.parquet"

    if year_cache.exists():
        chunk = pd.read_parquet(year_cache)
        print(f"  {year}: cache hit — {len(chunk):,} rows")
    else:
        query = f"""
            SELECT permno, dlycaldt AS date, dlyprc AS prc, dlyret AS ret, shrout, dlycumfacshr AS cfacshr
            FROM crsp.dsf_v2
            WHERE permno IN ({perm_sql})
              AND dlycaldt BETWEEN '{year}-01-01' AND '{year}-12-31'
              AND dlyprc IS NOT NULL
        """
        print(f"  {year}: querying crsp.dsf_v2...", end=" ", flush=True)
        chunk = db.raw_sql(query, date_cols=["date"])
        chunk["permno"] = chunk["permno"].astype(int)
        chunk.to_parquet(year_cache, index=False)
        print(f"{len(chunk):,} rows saved")

    chunks.append(chunk)

db.close()

# ── Concat and compute market cap ─────────────────────────────────────────────
df = pd.concat(chunks, ignore_index=True)
df["date"]   = pd.to_datetime(df["date"])
df["prc"]    = df["prc"].abs()              # negative = bid-ask midpoint, take abs
df["ret"]    = pd.to_numeric(df["ret"], errors="coerce")
df["shrout"] = pd.to_numeric(df["shrout"], errors="coerce")  # shares in thousands

# Market cap in $M: price × shares_thousands / 1000
df["mktcap_m"] = df["prc"] * df["shrout"] / 1_000

df = df.drop(columns=["cfacshr"])
df = df.sort_values(["permno", "date"]).reset_index(drop=True)
df.to_parquet(FINAL_FILE, index=False)

print(f"\nSaved -> {FINAL_FILE}  ({len(df):,} rows)")
print(f"Date range     : {df['date'].min().date()} to {df['date'].max().date()}")
print(f"Unique permnos : {df['permno'].nunique():,}")
print(f"Null ret rows  : {df['ret'].isna().sum():,}")

print("\n=== Market cap distribution (all rows) ===")
print(df["mktcap_m"].describe().to_string())

# Trading calendar (for use in 06_analysis.py)
trading_days = sorted(df["date"].unique())
td_df = pd.DataFrame({"date": trading_days})
td_df.to_parquet("data/trading_calendar.parquet", index=False)
print(f"\nSaved trading calendar: {len(trading_days):,} days")

