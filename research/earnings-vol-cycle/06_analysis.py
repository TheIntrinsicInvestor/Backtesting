"""
06_analysis.py  —  Full earnings vol cycle analysis
Computes per-event metrics, IV run-up profiles, straddle P&L, and chart JSON.

Outputs:
  data/events_analysed.parquet   — one row per earnings event with all metrics
  charts/data_iv_profile.json
  charts/data_sector_analysis.json
  charts/data_mktcap_analysis.json
  charts/data_surprise_analysis.json
  charts/data_pnl.json
  charts/data_timing.json
  charts/data_heatmap.json
"""

import os
import json
import numpy as np
import pandas as pd
from pathlib import Path

os.makedirs("data",   exist_ok=True)
os.makedirs("charts", exist_ok=True)

EVENTS_CACHE = Path("data/events_analysed.parquet")

# BSM ATM straddle coefficient: value% = σ_annual × STRADDLE_COEFF for T days
# For 2-day holding: STRADDLE_COEFF = sqrt(2 * 2 / (252 * pi)) = sqrt(4 / (252π))
NOTIONAL = 10_000   # per-trade notional in dollars
PHI_0    = 1.0 / np.sqrt(2 * np.pi)   # 0.3989
SQRT_T30 = np.sqrt(30.0 / 252.0)      # 0.3450 — 30-day option

# ── Load all inputs ───────────────────────────────────────────────────────────
print("Loading data...")
universe     = pd.read_parquet("data/sp500_constituents.parquet")
earnings     = pd.read_parquet("data/earnings_dates.parquet")
secid_map    = pd.read_parquet("data/secid_map.parquet")
iv_panel     = pd.read_parquet("data/iv_panel.parquet")
prices       = pd.read_parquet("data/prices.parquet")
trading_cal  = pd.read_parquet("data/trading_calendar.parquet")

earnings["anndats"] = pd.to_datetime(earnings["anndats"])
iv_panel["date"]    = pd.to_datetime(iv_panel["date"])
prices["date"]      = pd.to_datetime(prices["date"])
trading_cal["date"] = pd.to_datetime(trading_cal["date"])

trading_days = pd.DatetimeIndex(sorted(trading_cal["date"].unique()))

# Sector lookup: permno -> sector (use most recent end_date)
sector_lu = (
    universe.sort_values("end_date", ascending=False, na_position="first")
    .drop_duplicates("permno")[["permno", "sector"]]
    .set_index("permno")["sector"]
    .to_dict()
)

# secid lookup: permno -> secid
perm_to_secid = secid_map.set_index("permno")["secid"].to_dict()

# IV lookup: (secid, date) -> impl_volatility
iv_idx = iv_panel.set_index(["secid", "date"])["impl_volatility"].to_dict()

# Price/return lookup: (permno, date) -> (prc, ret, mktcap_m)
prices_idx    = prices.set_index(["permno", "date"])[["prc", "ret", "mktcap_m"]]

def find_tday(event_date, offset):
    """Return the trading day at `offset` from `event_date` (0 = event_date or next trading day)."""
    idx = trading_days.searchsorted(pd.Timestamp(event_date))
    # Snap to next trading day if event_date is not a trading day
    if idx >= len(trading_days):
        return None
    target = idx + offset
    if 0 <= target < len(trading_days):
        return trading_days[target]
    return None

# ── Per-event analysis ────────────────────────────────────────────────────────
if EVENTS_CACHE.exists():
    print("Loading cached events_analysed.parquet...")
    events_df = pd.read_parquet(EVENTS_CACHE)
