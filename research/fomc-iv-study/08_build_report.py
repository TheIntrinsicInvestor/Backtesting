"""
08_build_report.py
------------------
Generate the complete standalone HTML report for the FOMC IV study.
Reads from all chart JSON files and parquets produced by scripts 06 and 07.

Output: index.html
"""

import os
import json
import numpy as np
import pandas as pd

# ── Load data ─────────────────────────────────────────────────────────────────
with open("charts/data_iv_profile.json")      as f: iv_profile    = json.load(f)
with open("charts/data_iv_by_decision.json")  as f: iv_decision   = json.load(f)
with open("charts/data_iv_by_comm_hold.json") as f: iv_comm       = json.load(f)
with open("charts/data_heatmap.json")         as f: heatmap_data  = json.load(f)
with open("charts/data_pre_pnl.json")         as f: pre_pnl       = json.load(f)
with open("charts/data_post_pnl.json")        as f: post_pnl      = json.load(f)
with open("charts/data_sensitivity.json")     as f: sensitivity   = json.load(f)

events    = pd.read_parquet("data/fomc_events.parquet")
pre_df    = pd.read_parquet("data/strategy_pre.parquet")
post_df   = pd.read_parquet("data/strategy_post.parquet")
sens_df   = pd.read_parquet("data/sensitivity.parquet")
profiles  = pd.read_parquet("data/event_profiles.parquet")

events["date"] = pd.to_datetime(events["date"])

# ── Extract KPI values ────────────────────────────────────────────────────────
n_meetings = iv_profile["n_meetings"]
labels     = iv_profile["labels"]
spx_mean   = iv_profile["spx_mean"]

t_minus1_idx = labels.index(-1)
t_plus1_idx  = labels.index(1)
iv_t_minus1  = spx_mean[t_minus1_idx] or 100
iv_t_plus1   = spx_mean[t_plus1_idx]  or 100
crush_pct    = (iv_t_plus1 - iv_t_minus1) / iv_t_minus1 * 100

pre_metrics  = pre_pnl["metrics"]
post_metrics = post_pnl["metrics"]
best_exit    = sensitivity["best_exit"]

pre_win  = pre_metrics["win_rate"]
post_win = post_metrics["win_rate"]

pre_sharpe  = pre_metrics.get("sharpe") or 0
post_sharpe = post_metrics.get("sharpe") or 0

# Heatmap color helper
def cell_bg(val):
    if val is None:
        return "#f7f4ec"
    if val >=  15: return "#fca5a5"
    if val >=   7: return "#fecaca"
    if val >=   3: return "#fee2e2"
    if val <=  -15: return "#93c5fd"
    if val <=   -7: return "#bfdbfe"
    if val <=   -3: return "#dbeafe"
    return "#f7f4ec"

def cell_color(val):
    if val is None:
        return "#4a6460"
    if val >=  15 or val <= -15:
        return "#0f2220"
    return "#4a6460"

def fmt_delta(val):
    if val is None:
        return "--"
    return f"{val:+.1f}"

CHECKPOINTS = [-5, -1, 0, 1, 5]
CP_LABELS   = ["T-5", "T-1", "T=0", "T+1", "T+5"]
INSTRUMENTS = ["SPX", "TLT", "VIX"]

# Sort heatmap rows by date
heatmap_data.sort(key=lambda r: r["fomc_date"])

# ── Sensitivity table rows ────────────────────────────────────────────────────
def sens_row_html(row, is_best):
    highlight = ' class="top-row"' if is_best else ""
    best_badge = ' <span style="font-size:0.65rem;background:var(--green2);color:#fff;padding:1px 5px;border-radius:3px;font-family:Inter,sans-serif">best</span>' if is_best else ""
    wr   = f"{row['win_rate']*100:.0f}%"
    pnl  = f"${row['avg_pnl']:+.0f}"
    sh   = f"{row['sharpe']:.2f}" if row['sharpe'] else "--"
    mdd  = f"${row['max_dd']:.0f}"
    return f'<tr{highlight}><td>{row["exit_label"]}{best_badge}</td><td>{row["n"]}</td><td>{wr}</td><td>{pnl}</td><td>{sh}</td><td>{mdd}</td></tr>'

best_sharpe = sens_df.loc[sens_df["sharpe"].idxmax(), "exit_label"] if sens_df["sharpe"].notna().any() else "T+5"
sens_rows_html = ""
for _, row in sens_df.iterrows():
    sens_rows_html += sens_row_html(row, row["exit_label"] == best_sharpe)

# ── Per-meeting P&L table (pre-meeting) ───────────────────────────────────────
pre_df = pre_df.sort_values("fomc_date")
pre_table_rows = ""
for _, r in pre_df.iterrows():
    pnl_style = "color:var(--green2)" if r["pnl_per_contract"] > 0 else "color:var(--red2)"
    emg = " ⚡" if r.get("is_emergency") else ""
    pre_table_rows += (
        f'<tr>'
        f'<td style="font-family:JetBrains Mono,monospace;font-size:0.8rem">{r["fomc_date"].strftime("%b %d, %Y")}{emg}</td>'
        f'<td>{r["decision_type"]}</td>'
        f'<td>{r["comm_surprise"]}</td>'
        f'<td style="font-family:JetBrains Mono,monospace;text-align:right">${r["straddle_entry"]:.2f}</td>'
        f'<td style="font-family:JetBrains Mono,monospace;text-align:right">${r["straddle_exit"]:.2f}</td>'
        f'<td style="font-family:JetBrains Mono,monospace;text-align:right;{pnl_style}">${r["pnl_per_contract"]:+.0f}</td>'
        f'<td style="font-family:JetBrains Mono,monospace;text-align:right">${r["cum_pnl"]:+.0f}</td>'
        f'</tr>\n'
    )

# ── Heatmap table HTML ────────────────────────────────────────────────────────
def build_heatmap_html():
    lines = ['<table class="heatmap-table">']
    # Header
    lines.append('<thead><tr>')
    lines.append('<th>Date</th><th>Decision</th><th>Comm</th>')
    for instr in INSTRUMENTS:
        for lbl in CP_LABELS:
            lines.append(f'<th>{instr}<br><span style="font-weight:400;font-size:0.7rem">{lbl}</span></th>')
    lines.append('</tr></thead><tbody>')
    # Rows
    for row in heatmap_data:
        dtype = row["decision_type"]
        cs    = row["comm_surprise"]
        emg   = " ⚡" if row.get("is_emergency") else ""
        lines.append('<tr>')
        lines.append(f'<td style="font-family:JetBrains Mono,monospace;font-size:0.78rem;white-space:nowrap">{row["fomc_date"]}{emg}</td>')
        lines.append(f'<td>{dtype}</td>')
        lines.append(f'<td>{cs}</td>')
        for instr in INSTRUMENTS:
            for cp in CHECKPOINTS:
                key = f"{instr}_T{cp:+d}"
                val = row.get(key)
                bg  = cell_bg(val)
                col = cell_color(val)
                txt = fmt_delta(val)
                lines.append(f'<td style="background:{bg};color:{col};font-family:JetBrains Mono,monospace;font-size:0.75rem;text-align:right">{txt}</td>')
        lines.append('</tr>')
    lines.append('</tbody></table>')
    return "\n".join(lines)

