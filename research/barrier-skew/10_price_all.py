# ruff: noqa
"""
10_price_all.py
---------------
Main pricing run. Usage:  python 10_price_all.py index   (SPX + SX5E)
                          python 10_price_all.py sn      (single-name universe)

For each (underlying, start date): fit SSVI, then for barriers 60/70/80% of spot on a
1y at-the-money down-and-in put (daily close monitoring):
  local vol    PDE: DIP price, vanilla put, knock-in probability
  ATM flat     closed form + BGK: DIP price, knock-in probability (1y ATM-forward vol)
  barrier flat closed form + BGK with the 1y vol at the barrier strike
  eq_vol       the flat vol that reproduces the local vol DIP price
Prices are % of notional. Quality flags: rmse > 1 vp, rho at its bound, local vol floor hit.
Outputs: prices_spx, prices_sx5e, prices_sn
"""

import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

import common as C
import pricer as P
import prep

BARRIERS = (0.6, 0.7, 0.8)


def price_one(task):
    meta, x = task
    surf, rmse, _ = P.fit_ssvi(x["T"], x["k"], x["iv"])
    S, r, b = x["S"], x["r"], x["b"]
    sig_atm = float(surf.iv(0.0, 1.0))
    lv_floor = float(surf.local_vol(np.linspace(-1.2, 0.3, 31), 0.5).min()) < 0.05
    rows = []
    for m in BARRIERS:
        H = m * S
        lv = P.solve_barrier(S, S, H, 1.0, r, b, surf.local_vol)
        sig_bar = float(surf.iv(np.log(m) - b, 1.0))
        rows.append({**meta, "barrier": m, "S": S, "r": r, "b": b, "sig_atm": sig_atm, "sig_bar": sig_bar,
                     "lv_p_ki": lv["p_ki"], "lv_dip": lv["dip"] / S * 100, "lv_put": lv["put"] / S * 100,
                     "atm_p_ki": P.ki_prob_closed(S, H, 1.0, b, sig_atm, discrete=True),
                     "atm_dip": P.dip_closed(S, S, H, 1.0, r, b, sig_atm, discrete=True) / S * 100,
                     "bar_p_ki": P.ki_prob_closed(S, H, 1.0, b, sig_bar, discrete=True),
                     "bar_dip": P.dip_closed(S, S, H, 1.0, r, b, sig_bar, discrete=True) / S * 100,
                     "eq_vol": P.flat_equivalent_vol(lv["dip"], S, S, H, 1.0, r, b),
                     "rmse": rmse, "rho": surf.rho,
                     "flag": (rmse > 1.0) or (surf.rho <= -0.99) or lv_floor})
    return rows


def index_tasks(name, starts):
    m = prep.load_index(name)
    tasks, skipped = [], 0
    for d in starts:
        x, _ = m.inputs(d)
        if x is None:
            skipped += 1
            continue
        tasks.append(({"underlying": name.upper(), "secid": 0, "permno": 0, "date": d}, x))
    print(f"  {name}: {len(tasks)} tasks, {skipped} skipped (missing inputs)")
    return tasks


def sn_tasks():
    u = C.cached("universe")
    u["start"] = pd.to_datetime(u["start"])
    surf, fwd, spot = C.cached("sn_surface"), C.cached("sn_fwd"), C.cached("sn_spot")
    zero = C.cached("us_zero")
    tasks, skipped = [], 0
    for secid, g in u.groupby("secid"):
        m = prep.Market(surf[surf.secid == secid], fwd[fwd.secid == secid], zero,
                        spot[spot.secid == secid], True)
        for row in g.itertuples():
            x, _ = m.inputs(row.start)
            if x is None:
                skipped += 1
                continue
            tasks.append(({"underlying": "SN", "secid": int(secid), "permno": int(row.permno),
                           "date": row.start, "final_rank": int(row.final_rank)}, x))
    print(f"  single names: {len(tasks)} tasks, {skipped} skipped (missing inputs)")
    del surf, fwd, spot, zero, m          # tasks hold only small arrays; free the big tables
    return tasks


WORKERS = 4        # low enough to leave memory headroom on a 16 GB machine
BATCH = 1000       # checkpoint: each batch is saved as it finishes, so a kill loses one batch at most


def run(tasks, out_name):
    if (df := C.cached(out_name)) is not None:
        return df
    t0 = time.perf_counter()
    parts = []
    with Pool(WORKERS) as pool:
        for i in range(0, len(tasks), BATCH):
            f = C.DATA / f"{out_name}_part{i // BATCH:03d}.parquet"
            if not f.exists():
                res = pool.map(price_one, tasks[i:i + BATCH], chunksize=8)
                pd.DataFrame([r for rows in res for r in rows]).to_parquet(f, index=False)
                print(f"    batch {i // BATCH + 1}/{-(-len(tasks) // BATCH)} done, "
                      f"{(time.perf_counter() - t0) / 60:.1f} min elapsed", flush=True)
            parts.append(f)
    df = pd.concat([pd.read_parquet(f) for f in parts], ignore_index=True)
    print(f"  {out_name}: {len(tasks)} dates priced in {(time.perf_counter() - t0) / 60:.1f} min")
    df = C.save(df, out_name)
    for f in parts:
        f.unlink()
    return df


def summary(df):
    g = df.groupby("barrier")
    s = pd.DataFrame({
        "P(KI) local vol": g.lv_p_ki.mean() * 100, "P(KI) ATM flat": g.atm_p_ki.mean() * 100,
        "P(KI) barrier flat": g.bar_p_ki.mean() * 100,
        "DIP local vol": g.lv_dip.mean(), "DIP ATM flat": g.atm_dip.mean(), "DIP barrier flat": g.bar_dip.mean(),
        "eq vol": g.eq_vol.mean() * 100, "ATM vol": g.sig_atm.mean() * 100, "barrier vol": g.sig_bar.mean() * 100,
        "flagged dates": g.flag.sum()})
    print(s.round(2).T.to_string())


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "index"
    if which == "index":
        for name, starts in (("spx", C.cached("start_dates_us")["start"]), ("sx5e", C.cached("start_dates_eu")["start"])):
            print(f"\n=== {name.upper()} ===")
            df = run(index_tasks(name, pd.to_datetime(starts)), f"prices_{name}")
            summary(df)
    else:
        print("\n=== Single names ===")
        df = run(sn_tasks(), "prices_sn")
        summary(df)
    print("\n=== 10 complete ===")
