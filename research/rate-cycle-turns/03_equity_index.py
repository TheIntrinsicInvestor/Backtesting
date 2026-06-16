"""
03_equity_index.py
------------------
Pull S&P 500 and CRSP value-weighted market daily returns from CRSP.
Uses crsp.dsi (daily stock index table):
  sprtrn : S&P 500 composite total return (dividends reinvested)
  vwretd : CRSP value-weighted market total return (broader than SPX)
  spindx : S&P 500 index level (price-only, not total-return)

Output: data/equity.parquet
Columns: date, sprtrn, vwretd, spx_level (cumulative total-return index, base 100)
"""
import os, builtins, getpass
import pandas as pd
import wrds
from pathlib import Path

DATA  = Path("data")
DATA.mkdir(exist_ok=True)
CACHE = DATA / "equity.parquet"
START, END = "1994-01-01", "2025-12-31"

if CACHE.exists():
    df = pd.read_parquet(CACHE)
    print(f"Cache hit — {len(df):,} rows, "
          f"{df['date'].min().date()} to {df['date'].max().date()}")
    raise SystemExit(0)

# WRDS non-interactive auth
_u = os.environ.get("WRDS_USERNAME", "hoovyalert")
_p = os.environ.get("PGPASSWORD", "")
def _ai(p=""):
    if "username" in p.lower(): v = _u
    elif "y/n" in p.lower():    v = "n"
    else:                       v = ""
    print(p + v); return v
builtins.input = _ai
getpass.getpass = lambda p="": _p

print("Connecting to WRDS...")
db = wrds.Connection(wrds_username=_u)

q = """
    SELECT date, sprtrn, vwretd, spindx
    FROM crsp.dsi
    WHERE date BETWEEN %(start)s AND %(end)s
    ORDER BY date
"""
print("Querying crsp.dsi (sprtrn + vwretd + spindx)...")
raw = db.raw_sql(q, params={"start": START, "end": END}, date_cols=["date"])
db.close()

print(f"Raw query: {len(raw):,} rows, "
      f"{raw['date'].min().date()} to {raw['date'].max().date()}")

raw = raw.sort_values("date").reset_index(drop=True)
raw["sprtrn"] = pd.to_numeric(raw["sprtrn"], errors="coerce")
raw["vwretd"] = pd.to_numeric(raw["vwretd"], errors="coerce")

nulls = raw["sprtrn"].isna().sum()
if nulls > 0:
    print(f"WARNING: {nulls} null sprtrn rows")

# Cumulative index level rebased to 100 at first trading day
raw["spx_level"] = (1 + raw["sprtrn"].fillna(0)).cumprod() * 100

total_return = raw["spx_level"].iloc[-1] / 100
years = (raw["date"].iloc[-1] - raw["date"].iloc[0]).days / 365.25
cagr  = (total_return ** (1 / years) - 1) * 100
print(f"SPX 1994-2025 cumulative: {total_return:.1f}x  |  CAGR: {cagr:.1f}%")

raw.to_parquet(CACHE, index=False)
print(f"Saved {len(raw):,} rows to {CACHE}")
print("Done.")
