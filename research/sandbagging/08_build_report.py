"""
08_build_report.py  —  Generate research/sandbagging/index.html
Reads data/analysis.json and writes all figures as JS constants.
Prose cites constants only. Keep WIP/unlisted until visual QA passes.
"""

import json
from pathlib import Path

with open("data/analysis.json") as f:
    d = json.load(f)

kpi   = d["kpis"]
meta  = d["meta"]
wdist = d["walkdown_dist"]
wc    = d["walk_curves"]
xt    = d["crosstab"]
cp    = d["cohort_profile"]
strat = d["strategy"]

# ── Verdict logic ─────────────────────────────────────────────────────────────
rxn_gen = strat["reaction"]["genuine_beat"]
rxn_mfg = strat["reaction"]["manufactured_beat"]
dft_gen = strat["drift"]["genuine_beat"]
dft_mfg = strat["drift"]["manufactured_beat"]
ls_rxn  = strat["reaction"]["ls_spread_pct"]
ls_dft  = strat["drift"]["ls_spread_pct"]
dft_sh  = (strat["drift"]["ls_sharpe"] or {}).get("sharpe")
rxn_sh  = (strat["reaction"]["ls_sharpe"] or {}).get("sharpe")
dft_t   = abs(dft_mfg["t_stat"] or 0)
n_ann   = (strat["drift"]["ls_sharpe"] or {}).get("n_years", 0)

verdict_viable = bool(ls_dft and ls_dft > 0 and dft_t > 1.65 and dft_sh and dft_sh > 0.3)
dft_sh_str  = f"{dft_sh:.2f}"  if dft_sh  is not None else "n/a"
rxn_sh_str  = f"{rxn_sh:.2f}" if rxn_sh  is not None else "n/a"
ls_dft_str  = f"{ls_dft:+.2f}" if ls_dft is not None else "n/a"
ls_rxn_str  = f"{ls_rxn:+.2f}" if ls_rxn is not None else "n/a"
dft_t_str   = f"{dft_mfg['t_stat']:.2f}" if dft_mfg['t_stat'] else "n/a"

if verdict_viable:
    verdict_class  = "amber"
    verdict_head   = "Conditional signal: practical execution is the barrier"
    verdict_body   = (
        f"The {ls_dft_str}&#160;pp 60-day drift spread (Sharpe {dft_sh_str} over {n_ann} years) "
        f"is statistically present. Three practical hurdles likely erode it in live trading: "
        f"(1) shorting manufactured beats requires locating borrow on large-cap names around "
        f"earnings, often at elevated fees; (2) the strategy competes with post-earnings "
        f"drift traders already positioned in these names; (3) running "
        f"~{meta['n_manufactured']} short and ~{meta['n_genuine']} long positions per year "
        f"generates meaningful transaction costs over a 59-trading-day holding period. "
        f"A paper-trading exercise is warranted before committing capital."
    )
else:
    verdict_class = "red"
    sig_note = "statistically weak, " if dft_t < 1.65 else ""
    verdict_head  = "Not viable in practice"
    verdict_body  = (
        f"The L/S drift spread of {ls_dft_str}&#160;pp over 59 trading days "
        f"({sig_note}t&#160;=&#160;{dft_t_str}) is insufficient to overcome real-world frictions. "
        f"Short-selling manufactured beats requires borrow at elevated fees around earnings, "
        f"these are high-profile names that attract competition from event-driven funds, and "
        f"the drift window spans nearly three months of carrying costs. "
        f"The reaction spread of {ls_rxn_str}&#160;pp over two days is similarly unactionable "
        f"after bid-ask and market-impact costs on "
        f"~{meta['n_manufactured'] + meta['n_genuine']:,} events per year. "
        f"Annual Sharpe&#160;=&#160;{dft_sh_str} (drift) over {n_ann} years. "
        f"<strong>This report documents the phenomenon. It does not constitute a tradeable strategy recommendation.</strong>"
    )

# ── Formatters ────────────────────────────────────────────────────────────────
def fp(v, d=1, sign=True):
    if v is None: return "n/a"
    return f"{'+'if sign and v>0 else ''}{v:.{d}f}%"

def fn(v):
    if v is None: return "n/a"
    return f"{int(v):,}"

def tstr(t):
    if t is None: return "n/a"
    stars = "***" if abs(t)>2.576 else ("**" if abs(t)>1.96 else ("*" if abs(t)>1.645 else ""))
    return f"{t:.2f}{(' '+stars) if stars else ''}"

def ja(lst):
    parts = []
    for v in lst:
        if v is None: parts.append("null")
        elif isinstance(v, bool): parts.append("true" if v else "false")
        else: parts.append(str(v))
    return "[" + ",".join(parts) + "]"

def js(lst):
    return "[" + ",".join(f'"{v}"' for v in lst) + "]"

# ── Cross-tab HTML ────────────────────────────────────────────────────────────
bin_lab = {"down": "Walk-Down &lt;&#8722;2%", "flat": "Flat &#177;2%", "up": "Walk-Up &gt;+2%"}
xt_rows = ""
for i, b in enumerate(xt["bins"]):
    cells = "".join(
        f'<td class="mono" style="{"color:var(--red2);font-weight:600" if xt["classifications"][j]=="manufactured_beat" else ""}">'
        f'{fn(xt["counts"][i][j])}</td>'
        for j in range(len(xt["classifications"]))
    )
    xt_rows += (f'<tr><td style="color:var(--muted)">{bin_lab[b]}</td>{cells}'
                f'<td class="mono" style="color:var(--hint)">{fn(xt["bin_totals"][i])} ({xt["bin_pcts"][i]}%)</td></tr>\n')

xtab_html = f"""<div style="overflow-x:auto">
<table class="data-table" style="max-width:680px;margin:1.5rem auto">
  <thead><tr>
    <th>Walk-Down Bin</th><th>Genuine Beat</th>
    <th style="background:var(--red2);color:#fff">Manufactured Beat</th>
    <th>Miss</th><th>Total</th>
  </tr></thead>
  <tbody>{xt_rows}</tbody>
</table></div>"""

