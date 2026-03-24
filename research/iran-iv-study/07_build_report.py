# ruff: noqa
"""
07_build_report.py
------------------
Generates the full HTML report at report/index.html, matching the
theintrinsicinvestor.com design system exactly.
"""

import json, os
import numpy as np
import pandas as pd
from events import EVENTS

os.makedirs("report", exist_ok=True)

# ── Load data ─────────────────────────────────────────────────────────────────
with open("charts/data_iv_profile.json") as f:
    profile_data = json.load(f)
with open("charts/data_heatmap.json") as f:
    heatmap_raw = json.load(f)
with open("charts/data_pnl.json") as f:
    pnl_data_raw = json.load(f)

profiles = pd.read_parquet("data/event_iv_profiles.parquet")
metadata = pd.read_parquet("data/event_metadata.parquet")

# ── Compute T+20 per-event P&L ────────────────────────────────────────────────
ok_meta   = metadata[metadata["status"] == "OK"]
ok_ids    = ok_meta["event_id"].tolist()
id_to_label   = dict(zip(metadata["event_id"], metadata["label"]))
id_to_cluster = dict(zip(metadata["event_id"], metadata["cluster"]))
id_to_t0      = dict(zip(metadata["event_id"], metadata["t0_date"]))

composite = (
    profiles.dropna(subset=["iv_norm"])
    .groupby(["event_id", "t_day"])["iv_norm"]
    .mean().reset_index()
    .rename(columns={"iv_norm": "iv_composite"})
)

DISTORTED = {2}  # GFC contamination
EXIT_T    = 20

t20_rows = []
for eid in ok_ids:
    ev    = composite[composite["event_id"] == eid].set_index("t_day")["iv_composite"]
    iv_t0 = ev.get(0, np.nan)
    iv_ex = np.nan
    for off in [0, 1, -1, 2, -2]:
        v = ev.get(EXIT_T + off, np.nan)
        if not np.isnan(v):
            iv_ex = v; break
    if not (np.isnan(iv_t0) or np.isnan(iv_ex)):
        t20_rows.append({"event_id": eid, "label": id_to_label[eid],
                         "cluster": id_to_cluster[eid],
                         "iv_t0": round(iv_t0, 2), "iv_exit": round(iv_ex, 2),
                         "pnl": round(iv_t0 - iv_ex, 2),
                         "distorted": eid in DISTORTED})

strat_df = pd.DataFrame(t20_rows)
strat_df["cum_pnl"] = strat_df["pnl"].cumsum()

def stats(df):
    return {"n": len(df),
            "win_rate": (df["pnl"] > 0).mean(),
            "avg":      round(df["pnl"].mean(), 2),
            "total":    round(df["pnl"].sum(), 2),
            "max_loss": round(df["pnl"].min(), 2),
            "max_gain": round(df["pnl"].max(), 2)}

s_full = stats(strat_df)
s_adj  = stats(strat_df[~strat_df["distorted"]].assign(
    cum_pnl=lambda d: d["pnl"].cumsum()))

# ex-event-2 cumulative mapped back to full event axis
cum_adj_values, running = [], 0.0
for _, row in strat_df.iterrows():
    if row["distorted"]:
        cum_adj_values.append(None)
    else:
        running += row["pnl"]
        cum_adj_values.append(round(running, 2))

# ── Average profile stats ─────────────────────────────────────────────────────
mean_arr = profile_data["mean"]
t_days   = list(range(-20, 31))
peak_idx = int(np.nanargmax(mean_arr))
peak_val = mean_arr[peak_idx]
peak_t   = t_days[peak_idx]
t30_val  = mean_arr[t_days.index(30)]
t0_val   = mean_arr[t_days.index(0)]

print(f"Profile peak: {peak_val:.1f} at T{peak_t:+d}")
print(f"T0 composite: {t0_val:.1f} | T+30 composite: {t30_val:.1f}")
print(f"T+20 full  : {s_full['win_rate']:.0%} win, {s_full['avg']:+.2f} avg")
print(f"T+20 ex-ev2: {s_adj['win_rate']:.0%} win, {s_adj['avg']:+.2f} avg")

# ── Chart JS data ─────────────────────────────────────────────────────────────
profile_labels_js = json.dumps(profile_data["labels"])
profile_mean_js   = json.dumps(profile_data["mean"])
profile_upper_js  = json.dumps(profile_data["ci_upper"])
profile_lower_js  = json.dumps(profile_data["ci_lower"])
t0_x_idx          = profile_data["labels"].index("T0")

pnl_event_labels  = json.dumps([r["label"] for _, r in strat_df.iterrows()])
pnl_bar_values    = json.dumps([r["pnl"] for _, r in strat_df.iterrows()])
pnl_cum_full      = json.dumps(list(strat_df["cum_pnl"].round(2)))
pnl_cum_adj       = json.dumps(cum_adj_values)
pnl_bar_colors    = json.dumps([
    "rgba(146,64,14,0.75)"  if r["distorted"] else
    ("rgba(220,38,38,0.75)" if r["pnl"] < 0 else "rgba(5,150,105,0.75)")
    for _, r in strat_df.iterrows()
])

# ── Helpers ───────────────────────────────────────────────────────────────────
def cell_bg(val):
    if val is None: return "background:#f0ece2;color:#8aa49e"
    v = float(val)
    if v >= 20:  return "background:#fee2e2;color:#991b1b;font-weight:600"
    if v >= 10:  return "background:#fef2f2;color:#dc2626"
    if v >= 3:   return "background:#fffbeb;color:#92400e"
    if v >= -3:  return "background:#f7f4ec;color:#4a6460"
    if v >= -10: return "background:#eff6ff;color:#1e40af"
    return "background:#dbeafe;color:#1e40af;font-weight:600"

def fmt(val):
    return f"{val:+.1f}" if val is not None else "--"

CLUSTER_COLORS = {
    "Gulf War II":        "#f5f3ff",
    "Strait of Hormuz":  "#eff6ff",
    "Soleimani":         "#fffbeb",
    "Iran-Israel 2024":  "#f0fdf4",
    "Twelve-Day War 2025": "#fdf4ff",
    "2026 Conflict":     "#fef2f2",
}
CLUSTER_DOT = {
    "Gulf War II":        "#5b21b6",
    "Strait of Hormuz":  "#1e40af",
    "Soleimani":         "#92400e",
    "Iran-Israel 2024":  "#065f46",
    "Twelve-Day War 2025": "#86198f",
    "2026 Conflict":     "#991b1b",
}

