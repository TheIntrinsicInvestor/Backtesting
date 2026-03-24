import os
import wrds
import pandas as pd

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)

db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))

# Look up XLE secid
secid_df = db.raw_sql("SELECT * FROM optionm_all.secnmd WHERE ticker = 'XLE'")
print("=== XLE secid lookup ===")
print(secid_df)

if secid_df.empty:
    print("No secid found for XLE — exiting.")
    db.close()
    exit()

# Use secid 110011 — the main ETF (not intraday/NAV classes)
secid = 110011
print(f"\nUsing secid = {secid}\n")

# Query ATM 30-day IV for XLE around Jan 2020
# delta=50 (call ATM), days=30; Dec 2019 in vsurfd2019, Jan-Feb 2020 in vsurfd2020
query = f"""
    SELECT * FROM optionm_all.vsurfd2019
    WHERE secid = {secid} AND days = 30 AND delta = 50
      AND date >= '2019-12-01'
    UNION ALL
    SELECT * FROM optionm_all.vsurfd2020
    WHERE secid = {secid} AND days = 30 AND delta = 50
      AND date <= '2020-02-28'
    ORDER BY date
    LIMIT 20
"""

df = db.raw_sql(query)

print("=== Column names ===")
print(list(df.columns))

print(f"\n=== XLE ATM 30-day IV around Jan 2020 (n={len(df)}) ===")
print(df.to_string(index=False))

db.close()
