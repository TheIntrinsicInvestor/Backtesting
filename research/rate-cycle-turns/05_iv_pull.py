"""
05_iv_pull.py
-------------
Pull SPX 30-day ATM (delta=50) implied volatility from OptionMetrics
volatility surface tables. Covers 1996-2025 (OM data begins 1996).

  Table  : optionm_all.vsurfd{year}
  Secid  : 108105 (SPX)
  Filter : days=30, delta=50
  Cutoff : 2025-08-29 (confirmed WRDS cutoff as of May 2026)

Output: data/iv.parquet
Columns: date, impl_volatility
"""
import os, builtins, getpass
import pandas as pd
import wrds
from pathlib import Path

DATA  = Path("data")
DATA.mkdir(exist_ok=True)
CACHE = DATA / "iv.parquet"

SPX_SECID = 108105
YEARS     = list(range(1996, 2026))  # 1996-2025 inclusive

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

chunks = []
for year in YEARS:
    table = f"optionm_all.vsurfd{year}"
    q = f"""
        SELECT date, impl_volatility
        FROM {table}
        WHERE secid = {SPX_SECID}
          AND days  = 30
          AND delta = 50
        ORDER BY date
    """
    print(f"  {table} ...", end=" ", flush=True)
    try:
        chunk = db.raw_sql(q)
        print(f"{len(chunk):,} rows")
        chunks.append(chunk)
    except Exception as e:
        print(f"ERROR: {e}")

db.close()

if not chunks:
    raise RuntimeError("No data retrieved from OptionMetrics")

df = pd.concat(chunks, ignore_index=True)
df["date"]            = pd.to_datetime(df["date"])
df["impl_volatility"] = pd.to_numeric(df["impl_volatility"], errors="coerce")
df = df.dropna(subset=["impl_volatility"])

# De-duplicate: if call + put rows both exist, average them
dupes = df.groupby("date").size()
if (dupes > 1).any():
    print(f"De-duplicating {(dupes > 1).sum()} dates with multiple rows (averaging)...")
    df = df.groupby("date", as_index=False)["impl_volatility"].mean()

df = df.sort_values("date").reset_index(drop=True)

print(f"\nTotal: {len(df):,} rows, "
      f"{df['date'].min().date()} to {df['date'].max().date()}")
print(f"IV range: {df['impl_volatility'].min():.4f} to "
      f"{df['impl_volatility'].max():.4f}")
print(f"Mean IV: {df['impl_volatility'].mean():.4f} "
      f"(~{df['impl_volatility'].mean()*100:.1f}%)")

df.to_parquet(CACHE, index=False)
print(f"Saved {len(df):,} rows to {CACHE}")
print("Done.")
