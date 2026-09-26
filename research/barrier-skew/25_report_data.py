# ruff: noqa
"""
25_report_data.py
-----------------
Builds report_data.json: every number the report page shows, so the page's JS constants are the
single source of truth and the prose can quote them exactly.

Contents:
  smile        one illustrative SPX date: fitted 1y curve, OptionMetrics grid points, listed quotes
  slider       that date's knock-in probability and price at barriers 50-95% under all 3 models
               (real PDE and closed-form output, precomputed so the page's slider is not a toy)
  series       SPX 4-week means, per barrier: prices, equivalent vol, ATM and barrier vol
  summary      realised vs model, price, P&L, premium kept, ratio, bootstrap CIs, per set/barrier
  regimes      model minus realised by era and set
  episodes     knock-ins by start year
  calibration  binned model probability vs realised frequency
  terciles     single-name premium kept by ATM-vol tercile
  method       validation gate results, fit quality, exclusions, sample sizes, fee literature
"""

import json

import numpy as np
import pandas as pd

import common as C
import pricer as P
import prep

SMILE_DATE = pd.Timestamp("2023-05-03")      # a wing-gate date: listed quotes exist for the scatter
BARRIERS = (0.6, 0.7, 0.8)
SETS = {"SPX": ("stats_index", "SPX"), "SX5E": ("stats_index", "SX5E"), "SN": ("stats_sn", "SN")}
out = {}


def js(x):
    if isinstance(x, pd.Timestamp):
        return x.strftime("%Y-%m-%d")
    if isinstance(x, (float, np.floating)):
        return round(float(x), 4)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


stats = {k: json.load(open(C.DATA / f"{v[0]}.json", encoding="utf-8")) for k, v in
         {"index": ("stats_index",), "sn": ("stats_sn",)}.items()}
S = {"SPX": stats["index"]["SPX"], "SX5E": stats["index"]["SX5E"], "SN": stats["sn"]["SN"]}
S_clean = {"SPX": stats["index"]["SPX_clean"], "SX5E": stats["index"]["SX5E_clean"], "SN": stats["sn"]["SN_clean"]}

# ── 1. Smile and slider for one date ─────────────────────────────────────────
print("=== smile and slider ===")
m = prep.load_index("spx")
x, why = m.inputs(SMILE_DATE)
assert x is not None, why
surf, rmse, per = P.fit_ssvi(x["T"], x["k"], x["iv"])
S0, r, b = x["S"], x["r"], x["b"]
one = x["T"] == 1.0
mny_grid = np.linspace(0.45, 1.25, 161)
k_grid = np.log(mny_grid) - b                                    # 1y log-moneyness vs the forward
quotes = C.cached("wing_quotes")
quotes["date"] = pd.to_datetime(quotes["date"])
q = quotes[(quotes.date == SMILE_DATE) & quotes.impl_volatility.notna()]
out["smile"] = {
    "date": js(SMILE_DATE), "spot": js(S0), "rate": js(r), "carry": js(b), "fit_rmse_vp": js(rmse),
    "fitted": [{"m": js(mm), "iv": js(float(surf.iv(kk, 1.0)) * 100)} for mm, kk in zip(mny_grid, k_grid)],
    "grid": [{"m": js(float(np.exp(kk + b))), "iv": js(float(vv) * 100)}
             for kk, vv in zip(x["k"][one], x["iv"][one])],
    "quotes": [{"m": js(mm), "iv": js(vv)} for mm, vv in zip(q.moneyness, q.impl_volatility * 100)],
}
print(f"  {SMILE_DATE.date()}: spot {S0:.0f}, 1y ATM {surf.iv(0.0, 1.0)*100:.1f}%, "
      f"fit rmse {rmse:.2f} vp, {len(q)} listed quotes")

