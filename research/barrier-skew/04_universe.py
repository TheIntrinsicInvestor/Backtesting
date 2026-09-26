# ruff: noqa
"""
04_universe.py
--------------
Batch A, script 2. Point-in-time single-name universe, no hindsight.

At each weekly start date d:
  eligible  = S&P 500 members on d (crsp.dsp500list_v2), linked to an OptionMetrics secid on d
              (wrdsapps_link_crsp_optionm.opcrsphist, score 1 only)
  ranking   = total option volume (calls + puts, opvold cp_flag NULL rows) over the 13 full
              weeks before the start week
  dedupe    = one share class per company (permco), keeping the most traded
  output    = top 15 candidates; 05 keeps the top 10 that also have a usable 1y surface

Single-name starts begin once 13 full weeks of volume exist (opvold starts 1996-01-04).
Outputs: start_dates_us, sp500_members, optm_link, opvol_weekly, universe_candidates
"""

import common as C
import pandas as pd

db = None
def conn():
    global db
    if db is None:
        db = C.connect()
    return db


def single(name, sql):
    if (df := C.cached(name)) is not None:
        return df
    return C.save(conn().raw_sql(sql), name)


# ── Start dates (SPX trading calendar) ────────────────────────────────────────
spot = C.cached("spx_spot")
starts = C.weekly_starts(spot["date"], C.US_FIRST, C.US_LAST_START)
C.save(pd.DataFrame({"start": starts}), "start_dates_us")
print(f"  US weekly starts: {len(starts)}  ({starts[0].date()} to {starts[-1].date()})")

# ── Membership, link, company ids ─────────────────────────────────────────────
members = single("sp500_members", """
    SELECT permno, mbrstartdt, mbrenddt FROM crsp.dsp500list_v2 WHERE mbrenddt >= '1995-01-01'""")
link = single("optm_link", "SELECT secid, sdate, edate, permno, score FROM wrdsapps_link_crsp_optionm.opcrsphist")
permnos = ",".join(str(int(p)) for p in members["permno"].unique())
permco = single("permco_map", f"""
    SELECT DISTINCT permno, permco FROM crsp.stksecurityinfohist WHERE permno IN ({permnos})""")

link = link[link["score"] == 1].copy()
link = link[link["permno"].isin(members["permno"])]
for df, cols in ((members, ("mbrstartdt", "mbrenddt")), (link, ("sdate", "edate"))):
    for c in cols:
        df[c] = pd.to_datetime(df[c])
print(f"  S&P 500 permnos since 1995: {members.permno.nunique():,}, linked secids (score 1): {link.secid.nunique():,}")

# ── Weekly option volume for linked secids ────────────────────────────────────
secids = ",".join(str(int(s)) for s in link["secid"].unique())
opvol = single("opvol_weekly", f"""
    SELECT secid, date_trunc('week', date)::date AS wk, SUM(volume) AS vol
    FROM optionm_all.opvold
    WHERE cp_flag IS NULL AND secid IN ({secids}) AND date <= '{C.US_LAST_START}'
    GROUP BY secid, wk""")
opvol["wk"] = pd.to_datetime(opvol["wk"])
if db is not None:
    db.close()

# ── Rank at each start date ───────────────────────────────────────────────────
first_full = opvol["wk"].min() + pd.Timedelta(weeks=C.VOL_WEEKS)
pm = permco.drop_duplicates("permno").set_index("permno")["permco"]
rows = []
for d in starts:
    wk0 = d - pd.Timedelta(days=d.dayofweek)          # Monday of the start week
    if wk0 < first_full:
        continue
    lo = wk0 - pd.Timedelta(weeks=C.VOL_WEEKS)
    mem = members[(members.mbrstartdt <= d) & (members.mbrenddt >= d)]["permno"]
    lk = link[(link.sdate <= d) & (link.edate >= d) & link.permno.isin(mem)][["secid", "permno"]]
    v = opvol[(opvol.wk >= lo) & (opvol.wk < wk0)].groupby("secid")["vol"].sum()
    lk = lk.assign(vol=lk.secid.map(v).fillna(0), permco=lk.permno.map(pm))
    lk = lk.sort_values("vol", ascending=False).drop_duplicates("permco").head(C.N_CANDIDATES)
    lk = lk.assign(start=d, rank=range(1, len(lk) + 1), n_members=len(mem))
    rows.append(lk)

cand = pd.concat(rows, ignore_index=True)
C.save(cand, "universe_candidates")

# ── Checks ────────────────────────────────────────────────────────────────────
print("\n=== Checks ===")
per = cand.groupby("start").agg(n=("secid", "size"), members=("n_members", "first"))
print(f"  single-name starts: {per.index.nunique()} ({per.index.min().date()} to {per.index.max().date()})")
print(f"  S&P members per date: min {per.members.min()}, max {per.members.max()} (expect ~490-505)")
print(f"  candidates per date: min {per.n.min()}  | distinct secids ever in top 15: {cand.secid.nunique()}, "
      f"in top 10: {cand[cand['rank'] <= C.N_NAMES].secid.nunique()}")

# Readable tickers for spot checks
tk = C.connect()
names = tk.raw_sql(f"""SELECT secid, ticker, effect_date FROM optionm_all.secnmd
                       WHERE secid IN ({','.join(str(int(s)) for s in cand.secid.unique())})""")
tk.close()
names["effect_date"] = pd.to_datetime(names["effect_date"])
names = names.sort_values("effect_date")
def ticker(secid, d):
    n = names[(names.secid == secid) & (names.effect_date <= d)]
    return n.ticker.iloc[-1] if len(n) else "?"
for d in ("1998-06-03", "2003-03-12", "2008-10-08", "2015-06-03", "2020-03-18", "2024-06-05"):
    d = pd.Timestamp(d)
    s = cand[cand.start == cand.start[cand.start >= d].min()]
    print(f"  {s.start.iloc[0].date()}: " + ", ".join(ticker(r.secid, r.start) for r in s.head(C.N_NAMES).itertuples()))
print("\n=== 04 complete ===")
