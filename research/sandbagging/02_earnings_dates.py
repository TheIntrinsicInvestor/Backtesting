"""
02_earnings_dates.py  —  IBES annual earnings dates + EPS actuals + statsum consensus
Pulls annual actual EPS and statsum consensus for S&P 500 constituents, 2015-2025.
statsum consensus cols (fpi='1') kept as cross-check reference for script 04's PIT validation.
Output: data/earnings_dates.parquet
Columns: permno, ticker, cusip, anndats, pends, actual_eps, consensus_eps, n_analysts,
         surprise_pct
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

CACHE = Path("data/earnings_dates.parquet")
START = "2015-01-01"   # annual events 2015-2025
END   = "2025-12-31"

if CACHE.exists():
    df = pd.read_parquet(CACHE)
    print(f"Cache hit — {len(df):,} rows")
    print(f"Date range: {df['anndats'].min()} to {df['anndats'].max()}")
    print(f"Unique permnos: {df['permno'].nunique():,}")
    print(f"Events with consensus: {df['consensus_eps'].notna().sum():,}")
    raise SystemExit(0)

Path("data").mkdir(exist_ok=True)

# ── Load universe ─────────────────────────────────────────────────────────────
universe = pd.read_parquet("data/sp500_constituents.parquet")
cusip_to_permno = (
    universe.dropna(subset=["ncusip"])
    .sort_values("end_date", ascending=False, na_position="first")
    .drop_duplicates("ncusip")[["ncusip", "permno"]]
    .set_index("ncusip")["permno"]
    .to_dict()
)
print(f"Universe: {universe['permno'].nunique():,} permnos, "
      f"{len(cusip_to_permno):,} unique CUSIPs")

db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))

# ── 1. IBES actuals ───────────────────────────────────────────────────────────
print("Pulling IBES actuals (actu_epsus)...")
actuals = db.raw_sql(f"""
    SELECT ticker, cusip, anndats, pends, value AS actual_eps
    FROM ibes.actu_epsus
    WHERE pdicity = 'ANN'
      AND anndats BETWEEN '{START}' AND '{END}'
      AND anndats IS NOT NULL
      AND cusip IS NOT NULL
""")
print(f"  Raw actuals: {len(actuals):,} rows")

# ── 2. statsum consensus (kept for PIT cross-check in script 04) ──────────────
print("Pulling IBES consensus (statsum_epsus, fpi=6)...")
consensus = db.raw_sql(f"""
    SELECT ticker, fpedats, statpers, meanest AS consensus_eps, numest AS n_analysts
    FROM ibes.statsum_epsus
    WHERE fpi = '1'
      AND statpers BETWEEN '{START}' AND '{END}'
      AND meanest IS NOT NULL
""")
print(f"  Raw consensus rows: {len(consensus):,}")

db.close()

# ── 3. Match consensus to each actual ─────────────────────────────────────────
actuals["anndats"] = pd.to_datetime(actuals["anndats"])
actuals["pends"]   = pd.to_datetime(actuals["pends"])
consensus["statpers"] = pd.to_datetime(consensus["statpers"])
consensus["fpedats"]  = pd.to_datetime(consensus["fpedats"])

consensus_indexed = consensus.set_index(["ticker", "fpedats"])

rows = []
for (ticker, pends), grp in actuals.groupby(["ticker", "pends"]):
    anndats = grp["anndats"].iloc[0]
    actual  = grp["actual_eps"].iloc[0]
    cusip   = grp["cusip"].iloc[0]

    try:
        cons_sub = consensus_indexed.loc[(ticker, pends)]
        if isinstance(cons_sub, pd.Series):
            cons_sub = cons_sub.to_frame().T
        before_ann = cons_sub[cons_sub["statpers"] < anndats]
        if len(before_ann) > 0:
            latest = before_ann.sort_values("statpers").iloc[-1]
            con_mean   = latest["consensus_eps"]
            n_analysts = int(latest["n_analysts"])
        else:
            con_mean   = None
            n_analysts = None
    except KeyError:
        con_mean   = None
        n_analysts = None

    rows.append({
        "ticker"       : ticker,
        "cusip"        : cusip,
        "anndats"      : anndats,
        "pends"        : pends,
        "actual_eps"   : actual,
        "consensus_eps": con_mean,
        "n_analysts"   : n_analysts,
    })

df = pd.DataFrame(rows)
print(f"Matched {len(df):,} earnings events")

# ── 4. EPS surprise ───────────────────────────────────────────────────────────
def safe_surprise(row):
    if pd.isna(row["consensus_eps"]) or row["consensus_eps"] == 0:
        return None
    return (row["actual_eps"] - row["consensus_eps"]) / abs(row["consensus_eps"]) * 100

df["surprise_pct"] = df.apply(safe_surprise, axis=1)

# ── 5. Map IBES CUSIP -> permno ────────────────────────────────────────────────
df["cusip8"] = df["cusip"].str[:8].str.strip()
df["permno"] = df["cusip8"].map(cusip_to_permno)

matched = df["permno"].notna().sum()
print(f"CUSIP match: {matched:,} / {len(df):,} events matched to a permno")

df = df.dropna(subset=["permno"]).copy()
df["permno"] = df["permno"].astype(int)

df = df.sort_values(["permno", "anndats", "n_analysts"], ascending=[True, True, False])
df = df.drop_duplicates(subset=["permno", "anndats"])
df = df.reset_index(drop=True)

df.to_parquet(CACHE, index=False)

print(f"\nSaved -> {CACHE}  ({len(df):,} rows)")
print(f"  Unique permnos  : {df['permno'].nunique():,}")
print(f"  Date range      : {df['anndats'].min().date()} to {df['anndats'].max().date()}")
print(f"  With consensus  : {df['consensus_eps'].notna().sum():,} ({df['consensus_eps'].notna().mean():.0%})")
print(f"  With surprise   : {df['surprise_pct'].notna().sum():,}")
print(f"\nSample:")
print(df.head(10).to_string())
