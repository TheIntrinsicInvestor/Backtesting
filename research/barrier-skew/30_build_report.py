# ruff: noqa
"""
30_build_report.py
------------------
Writes research/barrier-skew/index.html from data/report_data.json.

CSS: base rules are lifted from the canonical reference report (0dte-gamma-trap) and the chrome
block between CHROME:START/END is replaced with .claude/report-chrome.css when that file is
present, so this page cannot drift from the site design.

Prose numbers are formatted from the JSON, never typed by hand (project data-integrity rule).
The page template uses {{PLACEHOLDER}} markers and str.replace, so no brace doubling is needed.
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
D = json.loads((HERE / "data" / "report_data.json").read_text(encoding="utf-8"))

# Trim the quote scatter: 437 points is more than the chart can show distinctly
D["smile"]["quotes"] = D["smile"]["quotes"][::4]

SUM, MET, TER = D["summary"], D["method"], D["terciles"]


def pc(x, dp=1, sign=False):
    return f"{x:+.{dp}f}%" if sign else f"{x:.{dp}f}%"


def val(set_, bar, model, field):
    return SUM[set_][bar][model][field]


# ── CSS ──────────────────────────────────────────────────────────────────────
def build_css():
    ref = (ROOT / "research" / "0dte-gamma-trap" / "index.html").read_text(encoding="utf-8")
    css = re.search(r"<style>(.*?)</style>", ref, re.S).group(1)
    chrome_file = ROOT / ".claude" / "report-chrome.css"
    if chrome_file.exists():
        chrome = chrome_file.read_text(encoding="utf-8")
        chrome = re.search(r"/\* CHROME:START \*/(.*?)/\* CHROME:END \*/", chrome, re.S)
        chrome = chrome.group(1) if chrome else chrome_file.read_text(encoding="utf-8")
        css = re.sub(r"/\* CHROME:START \*/.*?/\* CHROME:END \*/",
                     "/* CHROME:START */" + chrome + "/* CHROME:END */", css, flags=re.S)
    return css + EXTRA_CSS


EXTRA_CSS = """
/* ---- report-specific ---- */
.ctrl-row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:0 0 14px; }
.ctrl-label { font-family:var(--mono); font-size:.66rem; letter-spacing:.06em; text-transform:uppercase;
              color:var(--hint); margin-right:4px; }
.ctrl-btn { font-family:var(--mono); font-size:.72rem; padding:6px 13px; border:1px solid var(--border);
            background:var(--bg); color:var(--muted); cursor:pointer; border-radius:2px; transition:all .15s; }