heatmap_html = build_heatmap_html()

# ── Build full HTML ───────────────────────────────────────────────────────────
IV_LABELS_JS  = json.dumps(iv_profile["labels"])
SPX_MEAN_JS   = json.dumps(iv_profile["spx_mean"])
SPX_UPPER_JS  = json.dumps(iv_profile["spx_upper"])
SPX_LOWER_JS  = json.dumps(iv_profile["spx_lower"])
TLT_MEAN_JS   = json.dumps(iv_profile["tlt_mean"])
VIX_MEAN_JS   = json.dumps(iv_profile["vix_mean"])

DEC_HIKE_JS   = json.dumps(iv_decision.get("Hike", []))
DEC_HOLD_JS   = json.dumps(iv_decision.get("Hold", []))
DEC_CUT_JS    = json.dumps(iv_decision.get("Cut",  []))
DEC_HIKE_N    = iv_decision.get("Hike_n", 0)
DEC_HOLD_N    = iv_decision.get("Hold_n", 0)
DEC_CUT_N     = iv_decision.get("Cut_n",  0)

COMM_HAW_JS   = json.dumps(iv_comm.get("Hawkish", []))
COMM_NEU_JS   = json.dumps(iv_comm.get("Neutral", []))
COMM_DOV_JS   = json.dumps(iv_comm.get("Dovish",  []))
COMM_HAW_N    = iv_comm.get("Hawkish_n", 0)
COMM_NEU_N    = iv_comm.get("Neutral_n", 0)
COMM_DOV_N    = iv_comm.get("Dovish_n",  0)

PRE_LABELS_JS = json.dumps(pre_pnl["labels"])
PRE_BARS_JS   = json.dumps(pre_pnl["bars"])
PRE_COLORS_JS = json.dumps(pre_pnl["colors"])
PRE_CUM_JS    = json.dumps(pre_pnl["cum_line"])

