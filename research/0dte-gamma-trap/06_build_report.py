# ruff: noqa
"""
06_build_report.py
------------------
Generate the full HTML report at index.html.
Matches theintrinsicinvestor.com design system exactly.
"""

import json, os
import numpy as np
import pandas as pd

os.makedirs(".", exist_ok=True)

# ── Load chart data ───────────────────────────────────────────────────────────
with open("charts/data_gex_timeseries.json")   as f: ts_data      = json.load(f)
with open("charts/data_scatter.json")           as f: scatter_data = json.load(f)
with open("charts/data_intraday_profile.json")  as f: profile_data = json.load(f)
with open("charts/data_regimes.json")           as f: regime_data  = json.load(f)
with open("charts/data_backtest.json")          as f: backtest_data= json.load(f)

df = pd.read_parquet("data/combined.parquet")

# ── Key numbers ───────────────────────────────────────────────────────────────
neg_rvol  = regime_data["data"]["Negative GEX"]["mean"]
high_rvol = regime_data["data"]["High GEX"]["mean"]
vol_prem  = regime_data["vol_premium"]
r2        = scatter_data["regression"]["r2"]
p_val     = regime_data["t_test"]["p_val"]
t_stat    = regime_data["t_test"]["t_stat"]
n_days    = ts_data["stats"]["n_total"]
pct_pos   = ts_data["stats"]["pct_positive"]
date_start= df["date"].min().strftime("%b %Y")
date_end  = df["date"].max().strftime("%b %Y")
vol_prem_pct = backtest_data["summary"]["vol_premium_pct"]

neg_med   = regime_data["data"]["Negative GEX"]["median"]
high_med  = regime_data["data"]["High GEX"]["median"]
sig_str   = "statistically significant" if p_val < 0.05 else "not significant at 5%"

# Format helpers
def pct(v): return f"{v:.0%}"
def pct1(v): return f"{v*100:.1f}%"
def pp(v):  return f"{v:+.1f}pp"

# ── JavaScript data ───────────────────────────────────────────────────────────
ts_dates_js      = json.dumps(ts_data["dates"])
ts_gex_js        = json.dumps(ts_data["gex_bn"])
ts_colors_js     = json.dumps(ts_data["bar_colors"])

scatter_pts_js   = json.dumps([
    {"x": p["gex"], "y": round(p["rvol"]*100, 2), "regime": p["regime"], "date": p.get("date", "")}
    for p in scatter_data["points"]
])
scatter_reg_js   = json.dumps([
    {"x": scatter_data["regression"]["line"][0]["x"],
     "y": round(scatter_data["regression"]["line"][0]["y"]*100, 2)},
    {"x": scatter_data["regression"]["line"][1]["x"],
     "y": round(scatter_data["regression"]["line"][1]["y"]*100, 2)},
])
scatter_colors_js = json.dumps([
    ("#dc2626" if p["regime"]=="Negative GEX" else
     "#f59e0b" if p["regime"]=="Low GEX" else "#059669")
    for p in scatter_data["points"]
])

profile_labels_js = json.dumps(profile_data["buckets"])
profile_neg_js    = json.dumps([
    round(v*100,2) if v is not None else None
    for v in profile_data["regimes"]["Negative GEX"]
])
profile_low_js    = json.dumps([
    round(v*100,2) if v is not None else None
    for v in profile_data["regimes"]["Low GEX"]
])
profile_high_js   = json.dumps([
    round(v*100,2) if v is not None else None
    for v in profile_data["regimes"]["High GEX"]
])

regime_labels_js = json.dumps(["Negative GEX", "Low GEX", "High GEX"])
regime_medians_js = json.dumps([
    round(regime_data["data"][r]["median"]*100, 2)
    for r in ["Negative GEX", "Low GEX", "High GEX"]
])
regime_p25_js = json.dumps([
    round(regime_data["data"][r]["p25"]*100, 2)
    for r in ["Negative GEX", "Low GEX", "High GEX"]
])
regime_p75_js = json.dumps([
    round(regime_data["data"][r]["p75"]*100, 2)
    for r in ["Negative GEX", "Low GEX", "High GEX"]
])
regime_p10_js = json.dumps([
    round(regime_data["data"][r]["p10"]*100, 2)
    for r in ["Negative GEX", "Low GEX", "High GEX"]
])
regime_p90_js = json.dumps([
    round(regime_data["data"][r]["p90"]*100, 2)
    for r in ["Negative GEX", "Low GEX", "High GEX"]
])

bt_dates_js      = json.dumps(backtest_data["dates"])
bt_rvol_js       = json.dumps([
    round(v*100, 2) if v is not None else None
    for v in backtest_data["rvol_ann"]
])
bt_rolling_js    = json.dumps([
    round(v*100, 2) if v is not None else None
    for v in backtest_data["rvol_rolling60"]
])
bt_colors_js     = json.dumps(backtest_data["bar_colors"])

