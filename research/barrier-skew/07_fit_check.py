# ruff: noqa
"""
07_fit_check.py
---------------
Gates on real data before the main pricing run (SPEC section 5):
  1. SSVI fit quality on every weekly SPX and SX5E start date (rmse overall, at 1y, and at the
     deepest 1y put, which is the grid point nearest the barriers)
  2. No-arbitrage check on the fitted surface (Durrleman g >= 0 over the pricing range)
  3. Wing gate: fitted SPX vol vs raw listed put quotes at 55-75% moneyness, 20 sample dates.
     Pass = mean absolute gap within 1.5 vol points.
Outputs: fit_spx, fit_sx5e, wing_gate (parquet) and the summary below.
"""

import time

import numpy as np
import pandas as pd

import common as C
import pricer as P
import prep

K_CHECK = np.linspace(-2.5, 1.0, 141)
T_CHECK = np.array([0.05, 0.25, 0.5, 0.75, 1.0])


def fit_all(name, starts):
    m = prep.load_index(name)
    rows, skipped = [], {}
    t0 = time.perf_counter()
    for d in starts:
        x, why = m.inputs(d)
        if x is None:
            skipped[why] = skipped.get(why, 0) + 1
            continue
        surf, rmse, per = P.fit_ssvi(x["T"], x["k"], x["iv"])
        one = x["T"] == 1.0
        deep = one & (x["k"] == x["k"][one].min())
        g_min = min(surf.g(K_CHECK, t).min() for t in T_CHECK)
        lv = surf.local_vol(np.linspace(-1.0, 0.3, 27), 0.5)
        rows.append({"date": d, "rmse": rmse, "rmse_1y": per.get(1.0, np.nan),
                     "deep_k": float(x["k"][deep][0]), "deep_mkt": float(x["iv"][deep][0]) * 100,
                     "deep_fit": float(surf.iv(x["k"][deep][0], 1.0)) * 100,
                     "atm_1y": float(surf.iv(0.0, 1.0)) * 100,
                     "rho": surf.rho, "eta": surf.eta, "gamma": surf.gamma, "g_min": g_min,
                     "lv_min": lv.min(), "lv_max": lv.max(), "r": x["r"], "b": x["b"]})
    secs = time.perf_counter() - t0
    df = pd.DataFrame(rows)
    print(f"\n=== {name.upper()}: {len(df)} fitted, skipped {skipped}, {secs / max(len(df), 1):.2f}s per fit ===")
    q = df[["rmse", "rmse_1y"]].describe(percentiles=[0.5, 0.9, 0.99]).T[["mean", "50%", "90%", "99%", "max"]]
    print(q.round(3).to_string())
    gap = df.deep_fit - df.deep_mkt
    print(f"  deepest 1y put (moneyness k median {df.deep_k.median():.2f}): fit - market median {gap.median():+.2f} vp, "
          f"|gap| p90 {gap.abs().quantile(0.9):.2f}, max {gap.abs().max():.2f}")
    print(f"  arbitrage: dates with g < 0: {(df.g_min < 0).sum()}  | local vol at t=0.5 over k in [-1, 0.3]: "
          f"min {df.lv_min.min():.3f}, max {df.lv_max.max():.3f}")
    print(f"  params: rho median {df.rho.median():.2f} [{df.rho.min():.2f}, {df.rho.max():.2f}], "
          f"gamma median {df.gamma.median():.2f}, eta median {df.eta.median():.2f}")
    worst = df.nlargest(5, "rmse")[["date", "rmse", "rmse_1y", "deep_mkt", "deep_fit"]]
    print("  worst 5 fits:\n" + worst.round(2).to_string(index=False))
    return C.save(df, f"fit_{name}")


spx_starts = pd.to_datetime(C.cached("start_dates_us")["start"])
fit_spx = fit_all("spx", spx_starts)

eu_days = pd.to_datetime(C.cached("sx5e_path")["date"])
sx5e_starts = C.weekly_starts(eu_days, C.EU_FIRST, C.EU_LAST_START)
C.save(pd.DataFrame({"start": sx5e_starts}), "start_dates_eu")
fit_sx5e = fit_all("sx5e", sx5e_starts)

# ── Wing gate ─────────────────────────────────────────────────────────────────
print("\n=== Wing gate: fitted SPX vol vs listed 1y puts, 55-75% moneyness ===")
m = prep.load_index("spx")
q = C.cached("wing_quotes")
q["date"], q["exdate"] = pd.to_datetime(q["date"]), pd.to_datetime(q["exdate"])
q = q[(q.moneyness >= 0.55) & (q.moneyness <= 0.75) & q.impl_volatility.notna()]
out = []
for d, g in q.groupby("date"):
    x, why = m.inputs(d)
    if x is None:
        continue
    surf, _, _ = P.fit_ssvi(x["T"], x["k"], x["iv"])
    tb, bb = m.carry_curve(d)
    t = (g.exdate - d).dt.days.to_numpy() / 365
    k = np.log(g.strike.to_numpy() / (x["S"] * np.exp(np.interp(t, tb, bb) * t)))
    fit = surf.iv(k, t) * 100
    mkt = g.impl_volatility.to_numpy() * 100
    for mn, f_, m_ in zip(g.moneyness, fit, mkt):
        out.append({"date": d, "moneyness": mn, "fit": f_, "mkt": m_})
w = pd.DataFrame(out)
w["gap"] = w.fit - w.mkt
C.save(w, "wing_gate")
by = w.groupby("date").agg(n=("gap", "size"), mean_gap=("gap", "mean"), mae=("gap", lambda x: x.abs().mean()))
print(by.round(2).to_string())
band = w[(w.moneyness >= 0.57) & (w.moneyness <= 0.63)]
mae = w.gap.abs().mean()
print(f"\n  all quotes: n {len(w)}, mean gap {w.gap.mean():+.2f} vp, MAE {mae:.2f} vp")
print(f"  near 60% (57-63%): n {len(band)}, mean gap {band.gap.mean():+.2f} vp, MAE {band.gap.abs().mean():.2f} vp")
print(f"  GATE (MAE <= 1.5 vp): {'PASS' if mae <= 1.5 else 'FAIL'}")
print("\n=== 07 complete ===")
