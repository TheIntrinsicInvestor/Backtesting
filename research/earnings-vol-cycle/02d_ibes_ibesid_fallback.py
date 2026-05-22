"""
02d_ibes_ibesid_fallback.py  —  Pull IBES data using canonical IBES tickers (from ibes.id table)
For companies where the CRSP exchange ticker differs from the IBES internal ticker.

Targets:
  TELW  -> permno 92157  (TE Connectivity, exchange ticker TEL)
  HPLD  -> permno 13103  (Aptiv post-2017, exchange ticker APTV)
  DLPH  -> permno 13103  (Aptiv as Delphi Automotive, pre-2017-12-04 only)
  004W  -> permno 14714  (Arista Networks, exchange ticker ANET)
  SMIC  -> permno 91907  (Super Micro Computer, exchange ticker SMCI)
  053G  -> permno 25146  (Smurfit WestRock, exchange ticker SW)

Not recoverable:
  FOX   -> anndats NULL in IBES actu_epsus
  TFCF/TFCFA -> not in IBES
  BPYU  -> not in IBES
  QCP   -> 1-day S&P membership, skipped

Output: data/earnings_dates.parquet (updated in-place)
"""

import builtins, os
import wrds
import pandas as pd
from pathlib import Path

# Non-interactive WRDS auth
_u = os.environ.get("WRDS_USERNAME", "hoovyalert")
def _ai(p=""):
    v = _u if "username" in p.lower() else ""
    print(p + v)
    return v
builtins.input = _ai

EARNINGS_CACHE = Path("data/earnings_dates.parquet")
START = "2009-01-01"
END   = "2026-08-31"

# (ibes_ticker, permno, date_filter_end)
# date_filter_end: only keep anndats up to this date (None = no limit)
IBES_TARGETS = [
    ("TELW", 92157,  None),          # TE Connectivity
    ("HPLD", 13103,  None),          # Aptiv (post-spinoff)
    ("DLPH", 13103,  "2017-12-03"),  # Aptiv as Delphi Automotive (pre-split)
    ("004W", 14714,  None),          # Arista Networks
    ("SMIC", 91907,  None),          # Super Micro Computer
    ("053G", 25146,  None),          # Smurfit WestRock
]

ibes_tickers = tuple(t for t, _, _ in IBES_TARGETS)
print(f"Querying IBES for: {ibes_tickers}\n")

# ── WRDS pull ─────────────────────────────────────────────────────────────────
db = wrds.Connection(wrds_username=_u)

print("Pulling IBES actuals (actu_epsus)...")
actuals = db.raw_sql(f"""
    SELECT ticker, cusip, anndats, pends, value AS actual_eps
    FROM ibes.actu_epsus
    WHERE pdicity = 'QTR'
      AND anndats BETWEEN '{START}' AND '{END}'
      AND anndats IS NOT NULL
      AND ticker IN {ibes_tickers}
""")
print(f"  Raw actuals: {len(actuals):,} rows")
print(f"  Tickers found: {sorted(actuals['ticker'].unique().tolist())}")

print("\nPulling IBES consensus (statsum_epsus, fpi=6)...")
consensus = db.raw_sql(f"""
    SELECT ticker, fpedats, statpers, meanest AS consensus_eps, numest AS n_analysts
    FROM ibes.statsum_epsus
    WHERE fpi = '6'
      AND statpers BETWEEN '{START}' AND '{END}'
      AND meanest IS NOT NULL
      AND ticker IN {ibes_tickers}
""")
print(f"  Raw consensus rows: {len(consensus):,}")

db.close()

if len(actuals) == 0:
    print("No data found. Exiting.")
    raise SystemExit(0)

# ── Apply date filters and assign permno ──────────────────────────────────────
actuals["anndats"] = pd.to_datetime(actuals["anndats"])
actuals["pends"]   = pd.to_datetime(actuals["pends"])
consensus["statpers"] = pd.to_datetime(consensus["statpers"])
consensus["fpedats"]  = pd.to_datetime(consensus["fpedats"])

# Build ticker -> (permno, date_filter_end) lookup
ticker_meta = {}
for ibes_t, permno, date_end in IBES_TARGETS:
    ticker_meta[ibes_t] = (permno, pd.Timestamp(date_end) if date_end else None)

# Apply date filter and assign permno
rows_filtered = []
for _, row in actuals.iterrows():
    t = row["ticker"]
    if t not in ticker_meta:
        continue
    permno, date_end = ticker_meta[t]
    if date_end is not None and row["anndats"] > date_end:
        continue
    rows_filtered.append({**row.to_dict(), "permno": permno})

