"""
pricer.py
---------
Pricing engine for the barrier-skew study. No I/O, no WRDS.

  Flat vol     bs_put, dip_closed (Reiner-Rubinstein), ki_prob_closed; discrete=True applies
               the Broadie-Glasserman-Kou shift for daily monitoring
  Surface      SSVI (Gatheral-Jacquier 2014, power-law phi), fit_ssvi, Durrleman g
  Local vol    Gatheral's formula from SSVI total variance: sigma^2 = dw/dt / g(k)
  PDE          solve_barrier: theta-scheme finite differences in y = ln S with Rannacher
               smoothing after each monitoring date. Returns vanilla put, down-and-out put,
               down-and-in put and the risk-neutral knock-in probability in one pass.

Conventions: T in years, rates continuously compounded, b = r - q (carry),
k = ln(K / F_t) with F_t = S0 * exp(b t). A close at or below H counts as a knock-in.
"""

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.linalg import solve_banded
from scipy.optimize import brentq, least_squares
from scipy.stats import norm

BGK = 0.5826          # Broadie-Glasserman-Kou constant
DAYS = 252


# ── Flat volatility ───────────────────────────────────────────────────────────
def bs_put(S, K, T, r, b, sig):
    F, sd = S * np.exp(b * T), sig * np.sqrt(T)
    d1 = (np.log(F / K) + 0.5 * sd * sd) / sd
    return np.exp(-r * T) * (K * norm.cdf(-d1 + sd) - F * norm.cdf(-d1))


def implied_vol_put(price, S, K, T, r, b):
    lo = bs_put(S, K, T, r, b, 1e-4)
    if price <= lo + 1e-12:
        return np.nan
    return brentq(lambda s: bs_put(S, K, T, r, b, s) - price, 1e-4, 5.0, xtol=1e-10)


def _bgk(H, sig, discrete, n_days=DAYS, T=1.0):
    return H * np.exp(-BGK * sig * np.sqrt(T / n_days)) if discrete else H


def dip_closed(S, K, H, T, r, b, sig, discrete=False, n_days=DAYS):
    """Down-and-in put, H < K, no rebate (Haug: B - C + D)."""
    H = _bgk(H, sig, discrete, n_days, T)
    if S <= H:
        return bs_put(S, K, T, r, b, sig)
    sd = sig * np.sqrt(T)
    mu = (b - 0.5 * sig ** 2) / sig ** 2
    carry, df = np.exp((b - r) * T), np.exp(-r * T)
    x2 = np.log(S / H) / sd + (1 + mu) * sd
    y1 = np.log(H * H / (S * K)) / sd + (1 + mu) * sd
    y2 = np.log(H / S) / sd + (1 + mu) * sd
    # (H/S)^(2mu) * N(z) in log space: at low vol with negative carry the power alone overflows
    lhs = np.log(H / S)
    e1 = lambda z: np.exp(2 * (mu + 1) * lhs + norm.logcdf(z))
    e2 = lambda z: np.exp(2 * mu * lhs + norm.logcdf(z))
    B = -S * carry * norm.cdf(-x2) + K * df * norm.cdf(-x2 + sd)
    Cc = -S * carry * e1(y1) + K * df * e2(y1 - sd)
    D = -S * carry * e1(y2) + K * df * e2(y2 - sd)
    return B - Cc + D


def ki_prob_closed(S, H, T, b, sig, discrete=False, n_days=DAYS):
    """Risk-neutral probability that S touches H (below S) before T."""
    H = _bgk(H, sig, discrete, n_days, T)
    a, nu, sd = np.log(H / S), b - 0.5 * sig ** 2, sig * np.sqrt(T)
    # second term in log space: exp(2 nu a / sig^2) alone overflows at very low vol with big carry
    return norm.cdf((a - nu * T) / sd) + np.exp(2 * nu * a / sig ** 2 + norm.logcdf((a + nu * T) / sd))


def flat_equivalent_vol(target_dip, S, K, H, T, r, b, discrete=True):
    """Single flat vol whose closed-form DIP price equals target_dip."""
    f = lambda s: dip_closed(S, K, H, T, r, b, s, discrete) - target_dip
    try:
        return brentq(f, 0.01, 3.0, xtol=1e-8)
    except ValueError:
        return np.nan


# ── SSVI ──────────────────────────────────────────────────────────────────────
def _phi(theta, eta, gamma):
    return eta / (theta ** gamma * (1 + theta) ** (1 - gamma))