# ── Build heatmap table ───────────────────────────────────────────────────────
TICKERS     = ["XLE", "USO", "XOM", "CVX"]
CHECKPOINTS = ["T0", "T+5", "T+10", "T+30"]

heat_header = "<tr><th>Event</th>" + "".join(
    f'<th colspan="4" style="text-align:center;border-left:2px solid #e2ddd0">{t}</th>'
    for t in TICKERS) + "</tr>"
heat_subhdr = "<tr><th></th>" + "".join(
    f'<th style="border-left:{("2px" if i==0 else "1px")} solid #e2ddd0">{cp}</th>'
    for t in TICKERS for i, cp in enumerate(CHECKPOINTS)) + "</tr>"

heat_rows_html = ""
for ev in heatmap_raw["events"]:
    note = " <span style='font-size:10px;color:#92400e'>(GFC flag)</span>" if ev["event_id"] == 2 else ""
    t0_obj = id_to_t0.get(ev["event_id"])
    t0_str = t0_obj.strftime("%b %d, %Y") if hasattr(t0_obj, "strftime") else str(t0_obj)[:10]
    cells  = (f'<td style="white-space:nowrap">'
              f'<strong style="color:#0f2220;font-size:12px">{ev["label"]}{note}</strong>'
              f'<br><span style="font-size:11px;color:#8aa49e;font-family:\'JetBrains Mono\',monospace">{t0_str}</span>'
              f'</td>')
    for i, ticker in enumerate(TICKERS):
        for j, cp in enumerate(CHECKPOINTS):
            val = ev["tickers"][ticker].get(cp)
            style = cell_bg(val)
            border = "border-left:2px solid #e2ddd0;" if j == 0 else ""
            cells += f'<td style="text-align:right;{border}{style};font-family:\'JetBrains Mono\',monospace;font-size:12px">{fmt(val)}</td>'
    heat_rows_html += f"<tr>{cells}</tr>"

# ── Build events table ────────────────────────────────────────────────────────
STATUS_META = {e["id"]: metadata[metadata["event_id"]==e["id"]].iloc[0].to_dict()
               for e in EVENTS if not metadata[metadata["event_id"]==e["id"]].empty}

def status_badge(status, filter_pass):
    if status == "OK":
        return '<span style="background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:600">Included</span>'
    if status == "FILTERED_OUT":
        return '<span style="background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:600">Filtered</span>'
    if status == "DATA_UNAVAILABLE":
        return '<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:600">No data</span>'
    return '<span style="background:#f0ece2;color:#4a6460;padding:2px 8px;border-radius:99px;font-size:11px">--</span>'

events_rows_html = ""
for ev in EVENTS:
    m     = STATUS_META.get(ev["id"], {})
    raw_d = str(ev["date"])
    t0_obj = m.get("t0_date")
    t0_str = t0_obj.strftime("%b %d, %Y") if (t0_obj is not None and not pd.isnull(t0_obj)) else "--"
    status = m.get("status", "")
    badge  = status_badge(status, m.get("filter_pass"))
    note   = m.get("notes", "") or ""
    if ev["id"] == 2: note = "GFC contamination at T+10"
    if ev["id"] == 15: note = "WRDS data ends 2025-08-29"
    note_html = f'<br><span style="font-size:10px;color:#8aa49e">{note}</span>' if note else ""
    cluster_dot = f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{CLUSTER_DOT.get(ev["cluster"],"#4a6460")};margin-right:5px"></span>'
    instruments = ", ".join(ev["instruments"])
    events_rows_html += f"""<tr>
      <td style="font-family:'JetBrains Mono',monospace;color:#8aa49e">{ev["id"]}</td>
      <td style="font-family:'JetBrains Mono',monospace;font-size:12px">{raw_d}</td>
      <td><strong style="color:#0f2220;font-size:13px">{ev["label"]}</strong>{note_html}</td>
      <td style="font-size:12px">{cluster_dot}{ev["cluster"]}</td>
      <td style="font-size:12px;color:#4a6460">{instruments}</td>
      <td>{badge}</td>
    </tr>"""

# ── Build strategy sensitivity table ─────────────────────────────────────────
# Already computed from 06: T+5 full 73%/+1.75, T+5 ex-ev2 70%/+1.68
#                           T+17 full 45%/+6.15, T+17 ex-ev2 50%/+6.95
#                           T+20 full 82%/+7.21, T+20 ex-ev2 90%/+9.08
SENSITIVITY = [
    ("T+5",  "73%", "+1.75", "70%", "+1.68"),
    ("T+17", "45%", "+6.15", "50%", "+6.95"),
    ("T+20", "82%", "+7.21", "90%", "+9.08", "best"),
]
sens_rows = ""
for row in SENSITIVITY:
    is_best = len(row) == 6
    highlight = "background:#f0fdf4;" if is_best else ""
    tag = ' <span style="background:#1a5c52;color:#fff;padding:1px 6px;border-radius:99px;font-size:10px">best</span>' if is_best else ""
    sens_rows += f"""<tr style="{highlight}">
      <td style="font-family:'JetBrains Mono',monospace;font-weight:500">{row[0]}{tag}</td>
      <td style="color:#059669;font-family:'JetBrains Mono',monospace">{row[1]}</td>
      <td style="font-family:'JetBrains Mono',monospace">{row[2]}</td>
      <td style="color:#059669;font-family:'JetBrains Mono',monospace">{row[3]}</td>
      <td style="font-family:'JetBrains Mono',monospace">{row[4]}</td>
    </tr>"""

# ── Individual event P&L table ────────────────────────────────────────────────
strat_table_rows = ""
for _, row in strat_df.iterrows():
    pnl_color = "#dc2626" if row["pnl"] < 0 else "#059669"
    distorted_note = ' <span style="background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:99px;font-size:10px">GFC flag</span>' if row["distorted"] else ""
    strat_table_rows += f"""<tr>
      <td><strong style="color:#0f2220;font-size:12px">{row['label']}</strong>{distorted_note}</td>
      <td style="font-size:12px;color:#4a6460">{row['cluster']}</td>
      <td style="font-family:'JetBrains Mono',monospace;font-size:13px">{row['iv_t0']:.1f}</td>
      <td style="font-family:'JetBrains Mono',monospace;font-size:13px">{row['iv_exit']:.1f}</td>
      <td style="font-family:'JetBrains Mono',monospace;font-size:13px;color:{pnl_color};font-weight:500">{row['pnl']:+.2f}</td>
      <td style="font-family:'JetBrains Mono',monospace;font-size:13px">{row['cum_pnl']:+.2f}</td>
    </tr>"""

