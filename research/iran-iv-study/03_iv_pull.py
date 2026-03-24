"""
03_iv_pull.py
-------------
Pull 30-day constant maturity ATM (delta=50) implied volatility from
OptionMetrics vsurfd{year} tables for XLE, USO, XOM, CVX.

Covers years 2003–2025 (WRDS data cuts off 2025-08-29; event 15 on
2026-02-28 is entirely absent from OptionMetrics and will be flagged
as unavailable in all downstream analysis).

Output: data/iv_raw.parquet
Columns: secid, date, impl_volatility, ticker
"""

import os
import wrds
import pandas as pd

os.makedirs("data", exist_ok=True)

CACHE = "data/iv_raw.parquet"

SECID_MAP = {
    "XLE": 110011,
    "USO": 126681,
    "XOM": 104533,
    "CVX": 102968,
}

SECID_TO_TICKER = {v: k for k, v in SECID_MAP.items()}
SECIDS = list(SECID_MAP.values())
SECIDS_SQL = ", ".join(str(s) for s in SECIDS)

# Years needed: T-20 before earliest event (2003-03-20) is within 2003.
# Latest event with data is event 14 (2025-06-24); T+30 ≈ 2025-08-07 — within 2025.
YEARS = list(range(2003, 2026))  # 2003–2025 inclusive

if os.path.exists(CACHE):
    print(f"Cache found at {CACHE} — skipping WRDS query.")
    df = pd.read_parquet(CACHE)
    print(f"Loaded {len(df):,} rows. Date range: {df['date'].min()} to {df['date'].max()}")
else:
    print("No cache found — querying WRDS.")
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
for ticker in ["XLE", "USO", "XOM", "CVX"]:
    sample = df[df["ticker"] == ticker].head(3)
    print(f"\n{ticker}:")
    print(sample.to_string(index=False))