slider = []
for mb in np.round(np.arange(0.50, 0.96, 0.01), 2):
    H = mb * S0
    lv = P.solve_barrier(S0, S0, H, 1.0, r, b, surf.local_vol)
    sa = float(surf.iv(0.0, 1.0))
    sb = float(surf.iv(np.log(mb) - b, 1.0))
    slider.append({"barrier": js(mb), "atm_vol": js(sa * 100), "bar_vol": js(sb * 100),
                   "lv_p": js(lv["p_ki"] * 100), "atm_p": js(P.ki_prob_closed(S0, H, 1.0, b, sa, True) * 100),
                   "bar_p": js(P.ki_prob_closed(S0, H, 1.0, b, sb, True) * 100),
                   "lv_dip": js(lv["dip"] / S0 * 100),
                   "atm_dip": js(P.dip_closed(S0, S0, H, 1.0, r, b, sa, True) / S0 * 100),
                   "bar_dip": js(P.dip_closed(S0, S0, H, 1.0, r, b, sb, True) / S0 * 100)})
out["slider"] = slider
print(f"  slider: {len(slider)} barrier levels priced")

# ── 2. SPX time series (4-week means) ────────────────────────────────────────
print("\n=== time series ===")
px = C.cached("prices_spx")
px["date"] = pd.to_datetime(px["date"])
px = px[~((px.rmse > 3.0) | (px.rmse > 10.0 * px.sig_atm))]
out["series"] = {}
for bar in BARRIERS:
    g = px[px.barrier == bar].set_index("date").sort_index()
    w = g.resample("28D").mean(numeric_only=True).dropna(subset=["lv_dip"])
    out["series"][f"{bar:.1f}"] = [
        {"d": js(d), "lv": js(rw.lv_dip), "atm": js(rw.atm_dip), "bar": js(rw.bar_dip),
         "eq_vol": js(rw.eq_vol * 100), "atm_vol": js(rw.sig_atm * 100), "bar_vol": js(rw.sig_bar * 100)}
        for d, rw in w.iterrows()]
    print(f"  barrier {bar:.0%}: {len(w)} 4-week points")

# ── 3. Summary table ─────────────────────────────────────────────────────────
print("\n=== summary ===")
out["summary"] = {}
for name, s in S.items():
    out["summary"][name] = {}
    for bar in BARRIERS:
        b_ = s[f"{bar:.1f}"]
        row = {"realised": js(b_["realised_ki"] * 100), "n_starts": b_["n_starts"], "years": b_["years"],
               "first": b_["first"], "last": b_["last"]}
        for k in ("lv", "atm", "bar"):
            mm = b_[k]
            row[k] = {"p_ki": js(mm["p_ki"] * 100), "dip": js(mm["dip"]), "pnl": js(mm["pnl"]),
                      "gap": js(mm["gap"] * 100), "gap_lo": js(mm["gap_boot95"][0] * 100),
                      "gap_hi": js(mm["gap_boot95"][1] * 100), "gap_se": js(mm["gap_nw_se"] * 100),
                      "pnl_se": js(mm["pnl_nw_se"]), "win": js(mm["pnl_hit_rate"] * 100),
                      "kept": js(mm["pnl"] / mm["dip"] * 100),
                      "ratio": js(mm["p_ki"] / b_["realised_ki"])}
        # sensitivity: same numbers with flagged dates excluded
        c_ = S_clean[name][f"{bar:.1f}"]
        row["clean"] = {"realised": js(c_["realised_ki"] * 100),
                        **{k: js(c_[k]["p_ki"] * 100) for k in ("lv", "atm", "bar")}}
        out["summary"][name][f"{bar:.1f}"] = row
    print(f"  {name}: " + ", ".join(f"{bar:.0%} ratio {out['summary'][name][f'{bar:.1f}']['lv']['ratio']}"
                                    for bar in BARRIERS))

# ── 4. Regimes ───────────────────────────────────────────────────────────────
out["regimes"] = {name: {f"{bar:.1f}": s[f"{bar:.1f}"]["regimes"] for bar in BARRIERS} for name, s in S.items()}

