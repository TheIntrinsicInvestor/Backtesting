# ruff: noqa
"""
01_data_check.py
----------------
Verify data availability before any heavy pulling:
  1. Look up SPX secid in OptionMetrics secnmd
  2. Probe opprcd2022 to confirm 0DTE rows exist + column names
  3. Probe a TAQ consolidated-trades table to confirm SPY columns
"""

import os
import wrds
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 220)

db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))

# ── 1. SPX secid lookup ───────────────────────────────────────────────────────
print("=== SPX secid lookup ===")
secid_df = db.raw_sql("SELECT secid, ticker, issuer, effect_date FROM optionm_all.secnmd WHERE ticker = 'SPX' ORDER BY effect_date")
print(secid_df.to_string(index=False))

if secid_df.empty:
    print("No secid found for SPX — check OptionMetrics access.")
    db.close()
    exit()

# SPX cash index is typically secid 108105 in OptionMetrics
spx_secids = secid_df["secid"].unique().tolist()
print(f"\nAll SPX secids found: {spx_secids}")
SPX_SECID = int(spx_secids[0])
print(f"Will use secid = {SPX_SECID}\n")

# ── 2. Probe opprcd2022 for 0DTE SPX rows ─────────────────────────────────────
print("=== Probing optionm_all.opprcd2022 for 0DTE SPX options ===")
probe_q = f"""
    SELECT secid, date, exdate, cp_flag, strike_price,
           open_interest, gamma, delta, impl_volatility,
           best_bid, best_offer
    FROM optionm_all.opprcd2022
    WHERE secid = {SPX_SECID}
      AND exdate = date
      AND date = '2022-01-03'
    LIMIT 10
"""
try:
    probe_df = db.raw_sql(probe_q)
    print(f"Columns: {list(probe_df.columns)}")
    print(f"Rows returned: {len(probe_df)}")
    print(probe_df.to_string(index=False))
except Exception as e:
    print(f"ERROR querying opprcd2022: {e}")
    print("Trying alternative secids...")
    for sid in spx_secids[1:]:
        try:
            probe_df = db.raw_sql(probe_q.replace(str(SPX_SECID), str(sid)))
            if not probe_df.empty:
                print(f"  secid {sid} has data!")
                SPX_SECID = int(sid)
                break
        except Exception:
            pass

# Count total 0DTE rows for full year 2022
print("\n=== 0DTE SPX row count for 2022 ===")
count_q = f"""
    SELECT COUNT(*) as n_rows, MIN(date) as first_date, MAX(date) as last_date
    FROM optionm_all.opprcd2022
    WHERE secid = {SPX_SECID}
      AND exdate = date
"""
try:
    count_df = db.raw_sql(count_q)
    print(count_df.to_string(index=False))
except Exception as e:
    print(f"ERROR: {e}")

# ── 3. Probe TAQ consolidated trades for SPY ──────────────────────────────────
print("\n=== Probing TAQ for SPY intraday trades (2022-01-03) ===")
taq_table = "taq.ct_20220103"
try:
    taq_q = f"""
        SELECT *
        FROM {taq_table}
        WHERE sym_root = 'SPY'
        LIMIT 5
    """
    taq_df = db.raw_sql(taq_q)
    print(f"Table: {taq_table}")
    print(f"Columns: {list(taq_df.columns)}")
    print(f"Sample rows:")
    print(taq_df.to_string(index=False))

    # Count SPY rows for that day
    taq_count_q = f"SELECT COUNT(*) as n FROM {taq_table} WHERE sym_root = 'SPY'"
    n = db.raw_sql(taq_count_q)
    print(f"\nSPY trade count on 2022-01-03: {n.iloc[0,0]:,}")

except Exception as e:
    print(f"ERROR with {taq_table}: {e}")
    print("Trying taqmsec.ctm_20220103 ...")
    try:
        taq_q2 = "SELECT * FROM taqmsec.ctm_20220103 WHERE sym_root = 'SPY' LIMIT 5"
        taq_df2 = db.raw_sql(taq_q2)
        print(f"Columns: {list(taq_df2.columns)}")
        print(taq_df2.to_string(index=False))
    except Exception as e2:
        print(f"ERROR with taqmsec too: {e2}")

db.close()
print("\n=== data_check complete ===")