POST_LABELS_JS = json.dumps(post_pnl["labels"])
POST_BARS_JS   = json.dumps(post_pnl["bars"])
POST_COLORS_JS = json.dumps(post_pnl["colors"])
POST_CUM_JS    = json.dumps(post_pnl["cum_line"])

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The FOMC Vol Crush | The Intrinsic Investor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,600;1,9..144,300;1,9..144,400&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {{
  --bg:      #f7f4ec;
  --bg2:     #f0ece2;
  --ink:     #0f2220;
  --muted:   #4a6460;
  --hint:    #8aaba6;
  --accent:  #1a5c52;
  --green2:  #059669;
  --red2:    #dc2626;
  --blue2:   #2563eb;
  --amber:   #E3A008;
  --green-bg:#d1fae5;
  --red-bg:  #fee2e2;
  --amber-bg:#fef3c7;
  --blue-bg: #dbeafe;
  --purple-bg:#ede9fe;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{
  font-family:Inter,sans-serif;
  background:var(--bg);
  color:var(--ink);
  line-height:1.7;
  position:relative;
  overflow-x:hidden;
}}
body::before{{
  content:'';
  position:fixed;inset:0;
  background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='1'/%3E%3C/svg%3E");
  opacity:.5;mix-blend-mode:multiply;pointer-events:none;z-index:9999;
}}
#progress-bar{{position:fixed;top:0;left:0;height:3px;background:linear-gradient(90deg,var(--accent),var(--green2));width:0%;z-index:10000;transition:width .1s}}
nav{{
  position:sticky;top:0;z-index:1000;
  background:rgba(247,244,236,.85);backdrop-filter:blur(12px);
  border-bottom:1px solid rgba(15,34,32,.08);
  padding:.85rem 2rem;
  display:flex;align-items:center;justify-content:space-between;
}}
.nav-logo{{font-family:Fraunces,serif;font-size:1.1rem;color:var(--ink);text-decoration:none;font-weight:600}}
.nav-links{{display:flex;gap:2rem;list-style:none}}
.nav-links a{{color:var(--muted);text-decoration:none;font-size:.875rem;font-weight:500;transition:color .2s}}
.nav-links a:hover{{color:var(--ink)}}
.hero{{
  background:var(--ink);color:var(--bg);
  padding:5rem 2rem 4rem;
  position:relative;overflow:hidden;
}}
.hero::after{{
  content:'';position:absolute;inset:0;
  background:radial-gradient(ellipse at 70% 50%,rgba(26,92,82,.4) 0%,transparent 70%);
  pointer-events:none;
}}
.hero-inner{{max-width:860px;margin:0 auto;position:relative;z-index:1}}
.hero-eyebrow{{
  font-size:.75rem;font-weight:600;letter-spacing:.12em;
  text-transform:uppercase;color:rgba(247,244,236,.5);margin-bottom:1.2rem;
}}
.hero h1{{
  font-family:Fraunces,serif;font-size:clamp(2rem,5vw,3.2rem);
  font-weight:300;line-height:1.2;margin-bottom:1.2rem;
}}
.hero h1 em{{font-style:italic;color:#6ed4c8}}
.hero-sub{{font-size:1.05rem;color:rgba(247,244,236,.75);max-width:640px;line-height:1.6}}
.hero-meta{{
  display:flex;flex-wrap:wrap;gap:1.5rem;margin-top:2rem;
  font-size:.8rem;color:rgba(247,244,236,.55);align-items:center;
}}
.hero-meta span{{display:flex;align-items:center;gap:.4rem}}
.hero-meta a{{
  color:rgba(247,244,236,.55);text-decoration:none;border:1px solid rgba(247,244,236,.2);
  padding:.25rem .75rem;border-radius:4px;transition:all .2s;
}}
.hero-meta a:hover{{color:var(--bg);border-color:rgba(247,244,236,.5)}}
.kpi-strip{{
  display:grid;grid-template-columns:repeat(4,1fr);
  border-bottom:1px solid rgba(15,34,32,.1);
  background:var(--bg);
}}
.kpi-cell{{
  padding:1.8rem 2rem;
  border-right:1px solid rgba(15,34,32,.08);
}}
.kpi-cell:last-child{{border-right:none}}
.kpi-label{{font-size:.7rem;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--hint);margin-bottom:.5rem}}
.kpi-value{{font-family:Fraunces,serif;font-size:2rem;font-weight:300;color:var(--ink);line-height:1}}
.kpi-value.green{{color:var(--green2)}}
.kpi-value.blue{{color:var(--blue2)}}
.kpi-sub{{font-size:.75rem;color:var(--muted);margin-top:.35rem}}
#side-nav{{
  position:fixed;right:1.2rem;top:50%;transform:translateY(-50%);
  display:flex;flex-direction:column;gap:.6rem;z-index:900;
}}
.sn-item{{display:flex;align-items:center;gap:.5rem;cursor:pointer;justify-content:flex-end}}
.sn-dot{{
  width:7px;height:7px;border-radius:50%;
  background:var(--hint);transition:all .25s;flex-shrink:0;
}}
.sn-label{{
  font-size:.65rem;color:var(--hint);white-space:nowrap;
  transition:all .25s;opacity:0;transform:translateX(4px);
  font-family:Inter,sans-serif;font-weight:500;
}}
.sn-item:hover .sn-label,.sn-item.active .sn-label{{opacity:1;transform:translateX(0)}}
.sn-item.active .sn-dot{{background:var(--accent);transform:scale(1.4)}}
@media(max-width:860px){{#side-nav{{display:none}}}}
section{{padding:4.5rem 2rem;opacity:0;transform:translateY(18px);transition:opacity .55s,transform .55s}}
section.visible{{opacity:1;transform:none}}
.section-inner{{max-width:860px;margin:0 auto}}
.section-label{{
  font-size:.68rem;font-weight:600;letter-spacing:.14em;text-transform:uppercase;
  color:var(--accent);margin-bottom:.9rem;
}}
section h2{{
  font-family:Fraunces,serif;font-size:clamp(1.5rem,3vw,2.1rem);
  font-weight:300;margin-bottom:1.4rem;line-height:1.3;
}}
section h3{{
  font-family:Fraunces,serif;font-size:1.2rem;font-weight:400;
  margin:2rem 0 1rem;
}}
section p{{
  color:var(--muted);margin-bottom:1.1rem;
  text-align:justify;hyphens:auto;
}}
.callout{{
  padding:1rem 1.25rem;border-radius:6px;margin:1.2rem 0;
  border-left:3px solid;font-size:.9rem;color:var(--ink);
}}
.callout.green{{background:var(--green-bg);border-color:var(--green2)}}
.callout.amber{{background:var(--amber-bg);border-color:var(--amber)}}
.callout.blue{{background:var(--blue-bg);border-color:var(--blue2)}}
.callout.red{{background:var(--red-bg);border-color:var(--red2)}}
.callout.purple{{background:var(--purple-bg);border-color:#7c3aed}}
.callout strong{{font-weight:600}}
.chart-box{{
  background:var(--bg2);border:1px solid rgba(15,34,32,.08);
  border-radius:8px;padding:1.5rem;margin:1.5rem 0;
}}
.chart-title{{
  font-size:.68rem;font-weight:600;letter-spacing:.1em;
  text-transform:uppercase;color:var(--muted);margin-bottom:1rem;
}}
.chart-legend{{
  display:flex;flex-wrap:wrap;gap:1rem;margin-top:.8rem;font-size:.78rem;color:var(--muted);
}}
.legend-dot{{
  width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:.3rem;flex-shrink:0;
}}
.legend-line{{
  width:18px;height:2px;display:inline-block;margin-right:.3rem;vertical-align:middle;flex-shrink:0;
}}
.data-table{{width:100%;border-collapse:collapse;font-size:.83rem;margin:1rem 0}}
.data-table th{{
  background:var(--ink);color:var(--bg);
  padding:.55rem .8rem;text-align:left;font-weight:500;font-size:.72rem;letter-spacing:.04em;
}}
.data-table td{{
  padding:.5rem .8rem;border-bottom:1px solid rgba(15,34,32,.06);color:var(--muted);
}}
.data-table tr:hover td{{background:rgba(15,34,32,.02)}}
.data-table .top-row td{{background:#d1fae5!important;color:var(--ink)!important;font-weight:500}}
.heatmap-table{{width:100%;border-collapse:collapse;font-size:.75rem}}
.heatmap-table th{{
  background:var(--ink);color:var(--bg);
  padding:.4rem .5rem;font-weight:500;font-size:.65rem;text-align:center;letter-spacing:.03em;
}}
.heatmap-table td{{
  padding:.35rem .45rem;border-bottom:1px solid rgba(15,34,32,.05);
  text-align:center;
}}
.method-table{{width:100%;border-collapse:collapse;font-size:.85rem;margin:1rem 0}}
.method-table th{{
  background:var(--ink);color:var(--bg);padding:.6rem 1rem;
  font-weight:500;font-size:.75rem;text-align:left;
}}
.method-table td{{
  padding:.55rem 1rem;border-bottom:1px solid rgba(15,34,32,.08);
  color:var(--muted);vertical-align:top;
}}
.method-table td:first-child{{font-weight:500;color:var(--ink);white-space:nowrap;width:35%}}
.highlight-box{{
  background:var(--ink);color:var(--bg);border-radius:8px;
  padding:2rem;display:grid;grid-template-columns:repeat(3,1fr);gap:1.5rem;margin:1.5rem 0;
}}
.hb-val{{font-family:Fraunces,serif;font-size:2.2rem;font-weight:300;color:#6ed4c8}}
.hb-label{{font-size:.75rem;color:rgba(247,244,236,.6);margin-top:.3rem}}
footer{{
  background:var(--ink);color:rgba(247,244,236,.55);
  padding:3rem 2rem;font-size:.8rem;
}}
.footer-inner{{max-width:860px;margin:0 auto;display:flex;justify-content:space-between;flex-wrap:wrap;gap:1.5rem}}
.footer-copy{{font-family:JetBrains Mono,monospace;font-size:.72rem}}
.footer-links{{display:flex;gap:1.5rem}}
.footer-links a{{color:rgba(247,244,236,.45);text-decoration:none}}
.footer-links a:hover{{color:var(--bg)}}
@media(max-width:640px){{
  .kpi-strip{{grid-template-columns:repeat(2,1fr)}}
  .kpi-cell{{border-right:none;border-bottom:1px solid rgba(15,34,32,.08)}}
  .highlight-box{{grid-template-columns:1fr}}
}}
</style>
</head>
<body>
<div id="progress-bar"></div>

<nav>
  <a href="../../index.html" class="nav-logo">The Intrinsic Investor</a>
  <ul class="nav-links">
    <li><a href="../../index.html">Home</a></li>
    <li><a href="../index.html">Research</a></li>
    <li><a href="../../about.html">About</a></li>
  </ul>
</nav>

<!-- Side nav -->
<nav id="side-nav" aria-label="Page sections">
  <div class="sn-item" onclick="scrollToSection('s1')"><span class="sn-label">Study Design</span><div class="sn-dot"></div></div>
  <div class="sn-item" onclick="scrollToSection('s2')"><span class="sn-label">IV Profile</span><div class="sn-dot"></div></div>
  <div class="sn-item" onclick="scrollToSection('s3')"><span class="sn-label">Surprise Analysis</span><div class="sn-dot"></div></div>
  <div class="sn-item" onclick="scrollToSection('s4')"><span class="sn-label">Strategy A</span><div class="sn-dot"></div></div>
  <div class="sn-item" onclick="scrollToSection('s5')"><span class="sn-label">Strategy B</span><div class="sn-dot"></div></div>
  <div class="sn-item" onclick="scrollToSection('s6')"><span class="sn-label">Methodology</span><div class="sn-dot"></div></div>
  <div class="sn-item" onclick="scrollToSection('s7')"><span class="sn-label">Conclusions</span><div class="sn-dot"></div></div>
</nav>

<!-- Hero -->
<header class="hero">
  <div class="hero-inner">
    <div class="hero-eyebrow">Systematic Market Research</div>
    <h1>The FOMC Vol Crush: <em>Implied Volatility Dynamics Around Federal Reserve Decisions</em></h1>
    <p class="hero-sub">
      How SPX, TLT, and VIX implied volatility behaves before and after FOMC announcements,
      whether a pre-meeting IV build-up is reliably exploitable, and what communication
      surprises reveal about the limits of forward guidance.
    </p>
    <div class="hero-meta">
      <span>Brian Liew, BSc Accounting and Finance, LSE</span>
      <span>Published May 2026</span>
      <span>2018 to 2024, n={n_meetings} meetings</span>
      <span>OptionMetrics, FRED, CME FedWatch</span>
      <a href="https://github.com/TheIntrinsicInvestor/Backtesting" target="_blank" rel="noopener">GitHub Code</a>
    </div>
  </div>
</header>

<!-- KPI Strip -->
<div class="kpi-strip">
  <div class="kpi-cell">
    <div class="kpi-label">Meetings Analysed</div>
    <div class="kpi-value blue">{n_meetings}</div>
    <div class="kpi-sub">2018 to 2024, scheduled and emergency</div>
  </div>
  <div class="kpi-cell">
    <div class="kpi-label">Avg SPX IV Crush</div>
    <div class="kpi-value blue">{crush_pct:+.1f}%</div>
    <div class="kpi-sub">T-1 to T+1 (normalised, excl. outliers)</div>
  </div>
  <div class="kpi-cell">
    <div class="kpi-label">Pre-Meeting Sell Win Rate</div>
    <div class="kpi-value green">{pre_win:.0%}</div>
    <div class="kpi-sub">Enter T-1, exit T+1 (SPY straddle)</div>
  </div>
  <div class="kpi-cell">
    <div class="kpi-label">Post-Announcement Win Rate</div>
    <div class="kpi-value green">{post_win:.0%}</div>
    <div class="kpi-sub">Enter T+1, exit {best_exit} (SPY straddle)</div>
  </div>
</div>

<!-- Section 1: Study Design -->
<section id="s1">
  <div class="section-inner">
    <div class="section-label">01 — Study Design</div>
    <h2>Why FOMC meetings create a predictable options market cycle</h2>
    <p>
      Federal Reserve rate decisions are the single most anticipated scheduled macro events in global
      markets. The options market prices this anticipated uncertainty as a risk premium in the days
      before each meeting, then rapidly resets once the uncertainty resolves. This study asks whether
      that pattern is systematic, how it varies by decision type and communication surprise, and
      whether it can be profitably exploited via short straddle strategies on SPY.
    </p>
    <p>
      We track three implied volatility instruments across {n_meetings} FOMC meetings from 2018 to 2024:
      SPX 30-day ATM IV from OptionMetrics (delta=50, days=30), TLT 30-day ATM IV (representing rates
      market uncertainty), and the CBOE VIX (pulled from FRED). Each meeting is classified on two dimensions.
    </p>
    <div class="callout blue">
      <strong>Two-layer classification.</strong> Primary: decision type (Hike, Hold, or Cut) based on
      the actual rate change. Secondary: communication surprise (Hawkish, Neutral, or Dovish) based on
      dot plot changes, statement language, and same-day market reaction. The secondary layer captures
      what actually moves markets: many in-line rate decisions carry large guidance surprises.
    </div>
    <h3>Classification breakdown</h3>
    <table class="data-table">
      <thead><tr><th>Category</th><th>Sub-group</th><th>n</th><th>Example meetings</th></tr></thead>
      <tbody>
        <tr><td>Hike</td><td>Hawkish comm</td><td>{iv_decision.get("Hike_n",0)}</td><td>Jun 2022 (+75bps vs +50bps expected)</td></tr>
        <tr><td>Hold</td><td>Hawkish comm</td><td>{COMM_HAW_N}</td><td>Jun 2021 dot plot shift, Jan 2024 March cut walkback</td></tr>
        <tr><td>Hold</td><td>Neutral comm</td><td>{COMM_NEU_N}</td><td>Most ZLB-era holds, post-taper normalisation</td></tr>
        <tr><td>Hold</td><td>Dovish comm</td><td>{COMM_DOV_N}</td><td>Jan 2019 patient pivot, Dec 2023 cut signal</td></tr>
        <tr><td>Cut</td><td>All types</td><td>{iv_decision.get("Cut_n",0)}</td><td>2019 easing cycle, 2024 pivot, COVID emergency</td></tr>
      </tbody>
    </table>
    <div class="callout amber">
      <strong>Outliers and caveats.</strong> Three meetings are flagged as structural outliers: the
      unscheduled emergency cuts on 3 March and 15 March 2020 (COVID pandemic response) and the
      degenerate 18 March 2020 scheduled meeting that followed, at which rates were already at zero.
      These appear in the heatmap with a lightning mark and are excluded from profile aggregations.
      The 2018 to 2021 zero-rate era and the 2022 to 2024 hiking cycle represent materially different
      vol regimes and should be interpreted accordingly.
    </div>
  </div>
</section>

<!-- Section 2: IV Event Profile -->
<section id="s2" style="background:var(--bg2)">
  <div class="section-inner">
    <div class="section-label">02 — IV Event Profile</div>
    <h2>SPX implied vol builds in the final week before FOMC, then crushes on announcement day</h2>
    <p>
      Each meeting's IV series is normalised so that the mean of T-20 to T-15 equals 100, then averaged
      across all {n_meetings} meetings (excluding the three COVID outliers). The pattern is consistent: a
      gradual build in implied vol over the 5 to 10 days preceding the announcement, followed by a sharp
      collapse on or immediately after the decision day.
    </p>
    <p>
      SPX and VIX show the most pronounced pre-meeting premium, consistent with equity market uncertainty
      dominating options pricing around rate decisions. TLT IV tends to peak earlier, reflecting that
      rates market participants price in the decision further in advance.
    </p>
    <div class="chart-box">
      <div class="chart-title">Average normalised IV profile, T-20 to T+10 (baseline = 100 at T-20)</div>
      <canvas id="profileChart" height="80"></canvas>
      <div class="chart-legend">
        <span><span class="legend-line" style="background:#1a5c52"></span>SPX IV (mean)</span>
        <span><span class="legend-line" style="background:#1a5c52;opacity:.25"></span>SPX ±1 SD band</span>
        <span><span class="legend-line" style="background:#2563eb;border-top:2px dashed #2563eb"></span>TLT IV</span>
        <span><span class="legend-line" style="background:#d97706;border-top:2px dashed #d97706"></span>VIX</span>
      </div>
    </div>
    <div class="callout blue">
      <strong>Confidence band interpretation.</strong> The shaded region shows plus and minus one standard
      deviation across meetings, not a statistical confidence interval. The wide dispersion reflects genuine
      cross-meeting variation in vol regime (e.g., COVID 2020 vs. 2019 low-vol period). The aggregate
      pattern is consistent but the magnitude varies substantially.
    </div>
  </div>
</section>

<!-- Section 3: Surprise Analysis -->
<section id="s3">
  <div class="section-inner">
    <div class="section-label">03 — Surprise Analysis</div>
    <h2>Hike meetings carry the largest pre-meeting premium; dovish guidance collapses vol fastest</h2>
    <p>
      Splitting the IV profile by decision type reveals that hike meetings generate a more pronounced
      pre-meeting IV build-up, consistent with greater policy uncertainty when the Fed is actively
      tightening. Hold meetings show a smaller but still consistent pattern. Cut meetings are harder to
      interpret given the small sample and structural mix (2019 mid-cycle easing vs. 2024 normalisation
      vs. 2020 emergency actions).
    </p>
    <div class="chart-box">
      <div class="chart-title">SPX IV profile by decision type (Hike / Hold / Cut), normalised</div>
      <canvas id="decisionChart" height="80"></canvas>
      <div class="chart-legend">
        <span><span class="legend-dot" style="background:#dc2626"></span>Hike (n={DEC_HIKE_N})</span>
        <span><span class="legend-dot" style="background:#2563eb"></span>Hold (n={DEC_HOLD_N})</span>
        <span><span class="legend-dot" style="background:#059669"></span>Cut (n={DEC_CUT_N})</span>
      </div>
    </div>
    <p>
      Within hold meetings (n={DEC_HOLD_N}), communication surprises drive material differences in IV
      dynamics. Hawkish guidance surprises are associated with a sharper post-announcement IV spike as
      markets reprice the forward path, while dovish surprises produce the fastest IV collapse. Neutral
      holds show the textbook crush.
    </p>
    <div class="chart-box">
      <div class="chart-title">SPX IV profile by communication surprise, Hold meetings only</div>
      <canvas id="commChart" height="80"></canvas>
      <div class="chart-legend">
        <span><span class="legend-dot" style="background:#dc2626"></span>Hawkish guidance (n={COMM_HAW_N})</span>
        <span><span class="legend-dot" style="background:#6b7280"></span>Neutral (n={COMM_NEU_N})</span>
        <span><span class="legend-dot" style="background:#059669"></span>Dovish guidance (n={COMM_DOV_N})</span>
      </div>
    </div>
    <h3>IV change at key checkpoints by meeting and instrument</h3>
    <p>
      The heatmap below shows the change in normalised IV (vs. baseline of 100) at five checkpoints for
      each meeting across SPX, TLT, and VIX. Red cells indicate elevated IV above baseline; blue cells
      indicate IV below baseline. Empty cells indicate missing or insufficient data.
    </p>
    <div class="chart-box" style="overflow-x:auto;padding:1rem">
      {heatmap_html}
    </div>
    <p style="font-size:.75rem;color:var(--hint);font-family:JetBrains Mono,monospace">
      Values are (IV / baseline mean) - 100. ⚡ denotes emergency meeting. Baseline = mean(T-20 to T-15) = 100.
    </p>
  </div>
</section>

<!-- Section 4: Strategy A -->
<section id="s4" style="background:var(--bg2)">
  <div class="section-inner">
    <div class="section-label">04 — Strategy A: Pre-Meeting Straddle Sell</div>
    <h2>Selling the pre-meeting premium: enter T-1, exit T+1</h2>
    <p>
      The pre-meeting IV build-up creates a natural opportunity for short-vol traders. Strategy A
      sells an ATM SPY straddle at the close on T-1 (the last trading day before the announcement)
      and buys it back at the close on T+1. The position is short vega and short gamma, profiting
      when IV collapses post-announcement and the underlying does not move far enough to overcome
      the premium collected.
    </p>
    <p>
      All P&L figures are gross of transaction costs. SPY straddle bid-ask spreads typically run
      $0.05 to $0.15 per leg, or $10 to $30 per contract round-trip, which represents a meaningful
      drag at these premium levels.
    </p>
    <div class="highlight-box">
      <div>
        <div class="hb-val">{pre_win:.0%}</div>
        <div class="hb-label">Win rate (all meetings)</div>
      </div>
      <div>
        <div class="hb-val">${pre_metrics['avg_pnl']:+.0f}</div>
        <div class="hb-label">Avg P&L per contract</div>
      </div>
      <div>
        <div class="hb-val">{pre_sharpe:.2f}</div>
        <div class="hb-label">Annualised Sharpe (sqrt(8) scaling)</div>
      </div>
    </div>
    <div class="chart-box">
      <div class="chart-title">Pre-meeting straddle P&amp;L per meeting (Strategy A)</div>
      <canvas id="prePnlChart" height="90"></canvas>
      <div class="chart-legend">
        <span><span class="legend-dot" style="background:#059669"></span>Win</span>
        <span><span class="legend-dot" style="background:#dc2626"></span>Loss</span>
        <span><span class="legend-dot" style="background:#9ca3af"></span>Flagged outlier</span>
        <span style="margin-left:.5rem"><span class="legend-line" style="background:var(--ink)"></span>Cumulative P&amp;L</span>
      </div>
    </div>
    <h3>Performance by meeting type</h3>
    <table class="data-table">
      <thead><tr><th>Decision Type</th><th>Comm Surprise</th><th>n</th><th>Win Rate</th><th>Avg P&amp;L</th><th>Sharpe</th></tr></thead>
      <tbody>
"""

# Add rows for pre-meeting by decision_type and comm_surprise
pre_df["fomc_date"] = pd.to_datetime(pre_df["fomc_date"])
for dtype in ["Hike", "Hold", "Cut"]:
    sub = pre_df[pre_df["decision_type"] == dtype]
    if len(sub) == 0:
        continue
    n    = len(sub)
    wr   = (sub["pnl_per_contract"] > 0).mean()
    avg  = sub["pnl_per_contract"].mean()
    ret  = sub["return_pct"]
    sh   = ret.mean() / ret.std() * np.sqrt(8) if ret.std() > 0 else float('nan')
    html += f'<tr><td>{dtype}</td><td>All</td><td>{n}</td><td>{wr:.0%}</td><td>${avg:+.0f}</td><td>{"%.2f" % sh if not np.isnan(sh) else "--"}</td></tr>\n'
    if dtype == "Hold":
        for cs in ["Hawkish", "Neutral", "Dovish"]:
            csub = sub[sub["comm_surprise"] == cs]
            if len(csub) == 0:
                continue
            cn   = len(csub)
            cwr  = (csub["pnl_per_contract"] > 0).mean()
            cavg = csub["pnl_per_contract"].mean()
            cret = csub["return_pct"]
            csh  = cret.mean() / cret.std() * np.sqrt(8) if cret.std() > 0 else float('nan')
            html += f'<tr><td style="color:var(--hint)">Hold</td><td>{cs}</td><td>{cn}</td><td>{cwr:.0%}</td><td>${cavg:+.0f}</td><td>{"%.2f" % csh if not np.isnan(csh) else "--"}</td></tr>\n'

html += f"""      </tbody>
    </table>
    <h3>Per-meeting results</h3>
    <div style="overflow-x:auto">
    <table class="data-table">
      <thead><tr>
        <th>FOMC Date</th><th>Decision</th><th>Comm</th>
        <th style="text-align:right">Entry Straddle</th>
        <th style="text-align:right">Exit Straddle</th>
        <th style="text-align:right">P&amp;L / Contract</th>
        <th style="text-align:right">Cumulative</th>
      </tr></thead>
      <tbody>
        {pre_table_rows}
      </tbody>
    </table>
    </div>
    <div class="callout red">
      <strong>Important disclaimer.</strong> All P&amp;L is gross. Actual realised returns will be lower
      after bid-ask spread ($10 to $30 per contract round-trip), commissions, and margin costs for short
      options. The strategy carries unbounded gamma risk if the underlying gaps through the strike.
      No delta hedging is applied. These results are a backtested approximation, not a live trading record.
    </div>
  </div>
</section>

<!-- Section 5: Strategy B -->
<section id="s5">
  <div class="section-inner">
    <div class="section-label">05 — Strategy B: Post-Announcement Straddle Sell</div>
    <h2>Selling the residual premium: enter T+1, hold for continued mean-reversion</h2>
    <p>
      Strategy B enters at T+1 close (after the announcement) and holds for additional vol
      mean-reversion. The thesis is that even after the immediate crush, IV may remain elevated
      relative to realised vol for several days as markets digest the implications of the decision.
      The sensitivity table below shows performance at five exit points.
    </p>
    <div class="highlight-box">
      <div>
        <div class="hb-val">{post_win:.0%}</div>
        <div class="hb-label">Win rate ({best_exit} exit)</div>
      </div>
      <div>
        <div class="hb-val">${post_metrics['avg_pnl']:+.0f}</div>
        <div class="hb-label">Avg P&amp;L per contract</div>
      </div>
      <div>
        <div class="hb-val">{post_sharpe:.2f}</div>
        <div class="hb-label">Annualised Sharpe</div>
      </div>
    </div>
    <div class="chart-box">
      <div class="chart-title">Post-announcement straddle P&amp;L per meeting ({best_exit} exit)</div>
      <canvas id="postPnlChart" height="90"></canvas>
      <div class="chart-legend">
        <span><span class="legend-dot" style="background:#059669"></span>Win</span>
        <span><span class="legend-dot" style="background:#dc2626"></span>Loss</span>
        <span><span class="legend-dot" style="background:#9ca3af"></span>Flagged outlier</span>
        <span style="margin-left:.5rem"><span class="legend-line" style="background:var(--ink)"></span>Cumulative P&amp;L</span>
      </div>
    </div>
    <h3>Holding period sensitivity</h3>
    <table class="data-table" id="sensTable">
      <thead><tr><th>Exit</th><th>n</th><th>Win Rate</th><th>Avg P&amp;L</th><th>Sharpe</th><th>Max DD</th></tr></thead>
      <tbody>
        {sens_rows_html}
      </tbody>
    </table>
    <div class="callout blue">
      <strong>Sharpe methodology note.</strong> Per-trade returns are annualised using a sqrt(8) scaling
      factor (approximately 8 FOMC meetings per year). With n=55 to 58 trades, the 95% confidence interval
      on the Sharpe estimate is approximately plus or minus 0.55, making point estimates indicative rather
      than definitive.
    </div>
    <div class="callout red">
      <strong>Disclaimer.</strong> Same caveats as Strategy A. Additionally, longer holding periods
      introduce more directional drift risk as markets react to data releases and Fed speakers between
      meetings. No stop-loss or adjustment rules are applied.
    </div>
  </div>
</section>

<!-- Section 6: Methodology -->
<section id="s6" style="background:var(--bg2)">
  <div class="section-inner">
    <div class="section-label">06 — Methodology</div>
    <h2>Study construction</h2>
    <table class="method-table">
      <thead><tr><th>Dimension</th><th>Detail</th></tr></thead>
      <tbody>
        <tr><td>Universe</td><td>SPX and TLT 30-day ATM IV (delta=50, days=30 from OptionMetrics vsurfd); CBOE VIX from FRED VIXCLS; SPY ATM straddle prices from OptionMetrics opprcd</td></tr>
        <tr><td>Period</td><td>2018-01-31 to 2024-12-18 ({n_meetings} meetings including 2 emergency, 3 outliers flagged)</td></tr>
        <tr><td>Event window</td><td>T-20 to T+10 trading days relative to FOMC announcement date</td></tr>
        <tr><td>IV baseline</td><td>Mean of T-20 to T-15 (6 trading days) per meeting per instrument, set to 100. Meetings with fewer than 3 valid observations in the baseline window are excluded.</td></tr>
        <tr><td>Decision type</td><td>Hike (actual change greater than 0), Hold (actual change equals 0), Cut (actual change less than 0). Source: Federal Reserve press releases.</td></tr>
        <tr><td>Communication surprise</td><td>Manually classified as Hawkish, Neutral, or Dovish based on dot plot changes, statement language, and same-day market reaction. Source: FOMC minutes, CME FedWatch historical data, Bloomberg terminal records.</td></tr>
        <tr><td>Straddle construction</td><td>ATM call plus ATM put with nearest weekly expiry at least 14 calendar days after the FOMC date. ATM defined as strike closest to spot on entry date. Mid-price = (best bid plus best offer) divided by 2. Falls back to intrinsic value when exit price unavailable.</td></tr>
        <tr><td>P&amp;L</td><td>Gross. Excludes bid-ask spread (approx $10 to $30 per contract round-trip), commissions, and margin costs.</td></tr>
        <tr><td>Sharpe scaling</td><td>sqrt(8) — approximately 8 FOMC meetings per year. Per-trade return = P&amp;L divided by (entry straddle value times 100).</td></tr>
        <tr><td>Outliers</td><td>3 March 2020 (emergency -50bps), 15 March 2020 (emergency -100bps), and 18 March 2020 (degenerate scheduled meeting at ZLB). Included in per-meeting tables with flags but excluded from profile aggregations.</td></tr>
      </tbody>
    </table>
  </div>
</section>

<!-- Section 7: Conclusions -->
<section id="s7">
  <div class="section-inner">
    <div class="section-label">07 — Conclusions</div>
    <h2>Four takeaways from a systematic FOMC options study</h2>
    <div class="callout green">
      <strong>① The pre-meeting IV build-up is real and consistent.</strong> SPX implied vol rises
      systematically in the 5 to 10 trading days before FOMC announcements, normalising to a peak
      at or just before T=0. The pattern holds across hike, hold, and cut meetings, though the
      magnitude varies by rate cycle era.
    </div>
    <div class="callout green">
      <strong>② The IV crush is reliable but not uniform.</strong> Neutral communication meetings
      produce the most predictable crush. Hawkish guidance surprises can sustain or even increase
      vol post-announcement as markets reprice the forward path, limiting short-vol profitability
      in those specific cases.
    </div>
    <div class="callout green">
      <strong>③ Communication surprises matter more than rate decisions.</strong> Within hold meetings,
      the communication surprise layer (hawkish vs. dovish dot plot or statement) drives larger
      divergences in IV behaviour than the rate decision itself. The Fed's forward guidance regime
      has effectively made the rate decision a secondary variable.
    </div>
    <div class="callout green">
      <strong>④ Both straddle strategies show positive expected value gross of costs.</strong> The
      pre-meeting strategy benefits from a concentrated two-day window with a known catalyst. The
      post-announcement strategy benefits from continued mean-reversion but accepts more directional
      and event risk between meetings. Neither strategy is robust after realistic transaction costs
      at retail scale.
    </div>
    <h3>Limitations and what this study cannot claim</h3>
    <p>
      The total sample of {n_meetings} meetings limits statistical precision. Subgroup analyses
      (e.g., hawkish hold meetings, n=8) have insufficient power for robust inference. The 95%
      confidence interval on the Sharpe ratio is approximately plus or minus 0.55 at this sample
      size, meaning the point estimates are directionally informative but not decision-grade.
    </p>
    <p>
      The 2018 to 2021 zero-rate era and the 2022 to 2024 hiking cycle are structurally different
      vol regimes. The pre-meeting IV premium was compressed during the ZIRP era and amplified
      during the hiking cycle. Aggregating across both periods may obscure regime-specific dynamics
      that a practitioner would need to account for.
    </p>
    <div class="callout amber">
      <strong>Regime caveat.</strong> With the Fed's 2025 forward guidance pointing to a prolonged
      plateau, the 2024 cutting cycle pattern may not repeat. Studies using historical FOMC data
      should not be extrapolated into structurally novel rate environments without recalibration.
    </div>
  </div>
</section>

<footer>
  <div class="footer-inner">
    <div>
      <div style="font-family:Fraunces,serif;font-size:1rem;color:var(--bg);margin-bottom:.4rem">The Intrinsic Investor</div>
      <div class="footer-copy">Systematic quant research on institutional data</div>
      <div class="footer-copy" style="margin-top:.25rem">Data: OptionMetrics IvyDB (WRDS), FRED VIXCLS, CME FedWatch</div>
    </div>
    <div class="footer-links">
      <a href="https://www.linkedin.com/in/brian-liew" target="_blank">LinkedIn</a>
      <a href="https://github.com/TheIntrinsicInvestor" target="_blank">GitHub</a>
      <a href="mailto:brianliew99@gmail.com">Email</a>
    </div>
  </div>
</footer>

<script>
// ── Progress bar ────────────────────────────────────────────────────────────
window.addEventListener('scroll', () => {{
  const el  = document.getElementById('progress-bar');
  const pct = window.scrollY / (document.body.scrollHeight - window.innerHeight) * 100;
  el.style.width = Math.min(pct, 100) + '%';
}});

// ── Scroll reveal ───────────────────────────────────────────────────────────
const io = new IntersectionObserver(entries => {{
  entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }});
}}, {{ threshold: 0.07 }});
document.querySelectorAll('section').forEach(s => io.observe(s));

// ── Side nav ─────────────────────────────────────────────────────────────────
function scrollToSection(id) {{ document.getElementById(id).scrollIntoView({{behavior:'smooth'}}); }}
const sections = document.querySelectorAll('section[id]');
const navItems = document.querySelectorAll('.sn-item');
const navIo = new IntersectionObserver(entries => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      navItems.forEach(n => n.classList.remove('active'));
      const idx = Array.from(sections).indexOf(e.target);
      if (navItems[idx]) navItems[idx].classList.add('active');
    }}
  }});
}}, {{ threshold: 0.4 }});
sections.forEach(s => navIo.observe(s));