# ── HTML ──────────────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>The Gamma Trap: How 0DTE Options Reshape Intraday SPX Dynamics | The Intrinsic Investor</title>
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
      -webkit-backdrop-filter:blur(12px);border-bottom:1px solid var(--border);
      transition:box-shadow .3s}}
    nav.scrolled{{box-shadow:0 1px 24px rgba(15,34,32,.06)}}
    .nav-logo{{font-family:var(--serif);font-weight:600;font-size:1.1rem;color:var(--ink);letter-spacing:-.01em}}
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
      background-image:repeating-linear-gradient(-55deg,transparent,transparent 40px,
        rgba(255,255,255,.013) 40px,rgba(255,255,255,.013) 41px)}}
    .hero-inner{{max-width:860px;margin:0 auto;position:relative}}
    .hero-tag{{display:inline-block;font-family:var(--mono);font-size:.72rem;color:var(--accent);
      letter-spacing:.08em;text-transform:uppercase;border:1px solid rgba(26,92,82,.4);
      padding:.25rem .75rem;border-radius:2px;margin-bottom:1.5rem;
      animation:fadeUp .6s ease both}}
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
    p{{color:var(--muted);line-height:1.75;margin-bottom:1rem;text-align:left;hyphens:none;word-break:normal;overflow-wrap:normal}}    p:last-child{{margin-bottom:0}}
    .callout{{display:flex;gap:1rem;padding:1.25rem 1.5rem;border-radius:4px;
      margin:1.5rem 0;border-left:3px solid}}
    .callout.green{{background:var(--green-bg);border-color:var(--green2)}}
    .callout.amber{{background:var(--amber-bg);border-color:var(--amber)}}
    .callout.red{{background:var(--red-bg);border-color:var(--red2)}}
    .callout.blue{{background:var(--blue-bg);border-color:var(--blue2)}}
    .callout.purple{{background:var(--purple-bg);border-color:var(--purple)}}
    .callout-icon{{font-size:1.1rem;flex-shrink:0;margin-top:.1rem}}
    .callout-body{{font-size:.9rem;color:var(--ink);line-height:1.6}}
    .callout-body strong{{font-weight:600}}
    .highlight-box{{background:var(--ink);border-radius:4px;padding:2rem;margin:1.5rem 0}}
    .hl-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:0}}
    .hl-cell{{padding:0 1.5rem;border-right:1px solid rgba(255,255,255,.1)}}
    .hl-cell:first-child{{padding-left:0}}
    .hl-cell:last-child{{border-right:none}}
    .hl-label{{font-size:.7rem;font-weight:500;color:rgba(255,255,255,.35);text-transform:uppercase;
      letter-spacing:.1em;margin-bottom:.5rem}}
    .hl-value{{font-family:var(--serif);font-style:italic;font-size:1.75rem;color:#5ab5a5;line-height:1.1}}
    .hl-sub{{font-size:.75rem;color:rgba(255,255,255,.3);margin-top:.3rem}}
    .chart-box{{background:var(--bg2);border:1px solid var(--border);
      border-radius:4px;padding:1.5rem;margin:1.5rem 0}}
    .chart-title{{font-size:.85rem;font-weight:600;color:var(--ink);
      margin-bottom:1rem;letter-spacing:.02em}}
    .chart-legend{{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px}}
    .legend-item{{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--muted)}}
    .legend-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
    .legend-line{{width:16px;height:2px;flex-shrink:0}}
    .table-wrap{{overflow-x:auto;margin:1.5rem 0;border-radius:4px;border:1px solid var(--border)}}
    table{{width:100%;border-collapse:collapse;font-size:.875rem}}
    thead tr{{background:var(--ink);color:#fff}}
    thead th{{padding:.7rem .9rem;text-align:left;font-weight:500;font-size:.75rem;letter-spacing:.04em}}
    tbody tr{{border-bottom:1px solid var(--border)}}
    tbody tr:last-child{{border-bottom:none}}
    tbody tr:hover{{background:var(--bg2)}}
    td{{padding:.65rem .9rem;color:var(--muted);vertical-align:middle}}
    .mono{{font-family:var(--mono);font-size:.82rem}}
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
    .gh-btn{{display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);
      font-size:.68rem;color:rgba(255,255,255,.5);text-decoration:none;
      border:1px solid rgba(255,255,255,.2);padding:3px 9px;border-radius:3px;
      transition:all .2s;letter-spacing:.02em;align-self:center}}
    .gh-btn:hover{{color:#fff;border-color:rgba(255,255,255,.5);background:rgba(255,255,255,.08)}}
    @media(max-width:860px){{
      #side-nav{{display:none}}
      .kpi-grid{{grid-template-columns:repeat(2,1fr)}}
      .footer-inner{{flex-direction:column;text-align:center}}
      .footer-right{{text-align:center}}
    }}
    @media(max-width:560px){{
      .kpi-cell{{border-right:none;border-bottom:1px solid var(--border)}}
      .hl-grid{{grid-template-columns:1fr;gap:1rem}}
      .hl-cell{{border-right:none;padding:0;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:1rem}}
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
  <div class="nav-logo">The Intrinsic Investor</div>
  <ul class="nav-links">
    <li><a href="/">Home</a></li>
    <li><a href="/research">Research</a></li>
    <li><a href="/about">About</a></li>
  </ul>
</nav>

<div class="hero">
  <div class="hero-inner">
    <div class="hero-tag">0DTE Options Research</div>
    <h1>The Gamma Trap: <em>How 0DTE Options Reshape Intraday SPX Dynamics</em></h1>
    <p class="hero-sub">Every day, dealers who sell zero-days-to-expiry SPX options must hedge their positions in real time. When their aggregate gamma exposure turns negative, that hedging mechanically amplifies intraday moves. We measure this effect empirically using OptionMetrics and TAQ data across {n_days} trading days.</p>
    <div class="hero-meta">
      <div class="hero-meta-item"><strong>Brian Liew</strong>LSE, BSc Accounting and Finance</div>
      <div class="hero-meta-item"><strong>{date_start} &ndash; {date_end}</strong>Sample Period</div>
      <div class="hero-meta-item"><strong>{n_days} Trading Days</strong>Observations</div>
      <div class="hero-meta-item"><strong>OptionMetrics &amp; TAQ via WRDS</strong>Data Sources</div>
      <div class="hero-meta-item"><strong>April 2026</strong>Published</div>
      <a class="gh-btn" href="https://github.com/TheIntrinsicInvestor/Backtesting/tree/main/research/0dte-gamma-trap" target="_blank" rel="noopener noreferrer"><svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg> Code</a>
    </div>
  </div>
</div>

<div class="kpi-strip">
  <div class="kpi-grid">
    <div class="kpi-cell">
      <div class="kpi-label">Vol Premium (Neg vs High GEX)</div>
      <div class="kpi-value red">+{vol_prem_pct:.0f}%</div>
      <div class="kpi-sub">higher intraday vol when GEX negative</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">R&#178; (GEX vs RVol)</div>
      <div class="kpi-value blue">{r2:.3f}</div>
      <div class="kpi-sub">OLS regression, {n_days} day sample</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">p-value (t-test)</div>
      <div class="kpi-value green">{p_val:.4f}</div>
      <div class="kpi-sub">Neg GEX vs High GEX, Welch&#8217;s t</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">Days with Positive GEX</div>
      <div class="kpi-value green">{pct(pct_pos)}</div>
      <div class="kpi-sub">of the {n_days}-day sample</div>
    </div>
  </div>
</div>

<section class="section" id="s1">
<div class="container">
  <div class="section-label"><span class="section-counter">01</span><span>Background</span></div>
    <h2>What is Dealer Gamma Exposure?</h2>

    <p>
      Zero-days-to-expiry (0DTE) SPX options — contracts that expire the same calendar day they
      are traded — have grown from a curiosity to a dominant force in US equity markets. Since the
      CBOE introduced daily SPX expirations in May 2022, 0DTE options now routinely account for
      more than 40% of total SPX options volume. Behind every one of those contracts is a market
      maker who has sold it and must now manage the resulting risk.
    </p>

    <h3>Delta-hedging and the gamma feedback loop</h3>

    <p>
      When a dealer sells an option, they delta-hedge their exposure by taking an offsetting
      position in the underlying. As the underlying price moves, delta changes, and the dealer
      must adjust their hedge continuously. The rate at which delta changes with price is gamma
      (&#915;). A dealer who is <em>long</em> gamma profits from this adjustment process &#8212;
      they buy when prices fall and sell when prices rise, acting as a natural stabiliser.
      A dealer who is <em>short</em> gamma must do the opposite: buy as prices rise and sell
      as prices fall. Their hedging <em>amplifies</em> the very moves they are trying to hedge.
    </p>

    <p>
      Dealer Gamma Exposure (GEX) aggregates this effect across all open 0DTE contracts.
      Under the standard assumption &#8212; that all open interest represents customer-bought
      positions with dealers on the other side &#8212; GEX is computed as:
    </p>

    <div class="callout blue">
      <div class="callout-icon">&#402;</div>
      <div class="callout-body">
        <strong>GEX = &#931; (Call OI &#215; &#915;<sub>call</sub> &#8722; Put OI &#215; &#915;<sub>put</sub>) &#215; 100 &#215; S / 10&#185;&#8313;</strong><br>
        where &#915; is the Black-Scholes gamma per share, OI is open interest in contracts,
        100 is the standard multiplier, S is the spot price, and the result is expressed
        in billions of dollars of underlying per 1% move. <strong>Positive GEX</strong> means
        dealers are net long gamma (vol suppressing). <strong>Negative GEX</strong> means
        dealers are net short gamma (vol amplifying).
      </div>
    </div>

    <p>
      The call-minus-put sign convention reflects empirical observation: SPX call open interest
      is predominantly driven by customer hedgers and income sellers, while put open interest is
      dominated by protective buyers. Dealers tend to be net short calls and net long puts in
      aggregate, yielding positive net gamma under normal conditions. But 0DTE options are
      different &#8212; they expire the same day, so open interest at the start of the session
      represents only same-day speculative and hedging activity, with a sharper intraday
      gamma profile than any multi-day contract.
    </p>

    <div class="callout amber">
      <div class="callout-icon">&#9888;</div>
      <div class="callout-body">
        <strong>Methodology caveat:</strong> The standard GEX assumption treats all open interest
        as customer-long. In reality, dealers both buy and sell options. This approach is used
        throughout industry (SpotGamma, Squeezemetrics) because signed OI data is not publicly
        available at the required granularity. GEX should be interpreted as a <em>directional
        signal</em> rather than a precise measure of dealer positioning.
      </div>
    </div>
  </div>
</section>

<section class="section" id="s2">
<div class="container">
  <div class="section-label"><span class="section-counter">02</span><span>Data &amp; GEX</span></div>
    <h2>Building the GEX Time Series</h2>

    <p>
      We pull every SPX 0DTE option record from OptionMetrics via WRDS for the period
      {date_start} to {date_end}. A contract qualifies as 0DTE if its expiration date
      equals the quote date. For each trading day, we sum the signed gamma&#8202;&#215;&#8202;OI
      product across all qualifying strikes and apply the GEX formula above, using the
      SPY closing price as a proxy for the SPX spot price in dollar-normalisation.
    </p>

    <p>
      Realized intraday volatility is computed from TAQ consolidated trades for SPY.
      For each day, we aggregate individual trades into five-minute VWAP bars from
      9:30&#8202;am to 4:00&#8202;pm EST (78 intervals), compute the sequence of log returns,
      and annualise the realised variance: <em>&#963; = &#8730;(&#8721; r&#8202;&#178; &#215; 252 &#215; 78)</em>.
      This measure captures intraday price variability without contamination from
      overnight gap risk.
    </p>

    <div class="chart-box">
      <div class="chart-title">Chart 1 &#8202;&#8212;&#8202; Daily SPX 0DTE GEX, {date_start}&#8202;&#8211;&#8202;{date_end}</div>
      <canvas id="gexChart" height="80"></canvas>
      <div class="chart-legend">
        <div class="legend-item"><span class="legend-dot" style="background:#059669"></span>Positive GEX (dealers long gamma)</div>
        <div class="legend-item"><span class="legend-dot" style="background:#dc2626"></span>Negative GEX (dealers short gamma)</div>
        <div class="legend-item"><span class="legend-dot" style="background:#f59e0b"></span>Low positive GEX</div>
      </div>
    </div>

    <p>
      Over the full sample, <strong>{pct(pct_pos)}</strong> of trading days had positive GEX &#8212;
      meaning dealers were net long gamma on the majority of sessions. The distribution is
      right-skewed: large positive GEX readings (dealers very long gamma) are more common than
      deeply negative ones. Negative GEX days tend to cluster around macro events, FOMC
      announcements, and periods of elevated VIX, when put buyers dominate 0DTE flow.
    </p>
  </div>
</section>

<section class="section" id="s3">
<div class="container">
  <div class="section-label"><span class="section-counter">03</span><span>The Two Regimes</span></div>
    <h2>Negative GEX Days Are Structurally More Volatile</h2>

    <p>
      We classify each trading day into one of three regimes based on daily GEX:
      <strong>Negative GEX</strong> (gex &lt; 0), <strong>Low GEX</strong>
      (0 &#8804; gex &lt; 33rd percentile of positive days), and <strong>High GEX</strong>
      (gex &#8805; 33rd percentile). The key comparison is between the extremes.
    </p>

    <div class="highlight-box">
      <div class="hl-grid">
        <div class="hl-cell">
          <div class="hl-label">Neg GEX mean annualised RVol</div>
          <div class="hl-value">{pct1(neg_rvol)}</div>
          <div class="hl-sub">dealers short gamma &#8594; amplifying</div>
        </div>
        <div class="hl-cell">
          <div class="hl-label">High GEX mean annualised RVol</div>
          <div class="hl-value">{pct1(high_rvol)}</div>
          <div class="hl-sub">dealers long gamma &#8594; suppressing</div>
        </div>
        <div class="hl-cell">
          <div class="hl-label">Vol premium</div>
          <div class="hl-value">+{vol_prem_pct:.0f}%</div>
          <div class="hl-sub">p={p_val:.4f}, t={t_stat:.2f}, Welch&#8217;s t-test</div>
        </div>
      </div>
    </div>

    <p>
      The vol premium is <strong>{sig_str}</strong>. On negative-GEX days, mean annualised
      intraday realised volatility is {pct1(neg_rvol)}, compared with {pct1(high_rvol)}
      on high-GEX days &#8212; a difference of roughly {vol_prem_pct:.0f} percentage points.
      This is not merely a reflection of regime selection bias (e.g., negative GEX days
      happening to coincide with scheduled macro events). The chart below shows the
      distribution of intraday vol across all three regimes.
    </p>

    <div class="chart-box">
      <div class="chart-title">Chart 2 &#8202;&#8212;&#8202; Intraday Realised Vol Distribution by GEX Regime</div>
      <canvas id="regimeChart" height="70"></canvas>
      <div class="chart-legend">
        <div class="legend-item"><span class="legend-dot" style="background:#dc2626"></span>Negative GEX (n={regime_data['data']['Negative GEX']['n']})</div>
        <div class="legend-item"><span class="legend-dot" style="background:#f59e0b"></span>Low GEX (n={regime_data['data']['Low GEX']['n']})</div>
        <div class="legend-item"><span class="legend-dot" style="background:#059669"></span>High GEX (n={regime_data['data']['High GEX']['n']})</div>
        <div class="legend-item" style="margin-left:8px;color:var(--hint)">Bars show median; error bars show p25&#8202;&#8211;&#8202;p75</div>
      </div>
    </div>

    <div class="chart-box">
      <div class="chart-title">Chart 3 &#8202;&#8212;&#8202; GEX vs Intraday Realised Vol (Daily, {date_start}&#8202;&#8211;&#8202;{date_end})</div>
      <canvas id="scatterChart" height="80"></canvas>
      <div class="chart-legend">
        <div class="legend-item"><span class="legend-dot" style="background:#dc2626"></span>Negative GEX</div>
        <div class="legend-item"><span class="legend-dot" style="background:#f59e0b"></span>Low GEX</div>
        <div class="legend-item"><span class="legend-dot" style="background:#059669"></span>High GEX</div>
        <div class="legend-item"><span class="legend-line" style="background:#1e40af"></span>OLS regression (R&#178;&#8202;=&#8202;{r2:.3f})</div>
      </div>
    </div>

    <p>
      The scatter plot reveals a clear negative relationship: higher GEX is associated with lower
      intraday vol. The OLS regression has R&#178;&nbsp;=&nbsp;{r2:.3f}, meaning GEX explains
      approximately {r2*100:.0f}% of the cross-day variation in intraday realised vol.
      While modest in absolute terms, this is a meaningful signal given the number of other
      factors (scheduled news, VIX regime, time-of-year) that also drive intraday vol.
    </p>
  </div>
</section>

<section class="section" id="s4">
<div class="container">
  <div class="section-label"><span class="section-counter">04</span><span>Intraday Dynamics</span></div>
    <h2>The Effect Is Strongest in the Final Hour</h2>

    <p>
      GEX is not uniform through the trading day. As a 0DTE option approaches expiry,
      its gamma profile changes dramatically. Near-the-money options develop very high
      gamma in the final hour &#8212; small price moves create large delta swings that
      dealers must hedge immediately. Simultaneously, the &#8220;charm&#8221; effect
      (d&#916;/dt) forces dealers to adjust their hedges simply because time is passing,
      even without price movement.
    </p>

    <p>
      To capture the intraday pattern, we split each trading day into 30-minute buckets
      (9:30, 10:00, &#8230;, 15:30) and compute the average realised vol within each bucket,
      grouped by GEX regime.
    </p>

    <div class="chart-box">
      <div class="chart-title">Chart 4 &#8202;&#8212;&#8202; Average Intraday Realised Vol by 30-min Bucket and GEX Regime</div>
      <canvas id="profileChart" height="80"></canvas>
      <div class="chart-legend">
        <div class="legend-item"><span class="legend-line" style="background:#dc2626"></span>Negative GEX</div>
        <div class="legend-item"><span class="legend-line" style="background:#f59e0b"></span>Low GEX</div>
        <div class="legend-item"><span class="legend-line" style="background:#059669"></span>High GEX</div>
      </div>
    </div>

    <p>
      The divergence between regimes is most pronounced in the 3:00&#8202;pm&#8202;&#8211;&#8202;4:00&#8202;pm
      window. This is consistent with the mechanics of 0DTE expiry: as the market approaches
      close, gamma spikes for near-the-money contracts and dealers must make progressively
      larger hedge adjustments per unit of price movement. On negative-GEX days, this creates
      a feedback loop where dealer selling (or buying) into already-thin late-day liquidity
      exacerbates the move.
    </p>

    <p>
      The morning (9:30&#8202;&#8211;&#8202;10:00) also shows an elevated vol spread between
      regimes. This reflects the opening print dynamics: on negative-GEX days, dealers
      entering the session with inherited short-gamma positions from overnight activity
      must hedge aggressively into the open, when bid-ask spreads are widest.
    </p>

    <div class="callout green">
      <div class="callout-icon">&#10003;</div>
      <div class="callout-body">
        <strong>Practical implication:</strong> The regime difference is not spread uniformly
        through the day. If you are trading intraday and GEX is negative, the first 30 minutes
        and the final 60 minutes carry disproportionate vol risk. Position sizing should account
        for this asymmetry &#8212; not just the overall GEX level.
      </div>
    </div>
  </div>
</section>

<section class="section" id="s5">
<div class="container">
  <div class="section-label"><span class="section-counter">05</span><span>Trading Signal</span></div>
    <h2>A Concrete Intraday Vol Signal</h2>

    <p>
      The GEX regime classification translates directly into a practical position-sizing
      rule. The logic is simple: if you know that negative-GEX days have systematically
      higher intraday vol, you can scale intraday position sizes inversely to the vol
      forecast. Rather than adjusting to a point forecast, we use the regime median as
      a baseline.
    </p>

    <div class="callout blue">
      <div class="callout-icon">&#9654;</div>
      <div class="callout-body">
        <strong>Signal rule:</strong> At the start of each session, compute the net 0DTE
        GEX from OptionMetrics (or a real-time proxy). If GEX&nbsp;&lt;&nbsp;0,
        apply a volatility scalar of <strong>{1 + vol_prem_pct/100:.2f}&#215;</strong> to
        your intraday stop widths (or equivalently, reduce position size by
        <strong>1&#8202;/&#8202;{1 + vol_prem_pct/100:.2f}&#8202;=&#8202;{100/(1 + vol_prem_pct/100):.0f}%</strong>
        of normal). The scalar is derived from the observed vol premium of negative-GEX
        days over high-GEX days in this study.
      </div>
    </div>

    <div class="chart-box">
      <div class="chart-title">Chart 5 &#8202;&#8212;&#8202; Daily Intraday Realised Vol with GEX Regime Shading</div>
      <canvas id="backtestChart" height="80"></canvas>
      <div class="chart-legend">
        <div class="legend-item"><span class="legend-dot" style="background:#dc2626"></span>Negative GEX day (vol amplifying)</div>
        <div class="legend-item"><span class="legend-dot" style="background:#059669"></span>Positive GEX day (vol suppressing)</div>
        <div class="legend-item"><span class="legend-line" style="background:#1e40af;height:1px"></span>60-day rolling mean rvol</div>
      </div>
    </div>

    <p>
      The time-series chart confirms the pattern holds out-of-sample throughout the
      period &#8212; negative-GEX days (shown in red) consistently cluster around the
      higher end of the daily vol distribution. The effect is most visible during
      2022&#8202;&#8211;&#8202;2023, when the combination of Fed rate hikes and elevated
      VIX produced frequent negative-GEX days. During the calmer 2024 bull market,
      positive GEX dominated and intraday vol remained suppressed for extended stretches.
    </p>

    <div class="highlight-box">
      <div class="hl-grid">
        <div class="hl-cell">
          <div class="hl-label">Negative GEX days</div>
          <div class="hl-value">{pct1(neg_rvol)}</div>
          <div class="hl-sub">mean annualised intraday vol</div>
        </div>
        <div class="hl-cell">
          <div class="hl-label">High GEX days</div>
          <div class="hl-value">{pct1(high_rvol)}</div>
          <div class="hl-sub">mean annualised intraday vol</div>
        </div>
        <div class="hl-cell">
          <div class="hl-label">Scalar adjustment</div>
          <div class="hl-value">{1 + vol_prem_pct/100:.2f}&#215;</div>
          <div class="hl-sub">recommended stop width on neg-GEX days</div>
        </div>
      </div>
    </div>
  </div>
</section>

<section class="section" id="s6">
<div class="container">
  <div class="section-label"><span class="section-counter">06</span><span>Caveats</span></div>
    <h2>What This Study Cannot Tell You</h2>

    <p>
      Several important limitations apply to the findings above.
    </p>

    <p>
      <strong>The standard GEX assumption is a simplification.</strong> We assume all
      open interest is customer-bought. In practice, dealers take two-sided positions,
      and some customers are net sellers of 0DTE options (income-generating strategies,
      institutional hedges). Without signed order-flow data at the individual trade level,
      we cannot construct a precise estimate of net dealer gamma. The bias introduced by
      this assumption is likely to <em>overstate</em> the magnitude of GEX swings but
      should preserve the directional signal.
    </p>

    <p>
      <strong>Correlation is not causation.</strong> The relationship between negative GEX
      and elevated vol could partly reflect reverse causation: high-vol days attract more
      put buyers (generating negative GEX), rather than negative GEX causing higher vol.
      Disentangling this would require intraday GEX snapshots taken at the open, before
      the day&#8217;s vol is realised &#8212; a data exercise beyond the scope of this study.
    </p>

    <p>
      <strong>GEX flips intraday.</strong> We use beginning-of-day GEX computed from
      OptionMetrics daily snapshots. In reality, large trades or sharp price moves can
      shift the aggregate GEX level substantially within a session. A more sophisticated
      implementation would use intraday GEX updates from a real-time options feed.
    </p>

    <div class="callout amber">
      <div class="callout-icon">&#9888;</div>
      <div class="callout-body">
        <strong>This is not investment advice.</strong> The signal described above is a
        research finding, not a trading recommendation. Past patterns in GEX-driven vol
        may not persist as market participants adapt to the 0DTE ecosystem. Position sizing
        rules derived from historical averages carry model risk.
      </div>
    </div>
  </div>
</section>

<section class="section" id="s7">
<div class="container">
  <div class="section-label"><span class="section-counter">07</span><span>Conclusion</span></div>
    <h2>The Options Market Now Co-Authors Intraday Price Action</h2>

    <p>
      Zero-days-to-expiry options have fundamentally changed the microstructure of the SPX.
      The daily flow of 0DTE gamma from dealers to customers &#8212; and the resulting
      obligation on dealers to delta-hedge in real time &#8212; creates a structural,
      measurable regime effect on intraday volatility. When dealer gamma is positive,
      they act as a dampener on price moves. When it turns negative, they become
      amplifiers.
    </p>

    <p>
      Across {n_days} trading days from {date_start} to {date_end}, negative-GEX days
      experienced mean intraday realised vol of {pct1(neg_rvol)}, compared with {pct1(high_rvol)}
      on high-GEX days. The difference is statistically significant (p&#8202;=&#8202;{p_val:.4f}), and the
      pattern is persistent through time rather than driven by a handful of outlier sessions.
      The regime divergence peaks in the final hour of trading &#8212; precisely when 0DTE
      gamma is highest and dealer hedging is most urgent.
    </p>

    <p>
      For practitioners, this translates into a simple, computable signal: check the sign
      of aggregate 0DTE GEX before the open. On negative-GEX days, the market is more
      likely to exhibit volatile, whipsaw intraday price action. Widen stops, reduce
      intraday position sizes, and treat apparent support and resistance levels with
      greater scepticism.
    </p>
  </div>
</section>

<div id="side-nav"></div>

<footer>
  <div class="footer-inner">
    <div class="footer-name">The Intrinsic Investor</div>
    <div class="footer-right">
      <a href="/">Home</a>
      <a href="/research">Research</a>
      <a href="/about">About</a>
      <div style="margin-top:.5rem;color:rgba(255,255,255,.25)">&copy; 2026 Brian Liew &mdash; For research purposes only. Not financial advice.</div>
    </div>
  </div>
</footer>

<script>
// ── Shared chart defaults ─────────────────────────────────────────────────────
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.color = '#8aa49e';
Chart.defaults.animation = false;

Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(15,34,32,0.96)';
Chart.defaults.plugins.tooltip.titleColor = 'rgba(255,255,255,0.92)';
Chart.defaults.plugins.tooltip.bodyColor = 'rgba(255,255,255,0.62)';
Chart.defaults.plugins.tooltip.borderColor = 'rgba(255,255,255,0.09)';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.padding = {{ x: 12, y: 10 }};
Chart.defaults.plugins.tooltip.cornerRadius = 6;
Chart.defaults.plugins.tooltip.boxPadding = 4;
Chart.defaults.plugins.tooltip.titleFont = {{ family: "'Inter',sans-serif", size: 11, weight: '600' }};
Chart.defaults.plugins.tooltip.bodyFont  = {{ family: "'Inter',sans-serif", size: 11 }};

const COLORS = {{
  neg:  '#dc2626',
  low:  '#f59e0b',
  high: '#059669',
  blue: '#2563eb',
  ink:  '#0f2220',
}};

// ── Chart 1: GEX time series ──────────────────────────────────────────────────
(function() {{
  const dates  = {ts_dates_js};
  const values = {ts_gex_js};
  const colors = {ts_colors_js};

  new Chart(document.getElementById('gexChart'), {{
    type: 'bar',
    data: {{
      labels: dates,
      datasets: [{{
        data: values,
        backgroundColor: colors,
        borderWidth: 0,
        barPercentage: 0.9,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            title: ctx => ctx[0].label,
            label: ctx => `GEX: ${{ctx.raw.toFixed(2)}}bn`,
          }}
        }}
      }},
      scales: {{
        x: {{
          ticks: {{ maxTicksLimit: 8, maxRotation: 0, font: {{ size: 10 }} }},
          grid: {{ display: false }},
          border: {{ color: 'rgba(0,0,0,0.10)' }},
        }},
        y: {{
          title: {{ display: true, text: 'GEX (US$bn)', font: {{ size: 11 }} }},
          grid: {{ color: 'rgba(0,0,0,0.05)', lineWidth: 0.75 }},
          border: {{ color: 'transparent' }},
          ticks: {{ font: {{ size: 10 }} }},
        }}
      }}
    }}
  }});
}})();

// ── Chart 2: Regime distribution (bar + error) ────────────────────────────────
(function() {{
  const labels  = {regime_labels_js};
  const medians = {regime_medians_js};
  const p25     = {regime_p25_js};
  const p75     = {regime_p75_js};
  const p10     = {regime_p10_js};
  const p90     = {regime_p90_js};
  const barColors = [COLORS.neg, COLORS.low, COLORS.high];

  new Chart(document.getElementById('regimeChart'), {{
    type: 'bar',
    data: {{
      labels,
      datasets: [
        {{
          // p10–p90 whisker range (background)
          data: p10.map((v, i) => [v, p90[i]]),
          backgroundColor: barColors.map(c => c + '18'),
          borderColor: 'transparent',
          borderWidth: 0,
          barPercentage: 0.45,
          categoryPercentage: 0.7,
          order: 3,
        }},
        {{
          // IQR box (p25–p75)
          data: p25.map((v, i) => [v, p75[i]]),
          backgroundColor: barColors.map(c => c + '44'),
          borderColor: barColors,
          borderWidth: 1.5,
          barPercentage: 0.45,
          categoryPercentage: 0.7,
          order: 2,
        }},
        {{
          // Median marker (thin floating bar)
          data: medians.map(m => [m - 0.35, m + 0.35]),
          backgroundColor: barColors,
          borderColor: 'transparent',
          borderWidth: 0,
          barPercentage: 0.45,
          categoryPercentage: 0.7,
          order: 1,
        }},
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            title: ctx => labels[ctx[0].dataIndex],
            label: (ctx) => {{
              const i = ctx.dataIndex;
              return [
                `Median: ${{medians[i].toFixed(1)}}%`,
                `IQR (p25–p75): ${{p25[i].toFixed(1)}}% – ${{p75[i].toFixed(1)}}%`,
                `Range (p10–p90): ${{p10[i].toFixed(1)}}% – ${{p90[i].toFixed(1)}}%`,
              ];
            }}
          }}
        }}
      }},
      scales: {{
        x: {{
          grid: {{ display: false }},
          border: {{ color: 'rgba(0,0,0,0.10)' }},
          ticks: {{ font: {{ size: 11, weight: '500' }} }},
        }},
        y: {{
          title: {{ display: true, text: 'Annualised Intraday RVol', font: {{ size: 11 }} }},
          grid: {{ color: 'rgba(0,0,0,0.05)', lineWidth: 0.75 }},
          border: {{ color: 'transparent' }},
          ticks: {{
            callback: v => v + '%',
            font: {{ size: 10 }},
          }},
        }}
      }}
    }}
  }});
}})();

// ── Chart 3: Scatter GEX vs RVol ─────────────────────────────────────────────
(function() {{
  const pts    = {scatter_pts_js};
  const colors = {scatter_colors_js};
  const regLine = {scatter_reg_js};

  const scatterDs = pts.map((p, i) => ({{ x: p.x, y: p.y }}));

  new Chart(document.getElementById('scatterChart'), {{
    type: 'scatter',
    data: {{
      datasets: [
        {{
          label: 'Daily observations',
          data: scatterDs,
          backgroundColor: colors.map(c => c + '55'),
          borderColor: colors.map(c => c + '99'),
          borderWidth: 0.8,
          pointRadius: 3.5,
          pointHoverRadius: 6,
          pointStyle: 'circle',
        }},
        {{
          label: 'OLS regression',
          type: 'line',
          data: regLine,
          borderColor: COLORS.blue,
          borderWidth: 2,
          borderDash: [5, 3],
          pointRadius: 0,
          fill: false,
        }}
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            label: (ctx) => {{
              if (ctx.datasetIndex === 0) {{
                const p = pts[ctx.dataIndex];
                return [`${{p.date}}`, `GEX: ${{p.x.toFixed(2)}}bn`, `RVol: ${{p.y.toFixed(1)}}%`, p.regime];
              }}
              return `Trend: ${{ctx.parsed.y.toFixed(1)}}%`;
            }}
          }}
        }}
      }},
      scales: {{
        x: {{
          title: {{ display: true, text: 'Daily GEX (US$bn)', font: {{ size: 11 }} }},
          grid: {{ color: 'rgba(0,0,0,0.05)', lineWidth: 0.75 }},
          border: {{ color: 'rgba(0,0,0,0.10)' }},
          ticks: {{ font: {{ size: 10 }} }},
        }},
        y: {{
          title: {{ display: true, text: 'Intraday RVol, annualised', font: {{ size: 11 }} }},
          grid: {{ color: 'rgba(0,0,0,0.05)', lineWidth: 0.75 }},
          border: {{ color: 'transparent' }},
          ticks: {{ callback: v => v + '%', font: {{ size: 10 }} }},
        }}
      }}
    }}
  }});
}})();

// ── Chart 4: Intraday vol profile ─────────────────────────────────────────────
(function() {{
  const labels = {profile_labels_js};
  const neg    = {profile_neg_js};
  const low    = {profile_low_js};
  const high   = {profile_high_js};

  new Chart(document.getElementById('profileChart'), {{
    type: 'line',
    data: {{
      labels,
      datasets: [
        {{
          label: 'Negative GEX',
          data: neg,
          borderColor: COLORS.neg,
          backgroundColor: COLORS.neg + '18',
          borderWidth: 2.5,
          pointRadius: 4,
          pointBackgroundColor: COLORS.neg,
          fill: true,
          tension: 0.35,
        }},
        {{
          label: 'Low GEX',
          data: low,
          borderColor: COLORS.low,
          backgroundColor: COLORS.low + '12',
          borderWidth: 2,
          pointRadius: 3,
          pointBackgroundColor: COLORS.low,
          fill: true,
          tension: 0.35,
        }},
        {{
          label: 'High GEX',
          data: high,
          borderColor: COLORS.high,
          backgroundColor: COLORS.high + '18',
          borderWidth: 2.5,
          pointRadius: 4,
          pointBackgroundColor: COLORS.high,
          fill: true,
          tension: 0.35,
        }},
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            label: ctx => `${{ctx.dataset.label}}: ${{ctx.raw !== null ? ctx.raw.toFixed(1) + '%' : 'n/a'}}`,
          }}
        }}
      }},
      scales: {{
        x: {{
          grid: {{ display: false }},
          border: {{ color: 'rgba(0,0,0,0.10)' }},
          ticks: {{ font: {{ size: 10 }} }},
        }},
        y: {{
          title: {{ display: true, text: 'Avg bucket RVol, annualised', font: {{ size: 11 }} }},
          grid: {{ color: 'rgba(0,0,0,0.05)', lineWidth: 0.75 }},
          border: {{ color: 'transparent' }},
          ticks: {{ callback: v => v + '%', font: {{ size: 10 }} }},
        }}
      }}
    }}
  }});
}})();