# ── Full HTML ─────────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>IV Behaviour in Energy Options Around Iran Geopolitical Events | The Intrinsic Investor</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@1,300;1,400;1,600&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg:#f7f4ec; --bg2:#f0ece2; --bg3:#e8e3d8;
      --ink:#0f2220; --ink2:#2a3c38;
      --muted:#4a6460; --hint:#8aa49e; --border:#e2ddd0;
      --card:#ffffff;
      --accent:#1a5c52; --accent2:#144a42;
      --green:#0d6e4e; --green2:#059669; --green-bg:#ecfdf5; --green-border:#a7f3d0;
      --red:#991b1b; --red2:#dc2626; --red-bg:#fef2f2; --red-border:#fca5a5;
      --blue:#1e40af; --blue2:#2563eb; --blue-bg:#eff6ff; --blue-border:#bfdbfe;
      --amber:#92400e; --amber-bg:#fffbeb; --amber-border:#fcd34d;
      --purple:#5b21b6; --purple-bg:#f5f3ff; --purple-border:#c4b5fd;
    }}
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html {{ font-size: 16px; }}
    body {{ background: var(--bg); color: var(--ink); font-family: 'Inter', sans-serif; line-height: 1.6; }}

    /* Nav */
    nav {{ background: var(--ink); padding: 0 24px; display: flex; align-items: center; justify-content: space-between; height: 52px; position: sticky; top: 0; z-index: 100; }}
    .nav-logo {{ font-family: 'Fraunces', serif; font-style: italic; font-weight: 400; font-size: 15px; color: rgba(255,255,255,0.9); text-decoration: none; }}
    .nav-links {{ display: flex; gap: 28px; list-style: none; }}
    .nav-links a {{ color: rgba(255,255,255,0.5); text-decoration: none; font-size: 13px; font-weight: 400; letter-spacing: 0.01em; transition: color 0.15s; }}
    .nav-links a:hover {{ color: rgba(255,255,255,0.85); }}
    .nav-links a.active {{ color: rgba(255,255,255,0.9); font-weight: 500; }}

    /* Hero */
    .hero {{ background: var(--ink); padding: 64px 24px 80px; }}
    .hero-inner {{ max-width: 800px; margin: 0 auto; }}
    .eyebrow {{ display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }}
    .eyebrow::before {{ content: ''; display: block; width: 24px; height: 1px; background: var(--accent); }}
    .eyebrow span {{ font-family: 'Inter', sans-serif; font-size: 11px; font-weight: 500; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; }}
    .hero h1 {{ font-family: 'Fraunces', serif; font-style: italic; font-weight: 600; font-size: 2.4rem; color: #fff; line-height: 1.25; margin-bottom: 16px; }}
    .hero h1 em {{ color: #5ab5a5; font-style: italic; }}
    .hero-subtitle {{ font-family: 'Inter', sans-serif; font-size: 14px; font-weight: 300; color: rgba(255,255,255,0.55); line-height: 1.6; max-width: 640px; margin-bottom: 28px; }}
    .hero-meta {{ font-family: 'JetBrains Mono', monospace; font-size: 11px; color: rgba(255,255,255,0.3); display: flex; flex-wrap: wrap; gap: 16px; }}
    .hero-meta span {{ display: flex; align-items: center; gap: 6px; }}
    .hero-meta span::before {{ content: ''; display: inline-block; width: 1px; height: 10px; background: rgba(255,255,255,0.15); }}
    .hero-meta span:first-child::before {{ display: none; }}

    /* KPI Strip */
    .kpi-strip {{ max-width: 800px; margin: -32px auto 0; padding: 0 24px 24px; position: relative; z-index: 10; }}
    .kpi-warning {{ background: var(--amber-bg); border: 1px solid var(--amber-border); border-radius: 8px 8px 0 0; padding: 10px 16px; display: flex; align-items: flex-start; gap: 10px; }}
    .kpi-warning-icon {{ font-size: 14px; flex-shrink: 0; margin-top: 1px; }}
    .kpi-warning-text {{ font-size: 12px; color: var(--amber); line-height: 1.5; }}
    .kpi-warning-text strong {{ color: var(--amber); }}
    .kpi-tabs {{ display: flex; gap: 0; border-bottom: 1px solid var(--border); background: var(--card); padding: 0 16px; }}
    .kpi-tab {{ font-size: 12px; color: var(--hint); padding: 8px 12px; cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px; transition: all 0.15s; white-space: nowrap; }}
    .kpi-tab.active {{ color: var(--accent); border-bottom-color: var(--accent); font-weight: 500; }}
    .kpi-panel {{ display: none; background: var(--card); border: 1px solid var(--border); border-top: none; border-radius: 0 0 8px 8px; padding: 20px 16px; }}
    .kpi-panel.active {{ display: block; }}
    .kpi-warning + .kpi-tabs {{ border-radius: 0; }}
    .kpi-cells {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; }}
    .kpi-cell {{ padding: 4px 12px; border-right: 1px solid var(--border); }}
    .kpi-cell:last-child {{ border-right: none; }}
    .kpi-label {{ font-size: 10px; color: var(--hint); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px; }}
    .kpi-value {{ font-family: 'JetBrains Mono', monospace; font-size: 22px; line-height: 1.1; }}
    .kpi-value.green {{ color: var(--green2); }}
    .kpi-value.blue  {{ color: var(--blue2); }}
    .kpi-value.red   {{ color: var(--red2); }}
    .kpi-sub {{ font-size: 11px; color: var(--hint); margin-top: 2px; }}

    /* Sections */
    .section {{ padding: 52px 24px; border-bottom: 1px solid var(--border); }}
    .section:last-of-type {{ border-bottom: none; }}
    .section-inner {{ max-width: 800px; margin: 0 auto; }}
    .section-label {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }}
    .section-label::before {{ content: ''; display: block; width: 24px; height: 1px; background: var(--accent); }}
    .section-label span {{ font-size: 10px; font-weight: 500; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; }}
    .section h2 {{ font-family: 'Fraunces', serif; font-style: italic; font-weight: 600; font-size: 1.65rem; color: var(--ink); margin-bottom: 20px; line-height: 1.3; }}
    .section h2 em {{ color: var(--accent); font-style: italic; }}
    .section h3 {{ font-family: 'Fraunces', serif; font-style: italic; font-weight: 600; font-size: 1.15rem; color: var(--ink); margin: 28px 0 10px; }}
    p {{ font-size: 14px; color: var(--muted); line-height: 1.7; margin-bottom: 14px; }}
    p:last-child {{ margin-bottom: 0; }}
    p strong {{ color: var(--ink); }}

    /* Callout boxes */
    .callout {{ display: flex; gap: 14px; padding: 14px 16px; border-radius: 8px; margin: 20px 0; border: 1px solid; }}
    .callout-icon {{ font-size: 16px; flex-shrink: 0; margin-top: 1px; }}
    .callout-body {{ font-size: 13px; line-height: 1.6; }}
    .callout-body strong {{ display: block; margin-bottom: 3px; }}
    .callout.green  {{ background: var(--green-bg);  border-color: var(--green-border);  color: var(--green);  }}
    .callout.amber  {{ background: var(--amber-bg);  border-color: var(--amber-border);  color: var(--amber);  }}
    .callout.red    {{ background: var(--red-bg);    border-color: var(--red-border);    color: var(--red);    }}
    .callout.blue   {{ background: var(--blue-bg);   border-color: var(--blue-border);   color: var(--blue);   }}
    .callout.purple {{ background: var(--purple-bg); border-color: var(--purple-border); color: var(--purple); }}

    /* Tables */
    .table-wrap {{ border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin: 20px 0; }}
    .table-wrap.scrollable {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; }}
    thead tr {{ background: var(--ink); }}
    thead th {{ font-size: 10px; font-weight: 600; color: #fff; text-transform: uppercase; letter-spacing: 0.04em; padding: 10px 12px; text-align: left; white-space: nowrap; }}
    tbody tr:hover {{ background: var(--bg2); }}
    tbody td {{ font-size: 13px; color: var(--muted); padding: 9px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
    tbody tr:last-child td {{ border-bottom: none; }}

    /* Charts */
    .chart-box {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin: 20px 0; }}
    .chart-title {{ font-size: 10px; font-weight: 500; color: var(--hint); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 14px; }}
    .chart-legend {{ display: flex; flex-wrap: wrap; gap: 14px; margin-top: 12px; }}
    .chart-legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); }}
    .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
    .legend-line {{ width: 20px; height: 2px; flex-shrink: 0; }}

    /* Highlight box */
    .highlight-box {{ background: var(--ink); border-radius: 12px; padding: 28px 24px; margin: 28px 0; }}
    .highlight-box .hl-label {{ font-size: 10px; font-weight: 500; color: rgba(255,255,255,0.35); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 6px; }}
    .highlight-box .hl-value {{ font-family: 'Fraunces', serif; font-style: italic; font-size: 1.75rem; color: #5ab5a5; line-height: 1.1; }}
    .highlight-box .hl-sub {{ font-size: 11px; color: rgba(255,255,255,0.35); margin-top: 4px; }}
    .hl-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }}
    .hl-divider {{ border-right: 1px solid rgba(255,255,255,0.08); padding-right: 20px; }}
    .hl-divider:last-child {{ border-right: none; }}

    /* Footer */
    footer {{ background: var(--ink); padding: 36px 24px 0; }}
    .footer-inner {{ max-width: 800px; margin: 0 auto; }}
    .footer-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; padding-bottom: 24px; }}
    .footer-name {{ font-size: 13px; font-weight: 500; color: rgba(255,255,255,0.45); margin-bottom: 4px; }}
    .footer-desc {{ font-size: 12px; color: rgba(255,255,255,0.25); max-width: 420px; line-height: 1.5; }}
    .footer-links {{ display: flex; gap: 16px; flex-shrink: 0; }}
    .footer-links a {{ font-size: 12px; color: rgba(255,255,255,0.3); text-decoration: none; transition: color 0.15s; }}
    .footer-links a:hover {{ color: rgba(255,255,255,0.6); }}
    .footer-bottom {{ border-top: 1px solid rgba(255,255,255,0.08); padding: 14px 0; display: flex; justify-content: space-between; align-items: center; }}
    .footer-data {{ font-family: 'JetBrains Mono', monospace; font-size: 11px; color: rgba(255,255,255,0.2); }}
    .footer-disclaimer {{ font-size: 11px; color: rgba(255,255,255,0.2); }}

    @media (max-width: 640px) {{
      .hero h1 {{ font-size: 1.75rem; }}
      .kpi-cells {{ grid-template-columns: repeat(2, 1fr); }}
      .hl-grid {{ grid-template-columns: 1fr; }}
      .footer-top {{ flex-direction: column; }}
      .footer-bottom {{ flex-direction: column; gap: 8px; text-align: center; }}
    }}
  </style>