# ── Sector tilt HTML ──────────────────────────────────────────────────────────
sec_rows = ""
secs = list(zip(cp["sector_tilt"]["sectors"],
                cp["sector_tilt"]["manufactured_pct"],
                cp["sector_tilt"]["genuine_pct"],
                cp["sector_tilt"]["universe_pct"]))
for s, m, g, u in sorted(secs, key=lambda x: -x[1]):
    diff = m - u
    col  = "var(--red2)" if diff > 2 else ("var(--green2)" if diff < -2 else "var(--hint)")
    sec_rows += (f'<tr><td>{s}</td>'
                 f'<td class="mono" style="color:var(--red2)">{m:.1f}%</td>'
                 f'<td class="mono">{g:.1f}%</td>'
                 f'<td class="mono" style="color:var(--hint)">{u:.1f}%</td>'
                 f'<td class="mono" style="color:{col}">{diff:+.1f}&#160;pp</td></tr>\n')

sector_html = f"""<div style="overflow-x:auto">
<table class="data-table" style="max-width:640px;margin:1.5rem auto">
  <thead><tr>
    <th>Sector</th>
    <th style="background:var(--red2);color:#fff">Mfg Beat %</th>
    <th>Genuine Beat %</th><th>Universe %</th><th>Mfg vs Universe</th>
  </tr></thead>
  <tbody>{sec_rows}</tbody>
</table></div>"""

# ── Size profile HTML ─────────────────────────────────────────────────────────
sp = cp["size_profile"]
size_rows = "".join(
    f'<tr><td>{b}</td>'
    f'<td class="mono" style="color:var(--red2)">{sp["manufactured_pct"][i]:.1f}%</td>'
    f'<td class="mono">{sp["genuine_pct"][i]:.1f}%</td>'
    f'<td class="mono" style="color:var(--hint)">{sp["miss_pct"][i]:.1f}%</td></tr>\n'
    for i, b in enumerate(sp["buckets"])
)
size_html = f"""<div style="overflow-x:auto">
<table class="data-table" style="max-width:500px;margin:1.5rem auto">
  <thead><tr>
    <th>Market Cap</th>
    <th style="background:var(--red2);color:#fff">Mfg Beat %</th>
    <th>Genuine Beat %</th><th>Miss %</th>
  </tr></thead>
  <tbody>{size_rows}</tbody>
</table></div>"""

# ── Strategy tables HTML ──────────────────────────────────────────────────────
def strat_row_html(label, s, negate_mean=False):
    m = s["mean_pct"]
    if negate_mean and m is not None: m = -m
    return (f'<tr><td>{label}</td><td class="mono">{fn(s["n"])}</td>'
            f'<td class="mono">{fp(m, 2)}</td>'
            f'<td class="mono">{fp(s["median_pct"], 2)}</td>'
            f'<td class="mono">{fp(s["hit_rate_pct"], 1, sign=False)}</td>'
            f'<td class="mono">{tstr(s["t_stat"])}</td></tr>\n')

def strat_table_html(key):
    s      = strat[key]
    spread = s["ls_spread_pct"]
    sh     = (s["ls_sharpe"] or {}).get("sharpe")
    sh_str = f"{sh:.2f}" if sh is not None else "n/a"
    rows   = (strat_row_html("Long&#160;(Genuine Beat)", s["genuine_beat"])
            + strat_row_html("Short&#160;(Manufactured Beat)", s["manufactured_beat"])
            + f'<tr style="border-top:2px solid var(--border)">'
              f'<td><strong>L/S Spread</strong></td><td></td>'
              f'<td class="mono"><strong>{fp(spread, 2)}</strong></td>'
              f'<td></td><td></td>'
              f'<td class="mono">Sharpe&#160;{sh_str}</td></tr>\n')
    return f"""<div style="overflow-x:auto">
<table class="data-table" style="margin:1.5rem auto">
  <thead><tr>
    <th>Cohort</th><th>n</th>
    <th>Mean CAR</th><th>Median CAR</th><th>Hit Rate</th><th>t-stat</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table></div>"""

rxn_table_html = strat_table_html("reaction")
dft_table_html = strat_table_html("drift")

# ── Method table HTML ─────────────────────────────────────────────────────────
method_rows = [
    ("Universe",          "S&amp;P 500, point-in-time membership, 2015&#8211;2025"),
    ("EPS series",        "Annual (fpi&#160;=&#160;1) from IBES"),
    ("Estimate source",   "IBES Detail (individual analyst estimates, <code>ibes.det_epsus</code>)"),
    ("Walk-down window",  "T&#8722;270 to T&#8722;2 trading days before announcement"),
    ("Original consensus","Mean of active estimates, T&#8722;280 to T&#8722;260"),
    ("Final consensus",   "Mean of active estimates, T&#8722;7 to T&#8722;2"),
    ("Active estimate",   "Most-recent estimate per analyst, issued within prior 365 days"),
    ("Analyst floor",     "3 or more active analysts at both original and final snapshot"),
    ("Min EPS base",      "&#124;orig_consensus&#124; &ge; $0.10 (avoids % distortion on tiny bases)"),
    ("Classification",    "Genuine: actual &gt; orig. Manufactured: orig &ge; actual &gt; final. Miss: actual &le; final"),
    ("Returns",           "Price-only from CRSP dsf_v2 (dlyprc, adjusted close); dividends excluded"),
    ("Benchmark",         "SPY (permno 84398) over identical calendar windows"),
    ("Censoring",         "Events where T+60 falls after 2025-12-31 excluded from drift statistics"),
    ("Data cutoffs",      "IBES through 2026-02-19, CRSP v2 through 2025-12-31, yfinance n/a"),
]
method_html = "".join(f'<tr><td><strong>{k}</strong></td><td style="font-size:.9rem">{v}</td></tr>'
                      for k, v in method_rows)

# ── JS data constants ─────────────────────────────────────────────────────────
cov          = cp["analyst_coverage"]
m_an         = cov["manufactured"]["median"]
g_an         = cov["genuine"]["median"]
near5        = meta.get("near_miss_5pct_of_mfg", "n/a")
near10       = meta.get("near_miss_10pct_of_mfg", "n/a")

