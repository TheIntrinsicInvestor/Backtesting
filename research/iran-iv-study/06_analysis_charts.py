"""
06_analysis_charts.py
---------------------
Analysis engine and Chart.js output generator.

Produces:
  charts/data_iv_profile.json   — average normalised IV profile + confidence band
  charts/data_heatmap.json      — IV change at T0/T+5/T+10/T+30 per event/ticker
  charts/data_pnl.json          — strategy backtest cumulative P&L
  charts/preview.html           — standalone preview of all three charts

Strategy derivation is data-driven: the script analyses the average
composite IV profile, identifies the peak and decay structure, and
derives the trade rule from what the data shows.
"""

import os, json
import numpy as np
import pandas as pd

os.makedirs("charts", exist_ok=True)

# ── Load data ─────────────────────────────────────────────────────────────────
profiles = pd.read_parquet("data/event_iv_profiles.parquet")
metadata = pd.read_parquet("data/event_metadata.parquet")

ok_meta   = metadata[metadata["status"] == "OK"].copy()
ok_ids    = ok_meta["event_id"].tolist()
profiles  = profiles[profiles["event_id"].isin(ok_ids)].copy()

# Attach labels for display
id_to_label   = dict(zip(metadata["event_id"], metadata["label"]))
id_to_cluster = dict(zip(metadata["event_id"], metadata["cluster"]))

# ── Composite IV: average across available tickers per event × t_day ─────────
composite = (
    profiles
    .dropna(subset=["iv_norm"])
    .groupby(["event_id", "t_day"])["iv_norm"]
    .mean()
    .reset_index()
    .rename(columns={"iv_norm": "iv_composite"})
)

# ── Chart 1: Average normalised IV profile ────────────────────────────────────
t_days_full = list(range(-20, 31))

avg = (
    composite
    .groupby("t_day")["iv_composite"]
    .agg(mean="mean", std="std", n="count")
    .reindex(t_days_full)
)

avg["ci_upper"] = avg["mean"] + avg["std"]
avg["ci_lower"] = avg["mean"] - avg["std"]

# Identify peak and strategy
peak_t   = int(avg["mean"].idxmax())
peak_val = float(avg["mean"].max())

# Find first t_day >= peak where mean drops back below 103
decay_mask = (avg.index >= peak_t) & (avg["mean"] < 103)
exit_t = int(decay_mask[decay_mask].index[0]) if decay_mask.any() else 30

print(f"Average composite IV peak: {peak_val:.1f} at T{peak_t:+d}")
print(f"IV mean-reverts to <103 at T{exit_t:+d}")
print(f"Strategy: short vol at T0 close, exit at T{exit_t:+d}\n")

# Serialize chart 1
chart1_data = {
    "labels":   [f"T{d:+d}" if d != 0 else "T0" for d in t_days_full],
    "mean":     [round(float(avg.loc[d, "mean"]), 2) if not np.isnan(avg.loc[d, "mean"]) else None for d in t_days_full],
    "ci_upper": [round(float(avg.loc[d, "ci_upper"]), 2) if not np.isnan(avg.loc[d, "ci_upper"]) else None for d in t_days_full],
    "ci_lower": [round(float(avg.loc[d, "ci_lower"]), 2) if not np.isnan(avg.loc[d, "ci_lower"]) else None for d in t_days_full],
    "n_events": int(avg["n"].max()),
    "peak_t":   peak_t,
    "peak_val": round(peak_val, 2),
    "exit_t":   exit_t,
    "baseline": 100,
}
with open("charts/data_iv_profile.json", "w") as f:
    json.dump(chart1_data, f, indent=2)
print("Saved charts/data_iv_profile.json")

# ── Chart 2: Heatmap — IV change at key checkpoints ──────────────────────────
CHECKPOINTS = [0, 5, 10, 30]
TICKERS     = ["XLE", "USO", "XOM", "CVX"]

