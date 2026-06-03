"""
03_detail_pull.py  —  Pull individual analyst EPS estimates from ibes.det_epsus
Pulls the point-in-time detail estimates needed to reconstruct the consensus walk-down curve.
Output: data/det_epsus_raw.parquet
Columns: ticker, estimator, analys, fpi, fpedats, value, anndats, actdats, revdats, pdf
Annual fpi='1' (current fiscal year). Walk-down window T-270..T-2.
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

CACHE = Path("data/det_epsus_raw.parquet")
BATCH_SIZE = 150   # tickers per SQL query

if CACHE.exists():
    df = pd.read_parquet(CACHE)
    print(f"Cache hit — {len(df):,} rows")
    print(f"Tickers: {df['ticker'].nunique():,}  |  fpedats range: {df['fpedats'].min()} to {df['fpedats'].max()}")
    raise SystemExit(0)

Path("data").mkdir(exist_ok=True)

# ── Load event universe ───────────────────────────────────────────────────────
earnings = pd.read_parquet("data/earnings_dates.parquet")
earnings["anndats"] = pd.to_datetime(earnings["anndats"])
earnings["pends"]   = pd.to_datetime(earnings["pends"])

# Union of all IBES tickers (post-fallback) with their fiscal period ends
tickers_all = sorted(earnings["ticker"].dropna().unique().tolist())
print(f"Events: {len(earnings):,}  |  Unique IBES tickers: {len(tickers_all):,}")

# Build (ticker, fpedats) pairs that appear in our events, keyed by year
# We pull det rows where fpedats falls in each year (2014-2025)
# Using the year of pends as the chunk key
earnings["fpedats_year"] = earnings["pends"].dt.year
years = sorted(earnings["fpedats_year"].dropna().unique().astype(int).tolist())
print(f"Fiscal period years to pull: {years}")

# fpedats -> (ticker, pends) lookup for fast in-Python filtering after pull
ticker_pends = (
    earnings[["ticker", "pends"]]
    .drop_duplicates()
    .groupby("ticker")["pends"]
    .apply(set)
    .to_dict()
)

db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))

all_chunks = []

for year in years:
    year_tickers = sorted(
        earnings.loc[earnings["fpedats_year"] == year, "ticker"].dropna().unique().tolist()
    )
    if not year_tickers:
        continue

    year_start = f"{year}-01-01"
    year_end   = f"{year}-12-31"

    # Chunk tickers to keep query size manageable
    ticker_batches = [
        year_tickers[i : i + BATCH_SIZE]
        for i in range(0, len(year_tickers), BATCH_SIZE)
    ]
    print(f"\nYear {year}: {len(year_tickers)} tickers, {len(ticker_batches)} batches")

    year_chunks = []
    for b_idx, batch in enumerate(ticker_batches):
        tickers_sql = tuple(batch) if len(batch) > 1 else f"('{batch[0]}')"
        query = f"""
            SELECT ticker, estimator, analys, fpi, fpedats,
                   value, anndats, actdats, revdats, pdf
            FROM ibes.det_epsus
            WHERE fpi = '1'
              AND measure = 'EPS'
              AND ticker IN {tickers_sql}
              AND fpedats BETWEEN '{year_start}' AND '{year_end}'
        """
        print(f"  Batch {b_idx+1}/{len(ticker_batches)} ({len(batch)} tickers)...", end=" ", flush=True)
        chunk = db.raw_sql(query)
        print(f"{len(chunk):,} rows")
        if len(chunk) > 0:
            year_chunks.append(chunk)

    if year_chunks:
        year_df = pd.concat(year_chunks, ignore_index=True)
        all_chunks.append(year_df)
        print(f"  Year {year} total: {len(year_df):,} rows")

db.close()

if not all_chunks:
    print("No data pulled. Check ticker list and date range.")
    raise SystemExit(1)

# ── Concat and type-clean ─────────────────────────────────────────────────────
df = pd.concat(all_chunks, ignore_index=True)
print(f"\nTotal raw rows: {len(df):,}")

for col in ["anndats", "estdats", "actdats", "revdats", "fpedats"]:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")

df["value"] = pd.to_numeric(df["value"], errors="coerce")

# Drop rows with no estimate value or no issue date
n_before = len(df)
df = df.dropna(subset=["value", "anndats"]).copy()
print(f"After dropping null value/anndats: {len(df):,} rows ({n_before - len(df):,} dropped)")

df = df.reset_index(drop=True)
df.to_parquet(CACHE, index=False)

print(f"\nSaved -> {CACHE}  ({len(df):,} rows)")
print(f"  Tickers     : {df['ticker'].nunique():,}")
print(f"  Analysts    : {df['analys'].nunique():,}")
print(f"  fpedats range: {df['fpedats'].min().date()} to {df['fpedats'].max().date()}")
print(f"  anndats range: {df['anndats'].min().date()} to {df['anndats'].max().date()}")
print(f"\nRows per year (by fpedats):")
print(df.groupby(df["fpedats"].dt.year).size().to_string())