</head>
<body>

<!-- ── Nav ── -->
<nav>
  <a href="/" class="nav-logo">The Intrinsic Investor</a>
  <ul class="nav-links">
    <li><a href="/">Home</a></li>
    <li><a href="/research" class="active">Research</a></li>
    <li><a href="/about">About</a></li>
  </ul>
</nav>

<!-- ── Hero ── -->
<div class="hero">
  <div class="hero-inner">
    <div class="eyebrow"><span>Systematic Market Research</span></div>
    <h1>IV Behaviour in <em>Energy Sector Options</em><br>Around Iran-Related <em>Geopolitical Events</em></h1>
    <p class="hero-subtitle">
      An event study of 30-day ATM implied volatility across XLE, USO, XOM, and CVX
      around fifteen Iran-related escalation events from 2003 to 2026. The study derives
      a tradeable mean-reversion strategy from the IV patterns the data reveals.
    </p>
    <div class="hero-meta">
      <span>By: Brian Liew (LSE, BSc Accounting and Finance)</span>
      <span>Mar 2003 to Feb 2026</span>
      <span>15 Events Identified</span>
      <span>OptionMetrics via WRDS</span>
    </div>
  </div>
</div>

<!-- ── KPI Strip ── -->
<div class="kpi-strip">
  <div class="kpi-warning">
    <div class="kpi-warning-icon">&#9888;</div>
    <div class="kpi-warning-text">
      <strong>Two data caveats apply.</strong>
      Event 2 (Iranian speedboats, Jan 2008) has a T+10 IV spike of 48 to 57 points
      on XLE, XOM, and CVX that is almost certainly driven by the GFC volatility regime rather than geopolitical premium.
      Event 15 (Feb 2026) has no OptionMetrics IV data: the WRDS cutoff is 2025-08-29.
      Full-sample and adjusted figures are shown in separate tabs.
    </div>
  </div>
  <div class="kpi-tabs">
    <div class="kpi-tab active" onclick="switchTab('full')">Full sample (n=11)</div>
    <div class="kpi-tab" onclick="switchTab('adj')">Ex-event-2 / ex-GFC (n=10)</div>
  </div>
  <div id="panel-full" class="kpi-panel active">
    <div class="kpi-cells">
      <div class="kpi-cell">
        <div class="kpi-label">Events analyzed</div>
        <div class="kpi-value blue">11</div>
        <div class="kpi-sub">of 15 identified</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-label">IV peak (avg)</div>
        <div class="kpi-value blue">{peak_val:.1f}</div>
        <div class="kpi-sub">at T{peak_t:+d}, norm. baseline 100</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-label">Win rate (T+20)</div>
        <div class="kpi-value green">{s_full['win_rate']:.0%}</div>
        <div class="kpi-sub">{int(s_full['win_rate']*s_full['n'])}/{s_full['n']} events</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-label">Avg P&amp;L (T+20)</div>
        <div class="kpi-value green">{s_full['avg']:+.2f}</div>
        <div class="kpi-sub">IV points, short vol</div>
      </div>
    </div>
  </div>
  <div id="panel-adj" class="kpi-panel">
    <div class="kpi-cells">
      <div class="kpi-cell">
        <div class="kpi-label">Events analyzed</div>
        <div class="kpi-value blue">10</div>
        <div class="kpi-sub">ex-event-2 (GFC)</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-label">IV peak (avg)</div>
        <div class="kpi-value blue">{peak_val:.1f}</div>
        <div class="kpi-sub">at T{peak_t:+d}, norm. baseline 100</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-label">Win rate (T+20)</div>
        <div class="kpi-value green">{s_adj['win_rate']:.0%}</div>
        <div class="kpi-sub">{int(s_adj['win_rate']*s_adj['n'])}/{s_adj['n']} events</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-label">Avg P&amp;L (T+20)</div>
        <div class="kpi-value green">{s_adj['avg']:+.2f}</div>
        <div class="kpi-sub">IV points, short vol</div>
      </div>
    </div>
  </div>