# ── 5. Episodes: knock-ins by start year ─────────────────────────────────────
print("\n=== episodes ===")
oi, osn = C.cached("outcomes_index"), C.cached("outcomes_sn")
oi["date"], osn["date"] = pd.to_datetime(oi["date"]), pd.to_datetime(osn["date"])
out["episodes"] = {}
for name, df in (("SPX", oi[oi.underlying == "SPX"]), ("SX5E", oi[oi.underlying == "SX5E"]), ("SN", osn)):
    out["episodes"][name] = {}
    for bar in BARRIERS:
        g = df[df.barrier == bar]
        yr = g.groupby(g.date.dt.year).ki.agg(["mean", "size"])
        out["episodes"][name][f"{bar:.1f}"] = [{"y": int(y), "rate": js(rw["mean"] * 100), "n": int(rw["size"])}
                                               for y, rw in yr.iterrows()]
    print(f"  {name}: {len(out['episodes'][name]['0.7'])} start years")

# ── 6. Calibration ───────────────────────────────────────────────────────────
out["calibration"] = {name: {f"{bar:.1f}": S[name][f"{bar:.1f}"]["calibration_lv"] for bar in BARRIERS}
                      for name in SETS}

# ── 7. Single names by ATM-vol tercile ───────────────────────────────────────
print("\n=== single-name terciles ===")
sn = osn.copy()
sn["tercile"] = sn.groupby("barrier").sig_atm.transform(lambda s: pd.qcut(s, 3, labels=["low", "mid", "high"]))
ter = []
for (bar, t), g in sn.groupby(["barrier", "tercile"], observed=True):
    ter.append({"barrier": js(bar), "tercile": str(t), "n": int(len(g)), "vol": js(g.sig_atm.mean() * 100),
                "realised": js(g.ki.mean() * 100), "lv_p": js(g.lv_p_ki.mean() * 100),
                "dip": js(g.lv_dip.mean()), "pnl": js(g.lv_pnl.mean()),
                "kept": js(g.lv_pnl.mean() / g.lv_dip.mean() * 100)})
out["terciles"] = ter
for t in ter:
    if t["barrier"] == 0.7:
        print(f"  70% {t['tercile']:4s}: vol {t['vol']:.0f}%, realised {t['realised']:.0f}%, "
              f"model {t['lv_p']:.0f}%, kept {t['kept']:.0f}%")

# ── 8. Method and validation numbers ─────────────────────────────────────────
fs, fe = C.cached("fit_spx"), C.cached("fit_sx5e")
wing = C.cached("wing_gate")
sn_px = C.cached("prices_sn")
u = sn_px.drop_duplicates(["secid", "date"])
excl = (u.rmse > 3.0) | (u.rmse > 10.0 * u.sig_atm)
out["method"] = {
    "spx_fit_rmse_median": js(fs.rmse.median()), "sx5e_fit_rmse_median": js(fe.rmse.median()),
    "sn_fit_rmse_median": js(u.rmse.median()),
    "wing_n": int(len(wing)), "wing_mae": js(wing.gap.abs().mean()), "wing_mean_gap": js(wing.gap.mean()),
    "wing_near60_mae": js(wing[(wing.moneyness >= 0.57) & (wing.moneyness <= 0.63)].gap.abs().mean()),
    "sn_dates": int(len(u)), "sn_excluded": int(excl.sum()), "sn_excluded_pct": js(excl.mean() * 100),
    "sn_names": int(sn_px.permno.nunique()), "sn_products": int(len(u) - excl.sum()),
    "spx_starts": S["SPX"]["0.7"]["n_starts"], "sx5e_starts": S["SX5E"]["0.7"]["n_starts"],
    "spx_years": S["SPX"]["0.7"]["years"], "sx5e_years": S["SX5E"]["0.7"]["years"],
    "sn_years": S["SN"]["0.7"]["years"],
    "fees": [{"source": "Vokata (2021), JFE, 28,000+ US yield enhancement notes 2006-2015",
              "value": "6-7% per year"},
             {"source": "Henderson and Pearson (2011), JFE, 64 SPARQS issues", "value": "about 8% of issue price"},
             {"source": "Wallmeier and Diethelm (2009), Swiss barrier reverse convertibles", "value": "3.4%"},
             {"source": "Stoimenov and Wilkens (2005), German market", "value": "about 3%"}],
}

with open(C.DATA / "report_data.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1)
print(f"\n  [saved] report_data.json ({(C.DATA / 'report_data.json').stat().st_size / 1024:.0f} KB)")
print("=== 25 complete ===")
