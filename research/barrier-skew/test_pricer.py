"""
test_pricer.py
--------------
Validation gates for pricer.py (SPEC section 5). Run: python -m pytest test_pricer.py -v -s

Each test compares the engine with an independent answer:
  Black-Scholes closed form, Monte Carlo with exact daily GBM steps, and synthetic SSVI
  surfaces whose parameters are known.
"""

import time

import numpy as np
import pytest

import pricer as P

S, K, T, R, B = 100.0, 100.0, 1.0, 0.03, 0.01


def flat(sig):
    return lambda k, t: np.full_like(np.asarray(k, float), sig)


def mc_daily(H, sig, n=400_000, seed=7, chunk=20_000):
    """Daily-monitored DIP price and knock-in probability by Monte Carlo (antithetic)."""
    rng = np.random.default_rng(seed)
    dt = T / P.DAYS
    drift, vol = (B - 0.5 * sig ** 2) * dt, sig * np.sqrt(dt)
    pay, ki = [], []
    for _ in range(n // (2 * chunk)):
        z = rng.standard_normal((chunk, P.DAYS))
        for zz in (z, -z):
            lp = np.log(S) + np.cumsum(drift + vol * zz, axis=1)
            hit = lp.min(axis=1) <= np.log(H)
            pay.append(np.exp(-R * T) * hit * np.maximum(K - np.exp(lp[:, -1]), 0))
            ki.append(hit)
    pay, ki = np.concatenate(pay), np.concatenate(ki)
    # antithetic pairs are dependent: standard error from pair means
    pm = pay.reshape(2, -1).mean(axis=0)
    return pay.mean(), pm.std() / np.sqrt(pm.size), ki.mean(), np.sqrt(ki.mean() * (1 - ki.mean()) / ki.size)


def equity_ssvi():
    tn = np.array([30, 60, 91, 122, 152, 182, 273, 365, 547]) / 365
    theta = 0.04 * tn + 0.002 * np.sqrt(tn)          # ~20% ATM vol, mild term structure
    return P.SSVI(tn, theta, rho=-0.7, eta=1.2, gamma=0.4)


# ── Flat-vol engine ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("strike", [80.0, 100.0, 120.0])
def test_pde_vanilla_matches_black_scholes(strike):
    out = P.solve_barrier(S, strike, 1.0, T, R, B, flat(0.2))
    bs = P.bs_put(S, strike, T, R, B, 0.2)
    assert abs(out["put"] / bs - 1) < 1e-3, (out["put"], bs)


@pytest.mark.parametrize("sig", [0.15, 0.40])
@pytest.mark.parametrize("h", [60.0, 70.0, 80.0])
def test_daily_barrier_pde_and_closed_form_vs_mc(sig, h):
    mc, se, p_mc, p_se = mc_daily(h, sig)
    t0 = time.perf_counter()
    pde = P.solve_barrier(S, K, h, T, R, B, flat(sig))
    secs = time.perf_counter() - t0
    cf = P.dip_closed(S, K, h, T, R, B, sig, discrete=True)
    p_cf = P.ki_prob_closed(S, h, T, B, sig, discrete=True)
    print(f"\n  sig={sig} H={h}: MC {mc:.4f}±{se:.4f}  PDE {pde['dip']:.4f}  BGK {cf:.4f} | "
          f"P(KI) MC {p_mc:.4f}±{p_se:.4f}  PDE {pde['p_ki']:.4f}  BGK {p_cf:.4f} | PDE {secs:.2f}s")
    assert abs(pde["dip"] - mc) < 3 * se + 0.003 * mc + 1e-4
    assert abs(pde["p_ki"] - p_mc) < 3 * p_se + 1e-3
    assert abs(cf - mc) < 3 * se + 0.01 * mc + 1e-4          # BGK is an approximation: 1% band
    assert abs(p_cf - p_mc) < 3 * p_se + 2e-3


def test_in_out_parity_and_flat_equivalent_vol_roundtrip():
    out = P.solve_barrier(S, K, 70.0, T, R, B, flat(0.25))
    assert abs(out["dip"] + out["dop"] - out["put"]) < 1e-12
    price = P.dip_closed(S, K, 70.0, T, R, B, 0.25, discrete=True)
    assert abs(P.flat_equivalent_vol(price, S, K, 70.0, T, R, B) - 0.25) < 1e-6


# ── SSVI ──────────────────────────────────────────────────────────────────────
def test_ssvi_has_no_static_arbitrage():
    s = equity_ssvi()
    k = np.linspace(-3, 2, 501)
    ts = np.linspace(0.02, 1.5, 60)
    assert min(s.g(k, t).min() for t in ts) >= 0, "butterfly arbitrage"
    w = np.array([s.w(k, t) for t in ts])
    assert (np.diff(w, axis=0) >= -1e-12).all(), "calendar arbitrage"


def test_ssvi_fit_recovers_known_surface():
    s = equity_ssvi()
    Ts, ks = [], []
    for t in s.t_nodes:
        kk = np.linspace(-1.6, 0.6, 17) * np.sqrt(t) * 0.25      # delta grid spans ~±3 sd
        Ts += [t] * kk.size
        ks += list(kk)
    Ts, ks = np.array(Ts), np.array(ks)
    iv = s.iv(ks, Ts)
    fit, rmse, _ = P.fit_ssvi(Ts, ks, iv)
    print(f"\n  fit rmse {rmse:.4f} vp, rho {fit.rho:.3f} (true -0.7), eta {fit.eta:.3f} (1.2), gamma {fit.gamma:.3f} (0.4)")
    assert rmse < 0.05
    assert abs(fit.rho + 0.7) < 0.02


# ── Local vol ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("n_days", [126, 252])
def test_local_vol_pde_reprices_ssvi_vanillas(n_days):
    """Numerical gate: local vol PDE puts, inverted to implied vol, match SSVI within 0.25 vp."""
    s = equity_ssvi()
    t = n_days / P.DAYS
    errs = []
    for m in (0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2):
        k_strike = m * S
        out = P.solve_barrier(S, k_strike, 1.0, t, R, B, s.local_vol, n_days=n_days)
        iv_pde = P.implied_vol_put(out["put"], S, k_strike, t, R, B)
        iv_ssvi = float(s.iv(np.log(k_strike / (S * np.exp(B * t))), t))
        errs.append((m, iv_pde * 100, iv_ssvi * 100))
    print("\n  " + "  ".join(f"{m:.0%}: {a:.2f}/{b:.2f}" for m, a, b in errs))
    assert max(abs(a - b) for _, a, b in errs) < 0.25


def test_negative_skew_raises_knock_in_probability():
    s = equity_ssvi()
    lv = P.solve_barrier(S, K, 70.0, T, R, B, s.local_vol)
    atm = float(s.iv(0.0, T))
    p_flat = P.ki_prob_closed(S, 70.0, T, B, atm, discrete=True)
    print(f"\n  P(KI 70%): local vol {lv['p_ki']:.4f} vs ATM flat {p_flat:.4f} (ATM vol {atm:.3f})")
    assert lv["p_ki"] > p_flat