def ssvi_w(k, theta, rho, eta, gamma):
    p = _phi(theta, eta, gamma)
    return 0.5 * theta * (1 + rho * p * k + np.sqrt((p * k + rho) ** 2 + 1 - rho ** 2))


class SSVI:
    """SSVI surface with ATM total variance theta(t) monotone (PCHIP through fitted nodes)."""

    def __init__(self, t_nodes, theta_nodes, rho, eta, gamma):
        self.t_nodes, self.theta_nodes = np.asarray(t_nodes), np.asarray(theta_nodes)
        self.rho, self.eta, self.gamma = rho, eta, gamma
        self._th = PchipInterpolator(np.r_[0.0, self.t_nodes], np.r_[0.0, self.theta_nodes])
        self._dth = self._th.derivative()
        self.t_max = self.t_nodes[-1]

    def theta(self, t):
        return self._th(np.minimum(t, self.t_max))

    def w(self, k, t):
        return ssvi_w(k, self.theta(t), self.rho, self.eta, self.gamma)

    def iv(self, k, t):
        return np.sqrt(self.w(k, t) / t)

    def g(self, k, t):
        """Durrleman's condition: g >= 0 everywhere means no butterfly arbitrage."""
        w, w1, w2 = self._w_derivs(k, self.theta(t))
        return (1 - k * w1 / (2 * w)) ** 2 - w1 ** 2 / 4 * (1 / w + 0.25) + w2 / 2

    def _w_derivs(self, k, th):
        p = _phi(th, self.eta, self.gamma)
        z = p * k + self.rho
        R = np.sqrt(z * z + 1 - self.rho ** 2)
        w = 0.5 * th * (1 + self.rho * p * k + R)
        w1 = 0.5 * th * (self.rho * p + p * z / R)
        w2 = 0.5 * th * p * p * (1 - self.rho ** 2) / R ** 3
        return w, w1, w2

    def local_vol(self, k, t):
        th = self.theta(t)
        w, w1, w2 = self._w_derivs(k, th)
        g = (1 - k * w1 / (2 * w)) ** 2 - w1 ** 2 / 4 * (1 / w + 0.25) + w2 / 2
        e = 1e-6 * th
        dw_dth = (ssvi_w(k, th + e, self.rho, self.eta, self.gamma)
                  - ssvi_w(k, th - e, self.rho, self.eta, self.gamma)) / (2 * e)
        dw_dt = dw_dth * self._dth(min(t, self.t_max))
        return np.sqrt(np.maximum(dw_dt, 0) / np.maximum(g, 1e-8))


def _unpack(x, n):
    theta = np.cumsum(np.exp(x[:n]))                        # monotone ATM total variance
    rho = 0.999 * np.tanh(x[n])
    eta = 2.0 / (1 + abs(rho)) / (1 + np.exp(-x[n + 1]))    # eta (1 + |rho|) < 2: no butterfly arb
    gamma = 0.01 + 0.49 / (1 + np.exp(-x[n + 2]))           # gamma in (0.01, 0.5)
    return theta, rho, eta, gamma


def fit_ssvi(T, k, iv):
    """Least-squares SSVI fit in implied-vol space. T, k, iv are flat arrays of grid points.
    Returns (SSVI, rmse in vol points, per-tenor rmse dict)."""
    T, k, iv = map(np.asarray, (T, k, iv))
    tn = np.unique(T)
    n = len(tn)
    idx = np.searchsorted(tn, T)
    atm = np.array([np.interp(0.0, np.sort(k[idx == i]), iv[idx == i][np.argsort(k[idx == i])])
                    for i in range(n)])
    th0 = np.maximum.accumulate(atm ** 2 * tn)
    inc = np.diff(np.r_[0.0, th0])
    x0 = np.r_[np.log(np.maximum(inc, 1e-6)), np.arctanh(-0.7 / 0.999), 0.0, 0.0]

    def resid(x):
        theta, rho, eta, gamma = _unpack(x, n)
        w = ssvi_w(k, theta[idx], rho, eta, gamma)
        return np.sqrt(np.maximum(w, 1e-12) / T) - iv

    sol = least_squares(resid, x0, loss="soft_l1", f_scale=0.01, max_nfev=4000)
    theta, rho, eta, gamma = _unpack(sol.x, n)
    surf = SSVI(tn, theta, rho, eta, gamma)
    r = resid(sol.x)
    per = {float(t): float(np.sqrt(np.mean(r[idx == i] ** 2)) * 100) for i, t in enumerate(tn)}
    return surf, float(np.sqrt(np.mean(r ** 2)) * 100), per