WALK_OFFSETS = ja(wc["offsets"])
WALK_MFG     = ja(wc["manufactured"])
WALK_GEN     = ja(wc["genuine"])
DIST_BINS    = js(wdist["bins"])
DIST_TOTAL   = ja(wdist["counts_total"])
DIST_MFG     = ja(wdist["counts_mfg"])
DIST_GEN     = ja(wdist["counts_gen"])
DIST_MISS    = ja(wdist["counts_miss"])

RXN_MEANS    = ja([rxn_gen["mean_pct"], rxn_mfg["mean_pct"], strat["reaction"]["miss"]["mean_pct"]])
DFT_MEANS    = ja([dft_gen["mean_pct"], dft_mfg["mean_pct"], strat["drift"]["miss"]["mean_pct"]])

# ── Build HTML ────────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-HT9VG5C62E"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-HT9VG5C62E');</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Walk-Down: How the S&amp;P 500 Manufactures Earnings Beats</title>
<meta name="description" content="S&amp;P 500 firms selectively walk analyst estimates down before earnings so they can beat a lowered bar. 17.5% of annual beats are manufactured. New quant research.">
<meta property="og:title" content="The Walk-Down: How the S&amp;P 500 Manufactures Earnings Beats">
<meta property="og:description" content="17.5% of annual beats are manufactured by walking down analyst estimates. Quant research on S&amp;P 500 earnings sandbagging, 2015&#8211;2025.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,400;0,600;1,400&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{{
  --bg:#f7f4ec;--bg2:#f0ece2;--bg3:#e8e3d8;
  --ink:#0f2220;--muted:#4a6460;--hint:#8aa49e;--border:#e2ddd0;
  --accent:#1a5c52;--accent2:#144a42;
  --green:#0E9F6E;--green2:#059669;--green-bg:#ecfdf5;--green-border:#a7f3d0;
  --red:#E02424;--red2:#dc2626;--red-bg:#fef2f2;--red-border:#fca5a5;
  --blue:#1e40af;--blue2:#2563eb;--blue-bg:#eff6ff;--blue-border:#bfdbfe;
  --amber:#E3A008;--amber-bg:#fffbeb;--amber-border:#fcd34d;
  --font:'Inter',sans-serif;--serif:'Fraunces',serif;--mono:'JetBrains Mono',monospace;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{background:var(--bg);color:var(--ink);font-family:var(--font);font-size:1rem;line-height:1.7}}