// ── Chart defaults ──────────────────────────────────────────────────────────
Chart.defaults.font.family = 'Inter, sans-serif';
Chart.defaults.color = '#4a6460';
const GRID = {{ color: 'rgba(15,34,32,.05)', drawBorder: false }};
const TICK = {{ color: '#8aaba6', font: {{ size: 10 }} }};

// ── Chart 1: IV Profile ──────────────────────────────────────────────────────
const profileCtx = document.getElementById('profileChart').getContext('2d');
new Chart(profileCtx, {{
  type: 'line',
  data: {{
    labels: {IV_LABELS_JS},
    datasets: [
      {{ label: 'SPX upper', data: {SPX_UPPER_JS}, fill: '+1', borderWidth: 0, pointRadius: 0, backgroundColor: 'rgba(26,92,82,.12)', tension: 0.4 }},
      {{ label: 'SPX Mean', data: {SPX_MEAN_JS}, borderColor: '#1a5c52', borderWidth: 2, pointRadius: 0, fill: false, tension: 0.4 }},
      {{ label: 'SPX lower', data: {SPX_LOWER_JS}, fill: false, borderWidth: 0, pointRadius: 0, backgroundColor: 'rgba(26,92,82,.12)', tension: 0.4 }},
      {{ label: 'TLT IV', data: {TLT_MEAN_JS}, borderColor: '#2563eb', borderWidth: 1.5, borderDash: [4,3], pointRadius: 0, fill: false, tension: 0.4 }},
      {{ label: 'VIX', data: {VIX_MEAN_JS}, borderColor: '#d97706', borderWidth: 1.5, borderDash: [4,3], pointRadius: 0, fill: false, tension: 0.4 }},
    ]
  }},
  options: {{
    responsive: true, interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ display: false }}, tooltip: {{ filter: i => i.datasetIndex === 1 || i.datasetIndex === 3 || i.datasetIndex === 4 }} }},
    scales: {{
      x: {{ grid: GRID, ticks: {{ ...TICK, callback: (v,i) => {{ const l={IV_LABELS_JS}[i]; return l%5===0?'T'+(l>=0?'+':'')+l:''; }} }} }},
      y: {{ grid: GRID, ticks: TICK, title: {{ display: true, text: 'Normalised IV (baseline=100)', color:'#8aaba6', font:{{size:10}} }} }}
    }}
  }}
}});

