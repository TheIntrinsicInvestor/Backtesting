"""
02_secid_mapper.py
------------------
Look up OptionMetrics secids for SPX (index), TLT (ETF), and SPY (ETF).
Queries optionm_all.secnmd by ticker symbol.

Note: VIX is pulled from FRED (VIXCLS series) in 04_vix_pull.py and does
not require an OptionMetrics secid.

Output: data/secids.parquet
Columns: ticker, secid (int), issuer, effect_date
"""

import os
import wrds
import pandas as pd

os.makedirs("data", exist_ok=True)

CACHE = "data/secids.parquet"

if os.path.exists(CACHE):
    print(f"Cache found at {CACHE} — skipping WRDS query.")
    secids = pd.read_parquet(CACHE)
else:
    db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))

    query = """
        SELECT secid, ticker, issuer, effect_date
        FROM optionm_all.secnmd
        WHERE ticker IN ('SPX', 'TLT', 'SPY')
        ORDER BY ticker, effect_date DESC
    """
    df = db.raw_sql(query)
    db.close()

    # Take most recent row per ticker
    secids = (
        df.sort_values("effect_date", ascending=False)
        .groupby("ticker")
        .first()
        .reset_index()[["ticker", "secid", "issuer", "effect_date"]]
    )
    secids["secid"] = secids["secid"].astype(int)
    secids.to_parquet(CACHE, index=False)
    print(f"Saved to {CACHE}")

# Ensure int on load (parquet may restore as float)
secids["secid"] = secids["secid"].astype(int)

print("\nSecid map:")
print(secids[["ticker", "secid", "issuer"]].to_string(index=False))
print()

# Expose as dict for use in downstream scripts
SECID_MAP = dict(zip(secids["ticker"], secids["secid"]))
print("SECID_MAP =", SECID_MAP)
