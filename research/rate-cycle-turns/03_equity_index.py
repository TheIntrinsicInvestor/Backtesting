"""
03_equity_index.py (CRSP v2 upgrade)
--------------------------------------
Hybrid equity index:
  1994-01-01 to 2024-12-31: official crsp.dsi (CRSP-computed sprtrn, vwretd)
  2025-01-01 to 2025-12-31: reconstructed from crsp.dsf_v2
      sprtrn = market-cap-weighted S&P 500 return  (msp500list_v2 membership)
      vwretd = market-cap-weighted US common stocks (shrcd IN (10, 11) from stocknames_v2)

Output: data/equity.parquet
Columns: date, sprtrn, vwretd, spx_level
"""
import os, builtins, getpass
import pandas as pd
import wrds
from pathlib import Path

DATA  = Path("data")
DATA.mkdir(exist_ok=True)
CACHE = DATA / "equity.parquet"

LEG_START, LEG_END = "1994-01-01", "2024-12-31"
V2_START,  V2_END  = "2025-01-01", "2025-12-31"

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

# ── Phase 1: legacy crsp.dsi, 1994-2024 ──────────────────────────────────────
print(f"Querying crsp.dsi ({LEG_START} to {LEG_END})...")
q_leg = """
    SELECT date, sprtrn, vwretd
    FROM crsp.dsi
    WHERE date BETWEEN %(start)s AND %(end)s
    ORDER BY date
"""
legacy = db.raw_sql(q_leg, params={"start": LEG_START, "end": LEG_END}, date_cols=["date"])
print(f"  crsp.dsi: {len(legacy):,} rows  "
      f"({legacy['date'].min().date()} to {legacy['date'].max().date()})")

# ── Phase 2: sprtrn for 2025 from dsf_v2 + msp500list_v2 ─────────────────────
# Market-cap weight = ABS(dlyprc) * shrout; the 1000-unit scale cancels in ratio.
# ABS(dlyprc) because CRSP encodes bid/ask midpoints as negative prices.
print(f"Querying dsf_v2 + msp500list_v2 for sprtrn ({V2_START} to {V2_END})...")
q_spx = """
    SELECT
        f.dlycaldt AS date,
        SUM(f.dlyret * ABS(f.dlyprc) * f.shrout)
            / NULLIF(SUM(ABS(f.dlyprc) * f.shrout), 0) AS sprtrn
    FROM crsp.dsf_v2 f
    JOIN crsp.msp500list_v2 m
        ON f.permno = m.permno
        AND f.dlycaldt BETWEEN m.mbrstartdt
            AND COALESCE(m.mbrenddt, '2099-12-31'::date)
    WHERE f.dlycaldt BETWEEN %(start)s AND %(end)s
        AND f.dlyret  IS NOT NULL
        AND f.dlyprc  IS NOT NULL
        AND f.shrout  > 0
    GROUP BY f.dlycaldt
    ORDER BY f.dlycaldt
"""
v2_spx = db.raw_sql(q_spx, params={"start": V2_START, "end": V2_END}, date_cols=["date"])
print(f"  sprtrn 2025: {len(v2_spx):,} trading days  "
      f"({v2_spx['date'].min().date() if len(v2_spx) else 'none'} to "
      f"{v2_spx['date'].max().date() if len(v2_spx) else 'none'})")

# ── Phase 3: vwretd for 2025 — all US common stocks from dsf_v2 ───────────────
# stocknames_v2 replaces shrcd with securitysubtype + usincflg:
#   securitysubtype='COM'  ordinary common shares (was shrcd 10/11)
#   usincflg='Y'           US-incorporated issuer
# DISTINCT permno subquery avoids date-range join complexity on stocknames_v2.
print(f"Querying dsf_v2 for vwretd (US common stocks, {V2_START} to {V2_END})...")
q_vw = """
    SELECT
        f.dlycaldt AS date,
        SUM(f.dlyret * ABS(f.dlyprc) * f.shrout)
            / NULLIF(SUM(ABS(f.dlyprc) * f.shrout), 0) AS vwretd
    FROM crsp.dsf_v2 f
    JOIN (
        SELECT DISTINCT permno
        FROM crsp.stocknames_v2
        WHERE securitysubtype = 'COM'
          AND usincflg = 'Y'
    ) s ON f.permno = s.permno
    WHERE f.dlycaldt BETWEEN %(start)s AND %(end)s
        AND f.dlyret  IS NOT NULL
        AND f.dlyprc  IS NOT NULL
        AND f.shrout  > 0
    GROUP BY f.dlycaldt
    ORDER BY f.dlycaldt
"""
v2_vw = db.raw_sql(q_vw, params={"start": V2_START, "end": V2_END}, date_cols=["date"])
print(f"  vwretd 2025: {len(v2_vw):,} trading days")

db.close()

# ── Combine and concatenate ────────────────────────────────────────────────────
v2_ext = v2_spx.merge(v2_vw, on="date", how="outer").sort_values("date").reset_index(drop=True)

legacy["sprtrn"] = pd.to_numeric(legacy["sprtrn"], errors="coerce")
legacy["vwretd"] = pd.to_numeric(legacy["vwretd"], errors="coerce")
v2_ext["sprtrn"] = pd.to_numeric(v2_ext["sprtrn"], errors="coerce")
v2_ext["vwretd"] = pd.to_numeric(v2_ext["vwretd"], errors="coerce")

raw = pd.concat([legacy[["date", "sprtrn", "vwretd"]],
                 v2_ext[["date", "sprtrn", "vwretd"]]], ignore_index=True)
raw = raw.drop_duplicates("date").sort_values("date").reset_index(drop=True)

nulls = raw["sprtrn"].isna().sum()
if nulls > 0:
    print(f"WARNING: {nulls} null sprtrn rows")

print(f"Combined: {len(raw):,} rows  "
      f"({raw['date'].min().date()} to {raw['date'].max().date()})")
print(f"  Legacy rows (crsp.dsi):  {len(legacy):,}")
print(f"  Extension rows (dsf_v2): {len(v2_ext):,}")

raw["spx_level"] = (1 + raw["sprtrn"].fillna(0)).cumprod() * 100

total = raw["spx_level"].iloc[-1] / 100
years = (raw["date"].iloc[-1] - raw["date"].iloc[0]).days / 365.25
cagr  = (total ** (1 / years) - 1) * 100
print(f"SPX 1994-2025 cumulative: {total:.1f}x  |  CAGR: {cagr:.1f}%")

raw.to_parquet(CACHE, index=False)
print(f"Saved {len(raw):,} rows to {CACHE}")
print("Done.")