# ── PDE ───────────────────────────────────────────────────────────────────────
def _put_cell_avg(y, dy, K):
    """Cell average of (K - e^u)^+ over [y - dy/2, y + dy/2] (smooths the payoff kink)."""
    lo, hi = y - dy / 2, y + dy / 2
    lk = np.log(K)
    top = np.minimum(hi, lk)
    val = np.where(top > lo, K * (top - lo) - (np.exp(top) - np.exp(lo)), 0.0)
    return val / dy


def solve_barrier(S0, K, H, T, r, b, locvol, n_days=DAYS, sub=4, n_space=800, width=None):
    """Down-and-in put and knock-in probability under local vol.

    locvol(k, t) -> sigma for arrays k (log-moneyness vs the forward) and scalar t.
    Solves undiscounted expectations for [vanilla put, down-and-out put, survival]
    backwards on a uniform grid in y = ln S with ln H midway between two nodes.
    """
    if width is None:
        sig_ref = max(float(np.max(locvol(np.array([0.0, np.log(H / S0)]), 0.5 * T))), 0.15)
        width = max(1.2, 6 * sig_ref * np.sqrt(T))
    lh, l0 = np.log(H), np.log(S0)
    dy = 2 * width / (n_space - 1)
    # ln H sits midway between two nodes: zeroing a node ON the barrier would kill half a
    # cell above it and shift the effective barrier up by dy/2
    y_lo = lh - dy / 2 - np.round((lh - (l0 - width)) / dy) * dy
    y = y_lo + dy * np.arange(n_space)
    below = y < lh

    V = np.empty((n_space, 3))
    V[:, 0] = _put_cell_avg(y, dy, K)
    V[:, 1] = np.where(below, 0.0, V[:, 0])
    V[:, 2] = np.where(below, 0.0, 1.0)

    n_steps = n_days * sub
    dt = T / n_steps
    ab = np.zeros((3, n_space))
    t = T
    smooth_left = 2                        # Rannacher: implicit half-steps pending
    for step in range(n_steps):
        t_new = t - dt
        tm = 0.5 * (t + t_new)
        sig = np.clip(locvol(y - l0 - b * tm, tm), 0.01, 3.0)
        a = 0.5 * sig * sig
        c = b - a
        lo_c = a / dy ** 2 - c / (2 * dy)
        di_c = -2 * a / dy ** 2
        up_c = a / dy ** 2 + c / (2 * dy)

        def apply(theta_, h, V):
            rhs = V.copy()
            if theta_ < 1:
                LV = np.zeros_like(V)
                LV[1:-1] = (lo_c[1:-1, None] * V[:-2] + di_c[1:-1, None] * V[1:-1]
                            + up_c[1:-1, None] * V[2:])
                rhs = V + (1 - theta_) * h * LV
            ab[0, 2:] = -theta_ * h * up_c[1:-1]
            ab[1, 1:-1] = 1 - theta_ * h * di_c[1:-1]
            ab[2, :-2] = -theta_ * h * lo_c[1:-1]
            ab[1, 0] = ab[1, -1] = 1.0
            ab[0, 1] = ab[2, -2] = 0.0
            tau = T - (t - h)
            rhs[0] = [K - np.exp(y[0] + b * tau), 0.0, 0.0]
            rhs[-1] = [0.0, 0.0, 1.0]
            return solve_banded((1, 1), ab, rhs)

        if smooth_left:
            V = apply(1.0, dt / 2, V)
            V = apply(1.0, dt / 2, V)
            smooth_left = 0
        else:
            V = apply(0.5, dt, V)
        t = t_new

        if (step + 1) % sub == 0 and step + 1 < n_steps:     # daily close, before maturity
            V[below, 1:] = 0.0
            smooth_left = 2

    df = np.exp(-r * T)
    put = df * np.interp(l0, y, V[:, 0])
    dop = df * np.interp(l0, y, V[:, 1])
    surv = np.interp(l0, y, V[:, 2])
    return {"put": put, "dop": dop, "dip": put - dop, "p_ki": 1 - surv}
