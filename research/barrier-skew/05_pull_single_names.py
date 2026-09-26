# ruff: noqa
"""
05_pull_single_names.py
-----------------------
Batch A, script 3. Surfaces, spot, forwards and realised paths for the single-name universe.

  sn_surface     vsurfd OTM grid for each (candidate secid, start date) pair
  sn_spot        OptionMetrics close on each start date
  sn_fwd         fwdprd forwards (expirations up to 800 days) for each pair
  universe       final top 10 per start date: candidates whose surface is usable
  sn_path        CRSP daily prices, split-adjusted, for every permno in the final universe
  sn_delist      CRSP delisting records for those permnos
  sn_tickers     OptionMetrics ticker history (labels only)

Usable surface: the 273d and 365d tenors, and at least 8 of the 9 tenors up to 365d,
each have 15 or more of the 17 OTM points with a valid implied vol.
"""

import common as C
import pandas as pd

db = None
def conn():
    global db
    if db is None:
        db = C.connect()
    return db


def ids(s):
    return ",".join(str(int(x)) for x in sorted(set(s)))


def dates(s):
    return ",".join(f"'{pd.Timestamp(x).date()}'" for x in sorted(set(s)))


cand = C.cached("universe_candidates")
cand["start"] = pd.to_datetime(cand["start"])
cand["year"] = cand.start.dt.year
pairs = cand[["secid", "start"]]


def by_year_pairs(name, sql_fn):
    """Pull per year for the year's candidate secids x start dates, keep only real pairs."""
    if (df := C.cached(name)) is not None:
        return df
    parts = []
    for yr, g in cand.groupby("year"):
        part = conn().raw_sql(sql_fn(yr, ids(g.secid), dates(g.start)))
        part["date"] = pd.to_datetime(part["date"])
        part = part.merge(g[["secid", "start"]].rename(columns={"start": "date"}), on=["secid", "date"])
        print(f"    {name} {yr}: {len(part):,}")
        parts.append(part)
    return C.save(pd.concat(parts, ignore_index=True), name)


print("=== Surfaces, spot, forwards ===")
surf = by_year_pairs("sn_surface", lambda y, s, d: f"""
    SELECT secid, date, days, delta, cp_flag, impl_volatility, impl_strike
    FROM optionm_all.vsurfd{y} WHERE secid IN ({s}) AND date IN ({d}) AND {C.OTM_US}""")
spot = by_year_pairs("sn_spot", lambda y, s, d: f"""
    SELECT secid, date, close, cfadj FROM optionm_all.secprd{y} WHERE secid IN ({s}) AND date IN ({d})""")
fwd = by_year_pairs("sn_fwd", lambda y, s, d: f"""
    SELECT secid, date, expiration, amsettlement, forwardprice FROM optionm_all.fwdprd{y}
    WHERE secid IN ({s}) AND date IN ({d}) AND expiration <= date + 800""")

# ── Usable-surface filter, final top 10 ───────────────────────────────────────
s = surf[surf.days <= 365].copy()
s["ok"] = s.impl_volatility.notna() & (s.impl_volatility > 0)
per_tenor = s.groupby(["secid", "date", "days"])["ok"].sum().unstack("days").fillna(0)
good = per_tenor >= 15
usable = good[273.0] & good[365.0] & (good.sum(axis=1) >= 8)
usable = usable[usable].reset_index()[["secid", "date"]].rename(columns={"date": "start"})
usable["usable"] = True

u = cand.merge(usable, on=["secid", "start"], how="left").fillna({"usable": False})
u = u[u.usable].sort_values(["start", "rank"]).groupby("start").head(C.N_NAMES)
u = u.assign(final_rank=u.groupby("start").cumcount() + 1).drop(columns=["usable", "year"])
C.save(u, "universe")

# ── Realised paths + delistings for final permnos ─────────────────────────────
print("\n=== Paths ===")
permnos = ids(u.permno)
path = C.cached("sn_path")
if path is None:
    path = C.save(conn().raw_sql(f"""
        SELECT permno, dlycaldt AS date, dlyprc, dlycumfacpr, dlydelflg
        FROM crsp.dsf_v2 WHERE permno IN ({permnos}) AND dlycaldt >= '1996-01-01' ORDER BY permno, dlycaldt"""), "sn_path")
delist = C.cached("sn_delist")
if delist is None:
    delist = C.save(conn().raw_sql(f"""
        SELECT permno, delistingdt, deldtprc, delactiontype, delstatustype, delreasontype,
               delpaymenttype, delret, delnextprc, delamtdt
        FROM crsp.stkdelists WHERE permno IN ({permnos})"""), "sn_delist")
tick = C.cached("sn_tickers")
if tick is None:
    tick = C.save(conn().raw_sql(f"""
        SELECT secid, ticker, issuer, effect_date FROM optionm_all.secnmd WHERE secid IN ({ids(u.secid)})"""), "sn_tickers")
if db is not None:
    db.close()

# ── Checks ────────────────────────────────────────────────────────────────────
print("\n=== Checks ===")
n_per = u.groupby("start").size()
cand_starts = cand.start.nunique()
print(f"  starts with candidates: {cand_starts}, with a final universe: {n_per.size}, "
      f"with fewer than {C.N_NAMES} usable names: {(n_per < C.N_NAMES).sum()}")
print(f"  usable share of candidate pairs by era:")
cu = cand.merge(usable, on=["secid", "start"], how="left").fillna({"usable": False})
for lo, hi in ((1996, 2001), (2002, 2007), (2008, 2013), (2014, 2019), (2020, 2024)):
    x = cu[(cu.year >= lo) & (cu.year <= hi)]
    print(f"    {lo}-{hi}: {x.usable.mean():.1%} of {len(x):,} pairs")
print(f"  final (start, name) pairs: {len(u):,}, distinct names: {u.permno.nunique()}")

path["date"] = pd.to_datetime(path["date"])
last = path.groupby("permno")["date"].max()
need = u.groupby("permno")["start"].max() + pd.Timedelta(days=365)
short = need[need > last.reindex(need.index)]
dl = delist.set_index("permno")
print(f"  permnos whose path ends before their last product matures: {len(short)} "
      f"(all should be delistings): {short.index.isin(dl.index).sum()} have a delisting record")
if len(short):
    x = dl.loc[dl.index.intersection(short.index), ["delistingdt", "delactiontype", "delreasontype", "delpaymenttype", "deldtprc"]]
    print(x.to_string())

# CRSP vs OptionMetrics spot on start dates (raw, unadjusted prices should match)
sp =spot.merge(u[["secid", "start", "permno"]].rename(columns={"start": "date"}), on=["secid", "date"])
sp = sp.merge(path[["permno", "date", "dlyprc"]], on=["permno", "date"], how="left")
gap = (sp["close"] / sp["dlyprc"].abs() - 1).abs()
print(f"  OptionMetrics vs CRSP close on start dates: {gap.notna().sum():,} matched, "
      f"median gap {gap.median():.4%}, pairs >1%: {(gap > 0.01).sum()}")
print("\n=== 05 complete ===")