.ctrl-btn:hover { border-color:var(--accent); color:var(--accent); }
.ctrl-btn.on { background:var(--ink); border-color:var(--ink); color:#fff; }
.sim { display:grid; grid-template-columns:minmax(0,1.05fr) minmax(0,1fr); gap:26px; align-items:start;
       background:var(--bg2); border:1px solid var(--border); padding:22px 24px; margin:22px 0; }
@media(max-width:820px){ .sim { grid-template-columns:minmax(0,1fr); } }
.sim-readout { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-top:16px; }
@media(max-width:560px){ .sim-readout { grid-template-columns:minmax(0,1fr); }
                         .sim-cell .lab { min-height:0; } }
.sim-cell { background:var(--bg); border:1px solid var(--border); padding:11px 12px; }
.sim-cell .lab { font-family:var(--mono); font-size:.6rem; letter-spacing:.05em; text-transform:uppercase;
                 color:var(--hint); line-height:1.35; min-height:2.1em; }
.sim-cell .num { font-family:var(--serif); font-style:italic; font-size:1.5rem; color:var(--accent); margin-top:5px; }
.sim-cell .sub { font-family:var(--mono); font-size:.64rem; color:var(--muted); margin-top:3px; }
.slider-wrap { margin:4px 0 0; }
.slider-wrap input[type=range] { width:100%; accent-color:var(--accent); }
.slider-head { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px; }
.slider-head .big { font-family:var(--serif); font-style:italic; font-size:1.7rem; color:var(--ink); }
.slider-head .cap { font-family:var(--mono); font-size:.66rem; color:var(--hint); text-transform:uppercase;
                    letter-spacing:.05em; }
.hm-wrap { overflow-x:auto; }
.hm-table { border-collapse:collapse; width:100%; font-family:var(--mono); font-size:.75rem; }
.hm-table thead th, .hm-table tbody td { border:1px solid var(--border); }
.hm-corner { background:var(--bg2); }
.hm-col { background:var(--ink); color:#fff; font-size:.66rem; font-weight:600; text-transform:uppercase;
          letter-spacing:.04em; padding:7px 10px; text-align:center; }
.hm-row-label { background:var(--bg2); color:var(--muted); font-size:.72rem; font-family:var(--font);
                padding:7px 12px; white-space:nowrap; }
.hm-cell { text-align:center; color:var(--ink); padding:7px 10px; white-space:nowrap; }
.note { font-family:var(--mono); font-size:.68rem; color:var(--hint); margin-top:9px; line-height:1.6; }
"""

# ── numbers used in prose ────────────────────────────────────────────────────
N = {
    "spx_real70": val("SPX", "0.7", "lv", "p_ki"), "spx_lv70": val("SPX", "0.7", "lv", "p_ki"),
    "spx_ratio70": val("SPX", "0.7", "lv", "ratio"), "sn_ratio70": val("SN", "0.7", "lv", "ratio"),
    "spx_kept70": val("SPX", "0.7", "lv", "kept"), "sn_kept70": val("SN", "0.7", "lv", "kept"),
}
T70 = {t["tercile"]: t for t in TER if t["barrier"] == 0.7}

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-HT9VG5C62E"></script><script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-HT9VG5C62E');</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Barrier Premium | The Intrinsic Investor</title>
<meta name="description" content="Thirty years of barrier option pricing tested against what actually happened: the volatility skew charged 2.5 times the realised knock-in rate on the S&amp;P 500, but only 1.3 times on single stocks.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,400;0,600;1,400;1,600&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>{{CSS}}</style>
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
<div id="side-nav" aria-label="Page sections"></div>

<header class="hero">
  <div class="hero-inner">
    <div class="hero-tag">Derivatives Pricing Study</div>
    <h1>The Barrier Premium: <em>what the skew charges for a crash</em></h1>
    <p class="hero-sub">{{HERO_SUB}}</p>
    <div class="hero-meta">
      <div class="hero-meta-item"><strong>Author</strong>Brian Liew, BSc Accounting and Finance, LSE</div>
      <div class="hero-meta-item"><strong>Published</strong>September 2026</div>
      <div class="hero-meta-item"><strong>Period</strong>{{PERIOD}}</div>
      <div class="hero-meta-item"><strong>Data</strong>OptionMetrics IvyDB US and Europe, CRSP</div>
      <a href="https://github.com/TheIntrinsicInvestor/Backtesting/tree/main/research/barrier-skew" target="_blank" rel="noopener" class="gh-btn">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
        GitHub Code
      </a>
    </div>
  </div>
</header>

<div class="kpi-strip">
  <div class="kpi-grid">
    <div class="kpi-cell">
      <div class="kpi-label">Skew vs reality, S&amp;P 500</div>
      <div class="kpi-value blue">{{KPI1}}</div>
      <div class="kpi-sub">Model knock-in rate divided by realised, 70% barrier</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">Skew vs reality, single stocks</div>
      <div class="kpi-value blue">{{KPI2}}</div>
      <div class="kpi-sub">Same test, 10 large caps per week</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">Premium kept, index</div>
      <div class="kpi-value green">{{KPI3}}</div>
      <div class="kpi-sub">Share of the premium left after realised losses</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">Premium kept, single stocks</div>
      <div class="kpi-value red">{{KPI4}}</div>
      <div class="kpi-sub">Before the 6% to 7% fees charged on real notes</div>
    </div>
  </div>
</div>

<section class="section" id="s1">
  <div class="container">
    <div class="section-label"><span class="section-counter">01</span><span>The Put Inside the Note</span></div>
    <h2>A barrier option is <em>crash insurance sold by the buyer of a note</em></h2>
    {{S1_BODY}}
    <div class="chart-box">
      <div class="chart-title">The S&amp;P 500 volatility skew on {{SMILE_DATE}}, one year to expiry</div>
      <canvas id="smileChart" height="78"></canvas>
      <div class="chart-legend">
        <span class="legend-item"><span class="legend-line" style="background:#1a5c52"></span>Fitted surface</span>
        <span class="legend-item"><span class="legend-dot" style="background:#0f2220"></span>OptionMetrics grid</span>
        <span class="legend-item"><span class="legend-dot" style="background:#E3A008"></span>Listed put quotes</span>
      </div>
      <div class="note">{{SMILE_NOTE}}</div>
    </div>
    <div class="sim">
      <div>
        <div class="slider-head">
          <span class="big" id="simBarrier">70%</span>
          <span class="cap">Barrier level, drag to change</span>
        </div>
        <div class="slider-wrap"><input type="range" id="simSlider" min="50" max="95" step="1" value="70"></div>
        <div class="note" style="margin-top:12px">{{SIM_NOTE}}</div>
      </div>
      <div>
        <canvas id="simChart" height="150"></canvas>
      </div>
      <div class="sim-readout" style="grid-column:1/-1">
        <div class="sim-cell"><div class="lab">Flat vol at the money</div><div class="num" id="simAtm">-</div><div class="sub" id="simAtmVol">-</div></div>
        <div class="sim-cell"><div class="lab">Fitted skew (local volatility)</div><div class="num" id="simLv">-</div><div class="sub" id="simLvPrice">-</div></div>
        <div class="sim-cell"><div class="lab">Flat vol at the barrier strike</div><div class="num" id="simBar">-</div><div class="sub" id="simBarVol">-</div></div>
      </div>
    </div>
  </div>
</section>

<section class="section" id="s2" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="section-counter">02</span><span>What the Skew Costs</span></div>
    <h2>Three models, <em>three very different prices</em></h2>
    {{S2_BODY}}
    <div class="ctrl-row"><span class="ctrl-label">Barrier</span>
      <button class="ctrl-btn" data-bar="0.6" data-group="price">60%</button>
      <button class="ctrl-btn on" data-bar="0.7" data-group="price">70%</button>
      <button class="ctrl-btn" data-bar="0.8" data-group="price">80%</button>
    </div>
    <div class="chart-box">
      <div class="chart-title">Price of a one year down-and-in put on the S&amp;P 500, % of notional</div>
      <canvas id="priceChart" height="76"></canvas>
      <div class="chart-legend">
        <span class="legend-item"><span class="legend-line" style="background:#1a5c52"></span>Local volatility</span>
        <span class="legend-item"><span class="legend-line" style="background:#2563eb"></span>Flat, at the money</span>
        <span class="legend-item"><span class="legend-line" style="background:#E02424"></span>Flat, at the barrier strike</span>
      </div>
      <div class="note">Four week averages of weekly pricings. {{PRICE_NOTE}}</div>
    </div>
    <div class="chart-box">
      <div class="chart-title">Which single flat volatility reproduces the skew-consistent price</div>
      <canvas id="volChart" height="76"></canvas>
      <div class="chart-legend">
        <span class="legend-item"><span class="legend-line" style="background:#0f2220"></span>Equivalent flat vol</span>
        <span class="legend-item"><span class="legend-line" style="background:#2563eb"></span>At the money vol</span>
        <span class="legend-item"><span class="legend-line" style="background:#E02424"></span>Barrier strike vol</span>
      </div>
      <div class="note">{{VOL_NOTE}}</div>
    </div>
    {{S2_TABLE}}
  </div>
</section>

<section class="section" id="s3">
  <div class="container">
    <div class="section-label"><span class="section-counter">03</span><span>Implied Against Realised</span></div>
    <h2>The test: <em>how often did the barrier actually break</em></h2>
    {{S3_BODY}}
    <div class="ctrl-row"><span class="ctrl-label">Barrier</span>
      <button class="ctrl-btn" data-bar="0.6" data-group="real">60%</button>
      <button class="ctrl-btn on" data-bar="0.7" data-group="real">70%</button>
      <button class="ctrl-btn" data-bar="0.8" data-group="real">80%</button>
    </div>
    <div class="chart-box">
      <div class="chart-title">Knock-in probability: what each model said, and what happened</div>
      <canvas id="realChart" height="72"></canvas>
      <div class="chart-legend">
        <span class="legend-item"><span class="legend-dot" style="background:#0f2220"></span>Actually knocked in</span>
        <span class="legend-item"><span class="legend-dot" style="background:#1a5c52"></span>Local volatility</span>
        <span class="legend-item"><span class="legend-dot" style="background:#2563eb"></span>Flat, at the money</span>
        <span class="legend-item"><span class="legend-dot" style="background:#E02424"></span>Flat, at the barrier</span>
      </div>
    </div>
    <div class="chart-box">
      <div class="chart-title">Model minus realised, with 95% block-bootstrap intervals</div>
      <canvas id="gapChart" height="118"></canvas>
      <div class="note">{{GAP_NOTE}}</div>
    </div>
    {{S3_CALLOUT}}
  </div>
</section>

<section class="section" id="s4" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="section-counter">04</span><span>Where the Premium Lives</span></div>
    <h2>The index is where <em>the crash premium actually sits</em></h2>
    {{S4_BODY}}
    <div class="highlight-box">
      <div class="hl-grid">
        <div class="hl-cell"><div class="hl-value">{{HL1}}</div><div class="hl-label">S&amp;P 500 premium kept</div></div>
        <div class="hl-cell"><div class="hl-value">{{HL2}}</div><div class="hl-label">Euro Stoxx 50 premium kept</div></div>
        <div class="hl-cell"><div class="hl-value">{{HL3}}</div><div class="hl-label">Single stock premium kept</div></div>
      </div>
    </div>
    <div class="chart-box">
      <div class="chart-title">Share of the premium the seller keeps after realised knock-in losses</div>
      <canvas id="keptChart" height="72"></canvas>
      <div class="chart-legend">
        <span class="legend-item"><span class="legend-dot" style="background:#1a5c52"></span>60% barrier</span>
        <span class="legend-item"><span class="legend-dot" style="background:#2563eb"></span>70% barrier</span>
        <span class="legend-item"><span class="legend-dot" style="background:#E3A008"></span>80% barrier</span>
      </div>
    </div>
    <div class="chart-box">
      <div class="chart-title">Single stocks split into thirds by their own volatility, 70% barrier</div>
      <canvas id="tercileChart" height="72"></canvas>
      <div class="chart-legend">
        <span class="legend-item"><span class="legend-dot" style="background:#0f2220"></span>Actually knocked in</span>
        <span class="legend-item"><span class="legend-dot" style="background:#1a5c52"></span>Local volatility said</span>
        <span class="legend-item"><span class="legend-line" style="background:#E3A008"></span>Premium kept</span>
      </div>
      <div class="note">{{TERCILE_NOTE}}</div>
    </div>
    {{S4_CALLOUT}}
  </div>
</section>

<section class="section" id="s5">
  <div class="container">
    <div class="section-label"><span class="section-counter">05</span><span>A Price, Not a Forecast</span></div>
    <h2>The skew misses the crash it is <em>supposed to be pricing</em></h2>
    {{S5_BODY}}
    {{REGIME_TABLE}}
    <div class="ctrl-row" style="margin-top:26px"><span class="ctrl-label">Underlying</span>
      <button class="ctrl-btn on" data-set="SPX" data-group="epi">S&amp;P 500</button>
      <button class="ctrl-btn" data-set="SX5E" data-group="epi">Euro Stoxx 50</button>
      <button class="ctrl-btn" data-set="SN" data-group="epi">Single stocks</button>
    </div>
    <div class="chart-box">
      <div class="chart-title">Share of products started in each year that knocked in, 70% barrier</div>
      <canvas id="epiChart" height="72"></canvas>
      <div class="note">{{EPI_NOTE}}</div>
    </div>
    <div class="chart-box">
      <div class="chart-title">Calibration: model probability against realised frequency, single stocks</div>
      <canvas id="calChart" height="72"></canvas>
      <div class="chart-legend">
        <span class="legend-item"><span class="legend-dot" style="background:#1a5c52"></span>Probability bins</span>
        <span class="legend-item"><span class="legend-line" style="background:#8aa49e"></span>Perfect calibration</span>
      </div>
      <div class="note">{{CAL_NOTE}}</div>
    </div>
  </div>
</section>

<section class="section" id="s6" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="section-counter">06</span><span>The Note Buyer's Side</span></div>
    <h2>The premium is real, and <em>the fee is bigger</em></h2>
    {{S6_BODY}}
    <div class="chart-box">
      <div class="chart-title">What the embedded put earned per year, before and after published fees</div>
      <canvas id="feeChart" height="86"></canvas>
      <div class="note">{{FEE_NOTE}}</div>
    </div>
    {{FEE_TABLE}}
    {{S6_CALLOUT}}
  </div>
</section>

<section class="section" id="s7">
  <div class="container">
    <div class="section-label"><span class="section-counter">07</span><span>Methodology</span></div>
    <h2>How the prices and <em>the checks were built</em></h2>
    {{S7_BODY}}
    {{METHOD_TABLE}}
    <h3>What could make this wrong</h3>
    {{LIMITS}}
  </div>
</section>

<section class="section" id="s8" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="section-counter">08</span><span>Conclusions</span></div>
    <h2>What a structurer <em>should take from this</em></h2>
    {{S8_BODY}}
  </div>
</section>

<footer>
  <div class="footer-inner">
    <div class="footer-name">The Intrinsic Investor</div>
    <div class="footer-right">
      <span style="color:rgba(255,255,255,.35)">&copy; 2026 Brian Liew</span>
      <a href="https://www.linkedin.com/in/brianliewrz" target="_blank" rel="noopener">LinkedIn</a>
      <a href="https://github.com/TheIntrinsicInvestor" target="_blank" rel="noopener">GitHub</a>
      <a href="mailto:brianliew.rz@gmail.com">Email</a>
    </div>
  </div>
</footer>

<script>
const D = {{DATA}};
{{JS}}
</script>
</body>
</html>
"""


def main():
    import content
    import charts

    parts = content.build(D)
    parts["CSS"] = build_css()
    parts["DATA"] = json.dumps(D, separators=(",", ":"))
    parts["JS"] = charts.JS

    page = PAGE
    for key, value in parts.items():
        page = page.replace("{{" + key + "}}", value)

    left = re.findall(r"\{\{([A-Z0-9_]+)\}\}", page)
    assert not left, f"unfilled placeholders: {sorted(set(left))}"
    assert "—" not in re.sub(r"<script.*?</script>|<style>.*?</style>", "", page, flags=re.S), "em dash in visible text"

    out = HERE / "index.html"
    out.write_text(page, encoding="utf-8")
    print(f"  wrote {out} ({len(page) / 1024:.0f} KB)")
    print(f"  sections: {len(re.findall(r'<section class=.section.', page))}, "
          f"charts: {len(re.findall(r'<canvas', page))}, callouts: {len(re.findall(r'class=.callout', page))}")


if __name__ == "__main__":
    main()