</div>

<!-- ── Section 1: Research Design ── -->
<section class="section">
  <div class="section-inner">
    <div class="section-label"><span>Study Design</span></div>
    <h2>Why <em>Iran and energy options</em></h2>

    <p>
      This report examines how implied volatility behaves in energy sector options around discrete
      Iran-related geopolitical events. The instruments are XLE (SPDR Energy ETF), USO (United States Oil Fund),
      XOM (ExxonMobil), and CVX (Chevron). Together they span ETF-level sector exposure, crude oil direct
      exposure, and single-name equity risk. Iran is the natural focus because the Strait of Hormuz, through
      which roughly 20 percent of global oil trade passes, sits at the centre of Iran's strategic leverage,
      and the country has repeatedly used or threatened that leverage since 2003.
    </p>

    <p>
      Fifteen events were identified across six clusters spanning March 2003 to February 2026: the Gulf War II
      invasion, four Strait of Hormuz incidents across 2008 to 2019, the Soleimani assassination in January
      2020, four Iran-Israel direct exchanges in 2024, the Twelve-Day War in June 2025, and the February 2026
      conflict. The goal was not to cherry-pick high-IV events but to catalogue the full sequence of
      escalation incidents and let the data determine which ones the options market actually reacted to.
    </p>

    <p>
      The study uses 30-day constant maturity ATM implied volatility from OptionMetrics via WRDS. IV is
      normalised to 100 at T-20 for each event, which allows profiles from different absolute volatility
      regimes to be averaged meaningfully. The event window runs from T-20 to T+30 trading days. A hybrid
      filter removes events where no instrument moved at least 1.5 percent on the event day or the
      following session, confirming the market registered the event.
    </p>

    <div class="callout blue">
      <div class="callout-icon">&#8505;</div>
      <div class="callout-body">
        <strong>USO data availability</strong>
        USO launched in April 2006 but OptionMetrics coverage begins in May 2007.
        For event 1 (March 2003), USO is unavailable and is excluded from that event's IV profile.
        For event 2 (January 2008), USO T-20 falls in December 2007, which is within the available window.
        This gap is handled transparently: the 2003 event is not excluded, and all USO gaps are noted per event.
      </div>
    </div>
  </div>
</section>

<!-- ── Section 2: Event Filter Results ── -->
<section class="section" style="background:var(--bg2)">
  <div class="section-inner">
    <div class="section-label"><span>Event Filter</span></div>
    <h2>Fifteen events, <em>eleven pass</em> the market reaction test</h2>

    <p>
      The filter results carry analytical content of their own.
      Three events were removed for insufficient underlying moves, and one has no IV data in OptionMetrics.
    </p>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th><th>Date</th><th>Event</th><th>Cluster</th><th>Instruments</th><th>Status</th>
          </tr>
        </thead>
        <tbody>{events_rows_html}</tbody>
      </table>
    </div>

    <h3>Three notable filter outcomes</h3>

    <div class="callout purple">
      <div class="callout-icon">&#128203;</div>
      <div class="callout-body">
        <strong>Event 1: Iraq invasion, March 2003</strong>
        XLE moved 0.98 percent and CVX moved less than 0.1 percent on the day and the day after.
        Energy IV had already run up in the weeks before the invasion as war became a near-certainty.
        By the time the invasion began, the event was fully priced. The absence of a reaction on the day
        is itself a finding: it suggests the options market processes geopolitical escalation gradually,
        not instantaneously.
      </div>
    </div>

    <div class="callout purple">
      <div class="callout-icon">&#128203;</div>
      <div class="callout-body">
        <strong>Event 7: Stena Impero seizure, July 2019</strong>
        The maximum single-instrument move was 0.95 percent. By that date, the Strait of Hormuz
        escalation sequence (events 4, 5, and 6 in the preceding ten weeks) had already generated
        significant IV repricing. The market was fatigued by the recurring incidents and the marginal
        IV impact of another one was limited.
      </div>
    </div>

    <div class="callout amber">
      <div class="callout-icon">&#9888;</div>
      <div class="callout-body">
        <strong>Event 10: Iran launches 300 missiles at Israel, April 2024</strong>
        This is the most notable filter exclusion in the dataset. Iran's launch of over 300 ballistic
        missiles and drones on April 13, 2024 was the largest direct Iranian attack on Israeli territory
        in history. T0 was April 15 (the 13th was a Saturday). The maximum move across all four
        instruments on T0 and T+1 was 0.94 percent. The market appears to have read the attack as a
        calibrated, signalling action rather than an escalation toward sustained conflict: Iran had
        reportedly communicated advance warning through intermediaries, and the strike caused minimal
        damage. Energy IV did not reprice. This is one of the more striking findings of the study.
      </div>
    </div>
  </div>