// ── Chart 2: By Decision Type ────────────────────────────────────────────────
const decisionCtx = document.getElementById('decisionChart').getContext('2d');
new Chart(decisionCtx, {{
  type: 'line',
  data: {{
    labels: {IV_LABELS_JS},
    datasets: [
      {{ label: 'Hike (n={DEC_HIKE_N})', data: {DEC_HIKE_JS}, borderColor: '#dc2626', borderWidth: 2, pointRadius: 0, fill: false, tension: 0.4 }},
      {{ label: 'Hold (n={DEC_HOLD_N})', data: {DEC_HOLD_JS}, borderColor: '#2563eb', borderWidth: 2, pointRadius: 0, fill: false, tension: 0.4 }},
      {{ label: 'Cut (n={DEC_CUT_N})',  data: {DEC_CUT_JS},  borderColor: '#059669', borderWidth: 2, pointRadius: 0, fill: false, tension: 0.4 }},
    ]
  }},
  options: {{
    responsive: true, interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ grid: GRID, ticks: {{ ...TICK, callback: (v,i) => {{ const l={IV_LABELS_JS}[i]; return l%5===0?'T'+(l>=0?'+':'')+l:''; }} }} }},
      y: {{ grid: GRID, ticks: TICK, title: {{ display: true, text: 'Normalised SPX IV (baseline=100)', color:'#8aaba6', font:{{size:10}} }} }}
    }}
  }}
}});

