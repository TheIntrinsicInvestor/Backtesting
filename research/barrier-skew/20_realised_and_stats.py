# ruff: noqa
"""
20_realised_and_stats.py
------------------------
Scores every priced product against what actually happened, then runs the statistics.
Usage: python 20_realised_and_stats.py index | sn

Realised outcome (per start date d, barrier m):
  path      daily closes on trading days in (d, d + 365 calendar days]
  knock-in  any close <= m * S0
  payoff    if knocked in: max(S0 - S_T, 0), % of notional
  seller    premium * exp(r) - payoff, per model (unhedged sell-and-hold)

Statistics (overlapping 1y windows started weekly):
  gap = model P(KI) - realised knock-in frequency. Mean with Newey-West SE (52 lags) and a
  moving-block bootstrap (52-week blocks). Single names are averaged across names per start
  date first, so each week is one observation (clusters by date). Effective N = years of data.
Outputs: outcomes_<set>.parquet, stats_<set>.json
"""

import json
import sys

import numpy as np
import pandas as pd

import common as C

MODELS = {"lv": "local vol", "atm": "ATM flat", "bar": "barrier flat"}
# Unusable surface fits are dropped from the headline (Brian, 2026-09-23). rmse is in vol points,
# sig_atm is a decimal, so "10% of ATM vol in vol points" is 10 * sig_atm.
MAX_RMSE_VP, MAX_RMSE_REL = 3.0, 10.0
REGIMES = [("1996-2007", "1996-01-01", "2007-06-30"), ("2007-2009 GFC", "2007-07-01", "2009-12-31"),
           ("2010-2019", "2010-01-01", "2019-12-31"), ("2020 onward", "2020-01-01", "2030-01-01")]


def outcome(dates, levels, d, S0, barriers):
    """Knock-in flag, payoff (% notional) and first-touch date for each barrier."""
    lo, hi = np.searchsorted(dates, d, side="right"), np.searchsorted(dates, d + np.timedelta64(365, "D"), side="right")
    p = levels[lo:hi]
    if hi - lo < 240:                                  # incomplete path: product not yet matured
        return None
    out = {}
    for m in barriers:
        hit = np.nonzero(p <= m * S0)[0]
        ki = hit.size > 0
        out[m] = (ki, max(S0 - p[-1], 0) / S0 * 100 if ki else 0.0, dates[lo + hit[0]] if ki else pd.NaT)
    return out


def newey_west(x, lags=52):
    x = np.asarray(x, float) - np.mean(x)
    n = x.size
    v = x @ x / n
    for L in range(1, lags + 1):
        v += 2 * (1 - L / (lags + 1)) * (x[L:] @ x[:-L]) / n
    return np.sqrt(v / n)


def block_bootstrap(x, block=52, n_boot=4000, seed=11):
    rng = np.random.default_rng(seed)
    x = np.asarray(x, float)
    n = x.size
    k = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(n_boot, k))
    idx = (starts[:, :, None] + np.arange(block)).reshape(n_boot, -1)[:, :n]
    means = x[idx].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def stats_for(df):
    """df: one row per start date (already averaged across names), columns per model."""
    df = df.sort_values("date")
    res = {"n_starts": int(len(df)),
           "years": round((df.date.max() - df.date.min()).days / 365.25 + 1, 1),
           "first": str(df.date.min().date()), "last": str(df.date.max().date()),
           "realised_ki": float(df.ki.mean())}
    for key, label in MODELS.items():
        gap = df[f"{key}_p_ki"] - df.ki
        pnl = df[f"{key}_pnl"]
        lo, hi = block_bootstrap(gap)
        res[key] = {"label": label, "p_ki": float(df[f"{key}_p_ki"].mean()),
                    "gap": float(gap.mean()), "gap_nw_se": float(newey_west(gap)), "gap_boot95": [lo, hi],
                    "dip": float(df[f"{key}_dip"].mean()), "pnl": float(pnl.mean()),
                    "pnl_nw_se": float(newey_west(pnl)), "pnl_boot95": list(block_bootstrap(pnl)),
                    "pnl_hit_rate": float((pnl > 0).mean())}
    res["regimes"] = {}
    for name, a, b in REGIMES:
        r = df[(df.date >= a) & (df.date <= b)]
        if len(r):
            res["regimes"][name] = {"n": int(len(r)), "realised": float(r.ki.mean()),
                                    **{k: float(r[f"{k}_p_ki"].mean()) for k in MODELS}}
    # calibration: bin by local vol probability
    bins = [0, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0]
    cut = pd.cut(df.lv_p_ki, bins, include_lowest=True)
    res["calibration_lv"] = [{"bin": str(i), "n": int(len(g)), "model": float(g.lv_p_ki.mean()), "realised": float(g.ki.mean())}
                             for i, g in df.groupby(cut, observed=True)]
    return res