else:
    print(f"Processing {len(earnings):,} earnings events...")

    # Filter to events 2010 onwards (2009 data used only for T-20 buffer)
    earnings_2010 = earnings[earnings["anndats"].dt.year >= 2010].copy()
    print(f"  Events from 2010+: {len(earnings_2010):,}")

    records = []
    n_skipped_no_secid = 0
    n_skipped_no_iv    = 0
    n_skipped_no_price = 0

    for idx_row, ev in earnings_2010.iterrows():
        permno   = int(ev["permno"])
        anndats  = ev["anndats"]
        sector   = sector_lu.get(permno, "Unknown")
        secid    = perm_to_secid.get(permno)

        if secid is None:
            n_skipped_no_secid += 1
            continue

        # ── Find T-day offsets ────────────────────────────────────────────────
        T_dates = {}
        for off in range(-20, 6):
            d = find_tday(anndats, off)
            if d is not None:
                T_dates[off] = d

        if -1 not in T_dates or 0 not in T_dates or 1 not in T_dates:
            continue

        # ── IV run-up profile ─────────────────────────────────────────────────
        iv_window = {}
        for off, d in T_dates.items():
            iv_val = iv_idx.get((secid, d))
            if iv_val is not None:
                iv_window[off] = float(iv_val)

        # Need at least T-1 IV and at least 3 baseline days (T-20 to T-15)
        baseline_ivs = [iv_window[o] for o in range(-20, -14) if o in iv_window]
        if len(baseline_ivs) < 3 or -1 not in iv_window:
            n_skipped_no_iv += 1
            continue

        baseline_mean = np.mean(baseline_ivs)
        if baseline_mean == 0:
            continue

        iv_t_minus1 = iv_window[-1]
        norm_profile = {off: iv / baseline_mean * 100 for off, iv in iv_window.items()}

        # ── Price / return data ───────────────────────────────────────────────
        try:
            prc_tm1 = float(prices_idx.loc[(permno, T_dates[-1]), "prc"])
            ret_t   = float(prices_idx.loc[(permno, T_dates[0]),  "ret"])
            ret_t1  = float(prices_idx.loc[(permno, T_dates[1]),  "ret"])
            mktcap  = float(prices_idx.loc[(permno, T_dates[-1]), "mktcap_m"])
        except (KeyError, TypeError):
            n_skipped_no_price += 1
            continue

        if np.isnan(ret_t) or np.isnan(ret_t1):
            n_skipped_no_price += 1
            continue

        # ── Straddle P&L: vega-gamma model ───────────────────────────────────────
        # OM impl_volatility is annualised, decimal (e.g. 0.30 = 30%)
        # 2-day compound return (decimal)
        actual_2day = abs((1 + ret_t) * (1 + ret_t1) - 1)

        # Need exit IV (T+1) for the vega P&L
        iv_t_plus1 = iv_window.get(1)
        if iv_t_plus1 is None or iv_t_minus1 <= 0:
            n_skipped_no_iv += 1
            continue

        # Vega P&L: $10K × straddle_vega_pct × IV_crush
        # straddle_vega_pct = 2 × PHI_0 × sqrt(T30) per unit vol (decimal)
        iv_crush  = iv_t_minus1 - iv_t_plus1
        vega_pnl  = NOTIONAL * 2.0 * PHI_0 * SQRT_T30 * iv_crush

        # Gamma P&L: loss from actual move (short-gamma cost)
        # gamma_loss = $10K × PHI_0 × actual_move² / (sigma × sqrt(T))
        gamma_loss = NOTIONAL * PHI_0 * (actual_2day ** 2) / (iv_t_minus1 * SQRT_T30)

        pnl_usd = vega_pnl - gamma_loss
        pnl_pct = pnl_usd / NOTIONAL * 100
        is_win  = pnl_usd > 0

        # IV-RV spread: both in annual percentage points
        iv_t_minus1_pct = iv_t_minus1 * 100
        realised_annual_pct = (actual_2day / np.sqrt(2)) * np.sqrt(252) * 100
        ivrv_spread_pct = iv_t_minus1_pct - realised_annual_pct

        records.append({
            "permno"          : permno,
            "anndats"         : anndats,
            "year"            : anndats.year,
            "quarter"         : anndats.quarter,
            "sector"          : sector,
            "mktcap_m"        : mktcap,
            "actual_eps"      : ev["actual_eps"],
            "consensus_eps"   : ev.get("consensus_eps"),
            "surprise_pct"    : ev.get("surprise_pct"),
            "n_analysts"      : ev.get("n_analysts"),
            "iv_t_minus1"     : iv_t_minus1,
            "iv_t_plus1"      : iv_t_plus1,
            "iv_crush_pp"     : iv_crush * 100,
            "baseline_iv_pct" : baseline_mean * 100,
            "norm_iv_t_minus1": norm_profile.get(-1),
            "actual_2day_pct" : actual_2day * 100,
            "iv_t_minus1_pct" : iv_t_minus1_pct,
            "ivrv_spread_pct" : ivrv_spread_pct,
            "pnl_pct"         : pnl_pct,
            "pnl_usd"         : pnl_usd,
            "is_win"          : is_win,
            # Store normalised IV at key T-days for profile chart
            **{f"norm_iv_T{off:+d}": norm_profile.get(off) for off in range(-20, 6)},
        })

    print(f"\nSkipped — no OM secid : {n_skipped_no_secid:,}")
    print(f"Skipped — no IV data  : {n_skipped_no_iv:,}")
    print(f"Skipped — no price    : {n_skipped_no_price:,}")
    print(f"Usable events         : {len(records):,}")

    events_df = pd.DataFrame(records)
    events_df.to_parquet(EVENTS_CACHE, index=False)
    print(f"Saved -> {EVENTS_CACHE}")

