"""
01_universe.py  —  S&P 500 point-in-time constituents, 2010-2024
Output: data/sp500_constituents.parquet
Columns: permno, ticker, company, ncusip, siccd, gsector, sector, start_date, end_date
"""

import os
import wrds
import pandas as pd
from pathlib import Path

CACHE = Path("data/sp500_constituents.parquet")
START = "2010-01-01"
END   = "2024-12-31"

GICS_MAP = {
    10: "Energy",
    15: "Materials",
    20: "Industrials",
    25: "Consumer Discretionary",
    30: "Consumer Staples",
    35: "Healthcare",
    40: "Financials",
    45: "Technology",
    50: "Communication Services",
    55: "Utilities",
    60: "Real Estate",
}

if CACHE.exists():
    df = pd.read_parquet(CACHE)
    print(f"Cache hit — {len(df):,} rows")
    print(df["sector"].value_counts().to_string())
    raise SystemExit(0)

Path("data").mkdir(exist_ok=True)
db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))

# ── 1. S&P 500 membership windows ────────────────────────────────────────────
print("Pulling S&P 500 constituent list...")
sp500 = db.raw_sql(f"""
    SELECT permno, start, ending
    FROM crsp.msp500list
    WHERE start <= '{END}'
      AND (ending IS NULL OR ending >= '{START}')
""")
sp500.columns = ["permno", "start_date", "end_date"]
permnos = tuple(map(int, sp500["permno"].unique()))
print(f"  {len(permnos):,} unique permnos")

# ── 2. Latest name / ticker / CUSIP for each permno ──────────────────────────
print("Pulling name data from msenames...")
names = db.raw_sql(f"""
    SELECT DISTINCT ON (permno) permno, ticker, comnam, ncusip, siccd
    FROM crsp.msenames
    WHERE permno IN {permnos}
    ORDER BY permno, namedt DESC
""")
names = names.rename(columns={"comnam": "company"})

# ── 3. GICS sector via CCM link -> Compustat company table ────────────────────
print("Pulling GICS sectors via CCM...")
gics = db.raw_sql(f"""
    SELECT DISTINCT ON (l.lpermno) l.lpermno AS permno, c.gsector
    FROM crsp.ccmxpf_linktable l
    JOIN comp.company c ON l.gvkey = c.gvkey
    WHERE l.lpermno IN {permnos}
      AND l.linktype IN ('LU', 'LC', 'LS')
      AND l.linkprim IN ('P', 'C')
    ORDER BY l.lpermno, l.linkdt DESC
""")

db.close()

# ── 4. Merge and label ────────────────────────────────────────────────────────
df = (sp500
      .merge(names, on="permno", how="left")
      .merge(gics,  on="permno", how="left"))

df["gsector"] = pd.to_numeric(df["gsector"], errors="coerce")
df["sector"]  = df["gsector"].map(
    lambda x: GICS_MAP.get(int(x), "Unknown") if pd.notna(x) else "Unknown"
)

df.to_parquet(CACHE, index=False)
print(f"\nSaved -> {CACHE}  ({len(df):,} rows)")
print(df["sector"].value_counts().to_string())
print(f"\nSample:\n{df.head(10).to_string()}")

