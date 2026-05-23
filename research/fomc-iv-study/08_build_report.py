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

# ── Subgroup metrics for strategy analysis sections ───────────────────────────
pre_df["fomc_date"]  = pd.to_datetime(pre_df["fomc_date"])
post_df["fomc_date"] = pd.to_datetime(post_df["fomc_date"])

def _sg(df):
    if len(df) == 0:
        return dict(n=0, win_rate=0.0, avg_pnl=0.0, sharpe=None)
    n   = len(df)
    wr  = float((df["pnl_per_contract"] > 0).mean())
    avg = float(df["pnl_per_contract"].mean())
    ret = df["return_pct"]
    sh  = ret.mean() / ret.std() * np.sqrt(8) if ret.std() > 0 else float("nan")
    return dict(n=n, win_rate=wr, avg_pnl=avg, sharpe=None if np.isnan(sh) else float(sh))

def _fmt_sh(m):
    return f"{m['sharpe']:.2f}" if m["sharpe"] is not None else "--"

_pre_hold = pre_df[pre_df["decision_type"] == "Hold"]
_pre_hike = pre_df[pre_df["decision_type"] == "Hike"]
_pre_cut  = pre_df[pre_df["decision_type"] == "Cut"]

sg_pre_hike    = _sg(_pre_hike)
sg_pre_cut     = _sg(_pre_cut)
sg_pre_neutral = _sg(_pre_hold[_pre_hold["comm_surprise"] == "Neutral"])
sg_pre_hawkish = _sg(_pre_hold[_pre_hold["comm_surprise"] == "Hawkish"])
sg_pre_dovish  = _sg(_pre_hold[_pre_hold["comm_surprise"] == "Dovish"])

_post_hike = post_df[post_df["decision_type"] == "Hike"]
_post_hold = post_df[post_df["decision_type"] == "Hold"]
_post_cut  = post_df[post_df["decision_type"] == "Cut"]

