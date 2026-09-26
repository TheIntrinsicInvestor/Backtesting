"""
prep.py
-------
Turns cached WRDS rows for one (underlying, date) into pricer inputs:
  grid(date)  -> T, k, iv arrays for fit_ssvi (tenors 30-547 days, valid IVs only)
  carry(date) -> b(t) interpolated from listed forwards, b1y = ln(F_1y / S) for the PDE
  rate(date)  -> 1y continuously compounded zero rate (decimal)
"""

import numpy as np
import pandas as pd

import common as C

TENORS = (30, 60, 91, 122, 152, 182, 273, 365, 547)
MIN_POINTS = 10


class Market:
    """Holds one underlying's cached tables, indexed by date for fast per-date lookups."""

    def __init__(self, surface, fwd, zero, spot, rate_is_percent):
        surface = surface.copy()
        surface["date"] = pd.to_datetime(surface["date"])
        iv = surface["impl_volatility"].astype(float)
        surface = surface[iv.notna() & (iv > 0) & (iv > C.EU_NA + 0.01) & surface["days"].isin(TENORS)
                          & (surface["impl_strike"] > 0)]
        self.surface = {d: g for d, g in surface.groupby("date")}
        fwd = fwd.copy()
        fwd["date"], fwd["expiration"] = pd.to_datetime(fwd["date"]), pd.to_datetime(fwd["expiration"])
        fwd = fwd[fwd["forwardprice"] > 0]
        self.fwd = {d: g for d, g in fwd.groupby("date")}
        zero = zero.copy()
        zero["date"] = pd.to_datetime(zero["date"])
        self.zero = {d: g.sort_values("days") for d, g in zero.groupby("date")}
        self.spot = dict(zip(pd.to_datetime(spot["date"]), spot["close"].astype(float)))
        self.pct = rate_is_percent

    def rate(self, d, days=365):
        z = self.zero.get(d)
        if z is None:
            return np.nan
        r = float(np.interp(days, z["days"], z["rate"]))
        return r / 100 if self.pct else r

    def carry_curve(self, d):
        """(t, b) points from listed forwards: b = ln(F / S) / t."""
        f, s = self.fwd.get(d), self.spot.get(d)
        if f is None or s is None:
            return None
        t = (f["expiration"] - d).dt.days.to_numpy() / 365
        keep = t > 7 / 365
        if not keep.any():
            return None
        t, b = t[keep], np.log(f["forwardprice"].to_numpy()[keep] / s) / t[keep]
        o = np.argsort(t)
        return t[o], b[o]

    def inputs(self, d):
        """Everything the fit and the PDE need for date d, or None with a reason."""
        s = self.spot.get(d)
        g = self.surface.get(d)
        cc = self.carry_curve(d)
        r = self.rate(d)
        if s is None or g is None or cc is None or np.isnan(r):
            return None, "missing spot/surface/forward/rate"
        tb, bb = cc
        T = g["days"].to_numpy() / 365
        b_t = np.interp(T, tb, bb)                     # flat extrapolation beyond listed expiries
        k = np.log(g["impl_strike"].to_numpy() / (s * np.exp(b_t * T)))
        iv = g["impl_volatility"].to_numpy().astype(float)
        counts = pd.Series(T).value_counts()
        ok = np.isin(T, counts[counts >= MIN_POINTS].index)
        if not {273 / 365, 365 / 365} <= set(T[ok]):
            return None, "273d or 365d tenor too thin"
        b1 = float(np.interp(1.0, tb, bb))
        return {"S": s, "r": r, "b": b1, "T": T[ok], "k": k[ok], "iv": iv[ok]}, None


def load_index(name):
    """Market object for 'spx' or 'sx5e' from the 03 caches."""
    if name == "spx":
        spot = C.cached("spx_spot")
        return Market(C.cached("spx_surface"), C.cached("spx_fwd"), C.cached("us_zero"), spot, True)
    path = C.cached("sx5e_path").rename(columns={"level": "close"})
    return Market(C.cached("sx5e_surface"), C.cached("sx5e_fwd"), C.cached("eur_zero"), path, False)
