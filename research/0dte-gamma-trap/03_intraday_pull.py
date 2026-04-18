# ruff: noqa
"""
03_intraday_pull.py
-------------------
Two-phase intraday data pull:

Phase 1 (fast): CRSP daily OHLC for SPY -> Parkinson realized vol for all 887 days.
    Parkinson vol: sigma = sqrt(252) * sqrt(1/4ln2) * ln(H/L)
    Single query, runs in seconds.

Phase 2 (targeted): TAQ for 30 representative days (10 per GEX regime) ->
    intraday 30-min vol profile used for Chart 3 only.

Outputs:
    data/rvol_daily.parquet     -- date, rvol_ann, open_to_close_return
    data/rvol_profile.parquet   -- date, bucket, bucket_rvol
"""

import os
import wrds
import pandas as pd
import numpy as np

os.makedirs("data", exist_ok=True)

CACHE_DAILY   = "data/rvol_daily.parquet"
CACHE_PROFILE = "data/rvol_profile.parquet"

SPY_PERMNO = 84398
START_DATE = "2022-01-01"
END_DATE   = "2025-08-29"
ANNUALIZE  = np.sqrt(252 * 78)   # for TAQ 5-min vol
PARK_CONST = 1.0 / (4.0 * np.log(2))

OPEN_TIME  = pd.Timestamp("09:30:00").time()
CLOSE_TIME = pd.Timestamp("16:00:00").time()

BUCKET_LABELS = [
    f"{h:02d}:{m:02d}"
    for h in range(9, 16) for m in [0, 30]
    if not (h == 9 and m == 0)
]

def time_to_bucket(t):
    h, m = t.hour, 0 if t.minute < 30 else 30
    if h == 16: return "15:30"
    return f"{h:02d}:{m:02d}"


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1: CRSP Parkinson vol for all trading days
# ═══════════════════════════════════════════════════════════════════════════════
if os.path.exists(CACHE_DAILY):
    print(f"Daily cache found -- skipping Phase 1.")
    daily_df = pd.read_parquet(CACHE_DAILY)
else:
    print("Phase 1: pulling SPY OHLC from CRSP...")
    db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))

    crsp = db.raw_sql(f"""
        SELECT date, openprc, askhi, bidlo, prc, ret
        FROM crsp.dsf
        WHERE permno = {SPY_PERMNO}
          AND date >= '{START_DATE}'
          AND date <= '{END_DATE}'
        ORDER BY date
    """)
    db.close()

    crsp["date"]   = pd.to_datetime(crsp["date"])
    crsp["askhi"]  = pd.to_numeric(crsp["askhi"],  errors="coerce")
    crsp["bidlo"]  = pd.to_numeric(crsp["bidlo"],  errors="coerce")
    crsp["openprc"]= pd.to_numeric(crsp["openprc"],errors="coerce")
    crsp["prc"]    = pd.to_numeric(crsp["prc"],    errors="coerce")
    crsp["ret"]    = pd.to_numeric(crsp["ret"],    errors="coerce")
    crsp = crsp.dropna(subset=["askhi","bidlo","openprc","prc"])
    crsp = crsp[crsp["bidlo"] > 0]

    # Parkinson annualised vol
    crsp["rvol_ann"] = np.sqrt(252 * PARK_CONST) * np.log(crsp["askhi"] / crsp["bidlo"])

    # Open-to-close log return (pure intraday, no overnight)
    crsp["open_to_close_return"] = np.log(crsp["prc"] / crsp["openprc"])

    daily_df = crsp[["date","rvol_ann","open_to_close_return"]].copy()
    daily_df.to_parquet(CACHE_DAILY, index=False)
    print(f"Saved {len(daily_df):,} rows to {CACHE_DAILY}")
    print(f"Mean rvol: {daily_df['rvol_ann'].mean():.1%}  |  range: {daily_df['rvol_ann'].min():.1%} - {daily_df['rvol_ann'].max():.1%}")


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: TAQ intraday profile for 30 representative days
# ═══════════════════════════════════════════════════════════════════════════════
if os.path.exists(CACHE_PROFILE):
    print(f"Profile cache found -- skipping Phase 2.")
