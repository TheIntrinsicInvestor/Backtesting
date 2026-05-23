"""
Build all chart JSONs for the congressional-herd critique report.

Inputs (from earlier scripts):
  data/all_trades.parquet
  data/event_returns_buy.parquet     (includes disc-date + trade-date returns)
  data/event_returns_sell.parquet    (same)
  data/etf_prices.parquet            (NANC, KRUZ, SPY)
  data/politician_committees.parquet (committee assignments + categories)

Outputs (research/congressional-herd/charts/*.json):
  Section 02 (Dead zone):    lag_histogram.json
  Section 03 (What they buy): largest_herds.json, sector_breakdown.json
  Section 04 (Trade vs disc): trade_vs_disc_returns.json
  Section 05 (Committee):     committee_jurisdiction.json
  Section 06 (ETF wrappers):  etf_performance.json
  Section 07 (Aggregate):     kpi_strip.json, forward_returns_curve.json, sensitivity_heatmap.json
  Section 08 (Sells):         sell_herd_returns.json
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

HERE = Path(__file__).parent
DATA = HERE / "data"
CHARTS = HERE / "charts"
CHARTS.mkdir(exist_ok=True)

HORIZONS = [10, 20, 60, 90, 180, 252]

# Sector tickers for the committee jurisdiction test
JURISDICTION_TICKERS = {
    "Financials":  None,   # use sector classification
    "Energy":      None,
    "Defense":     ["LMT", "RTX", "NOC", "GD", "BA", "LHX", "HII", "LDOS", "TDG"],
    "Health":      None,
    "IT":          None,
}

JURISDICTION_SECTORS = {
    "Financials":  ["Financials"],
    "Energy":      ["Energy"],
    "Health":      ["Health Care"],
    "IT":          ["Information Technology"],
    # Defense: ticker-based (defense contractors aren't a GICS sector)
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return float(v)


def round_or_none(v, decimals=4):
    s = safe(v)
    return None if s is None else round(s, decimals)


def compute_stats(series, horizon_days=10):
    er = series.dropna()
    n = len(er)
    if n < 5:
        return {"n": n, "win_rate": None, "mean": None, "median": None, "std": None, "sharpe": None, "t_stat": None}
    mean = float(er.mean())
    std = float(er.std())
    sharpe = float(mean / std * (252 / horizon_days) ** 0.5) if std > 0 else 0.0
    t_stat = float(scipy_stats.ttest_1samp(er, 0).statistic)
    return {
        "n": n,
        "win_rate": float((er > 0).mean()),
        "mean": mean,
        "median": float(er.median()),
        "std": std,
        "sharpe": sharpe,
        "t_stat": t_stat,
    }


def write(name, obj):
    path = CHARTS / name
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)
    return path


# ── Section 02: lag histogram ─────────────────────────────────────────────────

def build_lag_histogram():
    trades = pd.read_parquet(DATA / "all_trades.parquet")
    trades["trade_date"] = pd.to_datetime(trades["trade_date"])
    trades["disclosure_date"] = pd.to_datetime(trades["disclosure_date"])
    lag = (trades["disclosure_date"] - trades["trade_date"]).dt.days
    lag = lag.dropna()
    # Filter to non-negative (true reporting lag); also cap at 365 for display
    valid = lag[(lag >= 0) & (lag <= 365)]
    bins = list(range(0, 105, 5))  # 0-5, 5-10, ..., 95-100, then 100+ as overflow
    counts, edges = np.histogram(valid.clip(upper=100), bins=bins)
    bin_labels = [f"{int(edges[i])}-{int(edges[i+1])}" for i in range(len(bins) - 1)]
    bin_labels[-1] = "95-100+"
    return {
        "bin_labels": bin_labels,
        "counts": counts.tolist(),
        "median": float(valid.median()),
        "mean": float(valid.mean()),
        "p25": float(valid.quantile(0.25)),
        "p75": float(valid.quantile(0.75)),
        "p90": float(valid.quantile(0.90)),
        "n_total": int(len(lag)),
        "n_valid": int(len(valid)),
        "n_negative": int((lag < 0).sum()),
        "n_over_45": int((valid > 45).sum()),  # over STOCK Act 45-day limit
    }


# ── Section 03: what they buy ─────────────────────────────────────────────────

def build_largest_herds(buy_returns):
    primary = buy_returns[(buy_returns["threshold"] == 3) & (buy_returns["window_days"] == 30)]
    top_herds = primary.sort_values("politician_count", ascending=False).head(10)
    rows = []
    for _, row in top_herds.iterrows():
        try:
            pols = list(row["politicians"])
        except Exception:
            pols = []
        preview = ", ".join(pols[:4])
        if len(pols) > 4:
            preview += f", and {len(pols) - 4} more"
        excess = row.get("ret_10d_disc_excess")
        censored = row.get("censored_10d_disc", False)
        rows.append({
            "ticker": str(row["ticker"]),
            "window_start": pd.to_datetime(row["window_start"]).strftime("%Y-%m-%d"),
            "politician_count": int(row["politician_count"]),
            "politicians_preview": preview,
            "excess_10d": None if censored else round_or_none(excess),
        })
    return rows


def build_top_herded_tickers(buy_returns):
    """All threshold-3, 30d events grouped by ticker; top 15 by event count."""
    primary = buy_returns[(buy_returns["threshold"] == 3) & (buy_returns["window_days"] == 30)]
    top = primary.groupby("ticker").size().sort_values(ascending=False).head(15)
    rows = []
    for ticker, count in top.items():
        sub = primary[primary["ticker"] == ticker]
        # average disc-date 10d excess across all events for this ticker (non-censored only)
        excess_series = sub.loc[sub["censored_10d_disc"] == False, "ret_10d_disc_excess"].dropna()
        rows.append({
            "ticker": str(ticker),
            "event_count": int(count),
            "mean_excess_10d": round_or_none(excess_series.mean()) if len(excess_series) else None,
            "n_with_returns": int(len(excess_series)),
        })
    return rows


def build_sector_breakdown(buy_returns):
    primary = buy_returns[(buy_returns["threshold"] == 3) & (buy_returns["window_days"] == 30)]
    p10 = primary[primary["censored_10d_disc"] == False].copy()
    rows = []
    for sec, grp in p10.groupby("sector"):
        sub = grp["ret_10d_disc_excess"].dropna()
        n = len(sub)
        if n < 5:
            continue
        rows.append({
            "sector": str(sec),
            "n_events": int(n),
            "win_rate_10d": round_or_none(float((sub > 0).mean())),
            "mean_excess_10d": round_or_none(float(sub.mean())),
        })
    rows.sort(key=lambda x: x["n_events"], reverse=True)
    return rows


def build_party_chamber(buy_returns):
    primary = buy_returns[(buy_returns["threshold"] == 3) & (buy_returns["window_days"] == 30)]
    p10 = primary[primary["censored_10d_disc"] == False].copy()
    bip = p10[p10["is_bipartisan"] == True]["ret_10d_disc_excess"]
    par = p10[p10["is_bipartisan"] == False]["ret_10d_disc_excess"]
    return {
        "bipartisan": {
            "n": int(len(bip.dropna())),
            "share_of_total": round_or_none(len(p10[p10["is_bipartisan"] == True]) / max(1, len(p10))),
            "mean_excess": round_or_none(bip.mean()),
            "win_rate": round_or_none(float((bip.dropna() > 0).mean()) if len(bip.dropna()) else None),
        },
        "partisan": {
            "n": int(len(par.dropna())),
            "share_of_total": round_or_none(len(p10[p10["is_bipartisan"] == False]) / max(1, len(p10))),
            "mean_excess": round_or_none(par.mean()),
            "win_rate": round_or_none(float((par.dropna() > 0).mean()) if len(par.dropna()) else None),
        },
    }


# ── Section 04: trade-date vs disclosure-date ─────────────────────────────────

def build_trade_vs_disc(buy_returns):
    """
    KEY SECTION: exact holding periods and lag.
    """
    primary = buy_returns[(buy_returns["threshold"] == 3) & (buy_returns["window_days"] == 30)]

    lag_series = primary[["ret_during_lag", "spy_ret_during_lag", "excess_during_lag", "disc_trade_lag_days"]].dropna()
    lag_n = len(lag_series)
    lag_mean = float(lag_series["ret_during_lag"].mean()) if lag_n else None
    lag_excess_mean = float(lag_series["excess_during_lag"].mean()) if lag_n else None
    lag_excess_median = float(lag_series["excess_during_lag"].median()) if lag_n else None
    lag_excess_winrate = float((lag_series["excess_during_lag"] > 0).mean()) if lag_n else None
    lag_days_median = float(lag_series["disc_trade_lag_days"].median()) if lag_n else None

    # Realized returns
    real_df = primary.dropna(subset=["realized_trade_excess", "realized_disc_excess", "realized_hold_days"])
    real_n = len(real_df)
    
    out = {
        "horizons": HORIZONS,
        "disc_mean": [],
        "trade_mean": [],
        "n_events": [],
        
        "lag_n": int(lag_n),
        "lag_days_median": round_or_none(lag_days_median),
        "lag_period_mean_return": round_or_none(lag_mean),
        "lag_period_mean_excess": round_or_none(lag_excess_mean),
        "lag_period_median_excess": round_or_none(lag_excess_median),
        "lag_period_win_rate": round_or_none(lag_excess_winrate),
        
        "realized_n": int(real_n),
        "realized_trade_mean": round_or_none(float(real_df["realized_trade_excess"].mean())) if real_n else None,
        "realized_trade_winrate": round_or_none(float((real_df["realized_trade_excess"] > 0).mean())) if real_n else None,
        "realized_disc_mean": round_or_none(float(real_df["realized_disc_excess"].mean())) if real_n else None,
        "realized_disc_winrate": round_or_none(float((real_df["realized_disc_excess"] > 0).mean())) if real_n else None,
        "realized_hold_days": round_or_none(float(real_df["realized_hold_days"].mean())) if real_n else None,
    }
    
    for h in HORIZONS:
        disc_col = f"ret_{h}d_disc_excess"
        trade_col = f"ret_{h}d_trade_excess"
        paired = primary[primary[f"censored_{h}d_disc"] == False].copy()
        paired = paired[paired[f"censored_{h}d_trade"] == False]
        paired = paired.dropna(subset=[disc_col, trade_col])
        n = len(paired)
        if n < 5:
            out["disc_mean"].append(None)
            out["trade_mean"].append(None)
            out["n_events"].append(int(n))
            continue
        out["disc_mean"].append(round_or_none(paired[disc_col].mean()))
        out["trade_mean"].append(round_or_none(paired[trade_col].mean()))
        out["n_events"].append(int(n))
        
    return out


def build_cumulative_returns(buy_returns):
    crsp = pd.read_parquet(DATA / "crsp_prices.parquet")
    crsp["date"] = pd.to_datetime(crsp["date"])
    spy = pd.read_parquet(DATA / "etf_prices.parquet")
    spy = spy[spy["ticker"] == "SPY"].copy()
    spy["date"] = pd.to_datetime(spy["date"])
    spy = spy.sort_values("date")
    
    primary = buy_returns[(buy_returns["threshold"] == 3) & (buy_returns["window_days"] == 30)].copy()
    primary["hold_days"] = primary["realized_hold_days"].fillna(180)
    
    min_date = pd.to_datetime(primary["entry_trade_date"]).min()
    dates = spy[spy["date"] >= min_date]["date"].sort_values().reset_index(drop=True)
    
    spy_prc = spy.set_index("date")["prc"].to_dict()
    crsp_prc = {}
    for permno, grp in crsp.groupby("permno"):
        crsp_prc[permno] = grp.set_index("date")["prc"].to_dict()
        
    cum_trade = np.zeros(len(dates))
    cum_disc = np.zeros(len(dates))
    cum_spy_trade = np.zeros(len(dates))
    cum_spy_disc = np.zeros(len(dates))
    
    for _, row in primary.iterrows():
        permno = row["permno"]
        if pd.isna(permno) or permno not in crsp_prc:
            continue
            
        stock_prc_map = crsp_prc[permno]
        hold_days = row["hold_days"]
        
        # Trade date path
        t_entry = pd.to_datetime(row["entry_trade_date"])
        if pd.notna(t_entry):
            t_exit = t_entry + pd.Timedelta(days=hold_days)
            entry_p = stock_prc_map.get(t_entry)
            spy_entry_p = spy_prc.get(t_entry)
            
            if entry_p is None:
                for i in range(1, 6):
                    entry_p = stock_prc_map.get(t_entry + pd.Timedelta(days=i))
                    if entry_p is not None: break
            if spy_entry_p is None:
                for i in range(1, 6):
                    spy_entry_p = spy_prc.get(t_entry + pd.Timedelta(days=i))
                    if spy_entry_p is not None: break
                        
            if entry_p and spy_entry_p:
                realized = 0.0
                spy_realized = 0.0
                closed = False
                for i, d in enumerate(dates):
                    if d < t_entry:
                        continue
                    if d > t_exit:
                        if not closed:
                            last_p = stock_prc_map.get(d)
                            if last_p: realized = (last_p / entry_p) - 1
                            last_spy = spy_prc.get(d)
                            if last_spy: spy_realized = (last_spy / spy_entry_p) - 1
                            closed = True
                        cum_trade[i] += realized
                        cum_spy_trade[i] += spy_realized
                    else:
                        curr_p = stock_prc_map.get(d)
                        if curr_p:
                            realized = (curr_p / entry_p) - 1
                        cum_trade[i] += realized
                        
                        curr_spy = spy_prc.get(d)
                        if curr_spy:
                            spy_realized = (curr_spy / spy_entry_p) - 1
                        cum_spy_trade[i] += spy_realized

        # Disc date path
        d_entry = pd.to_datetime(row["entry_disclosure_date"])
        if pd.notna(d_entry):
            d_exit = d_entry + pd.Timedelta(days=hold_days)
            entry_p = stock_prc_map.get(d_entry)
            spy_entry_p = spy_prc.get(d_entry)
            
            if entry_p is None:
                for i in range(1, 6):
                    entry_p = stock_prc_map.get(d_entry + pd.Timedelta(days=i))
                    if entry_p is not None: break
            if spy_entry_p is None:
                for i in range(1, 6):
                    spy_entry_p = spy_prc.get(d_entry + pd.Timedelta(days=i))
                    if spy_entry_p is not None: break
                        
            if entry_p and spy_entry_p:
                realized = 0.0
                spy_realized = 0.0
                closed = False
                for i, d in enumerate(dates):
                    if d < d_entry:
                        continue
                    if d > d_exit:
                        if not closed:
                            last_p = stock_prc_map.get(d)
                            if last_p: realized = (last_p / entry_p) - 1
                            last_spy = spy_prc.get(d)
                            if last_spy: spy_realized = (last_spy / spy_entry_p) - 1
                            closed = True
                        cum_disc[i] += realized
                        cum_spy_disc[i] += spy_realized
                    else:
                        curr_p = stock_prc_map.get(d)
                        if curr_p:
                            realized = (curr_p / entry_p) - 1
                        cum_disc[i] += realized
                        
                        curr_spy = spy_prc.get(d)
                        if curr_spy:
                            spy_realized = (curr_spy / spy_entry_p) - 1
                        cum_spy_disc[i] += spy_realized

    step = max(1, len(dates) // 250)
    keep = list(range(0, len(dates), step))
    if keep[-1] != len(dates) - 1:
        keep.append(len(dates) - 1)
        
    return {
        "dates": [dates[i].strftime("%Y-%m-%d") for i in keep],
        "cum_trade": [round(float(cum_trade[i]), 3) for i in keep],
        "cum_disc": [round(float(cum_disc[i]), 3) for i in keep],
        "cum_spy_trade": [round(float(cum_spy_trade[i]), 3) for i in keep],
        "cum_spy_disc": [round(float(cum_spy_disc[i]), 3) for i in keep]
    }


# ── Section 05: committee jurisdiction ────────────────────────────────────────

def build_committee_jurisdiction(buy_returns):
    cmt_path = DATA / "politician_committees.parquet"
    if not cmt_path.exists():
        return {"error": "committee data not available", "categories": []}
    cmt = pd.read_parquet(cmt_path)

    # politician name -> set of categories
    name_to_cats = {}
    for _, row in cmt.iterrows():
        cats = row.get("committee_categories")
        if isinstance(cats, np.ndarray):
            cats = cats.tolist()
        if not isinstance(cats, list):
            cats = []
        name_to_cats[row["name"]] = set(cats)

    primary = buy_returns[(buy_returns["threshold"] == 3) & (buy_returns["window_days"] == 30)].copy()
    primary = primary[primary["censored_10d_disc"] == False]

    # For each event, get the set of categories represented by any herd member
    def event_cats(politicians):
        if not isinstance(politicians, (list, np.ndarray)):
            return set()
        s = set()
        for p in politicians:
            s |= name_to_cats.get(p, set())
        return s

    primary["event_cats"] = primary["politicians"].apply(event_cats)

    # Defense: ticker-based test
    defense_tickers = set(JURISDICTION_TICKERS["Defense"])

    out = {"categories": []}
    for cat in ["Financials", "Energy", "Health", "IT", "Defense"]:
        # Define "in jurisdiction" for an event: ticker matches jurisdiction AND >=1 herd member sits on that category's committee
        if cat == "Defense":
            ticker_match = primary["ticker"].isin(defense_tickers)
        else:
            sectors = JURISDICTION_SECTORS.get(cat, [])
            ticker_match = primary["sector"].isin(sectors)

        cat_match = primary["event_cats"].apply(lambda s: cat in s)

        in_juris = primary[ticker_match & cat_match]
        out_juris = primary[ticker_match & ~cat_match]
        random_other = primary[~ticker_match]

        def _agg(sub):
            s = sub["ret_10d_disc_excess"].dropna()
            if len(s) < 3:
                return {"n": int(len(s)), "mean_excess": None, "win_rate": None}
            return {
                "n": int(len(s)),
                "mean_excess": round_or_none(s.mean()),
                "win_rate": round_or_none(float((s > 0).mean())),
            }

        out["categories"].append({
            "category": cat,
            "in_jurisdiction": _agg(in_juris),       # ticker in sector AND herd member on committee
            "out_jurisdiction": _agg(out_juris),     # ticker in sector but NO herd member on committee
            "non_sector":       _agg(random_other),  # ticker NOT in sector (baseline)
        })

    return out


# ── Section 06: ETF wrappers ──────────────────────────────────────────────────

def build_etf_performance():
    etf_path = DATA / "etf_prices.parquet"
    if not etf_path.exists():
        return {"error": "etf data not available"}
    df = pd.read_parquet(etf_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["ticker", "date"])

    # Inception of NANC/KRUZ is 2023-02. Rebase all to 100 from the latest common start date.
    common_start = max(df[df["ticker"] == t]["date"].min() for t in ["NANC", "KRUZ", "SPY"])
    df = df[df["date"] >= common_start].copy()

    out = {"start_date": common_start.strftime("%Y-%m-%d")}
    series = {}
    for t in ["NANC", "KRUZ", "SPY"]:
        sub = df[df["ticker"] == t].sort_values("date").reset_index(drop=True)
        if sub.empty:
            continue
        rebased = (sub["prc"] / sub.iloc[0]["prc"]) * 100
        # Downsample to ~250 points for chart performance
        if len(sub) > 260:
            step = len(sub) // 250 + 1
            keep = list(range(0, len(sub), step)) + [len(sub) - 1]
            keep = sorted(set(keep))
        else:
            keep = list(range(len(sub)))
        series[t] = {
            "dates": sub.iloc[keep]["date"].dt.strftime("%Y-%m-%d").tolist(),
            "values": [round(float(rebased.iloc[i]), 3) for i in keep],
            "cum_return": round_or_none(float((sub.iloc[-1]["prc"] / sub.iloc[0]["prc"]) - 1)),
        }
    out["series"] = series
    # Annualised stats
    for t in ["NANC", "KRUZ", "SPY"]:
        sub = df[df["ticker"] == t].dropna(subset=["ret"])
        if sub.empty:
            continue
        daily_ret = sub["ret"].values
        ann_ret = (1 + np.mean(daily_ret)) ** 252 - 1
        ann_vol = np.std(daily_ret) * np.sqrt(252)
        sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
        series[t]["ann_return"] = round_or_none(float(ann_ret))
        series[t]["ann_vol"] = round_or_none(float(ann_vol))
        series[t]["sharpe"] = round_or_none(float(sharpe))
    # Excess vs SPY (cumulative)
    spy_cum = series.get("SPY", {}).get("cum_return")
    for t in ["NANC", "KRUZ"]:
        if t in series and spy_cum is not None:
            series[t]["cum_excess_vs_spy"] = round_or_none(series[t]["cum_return"] - spy_cum)
    return out


# ── Section 07: aggregate backtest ────────────────────────────────────────────

def build_kpi_strip(buy_returns):
    primary = buy_returns[(buy_returns["threshold"] == 3) & (buy_returns["window_days"] == 30)]
    p10 = primary[primary["censored_10d_disc"] == False]
    stats = compute_stats(p10["ret_10d_disc_excess"], 10)
    return {
        "n_events": stats["n"],
        "win_rate_10d": round_or_none(stats["win_rate"]),
        "mean_excess_10d": round_or_none(stats["mean"]),
        "sharpe_10d": round_or_none(stats["sharpe"]),
        "t_stat_10d": round_or_none(stats["t_stat"]),
    }


def build_forward_returns_curve(buy_returns):
    primary = buy_returns[(buy_returns["threshold"] == 3) & (buy_returns["window_days"] == 30)]
    out = {"horizons": HORIZONS, "mean_excess": [], "p25_excess": [], "p75_excess": [], "n_events": []}
    for h in HORIZONS:
        sub = primary[primary[f"censored_{h}d_disc"] == False][f"ret_{h}d_disc_excess"].dropna()
        if len(sub) >= 5:
            out["mean_excess"].append(round_or_none(sub.mean()))
            out["p25_excess"].append(round_or_none(sub.quantile(0.25)))
            out["p75_excess"].append(round_or_none(sub.quantile(0.75)))
        else:
            out["mean_excess"].append(None)
            out["p25_excess"].append(None)
            out["p75_excess"].append(None)
        out["n_events"].append(int(len(sub)))
    return out


def build_sensitivity(buy_returns):
    thresholds = [2, 3, 4, 5]
    windows = [14, 30, 60]
    win_rates, mean_excess, n_grid = [], [], []
    for thr in thresholds:
        row_wr, row_me, row_n = [], [], []
        for win in windows:
            sub = buy_returns[(buy_returns["threshold"] == thr) & (buy_returns["window_days"] == win)]
            sub10 = sub[sub["censored_10d_disc"] == False]["ret_10d_disc_excess"].dropna()
            n = len(sub10)
            row_wr.append(round_or_none(float((sub10 > 0).mean())) if n >= 5 else None)
            row_me.append(round_or_none(float(sub10.mean())) if n >= 5 else None)
            row_n.append(int(n))
        win_rates.append(row_wr)
        mean_excess.append(row_me)
        n_grid.append(row_n)
    return {
        "thresholds": thresholds,
        "windows": windows,
        "win_rates": win_rates,
        "mean_excess": mean_excess,
        "n_events": n_grid,
    }


# ── Section 08: sells ─────────────────────────────────────────────────────────

def build_sell_herd_returns(sell_returns):
    primary = sell_returns[(sell_returns["threshold"] == 3) & (sell_returns["window_days"] == 30)]
    p10 = primary[primary["censored_10d_disc"] == False]

    # forward returns curve for sells
    curve = {"horizons": HORIZONS, "mean_excess": [], "p25_excess": [], "p75_excess": [], "n_events": []}
    for h in HORIZONS:
        sub = primary[primary[f"censored_{h}d_disc"] == False][f"ret_{h}d_disc_excess"].dropna()
        if len(sub) >= 5:
            curve["mean_excess"].append(round_or_none(sub.mean()))
            curve["p25_excess"].append(round_or_none(sub.quantile(0.25)))
            curve["p75_excess"].append(round_or_none(sub.quantile(0.75)))
        else:
            curve["mean_excess"].append(None)
            curve["p25_excess"].append(None)
            curve["p75_excess"].append(None)
        curve["n_events"].append(int(len(sub)))

    stats10 = compute_stats(p10["ret_10d_disc_excess"], 10)

    # Trade-date vs disclosure-date for sells too
    paired = primary[
        (primary["censored_10d_disc"] == False) &
        (primary["censored_10d_trade"] == False)
    ].dropna(subset=["ret_10d_disc_excess", "ret_10d_trade_excess"])
    disc_mean = float(paired["ret_10d_disc_excess"].mean()) if len(paired) else None
    trade_mean = float(paired["ret_10d_trade_excess"].mean()) if len(paired) else None

    # Top sold tickers (sell herds)
    top_sold = primary.groupby("ticker").size().sort_values(ascending=False).head(10)
    top_rows = []
    for ticker, count in top_sold.items():
        sub = primary[primary["ticker"] == ticker]
        excess_series = sub.loc[sub["censored_10d_disc"] == False, "ret_10d_disc_excess"].dropna()
        top_rows.append({
            "ticker": str(ticker),
            "event_count": int(count),
            "mean_excess_10d": round_or_none(excess_series.mean()) if len(excess_series) else None,
            "n_with_returns": int(len(excess_series)),
        })

    return {
        "kpi": {
            "n_events": stats10["n"],
            "win_rate_10d": round_or_none(stats10["win_rate"]),
            "mean_excess_10d": round_or_none(stats10["mean"]),
            "sharpe_10d": round_or_none(stats10["sharpe"]),
            "t_stat_10d": round_or_none(stats10["t_stat"]),
        },
        "curve": curve,
        "trade_vs_disc": {
            "n_paired": int(len(paired)),
            "disc_mean_10d": round_or_none(disc_mean),
            "trade_mean_10d": round_or_none(trade_mean),
        },
        "top_sold_tickers": top_rows,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading data...")
    buy = pd.read_parquet(DATA / "event_returns_buy.parquet")
    sell = pd.read_parquet(DATA / "event_returns_sell.parquet")

    print("\n--- Section 02: lag histogram ---")
    lag = build_lag_histogram()
    write("lag_histogram.json", lag)
    print(f"  median={lag['median']:.1f}d, mean={lag['mean']:.1f}d, n_over_45={lag['n_over_45']:,} ({lag['n_over_45']/lag['n_valid']*100:.1f}%)")

    print("\n--- Section 03: what they buy ---")
    write("largest_herds.json", build_largest_herds(buy))
    write("top_herded_tickers.json", build_top_herded_tickers(buy))
    write("sector_breakdown.json", build_sector_breakdown(buy))
    write("party_chamber.json", build_party_chamber(buy))

    print("\n--- Section 04: trade-date vs disclosure-date ---")
    tvd = build_trade_vs_disc(buy)
    write("trade_vs_disc_returns.json", tvd)
    
    print("  Building cumulative time series...")
    cum = build_cumulative_returns(buy)
    write("cumulative_returns.json", cum)
    
    print(f"  DURING LAG (median {tvd['lag_days_median']:.0f}d): "
          f"mean stock ret {tvd['lag_period_mean_return']:+.4f}  "
          f"mean excess vs SPY {tvd['lag_period_mean_excess']:+.4f}  "
          f"win rate {tvd['lag_period_win_rate']:.1%}  n={tvd['lag_n']}")
    print(f"  REALIZED: n={tvd['realized_n']}, hold={tvd['realized_hold_days']:.0f}d")
    print(f"    Politician: mean={tvd['realized_trade_mean']:+.4f}, winrate={tvd['realized_trade_winrate']:.1%}")
    print(f"    Follower:   mean={tvd['realized_disc_mean']:+.4f}, winrate={tvd['realized_disc_winrate']:.1%}")

    print("\n--- Section 05: committee jurisdiction ---")
    cmt = build_committee_jurisdiction(buy)
    write("committee_jurisdiction.json", cmt)
    def _fmt(v):
        return f"{v:+.4f}" if v is not None else " NA   "
    for c in cmt.get("categories", []):
        ij = c["in_jurisdiction"]
        oj = c["out_jurisdiction"]
        print(f"  {c['category']:<12} in-juris n={ij['n']:>3} mean={_fmt(ij['mean_excess'])} | out-juris n={oj['n']:>3} mean={_fmt(oj['mean_excess'])}")

    print("\n--- Section 06: ETF wrappers ---")
    etf = build_etf_performance()
    write("etf_performance.json", etf)
    for t in ["NANC", "KRUZ", "SPY"]:
        s = etf.get("series", {}).get(t)
        if s:
            print(f"  {t}: cum_ret={s['cum_return']:+.2%}  ann={s.get('ann_return', 0):+.2%}  sharpe={s.get('sharpe', 0):+.2f}")

    print("\n--- Section 07: aggregate backtest ---")
    kpi = build_kpi_strip(buy)
    write("kpi_strip.json", kpi)
    write("forward_returns_curve.json", build_forward_returns_curve(buy))
    write("sensitivity_heatmap.json", build_sensitivity(buy))
    print(f"  KPI: n={kpi['n_events']}, win_rate={kpi['win_rate_10d']:.1%}, mean_excess={kpi['mean_excess_10d']:+.2%}, sharpe={kpi['sharpe_10d']:+.2f}, t={kpi['t_stat_10d']:+.2f}")

    print("\n--- Section 08: sells ---")
    sells = build_sell_herd_returns(sell)
    write("sell_herd_returns.json", sells)
    write("sell_sensitivity_heatmap.json", build_sensitivity(sell))
    skpi = sells["kpi"]
    print(f"  Sell KPI: n={skpi['n_events']}, win_rate={skpi['win_rate_10d']:.1%}, mean_excess={skpi['mean_excess_10d']:+.2%}, sharpe={skpi['sharpe_10d']:+.2f}, t={skpi['t_stat_10d']:+.2f}")

    print("\nAll chart JSONs written.")


if __name__ == "__main__":
    main()