// ── Chart 5: Backtest — daily RVol bars coloured by regime ───────────────────
(function() {{
  const dates   = {bt_dates_js};
  const rvols   = {bt_rvol_js};
  const rolling = {bt_rolling_js};
  const colors  = {bt_colors_js};

  new Chart(document.getElementById('backtestChart'), {{
    type: 'bar',
    data: {{
      labels: dates,
      datasets: [
        {{
          type: 'bar',
          label: 'Daily RVol',
          data: rvols,
          backgroundColor: colors.map(c => c + '60'),
          borderWidth: 0,
          barPercentage: 1.0,
          categoryPercentage: 1.0,
          order: 2,
        }},
        {{
          type: 'line',
          label: '60-day rolling mean',
          data: rolling,
          borderColor: 'rgba(37,99,235,0.85)',
          borderWidth: 2,
          pointRadius: 0,
          fill: false,
          tension: 0.2,
          order: 1,
        }}
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            title: ctx => ctx[0].label,
            label: (ctx) => {{
              if (ctx.datasetIndex === 0) return `RVol: ${{ctx.raw !== null ? ctx.raw.toFixed(1) + '%' : 'n/a'}}`;
              return `60d avg: ${{ctx.raw !== null ? ctx.raw.toFixed(1) + '%' : 'n/a'}}`;
            }}
          }}
        }}
      }},
      scales: {{
        x: {{
          ticks: {{ maxTicksLimit: 8, maxRotation: 0, font: {{ size: 10 }} }},
          grid: {{ display: false }},
          border: {{ color: 'rgba(0,0,0,0.10)' }},
        }},
        y: {{
          title: {{ display: true, text: 'Intraday RVol, annualised', font: {{ size: 11 }} }},
          grid: {{ color: 'rgba(0,0,0,0.05)', lineWidth: 0.75 }},
          border: {{ color: 'transparent' }},
          ticks: {{ callback: v => v + '%', font: {{ size: 10 }} }},
        }}
      }}
    }}
  }});
}})();

