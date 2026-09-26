# ruff: noqa
"""
01_data_probe.py
----------------
Feasibility probe for the barrier-skew study. Read-only, small queries.
  1. Which OptionMetrics / CRSP libraries this account can see
  2. Latest date in OptionMetrics (secprd, opprcd, vsurfd) for SPX
  3. Earliest vsurfd year for SPX
  4. Latest date in every CRSP stock library variant (annual / quarterly / monthly)
  5. Whether IvyDB Europe is in the subscription
"""

import os
import wrds
import pandas as pd

pd.set_option("display.width", 220)

SPX = 108105
AAPL_PERMNO = 14593

db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))


def q(sql):
    try:
        return db.raw_sql(sql)
    except Exception as e:
        return f"ERROR: {str(e).splitlines()[0][:160]}"


# ── 1. Libraries ──────────────────────────────────────────────────────────────
libs = db.list_libraries()
print("=== Libraries matching option / ivy / crsp ===")
for lib in sorted(libs):
    if any(k in lib.lower() for k in ("option", "ivy", "crsp")):
        print("  ", lib)

# ── 2-3. OptionMetrics US ─────────────────────────────────────────────────────
for lib in ("optionm_all", "optionm"):
    if lib not in libs:
        print(f"\n{lib}: not accessible")
        continue
    tables = db.list_tables(lib)
    print(f"\n=== {lib}: {len(tables)} tables ===")
    for stem in ("secprd", "opprcd", "vsurfd", "stdopd"):
        years = sorted(int(t[len(stem):]) for t in tables
                       if t.startswith(stem) and t[len(stem):].isdigit())
        if not years:
            print(f"  {stem}: no year tables")
            continue
        print(f"  {stem}: {years[0]}-{years[-1]}")
        last = f"{lib}.{stem}{years[-1]}"
        r = q(f"SELECT MIN(date) AS first, MAX(date) AS last, COUNT(*) AS n FROM {last} WHERE secid = {SPX}")
        print(f"    SPX in {last}:", r if isinstance(r, str) else r.to_dict("records"))

# vsurfd columns + one-day sample (grid shape we will calibrate from)
print("\n=== vsurfd sample (SPX, first day of last table) ===")
vs_years = sorted(int(t[6:]) for t in db.list_tables("optionm_all") if t.startswith("vsurfd") and t[6:].isdigit())
res = q(f"""SELECT days, delta, cp_flag, impl_strike, impl_volatility
            FROM optionm_all.vsurfd{vs_years[-1]}
            WHERE secid = {SPX} AND date = (SELECT MIN(date) FROM optionm_all.vsurfd{vs_years[-1]} WHERE secid = {SPX})
            ORDER BY days, cp_flag, delta""")
if isinstance(res, str):
    print(res)
else:
    print(f"rows: {len(res)}, maturities (days): {sorted(res['days'].unique())}")
    print(f"deltas: {sorted(res['delta'].unique())}")
    print(res[res["days"] == 365].to_string(index=False))

# ── 4. CRSP variants ──────────────────────────────────────────────────────────
print("\n=== CRSP daily stock file, latest date by library ===")
for lib in ("crsp", "crsp_a_stock", "crsp_q_stock", "crsp_m_stock"):
    if lib not in libs:
        print(f"  {lib}: not accessible")
        continue
    r = q(f"SELECT MAX(dlycaldt) AS last FROM {lib}.dsf_v2 WHERE permno = {AAPL_PERMNO}")
    print(f"  {lib}.dsf_v2 (AAPL):", r if isinstance(r, str) else r.iloc[0, 0])

print("\n=== CRSP index (S&P 500 total return proxy), latest date ===")
for lib in ("crsp", "crsp_a_indexes", "crsp_q_indexes", "crsp_m_indexes"):
    if lib not in libs:
        print(f"  {lib}: not accessible")
        continue
    r = q(f"SELECT MAX(caldt) AS last FROM {lib}.dsp500")
    print(f"  {lib}.dsp500:", r if isinstance(r, str) else r.iloc[0, 0])

# ── 5. IvyDB Europe ───────────────────────────────────────────────────────────
print("\n=== IvyDB Europe ===")
eu = [l for l in libs if l.lower().startswith(("optionme", "ivydbeu", "optionm_eu", "ivye"))]
print("  candidate libraries:", eu or "none")
for lib in eu:
    try:
        print(f"  {lib} tables (first 20):", db.list_tables(lib)[:20])
    except Exception as e:
        print(f"  {lib}: {str(e).splitlines()[0][:160]}")

db.close()
print("\n=== probe complete ===")