def score(prices, paths):
    """Attach realised outcomes and per-model seller P&L to each priced row.

    The start level is read from the path itself, never from the OptionMetrics quote: CRSP prices
    are split-adjusted, so mixing a raw start price with an adjusted path turns a 4-for-1 split
    into a fake knock-in.
    """
    rows, ratios = [], []
    for (u, pk), g in prices.groupby(["underlying", "permno"]):
        dates, levels = paths[(u, pk)]
        for d, gd in g.groupby("date"):
            i0 = np.searchsorted(dates, np.datetime64(d), side="right") - 1
            if i0 < 0:
                continue
            S0 = levels[i0]
            ratios.append(S0 / gd.S.iloc[0])
            o = outcome(dates, levels, np.datetime64(d), S0, gd.barrier.tolist())
            if o is None:
                continue
            for r in gd.itertuples():
                ki, pay, first = o[r.barrier]
                row = r._asdict()
                row.update(ki=float(ki), payoff=pay, first_touch=first)
                for k in MODELS:
                    row[f"{k}_pnl"] = row[f"{k}_dip"] * np.exp(r.r) - pay
                rows.append(row)
    r = np.array(ratios)
    print(f"  path start level / OptionMetrics spot: median {np.median(r):.4f}, "
          f"products where they differ by >1% (splits): {(np.abs(r - 1) > 0.01).sum()} of {r.size}")
    return pd.DataFrame(rows).drop(columns="Index")


def drop_unusable(prices):
    bad = (prices.rmse > MAX_RMSE_VP) | (prices.rmse > MAX_RMSE_REL * prices.sig_atm)
    dates = prices[["underlying", "secid", "date"]].drop_duplicates()
    kept = prices[~bad]
    print(f"  excluded {bad.sum() // 3} of {len(dates)} fitted dates ({bad.mean():.1%} of rows) as unusable fits; "
          f"{kept.flag.sum() // 3} of the rest stay flagged")
    return kept


def index_paths():
    p = {}
    for u, name in (("SPX", "spx_path"), ("SX5E", "sx5e_path")):
        x = C.cached(name)
        x["date"] = pd.to_datetime(x["date"])
        x = x.sort_values("date")
        p[(u, 0)] = (x.date.to_numpy(), x.level.to_numpy(float))
    return p


def sn_paths(prices):
    """Split-adjusted CRSP closes; delisted names end at the delisting price held flat."""
    path = C.cached("sn_path")
    dl = C.cached("sn_delist")
    path["date"] = pd.to_datetime(path["date"])
    path["adj"] = path.dlyprc.abs() / path.dlycumfacpr
    p = {}
    for pk, g in path.groupby("permno"):
        g = g.dropna(subset=["adj"]).sort_values("date")
        dates, lv = g.date.to_numpy(), g.adj.to_numpy(float)
        d = dl[dl.permno == pk]
        if len(d) and pd.notna(d.delistingdt.iloc[0]):
            fac = g.dlycumfacpr.iloc[-1]
            last = lv[-1]
            ret = d.delret.iloc[0]
            final = last * (1 + ret) if pd.notna(ret) else (abs(d.deldtprc.iloc[0]) / fac if pd.notna(d.deldtprc.iloc[0]) else last)
            ext = pd.bdate_range(pd.Timestamp(dates[-1]) + pd.Timedelta(days=1), periods=260).to_numpy()
            dates, lv = np.r_[dates, ext], np.r_[lv, np.full(ext.size, final)]
        p[("SN", pk)] = (dates, lv)
    return p


def per_date(df):
    """Average across names at each start date so each week counts once."""
    cols = ["ki"] + [f"{k}_{c}" for k in MODELS for c in ("p_ki", "dip", "pnl")]
    return df.groupby(["barrier", "date"])[cols].mean().reset_index()


def report(label, df):
    out = {}
    for m, g in df.groupby("barrier"):
        s = stats_for(g)
        out[f"{m:.1f}"] = s
        print(f"\n  {label} barrier {m:.0%}: {s['n_starts']} starts over {s['years']} yrs, realised knock-in {s['realised_ki']:.1%}")
        for k in MODELS:
            x = s[k]
            print(f"    {x['label']:13s} P(KI) {x['p_ki']:.1%}  gap {x['gap']*100:+.1f}pp (NW se {x['gap_nw_se']*100:.1f}, "
                  f"boot95 [{x['gap_boot95'][0]*100:+.1f}, {x['gap_boot95'][1]*100:+.1f}])  "
                  f"DIP {x['dip']:.2f}%  seller P&L {x['pnl']:+.2f}% (NW se {x['pnl_nw_se']:.2f}, win {x['pnl_hit_rate']:.0%})")
    return out


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "index"
    results = {}
    if which == "index":
        prices = pd.concat([C.cached("prices_spx"), C.cached("prices_sx5e")])
        prices["date"] = pd.to_datetime(prices["date"])
        sc = score(drop_unusable(prices), index_paths())
        C.save(sc, "outcomes_index")
        for u, g in sc.groupby("underlying"):
            results[u] = report(u, g)
            results[u + "_clean"] = report(u + " (flagged dates excluded)", g[~g.flag])
        name = "stats_index"
    else:
        prices = C.cached("prices_sn")
        prices["date"] = pd.to_datetime(prices["date"])
        sc = score(drop_unusable(prices), sn_paths(prices))
        C.save(sc, "outcomes_sn")
        results["SN"] = report("Single names (date-averaged)", per_date(sc))
        results["SN_clean"] = report("Single names, flagged excluded", per_date(sc[~sc.flag]))
        name = "stats_sn"
    with open(C.DATA / f"{name}.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, default=str)
    print(f"\n  [saved] {name}.json\n=== 20 complete ===")