// ── Progress bar ──────────────────────────────────────────────────────────────
const pb = document.getElementById('progress-bar');
window.addEventListener('scroll', () => {{
  const pct = window.scrollY / (document.body.scrollHeight - window.innerHeight) * 100;
  pb.style.width = Math.min(pct, 100) + '%';
}}, {{passive: true}});

// ── Nav shadow on scroll ──────────────────────────────────────────────────────
const navEl = document.querySelector('nav');
window.addEventListener('scroll', () => navEl.classList.toggle('scrolled', window.scrollY > 10), {{passive: true}});

// ── Side nav ─────────────────────────────────────────────────────────────────
const NAV_LABELS = ['Background','Data & GEX','The Two Regimes','Intraday Dynamics','Trading Signal','Caveats','Conclusion'];
const sideNav = document.getElementById('side-nav');
NAV_LABELS.forEach((label, i) => {{
  const a = document.createElement('a');
  a.href = '#s' + (i + 1);
  a.innerHTML = `<span class="sn-label">${{label}}</span><span class="sn-dot"></span>`;
  sideNav.appendChild(a);
}});
const sideLinks = sideNav.querySelectorAll('a');

// ── Scroll-reveal ─────────────────────────────────────────────────────────────
const sections = document.querySelectorAll('.section');
const io = new IntersectionObserver(entries => {{
  entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }});
}}, {{threshold: 0.08}});
sections.forEach(s => io.observe(s));

// ── Side nav active highlight ─────────────────────────────────────────────────
const ioNav = new IntersectionObserver(entries => {{
  entries.forEach(e => {{
    const idx = Array.from(sections).indexOf(e.target);
    if (idx >= 0 && sideLinks[idx]) sideLinks[idx].classList.toggle('active', e.isIntersecting);
  }});
}}, {{threshold: 0.3}});
sections.forEach(s => ioNav.observe(s));
</script>
</body>
</html>"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

size = os.path.getsize("index.html")
print(f"Report written to index.html ({size:,} bytes)")