print(f"\nTotal events: {len(events_df):,}")
print(f"Win rate overall: {events_df['is_win'].mean():.1%}")
print(f"Avg P&L per trade: ${events_df['pnl_usd'].mean():+.0f}")
print(f"Avg IV-RV spread: {events_df['ivrv_spread_pct'].mean():+.1f}pp")

# ── Market cap quintiles ──────────────────────────────────────────────────────
events_df["mktcap_q"] = pd.qcut(
    events_df["mktcap_m"],
    q=5,
    labels=["Q1 (Smallest)", "Q2", "Q3", "Q4", "Q5 (Largest)"]
)

# ── Surprise quartiles ────────────────────────────────────────────────────────
surp_valid = events_df.dropna(subset=["surprise_pct"])
events_df["surprise_q"] = None
if len(surp_valid) > 100:
    events_df.loc[surp_valid.index, "surprise_q"] = pd.qcut(
        surp_valid["surprise_pct"],
        q=4,
        labels=["Large Miss (Q1)", "Slight Miss (Q2)", "Slight Beat (Q3)", "Large Beat (Q4)"]
    ).values

# ── Helper: compute metrics dict ──────────────────────────────────────────────
def metrics(df, label=""):
    n       = len(df)
    winrate = float(df["is_win"].mean()) if n > 0 else 0.0
    avgpnl  = float(df["pnl_usd"].mean()) if n > 0 else 0.0
    return {"label": label, "n": n, "win_rate": round(winrate, 4),
            "avg_pnl": round(avgpnl, 2)}

# ── Chart 1: IV Run-Up Profile ────────────────────────────────────────────────
T_OFFSETS  = list(range(-20, 6))
norm_cols  = [f"norm_iv_T{off:+d}" for off in T_OFFSETS]

profile_mean = events_df[norm_cols].mean()
profile_p25  = events_df[norm_cols].quantile(0.25)
profile_p75  = events_df[norm_cols].quantile(0.75)

def safe_list(series):
    return [round(v, 2) if not np.isnan(v) else None for v in series]

TARGET_SECTORS = [
    "Financials", "Industrials", "Consumer Discretionary", "Technology",
    "Healthcare", "Energy", "Consumer Staples",
]
top_sectors = [s for s in TARGET_SECTORS if s in events_df["sector"].unique()]

by_sector_profiles = {}
for sec in top_sectors:
    sub = events_df[events_df["sector"] == sec][norm_cols].mean()
    by_sector_profiles[sec] = safe_list(sub)

chart_iv_profile = {
    "labels"    : T_OFFSETS,
    "mean"      : safe_list(profile_mean),
    "p25"       : safe_list(profile_p25),
    "p75"       : safe_list(profile_p75),
    "by_sector" : by_sector_profiles,
    "n_events"  : int(events_df["norm_iv_T+0"].notna().sum()),
    "baseline_iv_mean_pct": round(float(events_df["baseline_iv_pct"].mean()), 1),
}

with open("charts/data_iv_profile.json", "w") as f:
    json.dump(chart_iv_profile, f, indent=2)
print("Saved charts/data_iv_profile.json")

# ── Chart 2: Sector analysis ──────────────────────────────────────────────────
sector_grp = (
    events_df[events_df["sector"] != "Unknown"]
    .groupby("sector")
    .agg(
        n          = ("is_win", "count"),
        win_rate   = ("is_win", "mean"),
        avg_pnl    = ("pnl_usd", "mean"),
        ivrv_spread= ("ivrv_spread_pct", "mean"),
    )
    .reset_index()
    .sort_values("win_rate", ascending=False)
)

chart_sector = {
    "sectors"          : sector_grp["sector"].tolist(),
    "win_rates"        : [round(v * 100, 1) for v in sector_grp["win_rate"]],
    "avg_pnl"          : [round(v, 0) for v in sector_grp["avg_pnl"]],
    "ivrv_spread"      : [round(v, 1) for v in sector_grp["ivrv_spread"]],
    "n_events"         : sector_grp["n"].tolist(),
}

with open("charts/data_sector_analysis.json", "w") as f:
    json.dump(chart_sector, f, indent=2)
print("Saved charts/data_sector_analysis.json")

