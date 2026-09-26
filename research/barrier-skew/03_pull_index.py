# ruff: noqa
"""
03_pull_index.py
----------------
Batch A, script 1. Pulls everything needed to price and score SPX and SX5E products.

US (SPX):
  spx_surface     vsurfd OTM grid, all tenors, 1996-2025
  spx_fwd         fwdprd forward prices, 1996-2025
  spx_divyield    idxdvd continuous dividend yield (fallback carry)
  us_zero         zerocd zero curve
  spx_path        crsp.dsp500_v2 S&P 500 level, to 2025-12-31 (realised path)
Europe (SX5E):
  sx5e_surface, sx5e_fwd, sx5e_div, eur_zero, sx5e_path   (2002-01-02 to 2023-02-28)

Every output is cached; re-running skips anything already pulled.
"""

import common as C
import numpy as np
import pandas as pd

db = None
def conn():
    global db
    if db is None:
        db = C.connect()
    return db


def by_year(name, years, sql_fn):
    if (df := C.cached(name)) is not None:
        return df
    parts = []
    for yr in years:
        part = conn().raw_sql(sql_fn(yr))
        print(f"    {name} {yr}: {len(part):,}")
        parts.append(part)
    return C.save(pd.concat(parts, ignore_index=True), name)


def single(name, sql):
    if (df := C.cached(name)) is not None:
        return df
    return C.save(conn().raw_sql(sql), name)


US_YEARS = range(1996, C.US_OPT_LAST + 1)
EU_YEARS = range(2002, 2024)

print("=== SPX ===")
spx_surface = by_year("spx_surface", US_YEARS, lambda y: f"""
    SELECT date, days, delta, cp_flag, impl_volatility, impl_strike
    FROM optionm_all.vsurfd{y}
    WHERE secid = {C.SPX_SECID} AND {C.OTM_US}""")
spx_fwd = by_year("spx_fwd", US_YEARS, lambda y: f"""
    SELECT date, expiration, amsettlement, forwardprice
    FROM optionm_all.fwdprd{y} WHERE secid = {C.SPX_SECID}""")
spx_div = single("spx_divyield", f"SELECT date, rate FROM optionm_all.idxdvd WHERE secid = {C.SPX_SECID}")
us_zero = single("us_zero", "SELECT date, days, rate FROM optionm_all.zerocd WHERE date >= '1996-01-01'")
spx_spot = by_year("spx_spot", US_YEARS, lambda y: f"""
    SELECT date, close FROM optionm_all.secprd{y} WHERE secid = {C.SPX_SECID}""")
spx_path = single("spx_path", """
    SELECT caldt AS date, spindx AS level FROM crsp.dsp500_v2
    WHERE caldt >= '1996-01-01' AND spindx IS NOT NULL ORDER BY caldt""")

print("\n=== SX5E ===")
sx5e_surface = by_year("sx5e_surface", EU_YEARS, lambda y: f"""
    SELECT date, days, delta, callput AS cp_flag, impliedvol AS impl_volatility, strike AS impl_strike
    FROM optionm_europe.volatility_surface_{y}
    WHERE securityid = {C.SX5E_SECID} AND {C.OTM_EU}""")
sx5e_fwd = single("sx5e_fwd", f"""
    SELECT date, expiration, amsettlement, forwardprice FROM optionm_europe.forward_price
    WHERE securityid = {C.SX5E_SECID}""")
sx5e_div = single("sx5e_div", f"""
    SELECT date, expiration, rate FROM optionm_europe.index_dividend WHERE securityid = {C.SX5E_SECID}""")
eur_zero = single("eur_zero", f"SELECT date, days, rate FROM optionm_europe.zero_curve WHERE currency = {C.EUR_CCY}")
sx5e_path = single("sx5e_path", f"""
    SELECT date, closeprice AS level FROM optionm_europe.security_price
    WHERE securityid = {C.SX5E_SECID} AND exchange = {C.SX5E_EXCHANGE} ORDER BY date""")

if db is not None:
    db.close()

# ── Sanity report (reads the cached frames, so it also runs on a warm cache) ──
print("\n=== Checks ===")


def span(df, col="date"):
    d = pd.to_datetime(df[col])
    return f"{d.min().date()} to {d.max().date()}, {d.nunique():,} dates"


for name, df in [("spx_surface", spx_surface), ("spx_fwd", spx_fwd), ("spx_divyield", spx_div),
                 ("us_zero", us_zero), ("spx_spot", spx_spot), ("spx_path", spx_path),
                 ("sx5e_surface", sx5e_surface), ("sx5e_fwd", sx5e_fwd), ("sx5e_div", sx5e_div),
                 ("eur_zero", eur_zero), ("sx5e_path", sx5e_path)]:
    print(f"  {name:13s} {len(df):>9,} rows  {span(df)}")

for name, df in [("spx_surface", spx_surface), ("sx5e_surface", sx5e_surface)]:
    iv = df["impl_volatility"].astype(float)
    bad = iv.isna() | (iv <= C.EU_NA + 0.01) | (iv <= 0)
    per_day = df.assign(ok=~bad).groupby("date")["ok"].sum()
    print(f"  {name}: {bad.mean():.2%} missing IV points, "
          f"days with <150 of 187 points: {(per_day < 150).sum()}")
    one_y = df[(df["days"] == 365) & ~bad]
    print(f"    365d median IV by delta (puts): "
          + ", ".join(f"{int(d)}:{v:.3f}" for d, v in one_y[one_y.cp_flag == "P"].groupby("delta")["impl_volatility"].median().items()))

# Europe rate units: decimal vs percent
print(f"  eur_zero rate median {eur_zero['rate'].median():.4f} (decimal expected), "
      f"us_zero median {us_zero['rate'].median():.3f} (percent expected)")

# Realised path vs OptionMetrics spot: the two SPX series must agree
m = spx_spot.assign(date=pd.to_datetime(spx_spot.date)).merge(
    spx_path.assign(date=pd.to_datetime(spx_path.date)), on="date")
gap = (m["close"] / m["level"] - 1).abs()
print(f"  SPX spot (OptionMetrics) vs spindx (CRSP): {len(m):,} common days, max abs gap {gap.max():.4%}, "
      f"days >0.1%: {(gap > 0.001).sum()}")
print(f"  SPX path last date: {pd.to_datetime(spx_path.date).max().date()}  "
      f"SX5E path last date: {pd.to_datetime(sx5e_path.date).max().date()}")
print("\n=== 03 complete ===")