// ── Chart 3: By Comm Surprise (Hold only) ────────────────────────────────────
const commCtx = document.getElementById('commChart').getContext('2d');
new Chart(commCtx, {{
  type: 'line',
  data: {{
    labels: {IV_LABELS_JS},
    datasets: [
      {{ label: 'Hawkish (n={COMM_HAW_N})', data: {COMM_HAW_JS}, borderColor: '#dc2626', borderWidth: 2, pointRadius: 0, fill: false, tension: 0.4 }},
      {{ label: 'Neutral (n={COMM_NEU_N})', data: {COMM_NEU_JS}, borderColor: '#6b7280', borderWidth: 2, pointRadius: 0, fill: false, tension: 0.4 }},
      {{ label: 'Dovish (n={COMM_DOV_N})',  data: {COMM_DOV_JS}, borderColor: '#059669', borderWidth: 2, pointRadius: 0, fill: false, tension: 0.4 }},
    ]
  }},
  options: {{
    responsive: true, interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ grid: GRID, ticks: {{ ...TICK, callback: (v,i) => {{ const l={IV_LABELS_JS}[i]; return l%5===0?'T'+(l>=0?'+':'')+l:''; }} }} }},
      y: {{ grid: GRID, ticks: TICK, title: {{ display: true, text: 'Normalised SPX IV, Hold meetings (baseline=100)', color:'#8aaba6', font:{{size:10}} }} }}
    }}
  }}
}});