# ── Chart 3: Market cap quintile analysis ─────────────────────────────────────
mktcap_grp = (
    events_df.dropna(subset=["mktcap_q"])
    .groupby("mktcap_q", observed=True)
    .agg(
        n             = ("is_win", "count"),
        win_rate      = ("is_win", "mean"),
        avg_pnl       = ("pnl_usd", "mean"),
        avg_mktcap_m  = ("mktcap_m", "median"),
        ivrv_spread   = ("ivrv_spread_pct", "mean"),
    )
    .reset_index()
)

chart_mktcap = {
    "quintiles"       : mktcap_grp["mktcap_q"].astype(str).tolist(),
    "win_rates"       : [round(v * 100, 1) for v in mktcap_grp["win_rate"]],
    "avg_pnl"         : [round(v, 0) for v in mktcap_grp["avg_pnl"]],
    "avg_mktcap_m"    : [round(v, 0) for v in mktcap_grp["avg_mktcap_m"]],
    "ivrv_spread"     : [round(v, 1) for v in mktcap_grp["ivrv_spread"]],
    "n_events"        : mktcap_grp["n"].tolist(),
}

with open("charts/data_mktcap_analysis.json", "w") as f:
    json.dump(chart_mktcap, f, indent=2)
print("Saved charts/data_mktcap_analysis.json")

# ── Chart 4: Earnings surprise interaction ────────────────────────────────────
surp_grp = (
    events_df.dropna(subset=["surprise_q"])
    .groupby("surprise_q", observed=True)
    .agg(
        n          = ("is_win", "count"),
        win_rate   = ("is_win", "mean"),
        avg_pnl    = ("pnl_usd", "mean"),
        avg_surprise = ("surprise_pct", "mean"),
    )
    .reset_index()
)

chart_surprise = {
    "quartiles"      : surp_grp["surprise_q"].astype(str).tolist(),
    "win_rates"      : [round(v * 100, 1) for v in surp_grp["win_rate"]],
    "avg_pnl"        : [round(v, 0) for v in surp_grp["avg_pnl"]],
    "avg_surprise"   : [round(v, 1) for v in surp_grp["avg_surprise"]],
    "n_events"       : surp_grp["n"].tolist(),
}

with open("charts/data_surprise_analysis.json", "w") as f:
    json.dump(chart_surprise, f, indent=2)
print("Saved charts/data_surprise_analysis.json")

# ── Chart 5: Straddle P&L by quarter (time series) ───────────────────────────
events_df["yrq"] = events_df["year"].astype(str) + "-Q" + events_df["quarter"].astype(str)

pnl_quarterly = (
    events_df.groupby("yrq")
    .agg(
        total_pnl = ("pnl_usd", "sum"),
        n_events  = ("pnl_usd", "count"),
    )
    .sort_index()
    .reset_index()
)
pnl_quarterly["cum_pnl"] = pnl_quarterly["total_pnl"].cumsum()

# Sharpe: annualised on quarterly P&L series
q_returns = pnl_quarterly["total_pnl"]
sharpe_q  = (q_returns.mean() / q_returns.std() * np.sqrt(4)) if q_returns.std() > 0 else None

def max_drawdown(cum):
    peak = cum.cummax()
    dd   = cum - peak
    return float(dd.min())

mdd = max_drawdown(pnl_quarterly["cum_pnl"])

chart_pnl = {
    "labels"    : pnl_quarterly["yrq"].tolist(),
    "bars"      : [round(v, 0) for v in pnl_quarterly["total_pnl"]],
    "colors"    : ["#059669" if v >= 0 else "#dc2626" for v in pnl_quarterly["total_pnl"]],
    "cum_line"  : [round(v, 0) for v in pnl_quarterly["cum_pnl"]],
    "n_events"  : pnl_quarterly["n_events"].tolist(),
    "metrics"   : {
        "n_quarters"       : int(len(pnl_quarterly)),
        "n_winning_qtrs"   : int((pnl_quarterly["total_pnl"] > 0).sum()),
        "win_rate_qtrs"    : round(float((pnl_quarterly["total_pnl"] > 0).mean()), 4),
        "win_rate_trades"  : round(float(events_df["is_win"].mean()), 4),
        "avg_pnl_per_trade": round(float(events_df["pnl_usd"].mean()), 2),
        "total_pnl"        : round(float(pnl_quarterly["total_pnl"].sum()), 0),
        "sharpe_quarterly" : round(float(sharpe_q), 3) if sharpe_q and not np.isnan(sharpe_q) else None,
        "max_dd"           : round(mdd, 0),
        "n_total_events"   : int(len(events_df)),
    }
}

