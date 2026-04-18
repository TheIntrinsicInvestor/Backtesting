# ruff: noqa
"""
02_gex_pull.py
--------------
Pull SPX 0DTE options from OptionMetrics opprcd tables (2022-2025).
OptionMetrics leaves impl_volatility/gamma NULL for SPX; we compute them
from option mid-prices using numerical Black-Scholes inversion.

Only near-ATM contracts (within 5% of spot, positive OI, positive mid)
are included -- deep OTM/ITM options have negligible gamma for 0DTE.

GEX = sum(call_OI * G_call - put_OI * G_put) * 100 * spot / 1e9

Output: data/gex_daily.parquet
"""

import os, warnings
import wrds
import pandas as pd
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq

os.makedirs("data", exist_ok=True)
warnings.filterwarnings("ignore")

CACHE      = "data/gex_daily.parquet"
SPX_SECID  = 108105
START_DATE = "2022-01-01"
END_DATE   = "2025-08-29"
YEARS      = list(range(2022, 2026))
RISK_FREE  = 0.045    # avg approx; good enough for GEX relative comparison
T_DAY      = 0.5 / 252  # half a trading day (options expire at close)
ATM_BAND   = 0.05    # only use options within 5% of spot


# ── Black-Scholes helpers ──────────────────────────────────────────────────────
def bs_price(S, K, r, sigma, T, flag):
    if T <= 0 or sigma <= 0:
        return max(0.0, (S - K) if flag == "C" else (K - S))
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if flag == "C":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

def bs_gamma(S, K, r, sigma, T):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))

def implied_vol(price, S, K, r, T, flag):
    """Invert B-S via Brent's method. Returns NaN if no solution found."""
    intrinsic = max(0.0, (S - K) if flag == "C" else (K - S))
    if price <= intrinsic + 1e-6:
        return np.nan
    try:
        def obj(v): return bs_price(S, K, r, v, T, flag) - price
        # bracket: vol between 0.001 and 20 (2000%)
        if obj(0.001) * obj(20.0) > 0:
            return np.nan
        return brentq(obj, 0.001, 20.0, xtol=1e-6, maxiter=100)
    except Exception:
        return np.nan


if os.path.exists(CACHE):
    print(f"Cache found at {CACHE} -- skipping WRDS query.")
    df = pd.read_parquet(CACHE)
    print(f"Loaded {len(df):,} rows.")
    print(f"Date range: {df['date'].min().date()} to {df['date'].max().date()}")