actuals_filt = pd.DataFrame(rows_filtered)
print(f"\nAfter date filtering: {len(actuals_filt):,} rows")

# ── Match consensus ───────────────────────────────────────────────────────────
consensus_indexed = consensus.set_index(["ticker", "fpedats"])

records = []
for (ticker, pends), grp in actuals_filt.groupby(["ticker", "pends"]):
    anndats = grp["anndats"].iloc[0]
    actual  = grp["actual_eps"].iloc[0]
    permno  = int(grp["permno"].iloc[0])
    cusip   = grp["cusip"].iloc[0] if "cusip" in grp.columns else None

    try:
        cons_sub = consensus_indexed.loc[(ticker, pends)]
        if isinstance(cons_sub, pd.Series):
            cons_sub = cons_sub.to_frame().T
        before_ann = cons_sub[cons_sub["statpers"] < anndats]
        if len(before_ann) > 0:
            latest = before_ann.sort_values("statpers").iloc[-1]
            con_mean   = float(latest["consensus_eps"])
            n_analysts = int(latest["n_analysts"])
        else:
            con_mean = None
            n_analysts = None
    except KeyError:
        con_mean = None
        n_analysts = None

    records.append({
        "ticker"       : ticker,
        "cusip"        : cusip,
        "anndats"      : anndats,
        "pends"        : pends,
        "actual_eps"   : float(actual),
        "consensus_eps": con_mean,
        "n_analysts"   : n_analysts,
        "permno"       : permno,
    })

df_new = pd.DataFrame(records)
print(f"Matched {len(df_new):,} earnings events")

# ── EPS surprise ──────────────────────────────────────────────────────────────
def safe_surprise(row):
    if pd.isna(row["consensus_eps"]) or row["consensus_eps"] == 0:
        return None
    return (row["actual_eps"] - row["consensus_eps"]) / abs(row["consensus_eps"]) * 100

df_new["surprise_pct"] = df_new.apply(safe_surprise, axis=1)

# ── Summary before appending ──────────────────────────────────────────────────
perm_to_label = {p: t for t, p, _ in IBES_TARGETS}
print("\nNew events by company:")

universe = pd.read_parquet("data/sp500_constituents.parquet")
uni_dedup = (universe.sort_values("end_date", ascending=False, na_position="first")
             .drop_duplicates("permno"))
perm_to_name = uni_dedup.set_index("permno")["company"].to_dict()

for permno, grp in df_new.groupby("permno"):
    name = perm_to_name.get(int(permno), "?")
    print(f"  permno {permno} ({name}): {len(grp):3d} events  "
          f"{grp['anndats'].min().date()} to {grp['anndats'].max().date()}")

# ── Load existing and check for duplicates ────────────────────────────────────
earnings = pd.read_parquet(EARNINGS_CACHE)
existing_pairs = set(zip(earnings["permno"].astype(int), earnings["anndats"].astype(str)))

df_new["permno"] = df_new["permno"].astype(int)
before_dedup = len(df_new)
df_new = df_new[
    ~df_new.apply(lambda r: (r["permno"], str(r["anndats"])) in existing_pairs, axis=1)
].copy()
print(f"\nDuplicate check: {before_dedup - len(df_new)} events already in earnings_dates (skipped)")
print(f"New events to append: {len(df_new)}")

if len(df_new) == 0:
    print("Nothing new to append.")
    raise SystemExit(0)

# ── Align columns and append ──────────────────────────────────────────────────
existing_cols = list(earnings.columns)
for col in existing_cols:
    if col not in df_new.columns:
        df_new[col] = None
df_new = df_new[existing_cols]

combined = pd.concat([earnings, df_new], ignore_index=True)
combined = combined.sort_values(["permno", "anndats", "n_analysts"], ascending=[True, True, False])
combined = combined.drop_duplicates(subset=["permno", "anndats"])
combined = combined.reset_index(drop=True)

combined.to_parquet(EARNINGS_CACHE, index=False)
print(f"\nSaved -> {EARNINGS_CACHE}")
print(f"  Before: {len(earnings):,} rows, {earnings['permno'].nunique():,} permnos")
print(f"  After:  {len(combined):,} rows, {combined['permno'].nunique():,} permnos")
print(f"  New permnos added: {combined['permno'].nunique() - earnings['permno'].nunique()}")