with open("charts/data_pnl.json", "w") as f:
    json.dump(chart_pnl, f, indent=2)
print("Saved charts/data_pnl.json")

# ── Chart 6: Entry timing sensitivity ────────────────────────────────────────
# Re-compute P&L for entries at T-5, T-3, T-2, T-1 using IV at each offset
timing_rows = []
for entry_off in [-5, -3, -2, -1]:
    col = f"norm_iv_T{entry_off:+d}"
    sub = events_df.dropna(subset=[col, "norm_iv_T-1", "iv_t_plus1"]).copy()
    # IV at entry: rescale T-1 IV by the normalised profile ratio
    sub["iv_entry"] = sub["iv_t_minus1"] * (sub[col] / sub["norm_iv_T-1"])
    # Vega-gamma model: enter at entry_off, exit at T+1
    actual_2day_dec = sub["actual_2day_pct"] / 100
    iv_crush_entry  = sub["iv_entry"] - sub["iv_t_plus1"]
    sub["pnl_entry"] = (
        NOTIONAL * 2.0 * PHI_0 * SQRT_T30 * iv_crush_entry
        - NOTIONAL * PHI_0 * (actual_2day_dec ** 2) / (sub["iv_entry"] * SQRT_T30)
    )
    sub["win_entry"] = sub["pnl_entry"] > 0

    q_pnl = sub.groupby("yrq")["pnl_entry"].sum().sort_index()
    sharpe = (q_pnl.mean() / q_pnl.std() * np.sqrt(4)) if q_pnl.std() > 0 else None

    timing_rows.append({
        "entry"    : f"T{entry_off:+d}",
        "n"        : int(len(sub)),
        "win_rate" : round(float(sub["win_entry"].mean()), 4),
        "avg_pnl"  : round(float(sub["pnl_entry"].mean()), 2),
        "sharpe"   : round(float(sharpe), 3) if sharpe and not np.isnan(sharpe) else None,
    })

chart_timing = {
    "entries"   : [r["entry"]    for r in timing_rows],
    "win_rates" : [round(r["win_rate"] * 100, 1) for r in timing_rows],
    "avg_pnl"   : [r["avg_pnl"]  for r in timing_rows],
    "sharpes"   : [r["sharpe"]   for r in timing_rows],
    "n_events"  : [r["n"]        for r in timing_rows],
    "rows"      : timing_rows,
}

with open("charts/data_timing.json", "w") as f:
    json.dump(chart_timing, f, indent=2)
print("Saved charts/data_timing.json")

# ── Chart 7: Sector × Year win rate heatmap ───────────────────────────────────
heat_sectors = [s for s in sector_grp["sector"].tolist() if s != "Unknown"]
heat_years   = sorted(events_df["year"].unique().tolist())

heatmap = {"sectors": heat_sectors, "years": heat_years, "win_rates": [], "n_events": []}
for sec in heat_sectors:
    row_wr = []
    row_n  = []
    for yr in heat_years:
        sub = events_df[(events_df["sector"] == sec) & (events_df["year"] == yr)]
        if len(sub) >= 5:
            row_wr.append(round(float(sub["is_win"].mean() * 100), 1))
            row_n.append(int(len(sub)))
        else:
            row_wr.append(None)
            row_n.append(0)
    heatmap["win_rates"].append(row_wr)
    heatmap["n_events"].append(row_n)

with open("charts/data_heatmap.json", "w") as f:
    json.dump(heatmap, f, indent=2)
print("Saved charts/data_heatmap.json")

# ── Key stats printout ────────────────────────────────────────────────────────
m = chart_pnl["metrics"]
print(f"\n=== KEY RESULTS ===")
print(f"Total events   : {m['n_total_events']:,}")
print(f"Win rate       : {m['win_rate_trades']:.1%}")
print(f"Avg P&L/trade  : ${m['avg_pnl_per_trade']:+.0f}")
print(f"Quarterly Sharpe: {m['sharpe_quarterly']}")
print(f"Max drawdown   : ${m['max_dd']:,.0f}")
print(f"\n=== SECTOR WIN RATES ===")
for _, row in sector_grp.iterrows():
    print(f"  {row['sector']:<30} n={row['n']:>5,}  win={row['win_rate']:.1%}  "
          f"avg=${row['avg_pnl']:+.0f}  IV-RV={row['ivrv_spread']:+.1f}pp")
print(f"\n=== ENTRY TIMING ===")
for r in timing_rows:
    print(f"  {r['entry']}  win={r['win_rate']:.1%}  avg=${r['avg_pnl']:+.0f}  sharpe={r['sharpe']}")