# For each event × ticker × checkpoint, compute iv_norm - 100
heat_rows = []
for eid in ok_ids:
    ev_profiles = profiles[profiles["event_id"] == eid]
    for ticker in TICKERS:
        tk_data = ev_profiles[ev_profiles["ticker"] == ticker].set_index("t_day")["iv_norm"]
        for cp in CHECKPOINTS:
            val = tk_data.get(cp, np.nan)
            # If exact t_day missing, take nearest within ±1
            if np.isnan(val):
                for offset in [1, -1]:
                    val = tk_data.get(cp + offset, np.nan)
                    if not np.isnan(val):
                        break
            heat_rows.append({
                "event_id":  eid,
                "label":     id_to_label[eid],
                "cluster":   id_to_cluster[eid],
                "ticker":    ticker,
                "checkpoint": cp,
                "iv_norm":   round(float(val), 2) if not np.isnan(val) else None,
                "iv_change": round(float(val) - 100, 2) if not np.isnan(val) else None,
            })

heat_df = pd.DataFrame(heat_rows)

# Pivot for clean display and for chart JSON
heat_pivot = heat_df.pivot_table(
    index=["event_id", "label", "cluster"],
    columns=["ticker", "checkpoint"],
    values="iv_change"
).round(2)
print("\n=== Heatmap: IV change from T-20 baseline ===")
print(heat_pivot.to_string())

# Build chart-friendly JSON: list of events with per-ticker per-checkpoint changes
heatmap_events = []
for eid in ok_ids:
    ev_data = {"event_id": eid, "label": id_to_label[eid], "cluster": id_to_cluster[eid], "tickers": {}}
    for ticker in TICKERS:
        ev_data["tickers"][ticker] = {}
        for cp in CHECKPOINTS:
            row = heat_df[(heat_df["event_id"] == eid) & (heat_df["ticker"] == ticker) & (heat_df["checkpoint"] == cp)]
            ev_data["tickers"][ticker][f"T{cp:+d}" if cp != 0 else "T0"] = (
                row["iv_change"].iloc[0] if not row.empty else None
            )
    heatmap_events.append(ev_data)

chart2_data = {"checkpoints": ["T0", "T+5", "T+10", "T+30"], "tickers": TICKERS, "events": heatmap_events}
with open("charts/data_heatmap.json", "w") as f:
    json.dump(chart2_data, f, indent=2)
print("\nSaved charts/data_heatmap.json")

# ── Strategy: sell composite IV at T0, buy back at exit_t ────────────────────
print(f"\n=== Strategy Backtest: short IV at T0 close, exit T{exit_t:+d} ===")

strat_rows = []
for eid in ok_ids:
    ev = composite[composite["event_id"] == eid].set_index("t_day")["iv_composite"]
    iv_t0 = ev.get(0, np.nan)

    # Find exit IV: exact exit_t or nearest within ±2
    iv_exit = np.nan
    actual_exit = None
    for offset in [0, 1, -1, 2, -2]:
        candidate = ev.get(exit_t + offset, np.nan)
        if not np.isnan(candidate):
            iv_exit = candidate
            actual_exit = exit_t + offset
            break

    if np.isnan(iv_t0) or np.isnan(iv_exit):
        print(f"  Event {eid:2d}: skipped (missing T0 or exit IV)")
        continue

    # P&L: sell IV point (normalised). Short straddle gains when IV falls.
    # Express as % of T-20 baseline (i.e. raw iv_norm point change).
    pnl = iv_t0 - iv_exit   # positive = IV fell = profit for short vol

    strat_rows.append({
        "event_id":    eid,
        "label":       id_to_label[eid],
        "cluster":     id_to_cluster[eid],
        "iv_t0":       round(iv_t0, 2),
        "iv_exit":     round(iv_exit, 2),
        "actual_exit": actual_exit,
        "pnl":         round(pnl, 2),
    })
    print(f"  Event {eid:2d}: IV T0={iv_t0:.1f} -> T{actual_exit:+d}={iv_exit:.1f}  P&L={pnl:+.1f}  ({id_to_label[eid]})")

strat_df = pd.DataFrame(strat_rows)
strat_df["cum_pnl"] = strat_df["pnl"].cumsum()

# ── Event 2 sensitivity flag ──────────────────────────────────────────────────
# Event 2 (Iranian speedboats, Jan 2008) T+10 IV spike (+48–57 pts on XLE/XOM/CVX)
# is almost certainly contaminated by GFC volatility regime (Bear Stearns collapsed
# Mar 2008; credit markets were seizing). The T+10 spike reflects macro vol, not
# geopolitical IV. Presented separately: full-sample and ex-event-2.
DISTORTED_EVENTS = {2: "Event 2 (Iranian speedboats, Jan 2008): T+10 IV spike likely driven by GFC vol regime, not geopolitical premium."}

