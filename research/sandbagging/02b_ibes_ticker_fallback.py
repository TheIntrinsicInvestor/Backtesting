"""
02b_ibes_ticker_fallback.py  —  IBES ticker-based recovery for CUSIP-unmatched permnos
For permnos that 02_earnings_dates.py missed (CUSIP mismatch between CRSP and IBES),
re-queries IBES actu_epsus by ticker and appends the matched events.
Output: data/earnings_dates.parquet (updated in-place)
"""

import os
import builtins
import wrds
import pandas as pd

_WRDS_USER = os.environ.get("WRDS_USERNAME", "hoovyalert")
_orig_input = builtins.input
def _auto_input(prompt=""):
    val = _WRDS_USER if "username" in prompt.lower() else ""
    print(f"{prompt}{val}")
    return val
builtins.input = _auto_input
from pathlib import Path

EARNINGS_CACHE = Path("data/earnings_dates.parquet")
START = "2015-01-01"
END   = "2025-12-31"

# ── Load current state ────────────────────────────────────────────────────────
universe = pd.read_parquet("data/sp500_constituents.parquet")
earnings = pd.read_parquet(EARNINGS_CACHE)

uni_dedup = (
    universe.sort_values("end_date", ascending=False, na_position="first")
    .drop_duplicates("permno")
)

all_permnos  = set(uni_dedup["permno"])
earn_permnos = set(earnings["permno"])
missing      = all_permnos - earn_permnos

print(f"Currently missing from earnings_dates: {len(missing)} permnos")
missing_df = uni_dedup[uni_dedup["permno"].isin(missing)][
    ["permno", "ticker", "company", "sector", "start_date", "end_date"]
].copy()
print(missing_df.sort_values("end_date", ascending=False).to_string(index=False))

if len(missing) == 0:
    print("No missing permnos. Nothing to do.")
    raise SystemExit(0)

# ── Permno -> ticker lookup ────────────────────────────────────────────────────
perm_to_ticker = missing_df.set_index("permno")["ticker"].to_dict()
ticker_to_perm = {}
for permno, ticker in perm_to_ticker.items():
    ticker_to_perm.setdefault(ticker, permno)

tickers_to_query = tuple(perm_to_ticker.values())
print(f"\nQuerying IBES by ticker: {tickers_to_query}")

# ── WRDS pull ─────────────────────────────────────────────────────────────────
db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))

print("\nPulling IBES actuals (actu_epsus) by ticker...")
actuals = db.raw_sql(f"""
    SELECT ticker, cusip, anndats, pends, value AS actual_eps
    FROM ibes.actu_epsus
    WHERE pdicity = 'ANN'
      AND anndats BETWEEN '{START}' AND '{END}'
      AND anndats IS NOT NULL
      AND ticker IN {tickers_to_query}
""")
print(f"  Raw actuals: {len(actuals):,} rows across {actuals['ticker'].nunique()} tickers")
print(f"  Tickers found: {sorted(actuals['ticker'].unique().tolist())}")

print("\nPulling IBES consensus (statsum_epsus, fpi=6) by ticker...")
consensus = db.raw_sql(f"""
    SELECT ticker, fpedats, statpers, meanest AS consensus_eps, numest AS n_analysts
    FROM ibes.statsum_epsus
    WHERE fpi = '1'
      AND statpers BETWEEN '{START}' AND '{END}'
      AND meanest IS NOT NULL
      AND ticker IN {tickers_to_query}
""")
print(f"  Raw consensus rows: {len(consensus):,}")

db.close()

if len(actuals) == 0:
    print("\nNo IBES data found for any of the missing tickers. Nothing to append.")
    raise SystemExit(0)

# ── Match consensus to actuals ────────────────────────────────────────────────
actuals["anndats"] = pd.to_datetime(actuals["anndats"])
actuals["pends"]   = pd.to_datetime(actuals["pends"])
consensus["statpers"] = pd.to_datetime(consensus["statpers"])
consensus["fpedats"]  = pd.to_datetime(consensus["fpedats"])

consensus_indexed = consensus.set_index(["ticker", "fpedats"])

rows = []
for (ticker, pends), grp in actuals.groupby(["ticker", "pends"]):
    anndats = grp["anndats"].iloc[0]
    actual  = grp["actual_eps"].iloc[0]
    cusip   = grp["cusip"].iloc[0] if "cusip" in grp.columns else None

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

df_new = pd.DataFrame(rows)
print(f"\nMatched {len(df_new):,} earnings events from fallback")

# ── EPS surprise ──────────────────────────────────────────────────────────────
def safe_surprise(row):
    if pd.isna(row["consensus_eps"]) or row["consensus_eps"] == 0:
        return None
    return (row["actual_eps"] - row["consensus_eps"]) / abs(row["consensus_eps"]) * 100

df_new["surprise_pct"] = df_new.apply(safe_surprise, axis=1)

# ── Map ticker -> permno ──────────────────────────────────────────────────────
df_new["permno"] = df_new["ticker"].map(ticker_to_perm)

cusip_to_permno = (
    uni_dedup.dropna(subset=["ncusip"])
    .sort_values("end_date", ascending=False, na_position="first")
    .drop_duplicates("ncusip")[["ncusip", "permno"]]
    .set_index("ncusip")["permno"]
    .to_dict()
)
cusip8_mapped = df_new["cusip"].str[:8].str.strip().map(cusip_to_permno)
df_new["permno"] = df_new["permno"].fillna(cusip8_mapped)

matched   = df_new["permno"].notna().sum()
unmatched = df_new["permno"].isna().sum()
print(f"Permno matched: {matched:,} / {len(df_new):,} rows  ({unmatched} unmatched)")

if unmatched > 0:
    print("Unmatched tickers:")
    print(df_new[df_new["permno"].isna()]["ticker"].value_counts().to_string())

df_new = df_new.dropna(subset=["permno"]).copy()
df_new["permno"] = df_new["permno"].astype(int)
df_new = df_new.sort_values(["permno", "anndats", "n_analysts"], ascending=[True, True, False])
df_new = df_new.drop_duplicates(subset=["permno", "anndats"])

print(f"\nNew events by permno:")
for permno, grp in df_new.groupby("permno"):
    ticker  = perm_to_ticker.get(permno, "?")
    company = uni_dedup[uni_dedup["permno"] == permno]["company"].values[0] if permno in set(uni_dedup["permno"]) else "?"
    print(f"  {ticker:6s} (permno {permno}): {len(grp):3d} events  "
          f"{grp['anndats'].min().date()} to {grp['anndats'].max().date()}")

# ── Append to earnings_dates.parquet ─────────────────────────────────────────
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
print(f"  New permnos recovered: {combined['permno'].nunique() - earnings['permno'].nunique()}")
