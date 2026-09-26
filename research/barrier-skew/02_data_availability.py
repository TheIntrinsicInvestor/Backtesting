# ruff: noqa
"""
02_data_availability.py
-----------------------
Confirms every input the barrier-skew method needs exists in this WRDS subscription,
with date coverage. Read-only, small filtered queries.

Needs:
  surfaces      optionm_all.vsurfd{yr}         (SPX + single names), optionm_europe.volatility_surface_{yr}
  rates         optionm_all.zerocd,              optionm_europe.zero_curve
  dividends     optionm_all.idxdvd / distrd / fwdprd, optionm_europe.index_dividend / forward_price
  realised path optionm_all.secprd{yr}, crsp.dsf_v2 (SPY, single names), CRSP index files
  universe      option volume per secid per date (opvold or opprcd), CRSP market cap
  link          wrdsapps_link_crsp_optionm
"""

import os
import wrds
import pandas as pd

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 20)

SPX, AAPL, MSFT = 108105, 101594, 107525
SPY_PERMNO = 84398
SX5E = 504880

db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))


def q(sql):
    try:
        return db.raw_sql(sql)
    except Exception as e:
        return f"ERROR: {str(e).splitlines()[0][:200]}"


def show(label, sql):
    r = q(sql)
    print(f"  {label}:", r if isinstance(r, str) else ("\n" + r.to_string(index=False) if len(r) > 1 else r.to_dict("records")))


us = db.list_tables("optionm_all")
stems = sorted({t.rstrip("0123456789") for t in us})
print("=== optionm_all table stems ===")
print("  ", stems)

# ── US surfaces: first year for SPX and single names ──────────────────────────
print("\n=== US volatility surfaces ===")
for yr in (1996, 2025):
    show(f"vsurfd{yr} SPX/AAPL/MSFT",
         f"SELECT secid, MIN(date) AS first, MAX(date) AS last, COUNT(DISTINCT date) AS days "
         f"FROM optionm_all.vsurfd{yr} WHERE secid IN ({SPX},{AAPL},{MSFT}) GROUP BY secid")
show("names with a 365-day surface on 2010-06-01",
     "SELECT COUNT(DISTINCT secid) AS n FROM optionm_all.vsurfd2010 WHERE date = '2010-06-01' AND days = 365")

# ── Rates ─────────────────────────────────────────────────────────────────────
print("\n=== Zero curve ===")
show("zerocd", "SELECT MIN(date) AS first, MAX(date) AS last, COUNT(DISTINCT date) AS days FROM optionm_all.zerocd")

# ── Dividends / forwards ──────────────────────────────────────────────────────
print("\n=== Dividends and forwards ===")
if "idxdvd" in us:
    show("idxdvd SPX", f"SELECT MIN(date) AS first, MAX(date) AS last FROM optionm_all.idxdvd WHERE secid = {SPX}")
if "distrd" in us:
    show("distrd AAPL", f"SELECT MIN(ex_date) AS first, MAX(ex_date) AS last, COUNT(*) AS n FROM optionm_all.distrd WHERE secid = {AAPL}")
fwd = sorted(t for t in us if t.startswith("fwdprd"))
print("  fwdprd tables:", (fwd[0], fwd[-1], len(fwd)) if fwd else "none")
if fwd:
    show(f"{fwd[-1]} SPX", f"SELECT MIN(date) AS first, MAX(date) AS last FROM optionm_all.{fwd[-1]} WHERE secid = {SPX}")

# ── Realised paths ────────────────────────────────────────────────────────────
print("\n=== Realised paths ===")
show("secprd1996 SPX", f"SELECT MIN(date) AS first FROM optionm_all.secprd1996 WHERE secid = {SPX}")
show("crsp.dsf_v2 SPY", f"SELECT MIN(dlycaldt) AS first, MAX(dlycaldt) AS last FROM crsp.dsf_v2 WHERE permno = {SPY_PERMNO}")
crsp_tables = db.list_tables("crsp")
idx = [t for t in crsp_tables if any(k in t for k in ("dsi", "dsp500", "inddly", "indexes", "dly"))]
print("  crsp index-like tables:", idx[:40])
for t in ("dsi", "dsi_v2", "wrds_dsi_v2"):
    if t in crsp_tables:
        cols = q(f"SELECT * FROM crsp.{t} LIMIT 1")
        datecol = next((c for c in (cols.columns if not isinstance(cols, str) else []) if "dt" in c or c in ("date", "caldt")), None)
        if datecol:
            show(f"crsp.{t}", f"SELECT MAX({datecol}) AS last FROM crsp.{t}")

# ── Universe: option volume ───────────────────────────────────────────────────
print("\n=== Option volume for point-in-time universe ===")
vol = sorted(t for t in us if t.startswith("opvold"))
print("  opvold tables:", (vol[0], vol[-1], len(vol)) if vol else "none")
if vol:
    cols = q(f"SELECT * FROM optionm_all.{vol[-1]} LIMIT 1")
    print("  columns:", cols if isinstance(cols, str) else list(cols.columns))
    show("top 12 by volume, 2010-06", f"""
        SELECT secid, SUM(volume) AS vol FROM optionm_all.opvold2010
        WHERE date BETWEEN '2010-06-01' AND '2010-06-30' AND cp_flag IS NULL
        GROUP BY secid ORDER BY vol DESC LIMIT 12""")

# ── Link table ────────────────────────────────────────────────────────────────
print("\n=== OptionMetrics <-> CRSP link ===")
lt = db.list_tables("wrdsapps_link_crsp_optionm")
print("  tables:", lt)
if lt:
    show("sample", f"SELECT * FROM wrdsapps_link_crsp_optionm.{lt[0]} WHERE secid = {AAPL}")

# ── Europe ────────────────────────────────────────────────────────────────────
print("\n=== IvyDB Europe inputs (SX5E) ===")
show("security_price SX5E", f"SELECT MIN(date) AS first, MAX(date) AS last, COUNT(*) AS n FROM optionm_europe.security_price WHERE securityid = {SX5E}")
show("zero_curve", "SELECT MIN(date) AS first, MAX(date) AS last, COUNT(DISTINCT currency) AS ccys FROM optionm_europe.zero_curve")
show("index_dividend SX5E", f"SELECT MIN(date) AS first, MAX(date) AS last FROM optionm_europe.index_dividend WHERE securityid = {SX5E}")
show("forward_price SX5E", f"SELECT MIN(date) AS first, MAX(date) AS last FROM optionm_europe.forward_price WHERE securityid = {SX5E}")
show("volatility_surface_2010 SX5E 365d grid", f"""
    SELECT COUNT(*) AS rows, COUNT(DISTINCT date) AS days FROM optionm_europe.volatility_surface_2010
    WHERE securityid = {SX5E} AND days = 365""")

db.close()
print("\n=== availability check complete ===")