</section>

<!-- ── Section 3: Average IV Profile ── -->
<section class="section">
  <div class="section-inner">
    <div class="section-label"><span>Average IV Profile</span></div>
    <h2>The peak arrives at <em>T+2, not T0</em></h2>

    <p>
      The average composite IV profile, normalised to 100 at T-20 and averaged equally across all
      eleven qualifying events and available instruments, peaks at {peak_val:.1f} at T{peak_t:+d}.
      The lag is consistent across the dataset: the peak is not on the event day itself but one to two
      sessions afterward. This likely reflects the mechanics of options repricing: market makers widen
      spreads immediately on the event day but the full IV mark-up takes one or two sessions to consolidate
      as the news is digested and new positions are established.
    </p>

    <p>
      From T+2 the composite mean decays steadily, crossing back below 103 at T+17. By T+30 the average
      sits at {t30_val:.1f}, slightly below the T-20 baseline. This suggests a modest IV overshoot on the
      downside: once the fear premium fully unwinds, options are briefly cheaper than before the event.
    </p>

    <div class="callout green">
      <div class="callout-icon">&#128200;</div>
      <div class="callout-body">
        <strong>The one-to-two session lag has a practical implication</strong>
        An investor who enters a short vol position at T0 close rather than waiting for T+1 or T+2
        may be entering before the IV peak rather than at it. The data suggests T+1 or T+2 is a
        better entry timing if execution flexibility exists, though the strategy tested here uses T0
        close for simplicity and replicability.
      </div>
    </div>

    <div class="chart-box">
      <div class="chart-title">Average normalised IV profile, T-20 to T+30 (composite, n={profile_data['n_events']} events)</div>
      <canvas id="profileChart" height="80"></canvas>
      <div class="chart-legend">
        <div class="chart-legend-item">
          <div class="legend-line" style="background:#059669"></div>
          Mean composite IV
        </div>
        <div class="chart-legend-item">
          <div class="legend-dot" style="background:rgba(5,150,105,0.15);border:1px solid rgba(5,150,105,0.4)"></div>
          Plus/minus 1 standard deviation
        </div>
      </div>
    </div>

    <div class="callout blue">
      <div class="callout-icon">&#8505;</div>
      <div class="callout-body">
        <strong>On the confidence band</strong>
        The shaded band is one standard deviation either side of the mean, not a formal confidence interval.
        It is wide, particularly in the T+5 to T+15 window. This reflects genuine dispersion across events:
        some produce sustained IV elevation (the Twelve-Day War escalation, the Gulf of Oman tanker attacks)
        while others show rapid mean reversion (the ceasefire, the Israeli retaliation in October 2024).
        The average profile is an abstraction. No individual event closely resembles the mean, and the band
        width is a reminder of that.
      </div>
    </div>
  </div>
</section>

<!-- ── Section 4: Instrument Divergence ── -->
<section class="section" style="background:var(--bg2)">
  <div class="section-inner">
    <div class="section-label"><span>Instrument Divergence</span></div>
    <h2>USO leads; <em>equity names lag and dampen</em></h2>

    <p>
      The heatmap below shows IV change from the T-20 baseline at four checkpoints across all eleven
      events and all four instruments. Red cells indicate elevated IV; blue cells indicate suppression.
      Values are composite-normalised IV minus 100, in percentage points.
    </p>

    <div class="table-wrap scrollable">
      <table>
        <thead>
          {heat_header}
          {heat_subhdr}
        </thead>
        <tbody>{heat_rows_html}</tbody>
      </table>
    </div>
    <p style="font-size:11px;color:var(--hint);margin-top:6px">
      Values are IV change from T-20 baseline (normalised to 100). Red = IV elevated above baseline; blue = IV suppressed below baseline.
      Event 2 T+10 spike is flagged as GFC-contaminated.
    </p>

    <h3>Four observations worth highlighting</h3>

    <div class="callout blue">
      <div class="callout-icon">&#128290;</div>
      <div class="callout-body">
        <strong>USO consistently leads and amplifies</strong>
        USO tracks front-month crude oil futures directly and shows larger IV moves than XLE, XOM, or CVX
        in most events. The equity names have a partial natural hedge: higher oil prices are partially
        beneficial for energy producers, which offsets the geopolitical risk premium. USO has no such offset.
        The clearest example is event 5 (Gulf of Oman tankers): USO rose 52 pts at T0 while XLE rose
        only 3 pts.
      </div>
    </div>

    <div class="callout amber">
      <div class="callout-icon">&#9888;</div>
      <div class="callout-body">
        <strong>Event 3 (Iran threatens Strait, January 2012): IV fell across all instruments</strong>
        XLE declined 23 pts below baseline by T0. The threat to close the Strait was widely read as a
        bluff: Iran's economy was already under severe sanctions and a prolonged closure would have damaged
        Iran more than its counterparties. The market repriced the threat as noise, not signal.
      </div>
    </div>

    <div class="callout green">
      <div class="callout-icon">&#128200;</div>
      <div class="callout-body">
        <strong>Event 12 (Israel strikes Iran directly, October 2024): USO fell 22 pts by T+30</strong>
        The market interpreted Israel's direct strike on Iranian air defences as a resolution event, not
        an escalation. The risk overhang of uncertain Iranian retaliation was removed by the strike itself,
        and IV compressed steadily from T0 onward. This is the inverse of the standard geopolitical
        escalation pattern.
      </div>
    </div>

    <div class="callout green">
      <div class="callout-icon">&#128200;</div>
      <div class="callout-body">
        <strong>Event 14 (Ceasefire, June 2025): the cleanest IV crush in the dataset</strong>
        All four instruments show progressive IV decline from T0 through T+30, with USO falling
        20 pts below baseline by T+10. Ceasefire and resolution events are potentially more
        reliably tradeable than escalation events, because the direction of IV change is more
        predictable. Event 12 and event 14 both illustrate this.
      </div>
    </div>
  </div>
</section>