else:
    # Need GEX data to pick representative days
    if not os.path.exists("data/gex_daily.parquet"):
        print("GEX cache not found -- skipping Phase 2 profile (run 02_gex_pull.py first).")
        pd.DataFrame(columns=["date","bucket","bucket_rvol"]).to_parquet(CACHE_PROFILE, index=False)
    else:
        gex = pd.read_parquet("data/gex_daily.parquet")
        gex["date"] = pd.to_datetime(gex["date"])
        merged = gex.merge(daily_df, on="date")

        # Classify regimes
        pos = merged[merged["gex_bn"] >= 0]["gex_bn"]
        p33 = float(pos.quantile(0.33))
        def regime(g):
            if g < 0: return "Negative GEX"
            elif g < p33: return "Low GEX"
            else: return "High GEX"
        merged["regime"] = merged["gex_bn"].apply(regime)

        # Pick 10 most extreme days per regime by rvol_ann
        sample_days = []
        for r in ["Negative GEX", "Low GEX", "High GEX"]:
            bucket = merged[merged["regime"] == r].nlargest(10, "rvol_ann")
            sample_days.extend(bucket["date"].tolist())

        print(f"\nPhase 2: pulling TAQ intraday profile for {len(sample_days)} representative days...")

        db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))
        profile_rows = []

        for i, td in enumerate(sorted(sample_days)):
            date_str = td.strftime("%Y%m%d")
            taq_table = f"taqmsec.ctm_{date_str}"
            if (i+1) % 5 == 0:
                print(f"  [{i+1}/{len(sample_days)}] {td.date()}")
            try:
                q = f"""
                    SELECT time_m, price, size
                    FROM {taq_table}
                    WHERE sym_root = 'SPY'
                      AND tr_corr = '00'
                      AND price > 0 AND size > 0
                """
                df_day = db.raw_sql(q)
                if df_day.empty: continue

                # Parse time_m -> Timestamp
                def to_ts(t):
                    try: return pd.Timestamp(f"2000-01-01 {t}")
                    except: return pd.NaT

                df_day["dt"] = df_day["time_m"].apply(to_ts)
                df_day = df_day.dropna(subset=["dt"])
                df_day["time"] = df_day["dt"].dt.time
                df_day = df_day[(df_day["time"] >= OPEN_TIME) & (df_day["time"] <= CLOSE_TIME)]
                if len(df_day) < 10: continue

                df_day["price"] = df_day["price"].astype(float)
                df_day["size"]  = df_day["size"].astype(float)
                df_day = df_day.sort_values("dt")

                # 5-min VWAP
                df_day["bin5"] = df_day["dt"].dt.floor("5min")
                vwap5 = (
                    df_day.groupby("bin5")
                    .apply(lambda g: np.average(g["price"], weights=g["size"]))
                    .rename("vwap").reset_index()
                ).sort_values("bin5")
                vwap5["ret"] = np.log(vwap5["vwap"] / vwap5["vwap"].shift(1))
                vwap5 = vwap5.dropna(subset=["ret"])

                # Per-bucket realized vol
                vwap5["bucket"] = vwap5["bin5"].dt.time.apply(time_to_bucket)
                for label, grp in vwap5.groupby("bucket"):
                    if len(grp) >= 2:
                        bv = float(np.sqrt((grp["ret"]**2).sum()) * ANNUALIZE)
                        profile_rows.append({"date": td, "bucket": label, "bucket_rvol": bv})
            except Exception as e:
                if "does not exist" not in str(e).lower():
                    print(f"  WARNING {td.date()}: {e}")

        db.close()

        profile_df = pd.DataFrame(profile_rows) if profile_rows else pd.DataFrame(columns=["date","bucket","bucket_rvol"])
        profile_df.to_parquet(CACHE_PROFILE, index=False)
        print(f"Saved {len(profile_df):,} profile rows to {CACHE_PROFILE}")

print("Done.")