a{{color:var(--accent);text-decoration:none}}
a:hover{{text-decoration:underline}}
code{{font-family:var(--mono);font-size:.85em;background:var(--bg3);padding:1px 4px;border-radius:3px}}
nav{{position:fixed;top:0;left:0;right:0;z-index:100;background:var(--ink);padding:.75rem 2rem;display:flex;align-items:center;justify-content:space-between}}
nav .logo{{color:#fff;font-family:var(--serif);font-size:1.05rem;font-weight:600}}
nav .nav-links{{display:flex;gap:1.5rem;list-style:none}}
nav .nav-links a{{color:rgba(255,255,255,.8);font-size:.875rem;position:relative}}
nav .nav-links a::after{{content:'';position:absolute;bottom:-2px;left:0;width:100%;height:1px;background:#fff;transform:scaleX(0);transform-origin:right;transition:transform .25s cubic-bezier(.4,0,.2,1)}}
nav .nav-links a:hover{{color:#fff;text-decoration:none}}
nav .nav-links a:hover::after{{transform:scaleX(1);transform-origin:left}}
#progress-bar{{position:fixed;top:48px;left:0;height:2px;background:var(--accent);width:0;z-index:99;transition:width .1s}}
#side-nav{{position:fixed;right:1.5rem;top:50%;transform:translateY(-50%);display:flex;flex-direction:column;gap:.6rem;z-index:90}}
#side-nav a{{display:flex;align-items:center;gap:.5rem;justify-content:flex-end;color:var(--hint);font-size:.68rem;font-family:var(--mono);text-transform:uppercase;letter-spacing:.08em;transition:color .2s;text-decoration:none}}
#side-nav a:hover,#side-nav a.active{{color:var(--ink)}}
#side-nav .sn-dot{{width:6px;height:6px;border-radius:50%;background:var(--hint);transition:all .2s;flex-shrink:0}}
#side-nav a.active .sn-dot{{width:8px;height:8px;background:var(--accent)}}
@media(max-width:980px){{#side-nav{{display:none}}}}
.hero{{background:var(--ink);color:#fff;padding:7rem 2rem 4rem;margin-top:48px;text-align:center}}
.hero-tag{{font-family:var(--mono);font-size:.7rem;text-transform:uppercase;letter-spacing:.15em;color:rgba(255,255,255,.55);margin-bottom:1rem}}
.hero h1{{font-family:var(--serif);font-size:clamp(1.7rem,4vw,2.8rem);font-weight:600;line-height:1.18;max-width:760px;margin:0 auto .75rem;animation:fadeUp .6s .1s both}}
.hero .subtitle{{color:rgba(255,255,255,.7);font-size:1.05rem;max-width:600px;margin:0 auto 1.5rem;animation:fadeUp .6s .2s both}}
.hero-meta{{display:flex;flex-wrap:wrap;gap:.75rem 1.5rem;justify-content:center;font-family:var(--mono);font-size:.72rem;color:rgba(255,255,255,.5)}}
.hero-meta span strong{{color:rgba(255,255,255,.8)}}
.hero-meta a{{color:rgba(255,255,255,.6);border:1px solid rgba(255,255,255,.2);padding:.3rem .8rem;border-radius:4px;font-size:.72rem;transition:all .2s}}
.hero-meta a:hover{{background:rgba(255,255,255,.1);text-decoration:none}}
.kpi-strip{{background:var(--ink);border-top:1px solid rgba(255,255,255,.1)}}
.kpi-grid{{max-width:900px;margin:0 auto;display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid rgba(255,255,255,.1)}}
.kpi-card{{padding:1.25rem 1rem;border-right:1px solid rgba(255,255,255,.1);text-align:center}}
.kpi-card:last-child{{border-right:none}}
.kpi-label{{font-family:var(--mono);font-size:.62rem;text-transform:uppercase;letter-spacing:.1em;color:rgba(255,255,255,.45);margin-bottom:.35rem}}
.kpi-value{{font-family:var(--serif);font-size:1.8rem;font-weight:600;color:#fff}}
.kpi-sub{{font-size:.75rem;color:rgba(255,255,255,.4);margin-top:.15rem}}
@media(max-width:600px){{.kpi-grid{{grid-template-columns:repeat(2,1fr)}}}}
.section{{padding:4rem 2rem;opacity:0;transform:translateY(16px);transition:opacity .5s,transform .5s}}
.section.visible{{opacity:1;transform:none}}
.container{{max-width:900px;margin:0 auto}}
.section-label{{font-family:var(--mono);font-size:.68rem;text-transform:uppercase;letter-spacing:.12em;color:var(--hint);margin-bottom:.6rem;display:flex;align-items:center;gap:.5rem}}
.section-label::after{{content:'';flex:1;height:1px;background:var(--border)}}
h2{{font-family:var(--serif);font-size:clamp(1.35rem,2.5vw,1.85rem);font-weight:600;margin-bottom:1rem;line-height:1.25}}
h2 em{{font-style:italic;color:var(--accent)}}
h3{{font-family:var(--serif);font-size:1.15rem;font-weight:600;margin:1.5rem 0 .5rem}}
p{{text-align:justify;hyphens:none;color:var(--muted);margin-bottom:1rem}}
.chart-box{{background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:1.5rem;margin:1.5rem 0}}
.chart-box canvas{{max-height:340px}}
.chart-caption{{font-family:var(--mono);font-size:.7rem;color:var(--hint);text-align:center;margin-top:.6rem}}
.callout{{border-radius:4px;padding:.9rem 1.1rem;margin:1rem 0;border-left:3px solid}}
.callout.green{{background:var(--green-bg);border-color:var(--green2)}}
.callout.red{{background:var(--red-bg);border-color:var(--red2)}}
.callout.amber{{background:var(--amber-bg);border-color:var(--amber)}}
.callout.blue{{background:var(--blue-bg);border-color:var(--blue2)}}
.callout p{{color:var(--ink);margin:0;font-size:.92rem;hyphens:none}}
.callout strong{{color:var(--ink)}}
.highlight-box{{background:var(--ink);color:#fff;border-radius:6px;padding:1.25rem 1.5rem;display:grid;grid-template-columns:repeat(3,1fr);gap:1px;margin:1.5rem 0;text-align:center}}
.highlight-box .hb-item{{padding:.75rem .5rem}}
.highlight-box .hb-val{{font-family:var(--serif);font-size:1.6rem;font-weight:600;color:#fff}}
.highlight-box .hb-label{{font-family:var(--mono);font-size:.62rem;text-transform:uppercase;letter-spacing:.08em;color:rgba(255,255,255,.45);margin-top:.2rem}}
.data-table{{width:100%;border-collapse:collapse;font-size:.88rem}}
.data-table th{{background:var(--ink);color:#fff;font-family:var(--mono);font-size:.65rem;text-transform:uppercase;letter-spacing:.06em;padding:.55rem .75rem;text-align:left}}
.data-table td{{padding:.5rem .75rem;border-bottom:1px solid var(--border)}}
.data-table tr:hover td{{background:var(--bg2)}}
.data-table td:first-child{{color:var(--ink)}}
.mono{{font-family:var(--mono);font-size:.86em}}
.top-row{{background:var(--green-bg)}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin:1.5rem 0}}
@media(max-width:640px){{.two-col{{grid-template-columns:1fr}}.highlight-box{{grid-template-columns:1fr}}}}
footer{{background:var(--ink);color:rgba(255,255,255,.4);text-align:center;padding:2rem;font-size:.82rem}}
footer a{{color:rgba(255,255,255,.5)}}
@keyframes fadeUp{{from{{opacity:0;transform:translateY(18px)}}to{{opacity:1;transform:translateY(0)}}}}
</style>
</head>
<body>

<nav>
  <a class="logo" href="/">The Intrinsic Investor</a>
  <ul class="nav-links">
    <li><a href="/">Home</a></li>
    <li><a href="/research/">Research</a></li>
    <li><a href="/about/">About</a></li>
  </ul>
</nav>

<div id="progress-bar"></div>

<div id="side-nav"></div>

<header class="hero">
  <div class="hero-tag">Quantitative Research &middot; Earnings &amp; Estimates</div>
  <h1>The Walk-Down: How the S&amp;P&#160;500 <em>Manufactures</em> Earnings Beats</h1>
  <p class="subtitle">Annual EPS estimates are selectively guided lower before earnings so firms
    can report a beat against a lowered bar. 17.5&#160;% of annual beats in the S&amp;P&#160;500
    are manufactured this way.</p>
  <div class="hero-meta">
    <span><strong>Universe</strong> S&amp;P 500</span>
    <span><strong>Period</strong> 2015&#8211;2025</span>
    <span><strong>Events</strong> {fn(meta['n_included'])} included</span>
    <span><strong>Data</strong> IBES &#43; CRSP v2</span>
    <span><strong>Published</strong> June 2026</span>
    <a href="https://github.com/TheIntrinsicInvestor/Backtesting/tree/main/research/sandbagging"
       target="_blank" rel="noopener">GitHub Code</a>
  </div>
</header>

<div class="kpi-strip">
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">Manufactured Beat Rate</div>
      <div class="kpi-value">{kpi['manufactured_beat_rate_pct']:.1f}%</div>
      <div class="kpi-sub">of all annual beats</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Manufactured Beats</div>
      <div class="kpi-value">{fn(kpi['n_manufactured'])}</div>
      <div class="kpi-sub">events, 2015&#8211;2025</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Median Walk-Down</div>
      <div class="kpi-value">{kpi['median_walkdown_mfg_pct']:.1f}%</div>
      <div class="kpi-sub">manufactured cohort</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">L/S Drift Spread</div>
      <div class="kpi-value">{fp(ls_dft, 2)}</div>
      <div class="kpi-sub">genuine minus manufactured, T+1 to T+60</div>
    </div>
  </div>
</div>

<!-- ── s1: Study Design ─────────────────────────────────────────────────────── -->
<section class="section" id="s1">
  <div class="container">
    <div class="section-label"><span class="mono">01</span> Study Design</div>
    <h2>What We Are Measuring, and the <em>Paradox</em></h2>
    <p>Earnings sandbagging is the practice where management, through guidance and investor-relations
      channels, encourages analysts to lower their annual EPS estimates before the earnings release,
      making it easier to report a nominal beat. This study tests whether that pattern is detectable
      at scale across the S&amp;P&#160;500 using point-in-time (PIT) analyst estimate reconstruction.</p>
    <p>We measure the <strong>walk-down</strong> as the percentage change in the mean consensus
      from T&#8722;270 (nine months before announcement) to T&#8722;2 (two days before). A
      negative value means the consensus fell over that window. Using IBES individual analyst
      estimates, we reconstruct the daily PIT consensus for each firm-year event between 2015
      and 2025.</p>

    <div class="callout amber">
      <p><strong>The paradox.</strong> Across all {fn(meta['n_included'])} included events,
        the <em>median</em> walk-down is {fp(meta['median_walk_all_pct'], 1)}.
        The typical S&amp;P&#160;500 firm does not walk estimates down at all, it walks them up.
        The walk-down is not a universal phenomenon. It is <strong>selective</strong>, deployed
        specifically on the firms that would otherwise miss.</p>
    </div>

    <h3>Classification</h3>
    <p>Each event is classified into one of three groups based on the relationship between
      the actual EPS, the original consensus, and the final consensus:</p>
    <div class="two-col" style="margin:1rem 0">
      <div class="callout green" style="margin:0">
        <p><strong>Genuine Beat ({fn(meta['n_genuine'])} events)</strong>
          Actual EPS exceeded the original consensus. The firm would have beaten regardless of
          any walk-down.</p>
      </div>
      <div class="callout red" style="margin:0">
        <p><strong>Manufactured Beat ({fn(meta['n_manufactured'])} events)</strong>
          Actual EPS missed the original consensus but beat the final (walked-down) consensus.
          The beat was manufactured by walking the bar down.</p>
      </div>
    </div>
    <div class="callout" style="background:var(--bg2);border-left:3px solid var(--hint);margin:0 0 1rem">
      <p><strong>Miss ({fn(meta['n_miss'])} events)</strong>
        Actual EPS fell below even the walked-down final consensus.</p>
    </div>
    <p>Quality filters exclude events with non-positive consensus, sign flips between original
      and final, fewer than 3 active analysts at either snapshot, or an absolute original
      consensus below $0.10. Of {fn(meta['n_events_total'])} raw event-year combinations,
      {fn(meta['n_included'])} pass all filters and form the study universe.</p>
  </div>
</section>

<!-- ── s2: The Selective Walk-Down ────────────────────────────────────────────── -->
<section class="section" id="s2" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="mono">02</span> The Selective Walk-Down</div>
    <h2>The Walk-Down Is Deployed <em>Selectively</em></h2>
    <p>The chart below shows the distribution of walk-down percentages across all included events.
      The overall distribution skews positive (more walk-ups than walk-downs), but the manufactured
      beats (red) are concentrated entirely in the flat and down bins. This is the core finding:
      the walk-down is not a market-wide phenomenon but a targeted tool used on specific firms.</p>

    <div class="chart-box">
      <canvas id="distChart" height="260"></canvas>
      <div class="chart-caption">Walk-down % for all {fn(meta['n_included'])} included events.
        Red = manufactured beats. Down (&lt;&#8722;2%): {xt['bin_pcts'][0]}% of events.
        Flat (&#177;2%): {xt['bin_pcts'][1]}%. Up (&gt;+2%): {xt['bin_pcts'][2]}%.</div>
    </div>

    <h3>The Hero Chart: Two Cohort Walk Curves</h3>
    <p>For each included event, the daily PIT consensus is normalised to its T&#8722;270 base
      (= 100). The chart below averages this normalised curve across the manufactured and genuine
      cohorts. The manufactured cohort (red) walks steadily down over nine months while the genuine
      cohort (green) drifts upward, reflecting natural upward earnings revisions for firms on track
      to beat. The two curves start at the same baseline and diverge, confirming that the
      walk-down is a distinct phenomenon, not random noise.</p>

    <div class="chart-box">
      <canvas id="walkChart" height="320"></canvas>
      <div class="chart-caption">Average normalised consensus curve by cohort (T&#8722;270 base = 100).
        Manufactured beats (red) walk down to a median of {meta['median_walk_mfg_pct']:.1f}%
        of the original consensus. Genuine beats (green) drift to a median of
        {meta['median_walk_gen_pct']:.1f}%.</div>
    </div>

    <h3>The Cross-Tab Clincher</h3>
    <p>If sandbagging were random or universal, we would expect manufactured beats to appear
      across all walk-down bins. The cross-tab below shows they do not. Of
      {fn(meta['n_manufactured'])} manufactured beats, {fn(meta['n_mfg_down'])} came from
      firms that walked estimates down, {fn(meta['n_mfg_flat'])} from firms that held estimates
      flat, and <strong>{fn(meta['n_mfg_up'])} came from firms that walked estimates up</strong>.
      Zero manufactured beats emerge from the up-walking bin, which confirms that the manufactured
      beat is definitionally tied to the walk-down.</p>

    {xtab_html}

    <div class="callout red">
      <p><strong>Zero manufactured beats from up-walking firms.</strong>
        Of {fn(meta['n_manufactured'])} manufactured beats, {fn(meta['n_mfg_down'])} come from
        firms that walked estimates down more than 2%, and {fn(meta['n_mfg_flat'])} from firms
        that held estimates flat. Not a single manufactured beat occurs at a firm where
        the consensus rose over the nine-month window.</p>
    </div>
  </div>
</section>

<!-- ── s3: Who Gets Walked Down ────────────────────────────────────────────── -->
<section class="section" id="s3">
  <div class="container">
    <div class="section-label"><span class="mono">03</span> Who Gets Walked Down</div>
    <h2>Sandbagging Happens at the <em>Most-Covered</em> Names</h2>
    <p>A naive prior might expect sandbagging to occur at smaller, less-scrutinised firms where
      management has more influence over the analyst consensus. The data shows the opposite.
      Manufactured beats are concentrated at <em>well-covered</em>, large-cap names where
      the analyst community is densest and the incentive to produce a clean beat is highest.</p>

    <div class="highlight-box">
      <div class="hb-item">
        <div class="hb-val">{m_an:.0f}</div>
        <div class="hb-label">Median analysts, manufactured cohort</div>
      </div>
      <div class="hb-item">
        <div class="hb-val">{g_an:.0f}</div>
        <div class="hb-label">Median analysts, genuine cohort</div>
      </div>
      <div class="hb-item">
        <div class="hb-val">{near5:.0f}%</div>
        <div class="hb-label">Mfg beats within 5% of original consensus</div>
      </div>
    </div>

    <p>The manufactured cohort has a median of {m_an:.0f} active analysts versus {g_an:.0f}
      for genuine beats. High analyst coverage means the consensus is harder to move, which
      makes the selective walk-down more conspicuous: management must guide many analysts
      to trim their estimates, not just one. That {near5:.0f}% of manufactured beats were
      within 5% of beating the original consensus underscores that the walk-down is often
      just enough, not a wholesale reset.</p>

    <h3>Sector Concentration</h3>
    <p>The table below shows the share of each sector in the manufactured beat cohort versus
      its universe share. A positive difference (red) indicates over-representation. The
      sectors with the largest over-representation tend to be those with the heaviest
      institutional investor scrutiny and the most visible earnings expectations.</p>

    {sector_html}

    <h3>Size Profile</h3>
    <p>Manufactured beats are disproportionately large-cap events. The table below shows
      the market cap distribution of each cohort at the time of announcement.</p>

    {size_html}
  </div>
</section>

<!-- ── s4: Strategy ────────────────────────────────────────────────────────── -->
<section class="section" id="s4" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="mono">04</span> Does It Pay?</div>
    <h2>Announcement Reaction and <em>Post-Print Drift</em></h2>
    <p>If manufactured beats are qualitatively different from genuine beats, market prices should
      reflect that. We test two windows: (1) the <em>announcement reaction</em>
      (CAR T&#8722;1 to T+1) to see whether the market immediately discounts the manufactured
      quality, and (2) <em>post-print drift</em> (CAR T+1 to T+60) to test whether
      recognition is delayed. All returns are market-adjusted vs SPY over identical calendar
      windows. A long-genuine/short-manufactured strategy is evaluated on both.</p>
    <p>Returns are price-only (dividends excluded). Events where the T+60 window extends beyond
      2025-12-31 are censored and excluded from drift statistics
      ({fn(meta['n_censored_drift'])} events removed). See Methodology for details.</p>

    <h3>Announcement Reaction: The Market Is Initially Fooled</h3>

    <div class="highlight-box">
      <div class="hb-item">
        <div class="hb-val">{fp(rxn_gen['mean_pct'], 2)}</div>
        <div class="hb-label">Mean CAR (T&#8722;1 to T+1), Genuine Beats</div>
      </div>
      <div class="hb-item">
        <div class="hb-val">{fp(rxn_mfg['mean_pct'], 2)}</div>
        <div class="hb-label">Mean CAR (T&#8722;1 to T+1), Manufactured Beats</div>
      </div>
      <div class="hb-item">
        <div class="hb-val">{fp(ls_rxn, 2)}</div>
        <div class="hb-label">L/S Spread (Genuine minus Manufactured)</div>
      </div>
    </div>

    <div class="chart-box">
      <canvas id="rxnChart" height="220"></canvas>
      <div class="chart-caption">Mean market-adjusted return (T&#8722;1 to T+1) by cohort.
        t-stat for manufactured: {tstr(rxn_mfg['t_stat'])} (vs zero).</div>
    </div>

    {rxn_table_html}

    <div class="callout amber">
      <p><strong>The market does not see through manufactured beats at announcement.</strong>
        Manufactured beats generate a mean CAR of {fp(rxn_mfg['mean_pct'], 2)} over the
        T&#8722;1 to T+1 window, modestly <em>above</em> the {fp(rxn_gen['mean_pct'], 2)}
        earned by genuine beats. The L/S reaction spread of {fp(ls_rxn, 2)} is small and
        (t&#160;=&#160;{tstr(rxn_mfg['t_stat'])}) not statistically significant.
        The market celebrates the nominal beat without immediately discounting its
        manufactured nature. This rules out a reaction-window strategy.</p>
    </div>

    <h3>Post-Print Drift: The Reality Reasserts Itself</h3>

    <div class="highlight-box">
      <div class="hb-item">
        <div class="hb-val">{fp(dft_gen['mean_pct'], 2)}</div>
        <div class="hb-label">Mean CAR (T+1 to T+60), Genuine Beats</div>
      </div>
      <div class="hb-item">
        <div class="hb-val">{fp(dft_mfg['mean_pct'], 2)}</div>
        <div class="hb-label">Mean CAR (T+1 to T+60), Manufactured Beats</div>
      </div>
      <div class="hb-item">
        <div class="hb-val">{fp(ls_dft, 2)}</div>
        <div class="hb-label">L/S Spread (Genuine minus Manufactured)</div>
      </div>
    </div>

    <div class="chart-box">
      <canvas id="dftChart" height="220"></canvas>
      <div class="chart-caption">Mean market-adjusted return (T+1 to T+60) by cohort.
        Non-censored events only ({fn(meta['n_included'] - meta['n_censored_drift'])} events).
        t-stat for manufactured: {tstr(dft_mfg['t_stat'])} (vs zero).</div>
    </div>

    {dft_table_html}

    <h3>What These Results Mean</h3>
    <p>The market initially over-celebrates manufactured beats: the announcement reaction is
      not muted but slightly <em>elevated</em> ({fp(rxn_mfg['mean_pct'], 2)} vs
      {fp(rxn_gen['mean_pct'], 2)} for genuine beats). Recognition is delayed, not immediate.
      Over the subsequent 59 trading days, manufactured beats reverse ({fp(dft_mfg['mean_pct'], 2)})
      while genuine beats hold positive ground ({fp(dft_gen['mean_pct'], 2)}), producing a
      drift L/S spread of {fp(ls_dft, 2)} (annual Sharpe {dft_sh_str} over {n_ann} years).
      Any viable strategy must enter after the announcement, not before.</p>

    <div class="callout {verdict_class}">
      <p><strong>{verdict_head}.</strong> {verdict_body}</p>
    </div>

    <div class="callout red">
      <p><strong>Disclaimer.</strong> This report is for educational and informational purposes
        only. Past performance is not indicative of future results. Nothing here constitutes
        investment advice or a recommendation to buy or sell any security. Any strategy
        described here has not been live-traded and faces implementation costs not captured
        in paper returns.</p>
    </div>
  </div>
</section>

<!-- ── s5: Methodology ────────────────────────────────────────────────────────── -->
<section class="section" id="s5">
  <div class="container">
    <div class="section-label"><span class="mono">05</span> Methodology</div>
    <h2>Data and <em>Construction Details</em></h2>
    <p>Key parameters and data choices are summarised below. The PIT reconstruction uses
      individual analyst estimates from IBES Detail rather than the pre-aggregated
      consensus, which avoids look-ahead bias from revision-timing differences in
      the summary table.</p>
    <div style="overflow-x:auto">
      <table class="data-table" style="max-width:720px;margin:1.5rem auto">
        <thead><tr><th>Parameter</th><th>Value</th></tr></thead>
        <tbody>{method_html}</tbody>
      </table>
    </div>
  </div>
</section>

<!-- ── s6: Conclusions ────────────────────────────────────────────────────────── -->
<section class="section" id="s6" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="mono">06</span> Conclusions</div>
    <h2>Four Key <em>Findings</em></h2>

    <div class="callout green">
      <p><strong>The walk-down is real, but selective.</strong> 17.5% of annual S&amp;P&#160;500
        beats between 2015 and 2025 are manufactured by walking analyst estimates down over the
        nine months before announcement. The median S&amp;P&#160;500 firm does not walk estimates
        down. The phenomenon is selective, concentrated at firms that would otherwise miss.</p>
    </div>

    <div class="callout red">
      <p><strong>Zero manufactured beats from up-walking firms.</strong> Every one of the
        {fn(meta['n_manufactured'])} manufactured beats comes from a firm in the down or flat
        walk-down bin. Not one manufactured beat occurs at a firm where the consensus rose.
        This is a structural feature of the classification, not a coincidence.</p>
    </div>

    <div class="callout amber">
      <p><strong>Sandbagging concentrates at the most-covered names.</strong> The manufactured
        cohort has a median of {m_an:.0f} active analysts vs {g_an:.0f} for genuine beats.
        Large-cap, heavily-covered names are the most active sandbagging sites, consistent
        with the hypothesis that the incentive to produce a clean institutional beat is
        highest where the audience is largest.</p>
    </div>

    <div class="callout blue">
      <p><strong>Statistical limits.</strong> The study uses price-only returns (dividends
        excluded), which slightly understates long-run performance for high-dividend names.
        The T+60 drift window censors {fn(meta['n_censored_drift'])} events where CRSP data
        ends before the exit date. Annual Sharpe estimates use {n_ann} year-observations
        and should be treated as indicative only. All t-statistics are one-sample tests
        against zero with no multiple-comparison correction.</p>
    </div>
  </div>
</section>

<footer>
  <p>&#169; 2026 The Intrinsic Investor &middot; Brian Liew, BSc Accounting &amp; Finance (LSE) &middot;
    <a href="/research/">Research</a> &middot; <a href="/about/">About</a></p>
</footer>

<script>
const WALK_OFFSETS = {WALK_OFFSETS};
const WALK_MFG     = {WALK_MFG};
const WALK_GEN     = {WALK_GEN};
const DIST_BINS    = {DIST_BINS};
const DIST_TOTAL   = {DIST_TOTAL};
const DIST_MFG     = {DIST_MFG};
const DIST_GEN     = {DIST_GEN};
const DIST_MISS    = {DIST_MISS};
const RXN_MEANS    = {RXN_MEANS};
const DFT_MEANS    = {DFT_MEANS};
const COHORT_LABELS = ['Genuine Beat','Manufactured Beat','Miss'];
const COHORT_COLORS = ['rgba(26,92,82,.8)','rgba(220,38,38,.8)','rgba(138,164,158,.7)'];

Chart.defaults.font.family = 'Inter, sans-serif';
Chart.defaults.color = '#4a6460';
const GRID = {{ color: 'rgba(15,34,32,.05)', drawBorder: false }};
const TICK = {{ color: '#8aaba6', font: {{ size: 10 }} }};

// Distribution chart
new Chart(document.getElementById('distChart'), {{
  type: 'bar',
  data: {{
    labels: DIST_BINS,
    datasets: [
      {{ label: 'Genuine Beat', data: DIST_GEN,  backgroundColor: 'rgba(26,92,82,.55)',  borderWidth: 0, borderRadius: 2, stack: 'a' }},
      {{ label: 'Manufactured Beat', data: DIST_MFG,  backgroundColor: 'rgba(220,38,38,.75)', borderWidth: 0, borderRadius: 0, stack: 'a' }},
      {{ label: 'Miss',  data: DIST_MISS, backgroundColor: 'rgba(138,164,158,.45)', borderWidth: 0, borderRadius: 0, stack: 'a' }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: true, position: 'top', labels: {{ font: {{ family: 'Inter', size: 10 }}, boxWidth: 14 }} }},
      tooltip: {{ callbacks: {{ title: ctx => 'Walk-down ' + ctx[0].label + '%', label: ctx => ctx.dataset.label + ': ' + ctx.raw }} }}
    }},
    scales: {{
      x: {{ stacked: true, ticks: {{ ...TICK, maxRotation: 0, autoSkip: true, maxTicksLimit: 14 }}, grid: {{ display: false }} }},
      y: {{ stacked: true, ticks: TICK, grid: GRID, title: {{ display: true, text: 'Number of events', color: '#4a6460', font: {{ size: 10 }} }} }}
    }}
  }}
}});

// Walk curves chart
new Chart(document.getElementById('walkChart'), {{
  type: 'line',
  data: {{
    labels: WALK_OFFSETS,
    datasets: [
      {{ label: 'Manufactured Beat', data: WALK_MFG, borderColor: '#dc2626', backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.3, spanGaps: true }},
      {{ label: 'Genuine Beat',      data: WALK_GEN, borderColor: '#1a5c52', backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.3, spanGaps: true }},
      {{ label: 'Baseline',          data: WALK_OFFSETS.map(() => 100), borderColor: 'rgba(138,164,158,.5)', borderWidth: 1, borderDash: [4,3], pointRadius: 0 }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ display: true, position: 'top', labels: {{ font: {{ family: 'Inter', size: 10 }}, boxWidth: 14,
        filter: item => item.text !== 'Baseline' }} }},
      tooltip: {{ callbacks: {{ label: ctx => ctx.dataset.label + ': ' + (ctx.raw != null ? ctx.raw.toFixed(2) : 'n/a') }} }}
    }},
    scales: {{
      x: {{ ticks: {{ ...TICK, maxRotation: 0, autoSkip: true, maxTicksLimit: 10,
           callback: v => v }}, grid: GRID,
           title: {{ display: true, text: 'Days before announcement (T=0)', color: '#4a6460', font: {{ size: 10 }} }} }},
      y: {{ ticks: {{ ...TICK, callback: v => v.toFixed(1) }}, grid: GRID,
           title: {{ display: true, text: 'Consensus as % of T−270 base', color: '#4a6460', font: {{ size: 10 }} }} }}
    }}
  }}
}});

// Reaction CAR chart
new Chart(document.getElementById('rxnChart'), {{
  type: 'bar',
  data: {{
    labels: COHORT_LABELS,
    datasets: [{{ label: 'Mean CAR (T−1 to T+1)', data: RXN_MEANS,
      backgroundColor: COHORT_COLORS, borderWidth: 0, borderRadius: 3 }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => 'Mean CAR: ' + (ctx.raw != null ? ctx.raw.toFixed(2) + '%' : 'n/a') }} }}
    }},
    scales: {{
      x: {{ ticks: TICK, grid: {{ display: false }} }},
      y: {{ ticks: {{ ...TICK, callback: v => v + '%' }}, grid: GRID,
           title: {{ display: true, text: 'Mean market-adjusted return (%)', color: '#4a6460', font: {{ size: 10 }} }} }}
    }}
  }}
}});

// Drift CAR chart
new Chart(document.getElementById('dftChart'), {{
  type: 'bar',
  data: {{
    labels: COHORT_LABELS,
    datasets: [{{ label: 'Mean CAR (T+1 to T+60)', data: DFT_MEANS,
      backgroundColor: COHORT_COLORS, borderWidth: 0, borderRadius: 3 }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => 'Mean CAR: ' + (ctx.raw != null ? ctx.raw.toFixed(2) + '%' : 'n/a') }} }}
    }},
    scales: {{
      x: {{ ticks: TICK, grid: {{ display: false }} }},
      y: {{ ticks: {{ ...TICK, callback: v => v + '%' }}, grid: GRID,
           title: {{ display: true, text: 'Mean market-adjusted return (%)', color: '#4a6460', font: {{ size: 10 }} }} }}
    }}
  }}
}});

// Progress bar
window.addEventListener('scroll', () => {{
  const p = window.scrollY / (document.body.scrollHeight - window.innerHeight) * 100;
  document.getElementById('progress-bar').style.width = Math.min(p, 100) + '%';
}});

// Section fade-in
const io = new IntersectionObserver(entries => {{
  entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }});
}}, {{ threshold: 0.07 }});
document.querySelectorAll('.section').forEach(s => io.observe(s));

// Side nav
const NAV_LABELS = ['Study Design','Selective Walk-Down','Who Gets Walked Down','Does It Pay?','Methodology','Conclusions'];
const sideNav    = document.getElementById('side-nav');
const sections   = document.querySelectorAll('.section[id]');
sections.forEach((s, i) => {{
  const a = document.createElement('a');
  a.href  = '#' + s.id;
  a.innerHTML = '<span class="sn-label">' + NAV_LABELS[i] + '</span><span class="sn-dot"></span>';
  sideNav.appendChild(a);
}});
const navLinks = sideNav.querySelectorAll('a');
const obs = new IntersectionObserver(entries => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      navLinks.forEach(a => a.classList.remove('active'));
      const idx = Array.from(sections).indexOf(e.target);
      if (idx >= 0) navLinks[idx].classList.add('active');
    }}
  }});
}}, {{ threshold: 0.4 }});
sections.forEach(s => obs.observe(s));
</script>
</body>
</html>"""

out = Path("index.html")
out.write_text(html, encoding="utf-8")
print(f"Written: {out}  ({out.stat().st_size:,} bytes)")
print("\nNOTE: report is WIP/unlisted.")
print("  - Do NOT add to homepage or research listing until visual QA passes.")
print("  - Preview with: .\\serve.ps1")
print(f"\nKey figures baked into HTML:")
print(f"  Manufactured beat rate : {kpi['manufactured_beat_rate_pct']:.1f}%")
print(f"  n manufactured         : {kpi['n_manufactured']:,}")
print(f"  Median walk-down (mfg) : {kpi['median_walkdown_mfg_pct']:.1f}%")
print(f"  L/S reaction spread    : {fp(kpi['ls_reaction_spread_pct'], 2)}")
print(f"  L/S drift spread       : {fp(ls_dft, 2)}")
print(f"  Verdict class          : {verdict_class}")
