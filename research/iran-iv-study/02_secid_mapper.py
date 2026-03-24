"""
02_secid_mapper.py
------------------
Look up OptionMetrics secids for all instruments used in the study.
XLE secid is already confirmed as 110011 from 01_data_check.py.
This script confirms that and resolves USO, XOM, CVX.

Output: prints a SECID_MAP dict ready to paste into subsequent scripts,
and saves data/secids.parquet.
"""

import os
import wrds
import pandas as pd

os.makedirs("data", exist_ok=True)

TICKERS = ["XLE", "USO", "XOM", "CVX"]

db = wrds.Connection(wrds_username="hoovyalert")

# secnmd holds name/ticker history; we want all matches then inspect
query = """
    SELECT secid, ticker, issuer, effect_date
    FROM optionm_all.secnmd
    WHERE ticker IN ('XLE', 'USO', 'XOM', 'CVX')
    ORDER BY ticker, effect_date
"""

df = db.raw_sql(query)
db.close()

df.to_parquet("data/secids.parquet", index=False)

print("=== All secnmd rows for our tickers ===")
print(df.to_string(index=False))

print("\n=== Recommended secid per ticker ===")
# For each ticker, take the row with the latest effect_date (most current mapping)
# or where expire_date is null (still active)
best = (
    df.sort_values("effect_date", ascending=False)
    .groupby("ticker")
    .first()
    .reset_index()[["ticker", "secid", "issuer", "effect_date"]]
)
print(best.to_string(index=False))

print("\nSECID_MAP = {")
for _, row in best.iterrows():
    print(f'    "{row["ticker"]}": {int(row["secid"])},')
print("}")