// ── Chart 4: Pre-Meeting P&L ─────────────────────────────────────────────────
const preCtx = document.getElementById('prePnlChart').getContext('2d');
new Chart(preCtx, {{
  type: 'bar',
  data: {{
    labels: {PRE_LABELS_JS},
    datasets: [
      {{ type: 'bar', label: 'P&L per contract ($)', data: {PRE_BARS_JS}, backgroundColor: {PRE_COLORS_JS}, yAxisID: 'y' }},
      {{ type: 'line', label: 'Cumulative P&L', data: {PRE_CUM_JS}, borderColor: '#0f2220', borderWidth: 1.5, pointRadius: 0, fill: false, yAxisID: 'y2' }},
    ]
  }},
  options: {{
    responsive: true, interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ grid: GRID, ticks: {{ ...TICK, maxRotation: 45, font: {{ size: 8 }} }} }},
      y:  {{ grid: GRID, ticks: TICK, title: {{ display: true, text: 'P&L per contract ($)', color:'#8aaba6', font:{{size:10}} }}, position: 'left' }},
      y2: {{ grid: {{ display:false }}, ticks: TICK, title: {{ display: true, text: 'Cumulative ($)', color:'#8aaba6', font:{{size:10}} }}, position: 'right' }},
    }}
  }}
}});

