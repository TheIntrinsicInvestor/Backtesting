"""
04_vix_pull.py
--------------
Pull CBOE VIX daily close from FRED (series: VIXCLS) via pandas_datareader.
No WRDS connection required.

Covers 2017-01-01 to 2025-12-31 (2017 for T-20 buffer).

Output: data/vix_raw.parquet
Columns: date, vix
"""

import os
import pandas as pd
import pandas_datareader.data as web
from datetime import date

os.makedirs("data", exist_ok=True)

CACHE = "data/vix_raw.parquet"

if os.path.exists(CACHE):
    print(f"Cache found at {CACHE} — skipping FRED query.")
    df = pd.read_parquet(CACHE)
else:
    print("Pulling VIXCLS from FRED...")
    raw = web.DataReader("VIXCLS", "fred", start="2017-01-01", end="2025-12-31")
    df = raw.reset_index().rename(columns={"DATE": "date", "VIXCLS": "vix"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["vix"]).sort_values("date").reset_index(drop=True)
    df.to_parquet(CACHE, index=False)
    print(f"Saved {len(df):,} rows to {CACHE}")

print(f"\nLoaded {len(df):,} rows.")
print(f"Date range: {df['date'].min().date()} to {df['date'].max().date()}")
print(f"VIX range:  {df['vix'].min():.1f} to {df['vix'].max():.1f}")
print(f"\nSample rows:")
print(df.head(5).to_string(index=False))
