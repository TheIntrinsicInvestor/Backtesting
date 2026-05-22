"""
03_secid_mapper.py  —  Map CRSP permno -> OptionMetrics secid via 8-char CUSIP
Queries optionm_all.secnmd; takes the most recent effect_date entry per CUSIP.
Output: data/secid_map.parquet
Columns: permno, secid, cusip8, ticker_om, issuer
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

CACHE = Path("data/secid_map.parquet")

if CACHE.exists():
    df = pd.read_parquet(CACHE)
    print(f"Cache hit — {len(df):,} rows")
    print(df.head(10).to_string())
    raise SystemExit(0)

Path("data").mkdir(exist_ok=True)

# ── Load universe ─────────────────────────────────────────────────────────────
universe = pd.read_parquet("data/sp500_constituents.parquet")
ncusips = set(
    universe.dropna(subset=["ncusip"])["ncusip"]
    .str[:8]
    .str.strip()
    .unique()
)
print(f"Universe: {len(ncusips):,} unique 8-char CUSIPs to map")

# ── Pull OptionMetrics security names ────────────────────────────────────────
db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))

print("Querying optionm_all.secnmd...")
secnmd = db.raw_sql("""
    SELECT secid, ticker, issuer, cusip, effect_date
    FROM optionm_all.secnmd
    WHERE cusip IS NOT NULL
    ORDER BY cusip, effect_date DESC
""")
db.close()

print(f"  {len(secnmd):,} rows from secnmd")

# ── Match on 8-char CUSIP ─────────────────────────────────────────────────────
secnmd["cusip8"] = secnmd["cusip"].str[:8].str.strip()

# Keep most recent entry per cusip8
secnmd_dedup = (
    secnmd.sort_values("effect_date", ascending=False)
    .drop_duplicates("cusip8")[["secid", "ticker", "issuer", "cusip8"]]
    .rename(columns={"ticker": "ticker_om"})
)
secnmd_dedup["secid"] = secnmd_dedup["secid"].astype(int)

# Build permno -> cusip8 from universe (use most recent membership end date)
universe_clean = (
    universe.dropna(subset=["ncusip"])
    .assign(cusip8=lambda d: d["ncusip"].str[:8].str.strip())
    .sort_values("end_date", ascending=False, na_position="first")
    .drop_duplicates("permno")[["permno", "cusip8"]]
)

# Join permno -> cusip8 -> secid
result = (
    universe_clean
    .merge(secnmd_dedup, on="cusip8", how="left")
)

matched = result["secid"].notna().sum()
total   = len(result)
print(f"\nMatched {matched:,} / {total:,} permnos to an OM secid "
      f"({matched/total:.1%})")

result = result.dropna(subset=["secid"]).copy()
result["secid"] = result["secid"].astype(int)
result["permno"] = result["permno"].astype(int)

result.to_parquet(CACHE, index=False)
print(f"\nSaved -> {CACHE}  ({len(result):,} rows)")
print(f"\nSample mapping:")
print(result.head(15).to_string())

print(f"\nTotal secids for IV pull: {result['secid'].nunique():,}")