def summarise(df, label):
    wr  = (df["pnl"] > 0).mean()
    avg = df["pnl"].mean()
    tot = df["pnl"].sum()
    mx  = df["pnl"].min()
    mn  = df["pnl"].max()
    print(f"\n  [{label}]")
    print(f"  Win rate  : {wr:.0%}  ({(df['pnl']>0).sum()}/{len(df)})")
    print(f"  Avg P&L   : {avg:+.2f} IV points")
    print(f"  Total P&L : {tot:+.2f} IV points")
    print(f"  Max loss  : {mx:+.2f}  (Event {df.loc[df['pnl'].idxmin(),'event_id']})")
    print(f"  Max gain  : {mn:+.2f}  (Event {df.loc[df['pnl'].idxmax(),'event_id']})")
    return {"n_events": len(df), "win_rate": round(wr,4), "avg_pnl": round(avg,2),
            "total_pnl": round(tot,2), "max_loss": round(mx,2), "max_gain": round(mn,2)}

summarise(strat_df, "Full sample")
strat_df_adj = strat_df[~strat_df["event_id"].isin(DISTORTED_EVENTS)].copy()
strat_df_adj["cum_pnl"] = strat_df_adj["pnl"].cumsum()
summarise(strat_df_adj, "Ex-event-2 (ex-GFC contamination)")

# Sensitivity: same strategy at T+5 and T+20, full-sample and ex-event-2
print("\n  Holding period sensitivity:")
for alt_exit in [5, 20]:
    for excl, tag in [([], "full"), ([2], "ex-ev2")]:
        ids = [e for e in ok_ids if e not in excl]
        alt_pnls = []
        for eid in ids:
            ev = composite[composite["event_id"] == eid].set_index("t_day")["iv_composite"]
            iv_t0  = ev.get(0, np.nan)
            iv_alt = np.nan
            for off in [0, 1, -1]:
                v = ev.get(alt_exit + off, np.nan)
                if not np.isnan(v):
                    iv_alt = v
                    break
            if not np.isnan(iv_t0) and not np.isnan(iv_alt):
                alt_pnls.append(iv_t0 - iv_alt)
        if alt_pnls:
            wr = sum(p > 0 for p in alt_pnls) / len(alt_pnls)
            print(f"    T+{alt_exit:2d} [{tag:6s}]: win rate {wr:.0%}, avg P&L {np.mean(alt_pnls):+.2f}")

print("\n  Distortion notes:")
for eid, note in DISTORTED_EVENTS.items():
    print(f"    {note}")

# Build summary dicts for JSON
summary_full = summarise.__wrapped__(strat_df, "") if hasattr(summarise, "__wrapped__") else {
    "n_events": len(strat_df), "win_rate": round((strat_df["pnl"]>0).mean(),4),
    "avg_pnl": round(strat_df["pnl"].mean(),2), "total_pnl": round(strat_df["pnl"].sum(),2),
    "max_loss": round(strat_df["pnl"].min(),2), "max_gain": round(strat_df["pnl"].max(),2),
}
summary_adj = {
    "n_events": len(strat_df_adj), "win_rate": round((strat_df_adj["pnl"]>0).mean(),4),
    "avg_pnl": round(strat_df_adj["pnl"].mean(),2), "total_pnl": round(strat_df_adj["pnl"].sum(),2),
    "max_loss": round(strat_df_adj["pnl"].min(),2), "max_gain": round(strat_df_adj["pnl"].max(),2),
}

chart3_data = {
    "strategy_label":   f"Short IV at T0 close, exit at T{exit_t:+d}",
    "exit_t":           exit_t,
    "distorted_events": DISTORTED_EVENTS,
    "events_full": [
        {"event_id": r["event_id"], "label": r["label"], "cluster": r["cluster"],
         "iv_t0": r["iv_t0"], "iv_exit": r["iv_exit"], "pnl": r["pnl"],
         "cum_pnl": round(r["cum_pnl"], 2),
         "distorted": r["event_id"] in DISTORTED_EVENTS}
        for _, r in strat_df.iterrows()
    ],
    "events_adjusted": [
        {"event_id": r["event_id"], "label": r["label"], "cluster": r["cluster"],
         "iv_t0": r["iv_t0"], "iv_exit": r["iv_exit"], "pnl": r["pnl"],
         "cum_pnl": round(r["cum_pnl"], 2)}
        for _, r in strat_df_adj.iterrows()
    ],
    "summary_full":     summary_full,
    "summary_adjusted": summary_adj,
}
with open("charts/data_pnl.json", "w") as f:
    json.dump(chart3_data, f, indent=2)