else:
    print("No cache -- querying WRDS.")
    db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))

    # ── 1. Pull 0DTE option prices ────────────────────────────────────────────
    opt_chunks = []
    for year in YEARS:
        table = f"optionm_all.opprcd{year}"
        query = f"""
            SELECT date, exdate, cp_flag, strike_price,
                   best_bid, best_offer, open_interest
            FROM {table}
            WHERE secid = {SPX_SECID}
              AND exdate = date
              AND open_interest > 0
              AND (best_bid + best_offer) > 0
              AND date >= '{START_DATE}'
              AND date <= '{END_DATE}'
        """
        print(f"  Querying {table}...", end=" ", flush=True)
        chunk = db.raw_sql(query)
        print(f"{len(chunk):,} rows")
        opt_chunks.append(chunk)

    # ── 2. Pull SPX spot (close) from secprd ──────────────────────────────────
    print("  Pulling SPX close from optionm_all.secprd...")
    spot_chunks = []
    for year in YEARS:
        q = f"""
            SELECT date, close AS spot
            FROM optionm_all.secprd{year}
            WHERE secid = {SPX_SECID}
              AND date >= '{START_DATE}'
              AND date <= '{END_DATE}'
        """
        spot_chunks.append(db.raw_sql(q))

    db.close()

    spot_df = pd.concat(spot_chunks, ignore_index=True)
    spot_df["date"] = pd.to_datetime(spot_df["date"])
    spot_df["spot"] = pd.to_numeric(spot_df["spot"], errors="coerce")
    spot_df = spot_df.dropna(subset=["spot"]).drop_duplicates("date")
    print(f"  Spot rows: {len(spot_df):,}")

    # ── 3. Combine and filter options ────────────────────────────────────────
    raw = pd.concat(opt_chunks, ignore_index=True)
    raw["date"]          = pd.to_datetime(raw["date"])
    raw["strike_price"]  = pd.to_numeric(raw["strike_price"], errors="coerce")
    raw["best_bid"]      = pd.to_numeric(raw["best_bid"],     errors="coerce")
    raw["best_offer"]    = pd.to_numeric(raw["best_offer"],   errors="coerce")
    raw["open_interest"] = pd.to_numeric(raw["open_interest"],errors="coerce")
    raw = raw.dropna()

    # Strike in dollars (OptionMetrics stores as integer * 1000)
    raw["strike"] = raw["strike_price"] / 1000.0
    raw["mid"]    = (raw["best_bid"] + raw["best_offer"]) / 2.0

    # Merge spot
    raw = raw.merge(spot_df, on="date", how="inner")

    # Keep only near-ATM (within ATM_BAND of spot)
    raw["moneyness"] = np.abs(np.log(raw["strike"] / raw["spot"]))
    raw = raw[raw["moneyness"] <= ATM_BAND]
    print(f"\nNear-ATM rows (within {ATM_BAND*100:.0f}% of spot): {len(raw):,}")

    # ── 4. Compute implied vol and gamma ─────────────────────────────────────
    print("Computing implied vol and gamma (this may take a minute)...")

    def compute_iv(row):
        return implied_vol(
            price=float(row["mid"]),
            S=float(row["spot"]),
            K=float(row["strike"]),
            r=RISK_FREE,
            T=T_DAY,
            flag=str(row["cp_flag"]),
        )

    raw["iv"] = raw.apply(compute_iv, axis=1)
    raw = raw.dropna(subset=["iv"])

    raw["gamma"] = raw.apply(
        lambda r: bs_gamma(float(r["spot"]), float(r["strike"]),
                           RISK_FREE, float(r["iv"]), T_DAY),
        axis=1,
    )
    raw = raw[raw["gamma"] > 1e-10]
    print(f"Rows with valid gamma: {len(raw):,}")

    # ── 5. Daily GEX ─────────────────────────────────────────────────────────
    raw["gamma_oi"] = raw["gamma"] * raw["open_interest"]

    daily = (
        raw.groupby(["date", "cp_flag"])["gamma_oi"]
        .sum().unstack(fill_value=0.0).reset_index()
    )
    daily.columns.name = None
    if "C" not in daily.columns: daily["C"] = 0.0
    if "P" not in daily.columns: daily["P"] = 0.0
    daily.rename(columns={"C": "call_gamma_oi", "P": "put_gamma_oi"}, inplace=True)

    oi_totals = (
        raw.groupby(["date", "cp_flag"])["open_interest"]
        .sum().unstack(fill_value=0).reset_index()
    )
    oi_totals.columns.name = None
    if "C" not in oi_totals.columns: oi_totals["C"] = 0
    if "P" not in oi_totals.columns: oi_totals["P"] = 0
    oi_totals.rename(columns={"C": "call_oi_total", "P": "put_oi_total"}, inplace=True)

    daily = daily.merge(oi_totals, on="date", how="left")
    daily = daily.merge(spot_df, on="date", how="left")

    daily["gex_bn"] = (
        (daily["call_gamma_oi"] - daily["put_gamma_oi"]) * 100 * daily["spot"] / 1e9
    )

    daily = daily.dropna(subset=["gex_bn"]).sort_values("date").reset_index(drop=True)

    # ── 6. Save ───────────────────────────────────────────────────────────────
    daily.to_parquet(CACHE, index=False)
    print(f"\nSaved {len(daily):,} rows to {CACHE}")
    print(f"Date range: {daily['date'].min().date()} to {daily['date'].max().date()}")
    print(f"GEX range: {daily['gex_bn'].min():.2f} to {daily['gex_bn'].max():.2f} bn")
    print(f"Positive GEX days: {(daily['gex_bn'] > 0).sum()} / {len(daily)}")
    print(f"Negative GEX days: {(daily['gex_bn'] < 0).sum()} / {len(daily)}")
    print("\nTop 5 highest GEX days:")
    print(daily.nlargest(5, "gex_bn")[["date", "gex_bn", "spot"]].to_string(index=False))
    print("\nTop 5 lowest GEX days:")
    print(daily.nsmallest(5, "gex_bn")[["date", "gex_bn", "spot"]].to_string(index=False))
