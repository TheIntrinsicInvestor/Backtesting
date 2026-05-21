import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as scipy_stats

CHARTS_DIR = Path(__file__).parent / "charts"
CHARTS_DIR.mkdir(exist_ok=True)
DATA_DIR = Path(__file__).parent / "data"

HORIZONS = [10, 20, 60, 90, 180, 252]


def safe(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return float(v)


def compute_stats(excess_series, horizon_days):
    er = excess_series.dropna()
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


def main():
    df = pd.read_parquet(DATA_DIR / "event_returns.parquet")
    df["entry_date"] = pd.to_datetime(df["entry_date"])

    for col in ["window_start", "entry_trade_date", "entry_disclosure_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])

    primary = df[(df["threshold"] == 3) & (df["window_days"] == 30)].copy()

    # ── 1. KPI strip ─────────────────────────────────────────────────────────────
    p60 = primary[primary["censored_60d"] == False].copy()
    kpi_stats = compute_stats(p60["ret_60d_excess"], 60)
    kpi = {
        "n_events": kpi_stats["n"],
        "win_rate_60d": round(kpi_stats["win_rate"], 4) if kpi_stats["win_rate"] is not None else None,
        "mean_excess_60d": round(kpi_stats["mean"], 4) if kpi_stats["mean"] is not None else None,
        "sharpe_60d": round(kpi_stats["sharpe"], 4) if kpi_stats["sharpe"] is not None else None,
        "t_stat_60d": round(kpi_stats["t_stat"], 4) if kpi_stats["t_stat"] is not None else None,
    }
    with open(CHARTS_DIR / "kpi_strip.json", "w") as f:
        json.dump(kpi, f, indent=2)
    print(
        f"KPI: n={kpi['n_events']}, "
        f"win_rate_60d={kpi['win_rate_60d']:.1%}, "
        f"mean_excess={kpi['mean_excess_60d']:.2%}, "
        f"sharpe={kpi['sharpe_60d']:.2f}, "
        f"t={kpi['t_stat_60d']:.2f}"
    )

    # ── 2. Forward returns curve ──────────────────────────────────────────────────
    curve = {"horizons": HORIZONS, "mean_excess": [], "p25_excess": [], "p75_excess": [], "n_events": []}
    for n in HORIZONS:
        censor_col = f"censored_{n}d"
        ret_col = f"ret_{n}d_excess"
        sub = primary[primary[censor_col] == False][ret_col].dropna()
        curve["mean_excess"].append(round(float(sub.mean()), 4) if len(sub) >= 5 else None)
        curve["p25_excess"].append(round(float(sub.quantile(0.25)), 4) if len(sub) >= 5 else None)
        curve["p75_excess"].append(round(float(sub.quantile(0.75)), 4) if len(sub) >= 5 else None)
        curve["n_events"].append(int(len(sub)))
    with open(CHARTS_DIR / "forward_returns_curve.json", "w") as f:
        json.dump(curve, f, indent=2)

    # ── 3. Sensitivity heatmap ────────────────────────────────────────────────────
    thresholds = [2, 3, 4, 5]
    windows = [14, 30, 60]
    win_rates = []
    n_events_grid = []
    for thr in thresholds:
        row_wr = []
        row_n = []
        for win in windows:
            sub = df[(df["threshold"] == thr) & (df["window_days"] == win)]
            sub60 = sub[sub["censored_60d"] == False]["ret_60d_excess"].dropna()
            n = len(sub60)
            row_wr.append(round(float((sub60 > 0).mean()), 4) if n >= 5 else None)
            row_n.append(int(n))
        win_rates.append(row_wr)
        n_events_grid.append(row_n)
    sens = {
        "thresholds": thresholds,
        "windows": windows,
        "win_rates": win_rates,
        "n_events": n_events_grid,
    }
    with open(CHARTS_DIR / "sensitivity_heatmap.json", "w") as f:
        json.dump(sens, f, indent=2)
    primary_wr = win_rates[thresholds.index(3)][windows.index(30)]
    print(f"Sensitivity: win rates at (3+,30d) = {primary_wr:.1%}" if primary_wr is not None else "Sensitivity: win rates at (3+,30d) = N/A")

    # ── 4. Sector breakdown ───────────────────────────────────────────────────────
    sector_rows = []
    for sec, grp in p60.groupby("sector"):
        sub = grp["ret_60d_excess"].dropna()
        n = len(sub)
        if n < 5:
            continue
        sector_rows.append({
            "sector": str(sec),
            "win_rate_60d": round(float((sub > 0).mean()), 4),
            "mean_excess_60d": round(float(sub.mean()), 4),
            "n_events": int(n),
        })
    sector_rows.sort(key=lambda x: x["n_events"], reverse=True)
    with open(CHARTS_DIR / "sector_breakdown.json", "w") as f:
        json.dump(sector_rows, f, indent=2)

    # ── 5. Market cap breakdown ───────────────────────────────────────────────────
    p60_mktcap = p60.dropna(subset=["mkt_cap_at_entry"]).copy()
    p60_mktcap["mktcap_q"] = pd.qcut(
        p60_mktcap["mkt_cap_at_entry"],
        q=5,
        labels=["Q1 (Smallest)", "Q2", "Q3", "Q4", "Q5 (Largest)"],
    )
    mktcap_rows = []
    for i, label in enumerate(["Q1 (Smallest)", "Q2", "Q3", "Q4", "Q5 (Largest)"], start=1):
        sub = p60_mktcap[p60_mktcap["mktcap_q"] == label]["ret_60d_excess"].dropna()
        n = len(sub)
        mktcap_rows.append({
            "quintile": i,
            "label": label,
            "win_rate_60d": round(float((sub > 0).mean()), 4) if n >= 5 else None,
            "mean_excess_60d": round(float(sub.mean()), 4) if n >= 5 else None,
            "n_events": int(n),
        })
    with open(CHARTS_DIR / "mkt_cap_breakdown.json", "w") as f:
        json.dump(mktcap_rows, f, indent=2)

    # ── 6. Party / chamber breakdown ─────────────────────────────────────────────
    def _all_dem(row):
        parties = row["parties_in_herd"]
        return isinstance(parties, list) and len(parties) > 0 and all(p == "Democrat" for p in parties)

    def _all_rep(row):
        parties = row["parties_in_herd"]
        return isinstance(parties, list) and len(parties) > 0 and all(p == "Republican" for p in parties)

    def _house_only(row):
        chambers = row["chambers_in_herd"]
        return isinstance(chambers, list) and len(chambers) > 0 and all(c == "House" for c in chambers)

    def _senate_only(row):
        chambers = row["chambers_in_herd"]
        return isinstance(chambers, list) and len(chambers) > 0 and all(c == "Senate" for c in chambers)

    def _both_chambers(row):
        chambers = row["chambers_in_herd"]
        return isinstance(chambers, list) and "House" in chambers and "Senate" in chambers

    masks = {
        "All Dem": p60.apply(_all_dem, axis=1),
        "All Rep": p60.apply(_all_rep, axis=1),
        "Bipartisan": p60["is_bipartisan"] == True,
        "House Only": p60.apply(_house_only, axis=1),
        "Senate Only": p60.apply(_senate_only, axis=1),
        "Both Chambers": p60.apply(_both_chambers, axis=1),
    }
    categories = list(masks.keys())
    pc_win_rate, pc_mean_excess, pc_n_events, pc_sharpe = [], [], [], []
    for cat in categories:
        sub = p60[masks[cat]]["ret_60d_excess"].dropna()
        n = len(sub)
        st = compute_stats(sub, 60)
        pc_win_rate.append(round(st["win_rate"], 4) if st["win_rate"] is not None else None)
        pc_mean_excess.append(round(st["mean"], 4) if st["mean"] is not None else None)
        pc_n_events.append(int(n))
        pc_sharpe.append(round(st["sharpe"], 4) if st["sharpe"] is not None else None)
    party_chamber = {
        "categories": categories,
        "win_rate": pc_win_rate,
        "mean_excess": pc_mean_excess,
        "n_events": pc_n_events,
        "sharpe": pc_sharpe,
    }
    with open(CHARTS_DIR / "party_chamber.json", "w") as f:
        json.dump(party_chamber, f, indent=2)

    # ── 7. Top politicians ────────────────────────────────────────────────────────
    p60_pol = p60.copy()
    p60_pol["politicians_exploded"] = p60_pol["politicians"].apply(
        lambda x: x if isinstance(x, list) else []
    )
    exploded = p60_pol.explode("politicians_exploded")
    exploded = exploded.dropna(subset=["politicians_exploded"])
    exploded = exploded[exploded["politicians_exploded"].astype(str).str.strip() != ""]

    pol_rows = []
    for name, grp in exploded.groupby("politicians_exploded"):
        sub = grp["ret_60d_excess"].dropna()
        n = len(sub)
        if n < 10:
            continue
        pol_rows.append({
            "name": str(name),
            "n_events": int(n),
            "win_rate_60d": round(float((sub > 0).mean()), 4),
            "mean_excess_60d": round(float(sub.mean()), 4),
        })
    pol_rows.sort(key=lambda x: x["n_events"], reverse=True)
    pol_rows = pol_rows[:20]
    with open(CHARTS_DIR / "top_politicians.json", "w") as f:
        json.dump(pol_rows, f, indent=2)

    # ── 8 & 9. Portfolio equity curves ───────────────────────────────────────────
    mean_pol_count = float(primary["politician_count"].mean())

    def build_equity_curve(events_df, size_weighted=False):
        events_sorted = events_df.dropna(subset=["ret_60d_abs"]).sort_values("entry_date").copy()
        if len(events_sorted) == 0:
            return {"dates": [], "strategy_value": [], "spy_value": [], "total_events": 0}

        if size_weighted:
            events_sorted["position_size"] = 10_000 * (events_sorted["politician_count"] / mean_pol_count)
        else:
            events_sorted["position_size"] = 10_000.0

        first_entry = events_sorted["entry_date"].min()
        last_entry = events_sorted["entry_date"].max()
        last_exit = last_entry + pd.Timedelta(days=84)
        all_dates = pd.date_range(start=first_entry, end=last_exit, freq="D")

        strat_vals = []
        spy_vals = []
        for d in all_dates:
            active = events_sorted[
                (events_sorted["entry_date"] <= d) &
                (d < events_sorted["entry_date"] + pd.Timedelta(days=84))
            ]
            if len(active) == 0:
                strat_vals.append(np.nan)
                spy_vals.append(np.nan)
                continue
            strat_total = 0.0
            spy_total = 0.0
            for _, ev in active.iterrows():
                entry = ev["entry_date"]
                exit_d = entry + pd.Timedelta(days=84)
                duration = (exit_d - entry).days
                if duration <= 0:
                    fraction = 1.0
                else:
                    fraction = min(1.0, (d - entry).days / duration)
                pos_size = ev["position_size"]
                strat_total += pos_size * (1.0 + ev["ret_60d_abs"] * fraction)
                spy_total += pos_size * (1.0 + (ev["ret_60d_spy"] if pd.notna(ev["ret_60d_spy"]) else 0.0) * fraction)
            strat_vals.append(strat_total)
            spy_vals.append(spy_total)

        strat_series = pd.Series(strat_vals, index=all_dates)
        spy_series = pd.Series(spy_vals, index=all_dates)
        strat_series = strat_series.dropna()
        spy_series = spy_series.dropna()

        if len(strat_series) == 0:
            return {"dates": [], "strategy_value": [], "spy_value": [], "total_events": int(len(events_sorted))}

        strat_rebased = strat_series / strat_series.iloc[0] * 100
        spy_rebased = spy_series / spy_series.iloc[0] * 100

        combined = pd.DataFrame({"strat": strat_rebased, "spy": spy_rebased}).dropna()

        if len(combined) > 500:
            step = len(combined) // 500 + 1
            combined = combined.iloc[::step]

        return {
            "dates": [d.strftime("%Y-%m-%d") for d in combined.index],
            "strategy_value": [round(v, 4) for v in combined["strat"]],
            "spy_value": [round(v, 4) for v in combined["spy"]],
            "total_events": int(len(events_sorted)),
        }

    eq_curve = build_equity_curve(primary, size_weighted=False)
    with open(CHARTS_DIR / "portfolio_eq_weight.json", "w") as f:
        json.dump(eq_curve, f, indent=2)

    sw_curve = build_equity_curve(primary, size_weighted=True)
    with open(CHARTS_DIR / "portfolio_size_weighted.json", "w") as f:
        json.dump(sw_curve, f, indent=2)

    # ── 10. Bipartisan vs partisan ────────────────────────────────────────────────
    bip = p60[p60["is_bipartisan"] == True]["ret_60d_excess"]
    par = p60[p60["is_bipartisan"] == False]["ret_60d_excess"]
    bip_stats = compute_stats(bip, 60)
    par_stats = compute_stats(par, 60)

    def _stats_dict(st):
        return {
            "n": st["n"],
            "win_rate": round(st["win_rate"], 4) if st["win_rate"] is not None else None,
            "mean_excess": round(st["mean"], 4) if st["mean"] is not None else None,
            "median_excess": round(st["median"], 4) if st["median"] is not None else None,
            "sharpe": round(st["sharpe"], 4) if st["sharpe"] is not None else None,
            "t_stat": round(st["t_stat"], 4) if st["t_stat"] is not None else None,
        }

    bvp = {"bipartisan": _stats_dict(bip_stats), "partisan": _stats_dict(par_stats)}
    with open(CHARTS_DIR / "bipartisan_vs_partisan.json", "w") as f:
        json.dump(bvp, f, indent=2)

    # ── 11. Largest herds ─────────────────────────────────────────────────────────
    top_herds = primary.sort_values("politician_count", ascending=False).head(10)
    herd_rows = []
    for _, row in top_herds.iterrows():
        pols = row["politicians"] if isinstance(row["politicians"], list) else []
        preview = ", ".join(pols[:4])
        if len(pols) > 4:
            preview += "..."
        excess_val = safe(row.get("ret_60d_excess"))
        censored = row.get("censored_60d", False)
        herd_rows.append({
            "ticker": str(row["ticker"]),
            "window_start": row["window_start"].strftime("%Y-%m-%d") if pd.notna(row["window_start"]) else None,
            "politician_count": int(row["politician_count"]),
            "politicians_preview": preview,
            "excess_60d": None if censored else (round(excess_val, 4) if excess_val is not None else None),
        })
    with open(CHARTS_DIR / "largest_herds.json", "w") as f:
        json.dump(herd_rows, f, indent=2)

    # ── Final summary ─────────────────────────────────────────────────────────────
    written = [
        "kpi_strip.json",
        "forward_returns_curve.json",
        "sensitivity_heatmap.json",
        "sector_breakdown.json",
        "mkt_cap_breakdown.json",
        "party_chamber.json",
        "top_politicians.json",
        "portfolio_eq_weight.json",
        "portfolio_size_weighted.json",
        "bipartisan_vs_partisan.json",
        "largest_herds.json",
    ]
    print("\nJSON files written:")
    for fname in written:
        path = CHARTS_DIR / fname
        print(f"  {path}")


if __name__ == "__main__":
    main()