print("\nSaved charts/data_pnl.json")

# ── HTML Preview ──────────────────────────────────────────────────────────────
# Colour scale for heatmap cells
def heat_colour(val):
    if val is None:
        return "#1a1a2e", "#666"
    if val >= 15:   return "#7f0000", "#fff"
    if val >= 8:    return "#c0392b", "#fff"
    if val >= 3:    return "#e67e22", "#fff"
    if val >= -3:   return "#2c3e50", "#ccc"
    if val >= -8:   return "#1a5276", "#fff"
    return "#0d2137", "#fff"

# Build heatmap HTML table
def build_heatmap_table():
    cp_labels = ["T0", "T+5", "T+10", "T+30"]
    header_cols = "".join(
        f'<th colspan="4" style="text-align:center;padding:4px 8px;border-right:1px solid #333">{t}</th>'
        for t in TICKERS
    )
    sub_cols = "".join(
        f'<th style="padding:3px 5px;font-size:11px;color:#aaa">{cp}</th>'
        for _ in TICKERS for cp in cp_labels
    )
    rows_html = ""
    for ev in heatmap_events:
        cluster_color = {
            "Gulf War II": "#4a235a",
            "Strait of Hormuz": "#1a3a4a",
            "Soleimani": "#4a3a1a",
            "Iran-Israel 2024": "#1a4a3a",
            "Twelve-Day War 2025": "#3a1a4a",
            "2026 Conflict": "#4a1a1a",
        }.get(ev["cluster"], "#2c3e50")
        cells = f'<td style="padding:4px 10px;font-size:12px;white-space:nowrap;background:{cluster_color}">{ev["label"]}</td>'
        for ticker in TICKERS:
            for cp_key in ["T0", "T+5", "T+10", "T+30"]:
                val = ev["tickers"][ticker].get(cp_key)
                bg, fg = heat_colour(val)
                txt = f"{val:+.1f}" if val is not None else "—"
                cells += f'<td style="padding:4px 6px;text-align:right;background:{bg};color:{fg};font-size:12px;font-family:monospace">{txt}</td>'
        rows_html += f"<tr>{cells}</tr>"
    return f"""
    <table style="border-collapse:collapse;width:100%;font-family:sans-serif">
      <thead>
        <tr>
          <th style="padding:6px 10px;text-align:left">Event</th>
          {header_cols}
        </tr>
        <tr>
          <th></th>{sub_cols}
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    <p style="font-size:11px;color:#888;margin-top:8px">
      Values are IV change from T-20 baseline (normalised to 100). Colour: red = IV elevated, blue = IV suppressed.
    </p>"""

heatmap_table_html = build_heatmap_table()

# Chart.js configs
profile_labels_js = json.dumps(chart1_data["labels"])
profile_mean_js   = json.dumps(chart1_data["mean"])
profile_upper_js  = json.dumps(chart1_data["ci_upper"])
profile_lower_js  = json.dumps(chart1_data["ci_lower"])
t0_line_idx       = chart1_data["labels"].index("T0")