// ── Chart 5: Post-Announcement P&L ───────────────────────────────────────────
const postCtx = document.getElementById('postPnlChart').getContext('2d');
new Chart(postCtx, {{
  type: 'bar',
  data: {{
    labels: {POST_LABELS_JS},
    datasets: [
      {{ type: 'bar', label: 'P&L per contract ($)', data: {POST_BARS_JS}, backgroundColor: {POST_COLORS_JS}, yAxisID: 'y' }},
      {{ type: 'line', label: 'Cumulative P&L', data: {POST_CUM_JS}, borderColor: '#0f2220', borderWidth: 1.5, pointRadius: 0, fill: false, yAxisID: 'y2' }},
    ]
  }},
  options: {{
    responsive: true, interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ grid: GRID, ticks: {{ ...TICK, maxRotation: 45, font: {{ size: 8 }} }} }},
      y:  {{ grid: GRID, ticks: TICK, title: {{ display: true, text: 'P&L per contract ($)', color:'#8aaba6', font:{{size:10}} }}, position: 'left' }},
      y2: {{ grid: {{ display:false }}, ticks: TICK, title: {{ display: true, text: 'Cumulative ($)', color:'#8aaba6', font:{{size:10}} }}, position: 'right' }},
    }}
  }}
}});
</script>
</body>
</html>"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"Written index.html ({len(html):,} chars)")
print(f"\nKey stats embedded in report:")
print(f"  Meetings: {n_meetings}")
print(f"  IV crush: {crush_pct:+.1f}%")
print(f"  Pre-meeting win rate: {pre_win:.0%}")
print(f"  Post-announcement win rate: {post_win:.0%}")
print(f"  Best post exit: {best_exit}")