<!-- ── Section 5: Strategy ── -->
<section class="section">
  <div class="section-inner">
    <div class="section-label"><span>Strategy</span></div>
    <h2>Short vol at T0 close, <em>exit at T+20</em></h2>

    <p>
      The average IV profile describes a consistent arc: IV builds into the event, peaks at T+2,
      then decays toward and below baseline by T+17 to T+20. This supports a short vol
      mean-reversion trade: sell ATM IV at T0 close on any event that passes the 1.5 percent
      filter, and close the position 20 trading days later.
    </p>

    <p>
      The 20-day holding period is derived from the sensitivity analysis below. It outperforms
      the T+5 and T+17 exits on both win rate and average P&L, and captures the full mean-reversion
      window without overstaying into the T+30 period where a small number of events show IV
      re-escalation.
    </p>

    <div class="highlight-box">
      <div class="hl-grid">
        <div class="hl-divider">
          <div class="hl-label">Win rate (T+20)</div>
          <div class="hl-value">{s_adj['win_rate']:.0%}</div>
          <div class="hl-sub">ex-event-2, n={s_adj['n']}</div>
        </div>
        <div class="hl-divider">
          <div class="hl-label">Avg P&amp;L (T+20)</div>
          <div class="hl-value">{s_adj['avg']:+.2f} pts</div>
          <div class="hl-sub">IV points, short vol</div>
        </div>
        <div class="hl-divider">
          <div class="hl-label">IV peak</div>
          <div class="hl-value">T{peak_t:+d}</div>
          <div class="hl-sub">{peak_val:.1f} avg, baseline 100</div>
        </div>
      </div>
    </div>

    <div class="chart-box">
      <div class="chart-title">Strategy backtest: short IV at T0 close, exit T+20 (IV point P&amp;L proxy)</div>
      <canvas id="pnlChart" height="95"></canvas>
      <div class="chart-legend">
        <div class="chart-legend-item"><div class="legend-dot" style="background:rgba(5,150,105,0.75)"></div>Win (IV fell)</div>
        <div class="chart-legend-item"><div class="legend-dot" style="background:rgba(220,38,38,0.75)"></div>Loss (IV rose)</div>
        <div class="chart-legend-item"><div class="legend-dot" style="background:rgba(146,64,14,0.75)"></div>Event 2 (GFC flag)</div>
        <div class="chart-legend-item"><div class="legend-line" style="background:#059669;height:2px"></div>Cumulative (full sample)</div>
        <div class="chart-legend-item"><div class="legend-line" style="background:#93c5fd;height:2px;border-top:2px dashed #93c5fd;background:transparent"></div>Cumulative (ex-event-2)</div>
      </div>
    </div>

    <h3>Holding period sensitivity</h3>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Exit</th>
            <th>Win rate (full)</th>
            <th>Avg P&amp;L (full)</th>
            <th>Win rate (ex-ev2)</th>
            <th>Avg P&amp;L (ex-ev2)</th>
          </tr>
        </thead>
        <tbody>{sens_rows}</tbody>
      </table>
    </div>

    <h3>Per-event results at T+20</h3>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Event</th><th>Cluster</th><th>IV at T0</th><th>IV at T+20</th><th>P&amp;L (pts)</th><th>Cumulative</th>
          </tr>
        </thead>
        <tbody>{strat_table_rows}</tbody>
      </table>
    </div>

    <div class="callout red">
      <div class="callout-icon">&#9888;</div>
      <div class="callout-body">
        <strong>Important: this is a conceptual framework, not a complete execution plan</strong>
        The P&L figures are IV-point proxies, computed as the change in normalised composite IV from
        T0 to T+20. They do not account for delta hedging costs, gamma risk, bid-ask spreads on straddle
        entry at elevated IV levels, or the dollar vega exposure of a straddle entered on a high-IV day.
        In practice, a short straddle entered at T0 close will carry higher dollar vega than a typical
        entry. The strategy requires active delta management and stop-loss discipline. The two losses in
        the ex-event-2 sample (events 9 and 11) both reflect cases where IV continued to build after T0,
        not cases where IV spiked and held: an investor monitoring the position would have seen those
        losses developing and had the option to exit early.
      </div>
    </div>
  </div>
</section>

<!-- ── Section 6: Conclusions ── -->
<section class="section" style="background:var(--bg2)">
  <div class="section-inner">
    <div class="section-label"><span>Conclusions</span></div>
    <h2>Four takeaways from <em>a small but structured dataset</em></h2>

    <div class="callout green">
      <div class="callout-icon">&#49;&#65039;&#8419;</div>
      <div class="callout-body">
        <strong>Iran events produce a measurable but inconsistent IV response</strong>
        Eleven of fifteen events triggered a 1.5 percent underlying move on T0 or T+1. Three did not.
        One of those three (the April 2024 missile barrage) is the single largest military action in
        the dataset, which underlines that market reaction to geopolitical events is not proportional
        to the scale of the action. Context, expectation, and perceived conflict trajectory matter more
        than headline severity.
      </div>
    </div>

    <div class="callout green">
      <div class="callout-icon">&#50;&#65039;&#8419;</div>
      <div class="callout-body">
        <strong>The IV peak arrives one to two sessions after the event, not on the day</strong>
        This is consistent across the qualifying events and has a practical implication for anyone
        trading options around geopolitical catalysts. Same-day entry into a short vol position may
        precede the peak by a session or two. T+1 or T+2 entry offers a marginally better short vol
        entry level, at the cost of missing the event-day move.
      </div>
    </div>

    <div class="callout green">
      <div class="callout-icon">&#51;&#65039;&#8419;</div>
      <div class="callout-body">
        <strong>The data supports a short vol, mean-reversion strategy with a 20-day hold</strong>
        The T+20 exit produces an 82 percent win rate on the full eleven-event sample and 90 percent
        on the ten-event ex-GFC sample. The two losses are cases of continued IV build, not spike-and-hold,
        which in practice might be managed with a stop-loss rule. The average P&L of 7 to 9 IV points
        is skewed by two large winners (events 12 and 13). The median outcome is more modest.
      </div>
    </div>

    <div class="callout green">
      <div class="callout-icon">&#52;&#65039;&#8419;</div>
      <div class="callout-body">
        <strong>Resolution events are the most reliable short vol setup</strong>
        Event 12 (Israeli retaliation, October 2024) and event 14 (Twelve-Day War ceasefire, June 2025)
        both show clean, progressive IV compression from T0 to T+30. When the market interprets an event
        as conflict-resolving rather than escalating, the IV decay is faster and more predictable than
        after pure escalation events. The practical challenge is identifying resolution events at the
        point of entry rather than in hindsight.
      </div>
    </div>

    <h3>Limitations and what this study cannot claim</h3>

    <p>
      The sample is fifteen events over twenty-three years, of which eleven are analyzed. Many events
      cluster in 2019 and 2024, limiting the assumption of independence. Event 2 is contaminated by the
      GFC volatility regime and is excluded from the adjusted figures. Event 15 (February 2026) has no
      OptionMetrics data and cannot be analyzed: the WRDS cutoff is August 2025, and the post-event
      IV behaviour of the ongoing 2026 conflict is unknown at the time of writing.
    </p>

    <p>
      An 82 to 90 percent win rate on ten to eleven events is a promising signal but not a statistically
      robust one. A broader study across a wider range of geopolitical catalysts, instruments, and time
      periods would be needed to claim any generalisable edge. This study is best read as a structured
      examination of a specific historical pattern, not as a trading signal.
    </p>

    <div class="callout amber">
      <div class="callout-icon">&#9888;</div>
      <div class="callout-body">
        <strong>Event 15 (February 28, 2026): incomplete observation</strong>
        The US-Israel strike on Iran and the reported killing of Ayatollah Khamenei on February 28, 2026
        is included in the event catalogue as an identification. It is not included in any quantitative
        analysis because OptionMetrics IV data does not yet extend to that date. Its inclusion here is
        to document the event for completeness and to note that any update to this study should incorporate
        it once data becomes available.
      </div>
    </div>
  </div>