sg_post_hike = _sg(_post_hike)
sg_post_hold = _sg(_post_hold)
sg_post_cut  = _sg(_post_cut)

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
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,400;0,600;1,400;1,600&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
:root {{
  --bg:#f7f4ec; --bg2:#f0ece2; --bg3:#e8e3d8; --card:#fff;
  --ink:#0f2220; --muted:#4a6460; --hint:#8aa49e;
  --border:#e2ddd0; --accent:#1a5c52; --accent2:#144a42;
  --green:#0E9F6E; --green2:#059669; --green-bg:#ecfdf5; --green-border:#a7f3d0;
  --red:#E02424; --red2:#dc2626; --red-bg:#fef2f2; --red-border:#fca5a5;
  --blue:#1e40af; --blue2:#2563eb; --blue-bg:#eff6ff; --blue-border:#bfdbfe;
  --amber:#E3A008; --amber-bg:#fffbeb; --amber-border:#fcd34d;
  --purple:#7E3AF2; --purple-bg:#f5f3ff; --purple-border:#c4b5fd;
  --font:'Inter',sans-serif; --serif:'Fraunces',serif; --mono:'JetBrains Mono',monospace;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{background:var(--bg);color:var(--ink);font-family:var(--font);font-size:16px;line-height:1.7}}
body::after{{content:'';position:fixed;inset:0;pointer-events:none;z-index:9999;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='250' height='250'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.80' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='250' height='250' filter='url(%23n)' opacity='0.07'/%3E%3C/svg%3E");
  mix-blend-mode:multiply;opacity:0.5}}
#progress-bar{{position:fixed;top:0;left:0;height:2px;width:0%;
  background:linear-gradient(90deg,#1a5c52,#2d9d8f);z-index:9998;transition:width .1s linear}}
nav{{position:sticky;top:0;z-index:100;height:62px;display:flex;align-items:center;
  justify-content:space-between;padding:0 2rem;
  background:rgba(247,244,236,.92);backdrop-filter:blur(12px);
  -webkit-backdrop-filter:blur(12px);border-bottom:1px solid var(--border);transition:box-shadow .3s}}
nav.scrolled{{box-shadow:0 1px 24px rgba(15,34,32,.06)}}
.nav-logo{{font-family:var(--serif);font-weight:600;font-size:1.1rem;color:var(--ink);letter-spacing:-.01em;text-decoration:none}}
.nav-links{{display:flex;gap:1.75rem;list-style:none}}
.nav-links a{{color:var(--muted);text-decoration:none;font-size:.9rem;font-weight:500;
  position:relative;padding-bottom:2px;transition:color .2s}}
.nav-links a:hover{{color:var(--ink)}}
.nav-links a::after{{content:'';position:absolute;bottom:-1px;left:0;right:0;height:1px;
  background:var(--accent);transform:scaleX(0);transform-origin:left;
  transition:transform .25s cubic-bezier(.4,0,.2,1)}}
.nav-links a:hover::after{{transform:scaleX(1)}}
.hero{{background:var(--ink);padding:5rem 2rem 4rem;position:relative;overflow:hidden}}
.hero::before{{content:'';position:absolute;inset:0;pointer-events:none;
  background-image:repeating-linear-gradient(-55deg,transparent,transparent 40px,rgba(255,255,255,.013) 40px,rgba(255,255,255,.013) 41px)}}
.hero-inner{{max-width:860px;margin:0 auto;position:relative}}
.hero-tag{{display:inline-block;font-family:var(--mono);font-size:.72rem;color:var(--accent);
  letter-spacing:.08em;text-transform:uppercase;border:1px solid rgba(26,92,82,.4);
  padding:.25rem .75rem;border-radius:2px;margin-bottom:1.5rem;animation:fadeUp .6s ease both}}
.hero h1{{font-family:var(--serif);font-size:clamp(1.9rem,4.5vw,3.2rem);font-weight:600;
  color:#fff;line-height:1.2;letter-spacing:-.02em;margin-bottom:1.25rem;
  animation:fadeUp .6s .1s ease both}}
.hero h1 em{{font-style:italic;color:var(--accent)}}
.hero-sub{{font-size:1rem;color:rgba(255,255,255,.65);max-width:620px;line-height:1.7;
  margin-bottom:2rem;animation:fadeUp .6s .2s ease both}}
.hero-meta{{display:flex;flex-wrap:wrap;gap:2rem;font-family:var(--mono);font-size:.75rem;
  color:rgba(255,255,255,.5);border-top:1px solid rgba(255,255,255,.1);
  padding-top:1.5rem;animation:fadeUp .6s .3s ease both}}
.hero-meta-item strong{{display:block;color:rgba(255,255,255,.85);font-size:.85rem;margin-bottom:.15rem}}
.gh-btn{{display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);
  font-size:.68rem;color:rgba(255,255,255,.5);text-decoration:none;
  border:1px solid rgba(255,255,255,.2);padding:3px 9px;border-radius:3px;
  transition:all .2s;letter-spacing:.02em;align-self:center}}
.gh-btn:hover{{color:#fff;border-color:rgba(255,255,255,.5);background:rgba(255,255,255,.08)}}
@keyframes fadeUp{{from{{opacity:0;transform:translateY(18px)}}to{{opacity:1;transform:translateY(0)}}}}
.kpi-strip{{background:var(--card);border-bottom:1px solid var(--border);padding:2rem}}
.kpi-grid{{max-width:900px;margin:0 auto;display:grid;grid-template-columns:repeat(4,1fr)}}
.kpi-cell{{padding:1.5rem;border-right:1px solid var(--border)}}
.kpi-cell:last-child{{border-right:none}}
.kpi-label{{font-size:.72rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
  color:var(--hint);margin-bottom:.5rem}}
.kpi-value{{font-family:var(--mono);font-size:1.9rem;font-weight:500;color:var(--ink);
  line-height:1;margin-bottom:.4rem}}
.kpi-value.green{{color:var(--green2)}}
.kpi-value.red{{color:var(--red2)}}
.kpi-value.blue{{color:var(--blue2)}}
.kpi-sub{{font-size:.78rem;color:var(--muted)}}
.container{{max-width:860px;margin:0 auto;padding:0 2rem}}
.section{{opacity:0;transform:translateY(16px);
  transition:opacity .55s ease,transform .55s ease;
  padding:4.5rem 0;border-bottom:1px solid var(--border)}}
.section.visible{{opacity:1;transform:none}}
.section:last-of-type{{border-bottom:none}}
.section-label{{display:flex;align-items:center;gap:.6rem;margin-bottom:1rem}}
.section-counter{{font-family:var(--mono);font-size:.72rem;color:var(--hint);letter-spacing:.04em}}
.section-label span:last-child{{font-size:.72rem;font-weight:600;letter-spacing:.08em;
  text-transform:uppercase;color:var(--hint)}}
h2{{font-family:var(--serif);font-size:clamp(1.5rem,3vw,2.1rem);font-weight:600;
  color:var(--ink);line-height:1.25;letter-spacing:-.02em;margin-bottom:1.25rem}}
h2 em{{font-style:italic;color:var(--accent)}}
h3{{font-family:var(--serif);font-size:1.15rem;font-weight:600;color:var(--ink);margin:2rem 0 .75rem}}
p{{color:var(--muted);line-height:1.75;margin-bottom:1rem;text-align:justify;hyphens:none;word-break:normal}}
p:last-child{{margin-bottom:0}}
.callout{{display:flex;gap:1rem;padding:1.25rem 1.5rem;border-radius:4px;
  margin:1.5rem 0;border-left:3px solid;font-size:.9rem;color:var(--ink);line-height:1.6}}
.callout.green{{background:var(--green-bg);border-color:var(--green2)}}
.callout.amber{{background:var(--amber-bg);border-color:var(--amber)}}
.callout.red{{background:var(--red-bg);border-color:var(--red2)}}
.callout.blue{{background:var(--blue-bg);border-color:var(--blue2)}}
.callout.purple{{background:var(--purple-bg);border-color:var(--purple)}}
.callout strong{{font-weight:600}}
.highlight-box{{background:var(--ink);border-radius:4px;padding:2rem;margin:1.5rem 0;display:grid;grid-template-columns:repeat(3,1fr)}}
.highlight-box > div{{padding:0 1.5rem;border-right:1px solid rgba(255,255,255,.1)}}
.highlight-box > div:first-child{{padding-left:0}}
.highlight-box > div:last-child{{border-right:none;padding-right:0}}
.hl-grid{{display:grid;grid-template-columns:repeat(3,1fr)}}
.hl-cell{{padding:0 1.5rem;border-right:1px solid rgba(255,255,255,.1)}}
.hl-cell:first-child{{padding-left:0}}
.hl-cell:last-child{{border-right:none;padding-right:0}}
.hl-label{{font-size:.7rem;font-weight:500;color:rgba(255,255,255,.35);text-transform:uppercase;
  letter-spacing:.1em;margin-bottom:.5rem}}
.hl-value{{font-family:var(--serif);font-style:italic;font-size:1.75rem;color:#5ab5a5;line-height:1.1}}
.hl-sub{{font-size:.75rem;color:rgba(255,255,255,.3);margin-top:.3rem}}
.hb-val{{font-family:var(--serif);font-style:italic;font-size:1.75rem;color:#5ab5a5;line-height:1.1}}
.hb-label{{font-size:.7rem;font-weight:500;color:rgba(255,255,255,.35);text-transform:uppercase;
  letter-spacing:.1em;margin-top:.35rem}}
.chart-box{{background:var(--bg2);border:1px solid var(--border);
  border-radius:4px;padding:1.5rem;margin:1.5rem 0}}
.chart-title{{font-size:.85rem;font-weight:600;color:var(--ink);
  margin-bottom:1rem;letter-spacing:.02em}}
.chart-legend{{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px}}
.legend-item{{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--muted)}}
.legend-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0;display:inline-block}}
.legend-line{{width:16px;height:2px;flex-shrink:0;display:inline-block;vertical-align:middle}}
.data-table{{width:100%;border-collapse:collapse;font-size:.83rem;margin:1rem 0}}
.data-table th{{background:var(--ink);color:var(--bg);padding:.55rem .8rem;text-align:left;font-weight:500;font-size:.72rem;letter-spacing:.04em}}
.data-table td{{padding:.5rem .8rem;border-bottom:1px solid rgba(15,34,32,.06);color:var(--muted)}}
.data-table tr:hover td{{background:rgba(15,34,32,.02)}}
.data-table .top-row td{{background:#d1fae5!important;color:var(--ink)!important;font-weight:500}}
.heatmap-table{{width:100%;border-collapse:collapse;font-size:.75rem}}
.heatmap-table th{{background:var(--ink);color:var(--bg);padding:.4rem .5rem;font-weight:500;font-size:.65rem;text-align:center;letter-spacing:.03em}}
.heatmap-table td{{padding:.35rem .45rem;border-bottom:1px solid rgba(15,34,32,.05);text-align:center}}
.method-table{{width:100%;border-collapse:collapse;font-size:.85rem;margin:1rem 0}}
.method-table th{{background:var(--ink);color:var(--bg);padding:.6rem 1rem;font-weight:500;font-size:.75rem;text-align:left}}
.method-table td{{padding:.55rem 1rem;border-bottom:1px solid rgba(15,34,32,.08);color:var(--muted);vertical-align:top}}
.method-table td:first-child{{font-weight:500;color:var(--ink);white-space:nowrap;width:35%}}
#side-nav{{position:fixed;right:0;top:50%;transform:translateY(-50%);
  z-index:50;display:flex;flex-direction:column;gap:2px;padding:10px 6px}}
#side-nav a{{display:flex;align-items:center;justify-content:flex-end;gap:7px;
  text-decoration:none;padding:5px 8px;border-radius:4px;transition:background .2s}}
#side-nav a:hover{{background:rgba(26,92,82,.07)}}
.sn-label{{font-size:.67rem;font-weight:500;color:var(--hint);white-space:nowrap;
  letter-spacing:.02em;font-family:var(--font);transition:color .2s;text-align:right}}
.sn-dot{{width:5px;height:5px;border-radius:50%;background:var(--border);
  flex-shrink:0;transition:all .2s}}
#side-nav a.active .sn-label{{color:var(--accent);font-weight:600}}
#side-nav a.active .sn-dot{{background:var(--accent);transform:scale(1.5)}}
#side-nav a:hover .sn-label{{color:var(--ink)}}
#side-nav a:hover .sn-dot{{background:var(--muted)}}
footer{{background:var(--ink);color:rgba(255,255,255,.6);padding:3rem 2rem}}
.footer-inner{{max-width:860px;margin:0 auto;display:flex;
  justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem}}
.footer-name{{font-family:var(--serif);font-weight:600;font-size:1rem;color:rgba(255,255,255,.9)}}
.footer-right{{font-size:.8rem;text-align:right}}
.footer-right a{{color:rgba(255,255,255,.5);text-decoration:none;margin-left:1.2rem}}
.footer-right a:hover{{color:rgba(255,255,255,.85)}}
@media(max-width:860px){{
  #side-nav{{display:none}}
  .kpi-grid{{grid-template-columns:repeat(2,1fr)}}
  .footer-inner{{flex-direction:column;text-align:center}}
  .footer-right{{text-align:center}}
}}
@media(max-width:560px){{
  .kpi-cell{{border-right:none;border-bottom:1px solid var(--border)}}
  .hl-grid{{grid-template-columns:1fr;gap:1rem}}
  .hl-cell{{border-right:none;padding:0;border-bottom:1px solid rgba(255,255,255,.08);padding-bottom:1rem}}
  .hl-cell:last-child{{border-bottom:none}}
}}
@media(prefers-reduced-motion:reduce){{
  *,*::before,*::after{{animation-duration:.01ms!important;transition-duration:.01ms!important}}
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
<div id="side-nav" aria-label="Page sections">
  <a href="#s1"><span class="sn-label">Study Design</span><div class="sn-dot"></div></a>
  <a href="#s2"><span class="sn-label">IV Profile</span><div class="sn-dot"></div></a>
  <a href="#s3"><span class="sn-label">Surprise Analysis</span><div class="sn-dot"></div></a>
  <a href="#s4"><span class="sn-label">Strategy A</span><div class="sn-dot"></div></a>
  <a href="#s5"><span class="sn-label">Strategy B</span><div class="sn-dot"></div></a>
  <a href="#s6"><span class="sn-label">Methodology</span><div class="sn-dot"></div></a>
  <a href="#s7"><span class="sn-label">Conclusions</span><div class="sn-dot"></div></a>
</div>

<!-- Hero -->
<header class="hero">
  <div class="hero-inner">
    <div class="hero-tag">FOMC Event Study</div>
    <h1>The FOMC Vol Crush: <em>Implied Volatility Dynamics Around Federal Reserve Decisions</em></h1>
    <p class="hero-sub">
      How SPX, TLT, and VIX implied volatility behaves before and after FOMC announcements,
      whether a pre-meeting IV build-up is reliably exploitable, and what communication
      surprises reveal about the limits of forward guidance.
    </p>
    <div class="hero-meta">
      <div class="hero-meta-item"><strong>Author</strong>Brian Liew, BSc Accounting and Finance, LSE</div>
      <div class="hero-meta-item"><strong>Published</strong>May 2026</div>
      <div class="hero-meta-item"><strong>Period</strong>2018 to 2025, n={n_meetings} meetings</div>
      <div class="hero-meta-item"><strong>Data</strong>OptionMetrics, FRED, CME FedWatch</div>
      <a href="https://github.com/TheIntrinsicInvestor/Backtesting" target="_blank" rel="noopener" class="gh-btn">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
        GitHub Code
      </a>
    </div>
  </div>
</header>

<!-- KPI Strip -->
<div class="kpi-strip">
  <div class="kpi-grid">
  <div class="kpi-cell">
    <div class="kpi-label">Meetings Analysed</div>
    <div class="kpi-value blue">{n_meetings}</div>
    <div class="kpi-sub">2018 to 2025, scheduled and emergency</div>
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
</div>

<!-- Section 1: Study Design -->
<section class="section" id="s1">
  <div class="container">
    <div class="section-label"><span class="section-counter">01</span><span>Study Design</span></div>
    <h2>Why FOMC meetings create a predictable options market cycle</h2>
    <p>
      Federal Reserve rate decisions are the single most anticipated scheduled macro events in global
      markets. The options market prices this anticipated uncertainty as a risk premium in the days
      before each meeting, then rapidly resets once the uncertainty resolves. This study asks whether
      that pattern is systematic, how it varies by decision type and communication surprise, and
      whether it can be profitably exploited via short straddle strategies on SPY.
    </p>
    <p>
      We track three implied volatility instruments across {n_meetings} FOMC meetings from 2018 to 2025:
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
<section class="section" id="s2" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="section-counter">02</span><span>IV Event Profile</span></div>
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
<section class="section" id="s3">
  <div class="container">
    <div class="section-label"><span class="section-counter">03</span><span>Surprise Analysis</span></div>
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
<section class="section" id="s4" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="section-counter">04</span><span>Strategy A: Pre-Meeting Straddle Sell</span></div>
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
    <h3>What these results mean</h3>
    <p style="text-align:justify;hyphens:none">
      Aggregate results do not support Strategy A as a systematic trade. The {pre_win:.0%} win rate
      is statistically indistinguishable from random, and the annualised Sharpe of {pre_sharpe:.2f}
      is negative. The strategy loses more on its bad trades than it earns on its good ones, driven
      by a small number of large losses around meetings that delivered unexpected policy shifts or
      aggressive communication tone changes.
    </p>
    <p style="text-align:justify;hyphens:none">
      Disaggregating by meeting type reveals where the edge concentrates and where it collapses.
      Hold meetings with Neutral communication ({sg_pre_neutral['n']} trades) are the only
      consistently profitable cohort: {sg_pre_neutral['win_rate']:.0%} win rate, avg
      ${sg_pre_neutral['avg_pnl']:+.0f} per contract, Sharpe {_fmt_sh(sg_pre_neutral)}.
      The logic holds in this regime: when the Fed holds rates with no surprises in tone or
      forward guidance, implied vol collapses after the announcement and the short straddle
      captures that decay cleanly. Hold meetings with Dovish communication
      ({sg_pre_dovish['n']} trades) invert this result entirely: {sg_pre_dovish['win_rate']:.0%}
      win rate and avg ${sg_pre_dovish['avg_pnl']:+.0f} per contract. A dovish pivot (rate cuts
      signalled, guidance softened) expands market uncertainty rather than resolving it. Hike
      meetings ({sg_pre_hike['n']} trades) average ${sg_pre_hike['avg_pnl']:+.0f}, as the market
      frequently moved sharply through the strike during the 2022 to 2023 hiking cycle.
    </p>
    <div class="highlight-box">
      <div>
        <div class="hb-val">{sg_pre_neutral['win_rate']:.0%}</div>
        <div class="hb-label">Win rate, Hold/Neutral<br>({sg_pre_neutral['n']} trades)</div>
      </div>
      <div>
        <div class="hb-val">${sg_pre_dovish['avg_pnl']:+.0f}</div>
        <div class="hb-label">Avg P&amp;L, Hold/Dovish<br>({sg_pre_dovish['n']} trades)</div>
      </div>
      <div>
        <div class="hb-val">${sg_pre_hike['avg_pnl']:+.0f}</div>
        <div class="hb-label">Avg P&amp;L, Hike meetings<br>({sg_pre_hike['n']} trades)</div>
      </div>
    </div>
    <p style="text-align:justify;hyphens:none">
      Implementation viability is limited even for the Hold/Neutral cohort. Communication tone is
      confirmed only after the FOMC statement is released, so pre-classifying a meeting as Neutral
      is impossible in practice. A systematic strategy cannot select only these meetings in advance.
      The +${sg_pre_neutral['avg_pnl']:.0f} gross average on Neutral/Hold meetings is also largely
      consumed by round-trip bid-ask costs of $10 to $30 per contract. Strategy A does not offer a
      robust, repeatable edge after realistic transaction costs.
    </p>
    <div class="callout red">
      <strong>Important disclaimer.</strong> All P&amp;L is gross. Actual realised returns will be lower
      after bid-ask spread ($10 to $30 per contract round-trip), commissions, and margin costs for short
      options. The strategy carries unbounded gamma risk if the underlying gaps through the strike.
      No delta hedging is applied. These results are a backtested approximation, not a live trading record.
    </div>
  </div>
</section>

<!-- Section 5: Strategy B -->
<section class="section" id="s5">
  <div class="container">
    <div class="section-label"><span class="section-counter">05</span><span>Strategy B: Post-Announcement Straddle Sell</span></div>
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
    <h3>What these results mean</h3>
    <p style="text-align:justify;hyphens:none">
      The T+5 aggregate looks constructive at {post_win:.0%} win rate and a positive Sharpe, but this
      headline number conceals a sharply bifurcated picture driven almost entirely by the rate cycle.
      Hike meetings ({sg_post_hike['n']} trades) account for nearly all the strategy's edge:
      {sg_post_hike['win_rate']:.0%} win rate, avg ${sg_post_hike['avg_pnl']:+.0f} per contract,
      Sharpe {_fmt_sh(sg_post_hike)}. Strip out hike meetings and the picture deteriorates rapidly.
      Hold meetings ({sg_post_hold['n']} trades) produce only avg ${sg_post_hold['avg_pnl']:+.0f}
      (Sharpe {_fmt_sh(sg_post_hold)}), and Cut meetings ({sg_post_cut['n']} trades) average
      ${sg_post_cut['avg_pnl']:+.0f}. The strategy is not a universal post-FOMC vol trade; it is
      a post-hike vol trade measured across a broader sample.
    </p>
    <div class="highlight-box">
      <div>
        <div class="hb-val">{sg_post_hike['win_rate']:.0%}</div>
        <div class="hb-label">Win rate, Hike meetings<br>({sg_post_hike['n']} trades)</div>
      </div>
      <div>
        <div class="hb-val">${sg_post_hike['avg_pnl']:+.0f}</div>
        <div class="hb-label">Avg P&amp;L, Hike meetings</div>
      </div>
      <div>
        <div class="hb-val">${sg_post_hold['avg_pnl']:+.0f}</div>
        <div class="hb-label">Avg P&amp;L, Hold meetings<br>({sg_post_hold['n']} trades)</div>
      </div>
    </div>
    <p style="text-align:justify;hyphens:none">
      The mechanism for the hike-cycle edge is intuitive. During the 2022 to 2023 hiking campaign,
      each meeting resolved acute uncertainty about the terminal rate. After a hike was delivered,
      implied vol deflated steadily over the following days as markets reprocessed the Fed's
      trajectory. The T+1 straddle entry captures the peak of post-hike IV, and the T+5 exit
      harvests most of the mean-reversion before other macro events introduce noise.
    </p>
    <p style="text-align:justify;hyphens:none">
      Implementation viability is cycle-dependent. The 15 hike meetings (2022 to 2023) drove the
      majority of this strategy's cumulative P&amp;L and produced a commercially attractive Sharpe.
      As of 2025, the Fed is in a hold and gradual-cut stance, which means the operative regime
      is closer to the Hold meeting subgroup (near breakeven) than the all-meetings aggregate. A
      disciplined implementation would condition the strategy on the rate cycle: apply it actively
      during confirmed hiking campaigns and stand aside during holds and cuts.
    </p>
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
<section class="section" id="s6" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="section-counter">06</span><span>Methodology</span></div>
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
<section class="section" id="s7">
  <div class="container">
    <div class="section-label"><span class="section-counter">07</span><span>Conclusions</span></div>
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
    <div class="footer-name">The Intrinsic Investor</div>
    <div class="footer-right">
      <span style="color:rgba(255,255,255,.35)">&copy; 2026 Brian Liew</span>
      <a href="https://www.linkedin.com/in/brian-liew" target="_blank">LinkedIn</a>
      <a href="https://github.com/TheIntrinsicInvestor" target="_blank">GitHub</a>
      <a href="mailto:brianliew99@gmail.com">Email</a>
    </div>
  </div>
</footer>

<script>
// ── Progress bar + nav.scrolled ─────────────────────────────────────────────
const _nav = document.querySelector('nav');
window.addEventListener('scroll', () => {{
  const el  = document.getElementById('progress-bar');
  const pct = window.scrollY / (document.body.scrollHeight - window.innerHeight) * 100;
  el.style.width = Math.min(pct, 100) + '%';
  _nav.classList.toggle('scrolled', window.scrollY > 40);
}}, {{ passive: true }});

// ── Scroll reveal ───────────────────────────────────────────────────────────
const io = new IntersectionObserver(entries => {{
  entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }});
}}, {{ threshold: 0.07 }});
document.querySelectorAll('.section').forEach(s => io.observe(s));

// ── Side nav active state ────────────────────────────────────────────────────
const sections = document.querySelectorAll('.section[id]');
const navItems = document.querySelectorAll('#side-nav a');
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