pnl_labels_js   = json.dumps([e["label"] for e in chart3_data["events_full"]])
pnl_bar_js      = json.dumps([e["pnl"] for e in chart3_data["events_full"]])
cum_pnl_full_js = json.dumps([e["cum_pnl"] for e in chart3_data["events_full"]])
cum_pnl_adj_js  = json.dumps([
    e["cum_pnl"] if not e.get("distorted") else None
    for e in chart3_data["events_full"]
])
bar_colours_js  = json.dumps([
    "rgba(180,120,0,0.6)" if e.get("distorted") else
    ("rgba(192,57,43,0.8)" if e["pnl"] < 0 else "rgba(39,174,96,0.8)")
    for e in chart3_data["events_full"]
])

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>IV Behaviour Around Iran Geopolitical Events — Preview</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body {{ background:#0d1117; color:#e6edf3; font-family:'Segoe UI',sans-serif; margin:0; padding:24px; }}
  h1   {{ font-size:20px; color:#58a6ff; margin-bottom:4px }}
  h2   {{ font-size:15px; color:#8b949e; margin:32px 0 8px }}
  p.note {{ font-size:12px; color:#8b949e; margin:4px 0 16px }}
  .chart-wrap {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:20px; margin-bottom:32px }}
  .stat {{ display:inline-block; background:#21262d; border:1px solid #30363d; border-radius:6px;
           padding:8px 16px; margin:4px; font-size:13px }}
  .stat span {{ color:#58a6ff; font-weight:600 }}
</style>
</head>
<body>
<h1>IV Behaviour in Energy Sector Options Around Iran-Related Geopolitical Events</h1>
<p class="note">
  Preview — {len(ok_ids)} events included (3 filtered by &lt;1.5% price move; 1 excluded — no WRDS data post-2025-08-29).
  IV normalised to 100 at T-20. Instruments: XLE, USO, XOM, CVX.
</p>

<!-- ── CHART 1: Average IV Profile ── -->
<h2>Chart 1 — Average Normalised IV Profile (T-20 to T+30)</h2>
<p class="note">
  Mean composite IV across {len(ok_ids)} events ± 1 std dev. Composite = equal-weight average of available
  tickers per event. Shaded band reflects cross-event dispersion, not a statistical confidence interval
  (n={len(ok_ids)} events — interpret with appropriate caution).
</p>
<div class="chart-wrap">
  <canvas id="profileChart" height="90"></canvas>
</div>

<!-- ── CHART 2: Heatmap ── -->
<h2>Chart 2 — Event × Instrument IV Change from T-20 Baseline</h2>
{heatmap_table_html}

<!-- ── CHART 3: Strategy P&L ── -->
<h2>Chart 3 — Strategy Backtest: Short IV at T0 Close, Exit T{exit_t:+d}</h2>
<p class="note">
  Strategy derived from average IV profile: composite IV peaks near T0, mean-reverts to baseline by T{exit_t:+d}.
  P&L = IV points gained/lost (short: profit when IV falls). Equal-weight, one unit per event.
  <strong>Note: simplified vega-proxy backtest — not an exact options P&amp;L.</strong><br>
  <span style="color:#f0a500">&#9888;</span>
  <strong style="color:#f0a500">Event 2 flagged (amber bars):</strong>
  Iranian speedboats Jan 2008 — T+10 IV spike of +48–57 pts likely driven by GFC vol regime
  (Bear Stearns Mar 2008), not geopolitical premium. Full-sample and ex-event-2 cumulative lines shown separately.
</p>
<p style="font-size:12px;color:#8b949e;margin:4px 0">Full sample ({chart3_data['summary_full']['n_events']} events)</p>
<div style="margin-bottom:8px">
  <div class="stat">Win rate <span>{chart3_data['summary_full']['win_rate']:.0%}</span></div>
  <div class="stat">Avg P&L <span>{chart3_data['summary_full']['avg_pnl']:+.2f} pts</span></div>
  <div class="stat">Total P&L <span>{chart3_data['summary_full']['total_pnl']:+.2f} pts</span></div>
  <div class="stat">Max loss <span>{chart3_data['summary_full']['max_loss']:+.2f} pts</span></div>
</div>
<p style="font-size:12px;color:#8b949e;margin:4px 0">Ex-event-2 / ex-GFC ({chart3_data['summary_adjusted']['n_events']} events)</p>
<div style="margin-bottom:16px">
  <div class="stat">Win rate <span>{chart3_data['summary_adjusted']['win_rate']:.0%}</span></div>
  <div class="stat">Avg P&L <span>{chart3_data['summary_adjusted']['avg_pnl']:+.2f} pts</span></div>
  <div class="stat">Total P&L <span>{chart3_data['summary_adjusted']['total_pnl']:+.2f} pts</span></div>
  <div class="stat">Max loss <span>{chart3_data['summary_adjusted']['max_loss']:+.2f} pts</span></div>
</div>
<div class="chart-wrap">
  <canvas id="pnlChart" height="100"></canvas>
</div>

<script>
// ── Chart 1: IV Profile ──────────────────────────────────────────────────────
const profileCtx = document.getElementById('profileChart').getContext('2d');
new Chart(profileCtx, {{
  data: {{
    labels: {profile_labels_js},
    datasets: [
      {{
        type: 'line',
        label: 'Upper band (mean + 1σ)',
        data: {profile_upper_js},
        borderColor: 'transparent',
        backgroundColor: 'rgba(88,166,255,0.12)',
        pointRadius: 0,
        fill: '+1',
        order: 3,
      }},
      {{
        type: 'line',
        label: 'Mean composite IV',
        data: {profile_mean_js},
        borderColor: '#58a6ff',
        backgroundColor: 'transparent',
        borderWidth: 2.5,
        pointRadius: 0,
        tension: 0.3,
        order: 1,
      }},
      {{
        type: 'line',
        label: 'Lower band (mean − 1σ)',
        data: {profile_lower_js},
        borderColor: 'transparent',
        backgroundColor: 'rgba(88,166,255,0.12)',
        pointRadius: 0,
        fill: '-1',
        order: 3,
      }},
    ]
  }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ labels: {{ color: '#8b949e', filter: item => item.label === 'Mean composite IV' }} }},
      tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.dataset.label}}: ${{ctx.parsed.y?.toFixed(1)}}` }} }},
      annotation: {{ annotations: {{
        t0Line: {{
          type: 'line', xMin: {t0_line_idx}, xMax: {t0_line_idx},
          borderColor: 'rgba(248,81,73,0.7)', borderWidth: 1.5, borderDash: [4,4],
          label: {{ content: 'T0', display: true, color: '#f85149', font: {{ size: 11 }} }}
        }},
        baseline: {{
          type: 'line', yMin: 100, yMax: 100,
          borderColor: 'rgba(139,148,158,0.3)', borderWidth: 1, borderDash: [4,4],
        }}
      }} }}
    }},
    scales: {{
      x: {{ ticks: {{ color: '#8b949e', maxTicksLimit: 11, font: {{ size: 11 }} }}, grid: {{ color: '#21262d' }} }},
      y: {{ ticks: {{ color: '#8b949e', font: {{ size: 11 }} }}, grid: {{ color: '#21262d' }},
           title: {{ display: true, text: 'Normalised IV (100 = T-20 level)', color: '#8b949e', font: {{ size: 11 }} }} }}
    }}
  }}
}});

// ── Chart 3: Strategy P&L ────────────────────────────────────────────────────
const pnlCtx = document.getElementById('pnlChart').getContext('2d');
new Chart(pnlCtx, {{
  data: {{
    labels: {pnl_labels_js},
    datasets: [
      {{
        type: 'bar',
        label: 'Per-event P&L (IV points)',
        data: {pnl_bar_js},
        backgroundColor: {bar_colours_js},
        order: 2,
        yAxisID: 'y',
      }},
      {{
        type: 'line',
        label: 'Cumulative P&L (full sample)',
        data: {cum_pnl_full_js},
        borderColor: '#f0a500',
        backgroundColor: 'transparent',
        borderWidth: 2,
        pointRadius: 3,
        tension: 0.1,
        order: 1,
        yAxisID: 'y2',
      }},
      {{
        type: 'line',
        label: 'Cumulative P&L (ex-event-2)',
        data: {cum_pnl_adj_js},
        borderColor: '#58a6ff',
        backgroundColor: 'transparent',
        borderWidth: 2,
        borderDash: [5, 3],
        pointRadius: 3,
        tension: 0.1,
        order: 1,
        yAxisID: 'y2',
        spanGaps: false,
      }},
    ]
  }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ labels: {{ color: '#8b949e' }} }},
      tooltip: {{ callbacks: {{ label: ctx => ` ${{ctx.dataset.label}}: ${{ctx.parsed.y?.toFixed(2)}}` }} }}
    }},
    scales: {{
      x: {{ ticks: {{ color: '#8b949e', font: {{ size: 10 }}, maxRotation: 45 }}, grid: {{ color: '#21262d' }} }},
      y: {{
        position: 'left',
        ticks: {{ color: '#8b949e', font: {{ size: 11 }} }},
        grid:  {{ color: '#21262d' }},
        title: {{ display: true, text: 'Per-event P&L (IV pts)', color: '#8b949e', font: {{ size: 11 }} }}
      }},
      y2: {{
        position: 'right',
        ticks: {{ color: '#f0a500', font: {{ size: 11 }} }},
        grid:  {{ drawOnChartArea: false }},
        title: {{ display: true, text: 'Cumulative P&L (IV pts)', color: '#f0a500', font: {{ size: 11 }} }}
      }}
    }}
  }}
}});
</script>
</body>
</html>"""

with open("charts/preview.html", "w", encoding="utf-8") as f:
    f.write(html)
print("Saved charts/preview.html")