</section>

<!-- ── Footer ── -->
<footer>
  <div class="footer-inner">
    <div class="footer-top">
      <div>
        <div class="footer-name">The Intrinsic Investor</div>
        <div class="footer-desc">
          Systematic trading research. Quantitative event studies and strategy
          backtests across equities, derivatives, and macro instruments.
        </div>
      </div>
      <div class="footer-links">
        <a href="https://www.linkedin.com/in/brianliew" target="_blank">LinkedIn</a>
        <a href="https://github.com/brianliew" target="_blank">GitHub</a>
        <a href="mailto:brian@theintrinsicinvestor.com" target="_blank">Email</a>
      </div>
    </div>
    <div class="footer-bottom">
      <div class="footer-data">OptionMetrics via WRDS | yfinance | Mar 2003 to Aug 2025</div>
      <div class="footer-disclaimer">For informational purposes only. Not investment advice.</div>
    </div>
  </div>
</footer>

<script>
// ── Tab switcher ──────────────────────────────────────────────────────────────
function switchTab(id) {{
  document.querySelectorAll('.kpi-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.kpi-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + id).classList.add('active');
  event.target.classList.add('active');
}}

// ── Chart 1: IV Profile ───────────────────────────────────────────────────────
const profileCtx = document.getElementById('profileChart').getContext('2d');
new Chart(profileCtx, {{
  data: {{
    labels: {profile_labels_js},
    datasets: [
      {{
        type: 'line',
        label: 'Upper (mean + 1sd)',
        data: {profile_upper_js},
        borderColor: 'transparent',
        backgroundColor: 'rgba(5,150,105,0.10)',
        pointRadius: 0,
        fill: '+1',
        order: 3,
      }},
      {{
        type: 'line',
        label: 'Mean composite IV',
        data: {profile_mean_js},
        borderColor: '#059669',
        backgroundColor: 'transparent',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.4,
        order: 1,
      }},
      {{
        type: 'line',
        label: 'Lower (mean - 1sd)',
        data: {profile_lower_js},
        borderColor: 'transparent',
        backgroundColor: 'rgba(5,150,105,0.10)',
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
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: ctx => ctx.dataset.label === 'Mean composite IV'
            ? ` IV: ${{ctx.parsed.y?.toFixed(1)}}` : null
        }}
      }}
    }},
    scales: {{
      x: {{
        ticks: {{ color: '#9ca3af', font: {{ family: 'Inter', size: 10 }}, maxTicksLimit: 11 }},
        grid:  {{ color: 'rgba(0,0,0,0.05)' }}
      }},
      y: {{
        ticks: {{ color: '#9ca3af', font: {{ family: 'Inter', size: 10 }} }},
        grid:  {{ color: 'rgba(0,0,0,0.05)' }},
        title: {{ display: true, text: 'Normalised IV (100 = T-20)', color: '#9ca3af', font: {{ family: 'Inter', size: 10 }} }}
      }}
    }}
  }}
}});

// ── Chart 3: P&L ─────────────────────────────────────────────────────────────
const pnlCtx = document.getElementById('pnlChart').getContext('2d');
new Chart(pnlCtx, {{
  data: {{
    labels: {pnl_event_labels},
    datasets: [
      {{
        type: 'bar',
        label: 'Per-event P&L (IV pts)',
        data: {pnl_bar_values},
        backgroundColor: {pnl_bar_colors},
        order: 2,
        yAxisID: 'y',
      }},
      {{
        type: 'line',
        label: 'Cumulative (full sample)',
        data: {pnl_cum_full},
        borderColor: '#059669',
        backgroundColor: 'transparent',
        borderWidth: 2,
        pointRadius: 3,
        pointBackgroundColor: '#059669',
        tension: 0.1,
        order: 1,
        yAxisID: 'y2',
      }},
      {{
        type: 'line',
        label: 'Cumulative (ex-event-2)',
        data: {pnl_cum_adj},
        borderColor: '#93c5fd',
        backgroundColor: 'transparent',
        borderWidth: 2,
        borderDash: [5, 3],
        pointRadius: 3,
        pointBackgroundColor: '#93c5fd',
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
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{
        ticks: {{ color: '#9ca3af', font: {{ family: 'Inter', size: 10 }}, maxRotation: 35 }},
        grid:  {{ color: 'rgba(0,0,0,0.05)' }}
      }},
      y: {{
        position: 'left',
        ticks: {{ color: '#9ca3af', font: {{ family: 'Inter', size: 10 }} }},
        grid:  {{ color: 'rgba(0,0,0,0.05)' }},
        title: {{ display: true, text: 'Per-event P&L (IV pts)', color: '#9ca3af', font: {{ family: 'Inter', size: 10 }} }}
      }},
      y2: {{
        position: 'right',
        ticks: {{ color: '#9ca3af', font: {{ family: 'Inter', size: 10 }} }},
        grid:  {{ drawOnChartArea: false }},
        title: {{ display: true, text: 'Cumulative P&L (IV pts)', color: '#9ca3af', font: {{ family: 'Inter', size: 10 }} }}
      }}
    }}
  }}
}});
</script>
</body>
</html>"""

out_path = "report/index.html"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Report written to {out_path} ({len(html):,} chars)")
