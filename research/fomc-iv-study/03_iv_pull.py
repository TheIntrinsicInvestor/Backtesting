"""
03_iv_pull.py
-------------
Pull 30-day ATM (delta=50) implied volatility for SPX and TLT from
OptionMetrics vsurfd{year} tables. Covers 2017-2024 (2017 included
for T-20 trading day buffer before the first Jan 2018 FOMC meeting).

Secids (from 02_secid_mapper.py):
  SPX : 108105
  TLT : 116070

Output: data/iv_raw.parquet
Columns: secid (int), date, impl_volatility, ticker
"""

import os
import wrds
import pandas as pd

os.makedirs("data", exist_ok=True)

CACHE = "data/iv_raw.parquet"

SECID_MAP = {
    "SPX": 108105,
    "TLT": 116070,
}
SECID_TO_TICKER = {v: k for k, v in SECID_MAP.items()}
SECIDS_SQL = ", ".join(str(s) for s in SECID_MAP.values())

YEARS = list(range(2017, 2025))  # 2017-2024 inclusive

if os.path.exists(CACHE):
    print(f"Cache found at {CACHE} — skipping WRDS query.")
    df = pd.read_parquet(CACHE)
    print(f"Loaded {len(df):,} rows. Date range: {df['date'].min().date()} to {df['date'].max().date()}")
else:
    print("No cache — querying WRDS.")
    db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))

    chunks = []
    for year in YEARS:
        table = f"optionm_all.vsurfd{year}"
        query = f"""
            SELECT secid, date, impl_volatility
            FROM {table}
            WHERE secid IN ({SECIDS_SQL})
              AND days = 30
              AND delta = 50
        """
        print(f"  Querying {table}...", end=" ", flush=True)
        chunk = db.raw_sql(query)
        print(f"{len(chunk):,} rows")
        chunks.append(chunk)

    db.close()

    df = pd.concat(chunks, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["secid"] = df["secid"].astype(int)
    df["ticker"] = df["secid"].map(SECID_TO_TICKER)
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

    df.to_parquet(CACHE, index=False)
    print(f"\nSaved {len(df):,} rows to {CACHE}")

print("\n=== Row counts per ticker ===")
print(df.groupby("ticker")["date"].agg(["count", "min", "max"]).rename(
    columns={"count": "rows", "min": "first_date", "max": "last_date"}
))

print("\n=== Null impl_volatility check ===")
nulls = df[df["impl_volatility"].isna()]
if nulls.empty:
    print("No nulls.")
else:
    print(f"WARNING: {len(nulls)} null IV rows:")
    print(nulls.groupby("ticker").size())

print("\n=== Sample rows ===")
for ticker in ["SPX", "TLT"]:
    sample = df[df["ticker"] == ticker].head(3)
    print(f"\n{ticker}:")
    print(sample.to_string(index=False))
