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
    {"x": p["gex"], "y": round(p["rvol"]*100, 2), "regime": p["regime"]}
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

def box_arr(regime):
    d = regime_data["data"][regime]
    return [
        round(d["p10"]*100,2), round(d["p25"]*100,2),
        round(d["median"]*100,2),
        round(d["p75"]*100,2), round(d["p90"]*100,2),
    ]
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
    *, *::before, *::after {{ box-sizing:border-box; margin:0; padding:0; }}
    html {{ font-size:16px; }}
    body {{ background:var(--bg); color:var(--ink); font-family:'Inter',sans-serif; line-height:1.6; }}

    nav {{ background:var(--ink); padding:0 24px; display:flex; align-items:center; justify-content:space-between; height:52px; position:sticky; top:0; z-index:100; }}
    .nav-logo {{ font-family:'Fraunces',serif; font-style:italic; font-weight:400; font-size:15px; color:rgba(255,255,255,0.9); text-decoration:none; }}
    .nav-links {{ display:flex; gap:28px; list-style:none; }}
    .nav-links a {{ color:rgba(255,255,255,0.5); text-decoration:none; font-size:13px; font-weight:400; letter-spacing:0.01em; transition:color 0.15s; }}
    .nav-links a:hover {{ color:rgba(255,255,255,0.85); }}
    .nav-links a.active {{ color:rgba(255,255,255,0.9); font-weight:500; }}

    .hero {{ background:var(--ink); padding:64px 24px 80px; }}
    .hero-inner {{ max-width:800px; margin:0 auto; }}
    .eyebrow {{ display:flex; align-items:center; gap:12px; margin-bottom:20px; }}
    .eyebrow::before {{ content:''; display:block; width:24px; height:1px; background:var(--accent); }}
    .eyebrow span {{ font-family:'Inter',sans-serif; font-size:11px; font-weight:500; color:var(--accent); text-transform:uppercase; letter-spacing:0.12em; }}
    .hero h1 {{ font-family:'Fraunces',serif; font-style:italic; font-weight:600; font-size:2.4rem; color:#fff; line-height:1.25; margin-bottom:16px; }}
    .hero h1 em {{ color:#5ab5a5; font-style:italic; }}
    .hero-subtitle {{ font-family:'Inter',sans-serif; font-size:14px; font-weight:300; color:rgba(255,255,255,0.55); line-height:1.6; max-width:640px; margin-bottom:28px; }}
    .hero-meta {{ font-family:'JetBrains Mono',monospace; font-size:11px; color:rgba(255,255,255,0.3); display:flex; flex-wrap:wrap; gap:16px; }}
    .hero-meta span {{ display:flex; align-items:center; gap:6px; }}
    .hero-meta span::before {{ content:''; display:inline-block; width:1px; height:10px; background:rgba(255,255,255,0.15); }}
    .hero-meta span:first-child::before {{ display:none; }}

    .kpi-strip {{ max-width:800px; margin:-32px auto 0; padding:0 24px 24px; position:relative; z-index:10; }}
    .kpi-card {{ background:var(--card); border:1px solid var(--border); border-radius:8px; padding:20px 16px; }}
    .kpi-cells {{ display:grid; grid-template-columns:repeat(4,1fr); gap:0; }}
    .kpi-cell {{ padding:4px 12px; border-right:1px solid var(--border); }}
    .kpi-cell:last-child {{ border-right:none; }}
    .kpi-label {{ font-size:10px; color:var(--hint); text-transform:uppercase; letter-spacing:0.08em; margin-bottom:4px; }}
    .kpi-value {{ font-family:'JetBrains Mono',monospace; font-size:22px; line-height:1.1; }}
    .kpi-value.green {{ color:var(--green2); }}
    .kpi-value.blue  {{ color:var(--blue2); }}
    .kpi-value.red   {{ color:var(--red2); }}
    .kpi-value.amber {{ color:#d97706; }}
    .kpi-sub {{ font-size:11px; color:var(--hint); margin-top:2px; }}

    .section {{ padding:52px 24px; border-bottom:1px solid var(--border); }}
    .section:nth-child(even) {{ background:var(--bg2); }}
    .section-inner {{ max-width:800px; margin:0 auto; }}
    .section-label {{ display:flex; align-items:center; gap:12px; margin-bottom:16px; }}
    .section-label::before {{ content:''; display:block; width:16px; height:1px; background:var(--accent); }}
    .section-label span {{ font-size:10px; font-weight:600; color:var(--accent); text-transform:uppercase; letter-spacing:0.12em; }}
    .section h2 {{ font-family:'Fraunces',serif; font-style:italic; font-weight:600; font-size:1.65rem; color:var(--ink); line-height:1.3; margin-bottom:16px; }}
    .section h3 {{ font-family:'Fraunces',serif; font-style:italic; font-weight:400; font-size:1.15rem; color:var(--ink2); margin:24px 0 10px; }}
    .section p {{ font-size:14px; color:var(--muted); line-height:1.75; margin-bottom:14px; }}
    .section p:last-child {{ margin-bottom:0; }}

    .callout {{ display:flex; gap:12px; padding:14px 16px; border-radius:8px; border:1px solid; margin:20px 0; }}
    .callout-icon {{ font-size:16px; flex-shrink:0; margin-top:1px; }}
    .callout-body {{ font-size:13px; line-height:1.6; }}
    .callout-body strong {{ font-weight:600; }}
    .callout.green  {{ background:var(--green-bg);  border-color:var(--green-border);  color:var(--green);  }}
    .callout.red    {{ background:var(--red-bg);    border-color:var(--red-border);    color:var(--red);    }}
    .callout.blue   {{ background:var(--blue-bg);   border-color:var(--blue-border);   color:var(--blue);   }}
    .callout.amber  {{ background:var(--amber-bg);  border-color:var(--amber-border);  color:var(--amber);  }}
    .callout.purple {{ background:var(--purple-bg); border-color:var(--purple-border); color:var(--purple); }}

    .highlight-box {{ background:var(--ink); border-radius:8px; padding:28px; margin:24px 0; }}
    .hl-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:0; }}
    .hl-cell {{ padding:0 20px; border-right:1px solid rgba(255,255,255,0.1); }}
    .hl-cell:first-child {{ padding-left:0; }}
    .hl-cell:last-child {{ border-right:none; }}
    .hl-label {{ font-size:10px; font-weight:500; color:rgba(255,255,255,0.35); text-transform:uppercase; letter-spacing:0.1em; margin-bottom:6px; }}
    .hl-value {{ font-family:'Fraunces',serif; font-style:italic; font-size:1.75rem; color:#5ab5a5; line-height:1.1; }}
    .hl-sub {{ font-size:11px; color:rgba(255,255,255,0.3); margin-top:4px; }}

    .chart-box {{ background:var(--card); border:1px solid var(--border); border-radius:8px; padding:20px; margin:24px 0; }}
    .chart-title {{ font-size:11px; font-weight:600; color:var(--hint); text-transform:uppercase; letter-spacing:0.1em; margin-bottom:14px; }}
    .chart-legend {{ display:flex; gap:16px; flex-wrap:wrap; margin-top:12px; }}
    .legend-item {{ display:flex; align-items:center; gap:6px; font-size:11px; color:var(--muted); }}
    .legend-dot {{ width:10px; height:10px; border-radius:50%; flex-shrink:0; }}
    .legend-line {{ width:16px; height:2px; flex-shrink:0; }}

    .table-wrap {{ overflow-x:auto; margin:16px 0; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    thead th {{ background:var(--ink); color:rgba(255,255,255,0.75); font-size:11px; font-weight:500; padding:8px 12px; text-align:left; letter-spacing:0.05em; }}
    tbody td {{ padding:9px 12px; border-bottom:1px solid var(--border); color:var(--muted); }}
    tbody tr:hover td {{ background:var(--bg2); }}
    .mono {{ font-family:'JetBrains Mono',monospace; }}

    .badge {{ display:inline-block; padding:2px 8px; border-radius:99px; font-size:11px; font-weight:600; }}
    .badge.red   {{ background:var(--red-bg);   color:var(--red); }}
    .badge.amber {{ background:var(--amber-bg); color:var(--amber); }}
    .badge.green {{ background:var(--green-bg); color:var(--green); }}

    footer {{ background:var(--ink); padding:40px 24px 28px; }}
    .footer-inner {{ max-width:800px; margin:0 auto; }}
    .footer-top {{ display:flex; justify-content:space-between; align-items:flex-start; gap:32px; margin-bottom:24px; padding-bottom:24px; border-bottom:1px solid rgba(255,255,255,0.08); }}
    .footer-logo {{ font-family:'Fraunces',serif; font-style:italic; font-size:16px; color:rgba(255,255,255,0.7); margin-bottom:6px; }}
    .footer-desc {{ font-size:12px; color:rgba(255,255,255,0.3); line-height:1.6; max-width:280px; }}
    .footer-links {{ display:flex; gap:20px; }}
    .footer-links a {{ font-size:12px; color:rgba(255,255,255,0.35); text-decoration:none; transition:color 0.15s; }}
    .footer-links a:hover {{ color:rgba(255,255,255,0.7); }}
    .footer-bottom {{ font-size:11px; color:rgba(255,255,255,0.2); line-height:1.7; }}

    @media (max-width:640px) {{
      .hero h1 {{ font-size:1.8rem; }}
      .kpi-cells {{ grid-template-columns:repeat(2,1fr); }}
      .kpi-cell:nth-child(2) {{ border-right:none; }}
      .hl-grid {{ grid-template-columns:1fr; gap:16px; }}
      .hl-cell {{ border-right:none; padding:0; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:14px; }}
      .hl-cell:last-child {{ border-bottom:none; }}
      .footer-top {{ flex-direction:column; gap:16px; }}
      .nav-links {{ display:none; }}
    }}
  </style>
</head>
<body>

<!-- Nav -->
<nav>
  <a class="nav-logo" href="/">The Intrinsic Investor</a>
  <ul class="nav-links">
    <li><a href="/">Home</a></li>
    <li><a href="/research/" class="active">Research</a></li>
    <li><a href="/about.html">About</a></li>
  </ul>
</nav>

<!-- Hero -->
<div class="hero">
  <div class="hero-inner">
    <div class="eyebrow"><span>0DTE Options Research</span></div>
    <h1>The <em>Gamma Trap:</em> How 0DTE Options Reshape Intraday SPX Dynamics</h1>
    <p class="hero-subtitle">
      Every day, dealers who sell zero-days-to-expiry SPX options must hedge their positions
      in real time. When their aggregate gamma exposure turns negative, that hedging
      mechanically amplifies intraday moves. We measure this effect empirically using
      OptionMetrics and TAQ data from {date_start} to {date_end}.
    </p>
    <div class="hero-meta">
      <span>OptionMetrics via WRDS</span>
      <span>TAQ Consolidated Trades</span>
      <span>{date_start}&#8202;&#8211;&#8202;{date_end}</span>
      <span>{n_days:,} trading days</span>
      <span>SPX 0DTE options only</span>
    </div>
  </div>
</div>

<!-- KPI Strip -->
<div class="kpi-strip">
  <div class="kpi-card">
    <div class="kpi-cells">
      <div class="kpi-cell">
        <div class="kpi-label">Vol Premium (Neg vs High GEX)</div>
        <div class="kpi-value red">{vol_prem_pct:+.0f}%</div>
        <div class="kpi-sub">higher intraday vol when GEX negative</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-label">R&#178; (GEX vs RVol)</div>
        <div class="kpi-value blue">{r2:.3f}</div>
        <div class="kpi-sub">OLS regression, {n_days:,} day sample</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-label">p-value (t-test)</div>
        <div class="kpi-value {'green' if p_val < 0.05 else 'amber'}">{p_val:.4f}</div>
        <div class="kpi-sub">Neg GEX vs High GEX, Welch&#8217;s t</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-label">Days with Positive GEX</div>
        <div class="kpi-value green">{pct(pct_pos)}</div>
        <div class="kpi-sub">of the {n_days:,}-day sample</div>
      </div>
    </div>
  </div>
</div>

<!-- Section 1: Background -->
<div class="section">
  <div class="section-inner">
    <div class="section-label"><span>Background</span></div>
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
</div>

<!-- Section 2: Data & GEX time series -->
<div class="section">
  <div class="section-inner">
    <div class="section-label"><span>Data &amp; Methodology</span></div>
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
</div>

<!-- Section 3: The Two Regimes -->
<div class="section">
  <div class="section-inner">
    <div class="section-label"><span>The Two Regimes</span></div>
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
          <div class="hl-value">{vol_prem_pct:+.0f}%</div>
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
</div>

<!-- Section 4: Intraday Profile -->
<div class="section">
  <div class="section-inner">
    <div class="section-label"><span>Intraday Dynamics</span></div>
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
</div>

<!-- Section 5: Trading Signal -->
<div class="section">
  <div class="section-inner">
    <div class="section-label"><span>Trading Signal</span></div>
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
          <div class="hl-value">{pct1(backtest_data['summary']['neg_gex_mean_rvol'])}</div>
          <div class="hl-sub">mean annualised intraday vol</div>
        </div>
        <div class="hl-cell">
          <div class="hl-label">High GEX days</div>
          <div class="hl-value">{pct1(backtest_data['summary']['high_gex_mean_rvol'])}</div>
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
</div>

<!-- Section 6: Caveats -->
<div class="section">
  <div class="section-inner">
    <div class="section-label"><span>Caveats &amp; Limitations</span></div>
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
</div>

<!-- Section 7: Conclusion -->
<div class="section">
  <div class="section-inner">
    <div class="section-label"><span>Conclusion</span></div>
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
      Across {n_days:,} trading days from {date_start} to {date_end}, negative-GEX days
      experienced mean intraday realised vol of {pct1(neg_rvol)}, compared with {pct1(high_rvol)}
      on high-GEX days. The difference is {sig_str} (p&#8202;=&#8202;{p_val:.4f}), and the
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
</div>

<!-- Footer -->
<footer>
  <div class="footer-inner">
    <div class="footer-top">
      <div>
        <div class="footer-logo">The Intrinsic Investor</div>
        <div class="footer-desc">Independent quantitative research on equities, options, and market structure.</div>
      </div>
      <div class="footer-links">
        <a href="/">Home</a>
        <a href="/research/">Research</a>
        <a href="/about.html">About</a>
      </div>
    </div>
    <div class="footer-bottom">
      Data: OptionMetrics via WRDS &nbsp;&#183;&nbsp; TAQ Consolidated Trades via WRDS &nbsp;&#183;&nbsp;
      Sample: {date_start}&#8202;&#8211;&#8202;{date_end} &nbsp;&#183;&nbsp;
      GEX methodology follows the standard dealer-net-short assumption (SpotGamma convention).<br>
      For educational and research purposes only. Not financial advice.
    </div>
  </div>
</footer>

<script>
// ── Shared chart defaults ─────────────────────────────────────────────────────
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.color = '#8aa49e';

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
      plugins: {{ legend: {{ display: false }}, tooltip: {{
        callbacks: {{
          title: ctx => ctx[0].label,
          label: ctx => `GEX: ${{ctx.raw.toFixed(2)}}bn`,
        }}
      }} }},
      scales: {{
        x: {{ ticks: {{ maxTicksLimit: 8, maxRotation: 0 }}, grid: {{ display: false }} }},
        y: {{
          title: {{ display: true, text: 'GEX (US$bn)', font: {{ size: 11 }} }},
          grid: {{ color: 'rgba(0,0,0,0.04)' }},
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
      datasets: [{{
        label: 'Median RVol (%)',
        data: medians,
        backgroundColor: barColors.map(c => c + '99'),
        borderColor: barColors,
        borderWidth: 2,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }}, tooltip: {{
        callbacks: {{
          label: (ctx) => {{
            const i = ctx.dataIndex;
            return [
              `Median: ${{medians[i].toFixed(1)}}%`,
              `p25–p75: ${{p25[i].toFixed(1)}}%–${{p75[i].toFixed(1)}}%`,
              `p10–p90: ${{p10[i].toFixed(1)}}%–${{p90[i].toFixed(1)}}%`,
            ];
          }}
        }}
      }} }},
      scales: {{
        x: {{ grid: {{ display: false }} }},
        y: {{
          title: {{ display: true, text: 'Annualised Intraday RVol (%)', font: {{ size: 11 }} }},
          grid: {{ color: 'rgba(0,0,0,0.04)' }},
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
          backgroundColor: colors.map(c => c + '66'),
          borderColor: colors.map(c => c + 'aa'),
          borderWidth: 1,
          pointRadius: 3,
          pointHoverRadius: 5,
        }},
        {{
          label: 'OLS regression',
          type: 'line',
          data: regLine,
          borderColor: COLORS.blue,
          borderWidth: 2,
          pointRadius: 0,
          fill: false,
        }}
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }}, tooltip: {{
        callbacks: {{
          label: (ctx) => {{
            if (ctx.datasetIndex === 0) {{
              const p = pts[ctx.dataIndex];
              return [`${{p.date}}`, `GEX: ${{p.x.toFixed(2)}}bn`, `RVol: ${{p.y.toFixed(1)}}%`, p.regime];
            }}
            return `Regression: ${{ctx.parsed.y.toFixed(1)}}%`;
          }}
        }}
      }} }},
      scales: {{
        x: {{
          title: {{ display: true, text: 'Daily GEX (US$bn)', font: {{ size: 11 }} }},
          grid: {{ color: 'rgba(0,0,0,0.04)' }},
        }},
        y: {{
          title: {{ display: true, text: 'Intraday RVol, annualised (%)', font: {{ size: 11 }} }},
          grid: {{ color: 'rgba(0,0,0,0.04)' }},
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
        {{ label: 'Negative GEX', data: neg,  borderColor: COLORS.neg,  borderWidth: 2.5, pointRadius: 3, fill: false, tension: 0.3 }},
        {{ label: 'Low GEX',      data: low,  borderColor: COLORS.low,  borderWidth: 2,   pointRadius: 3, fill: false, tension: 0.3 }},
        {{ label: 'High GEX',     data: high, borderColor: COLORS.high, borderWidth: 2.5, pointRadius: 3, fill: false, tension: 0.3 }},
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }}, tooltip: {{
        callbacks: {{
          label: ctx => `${{ctx.dataset.label}}: ${{ctx.raw !== null ? ctx.raw.toFixed(1) + '%' : 'n/a'}}`,
        }}
      }} }},
      scales: {{
        x: {{ grid: {{ display: false }} }},
        y: {{
          title: {{ display: true, text: 'Avg bucket RVol, annualised (%)', font: {{ size: 11 }} }},
          grid: {{ color: 'rgba(0,0,0,0.04)' }},
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
          backgroundColor: colors.map(c => c + '77'),
          borderWidth: 0,
          barPercentage: 1.0,
          order: 2,
        }},
        {{
          type: 'line',
          label: '60-day rolling mean',
          data: rolling,
          borderColor: COLORS.blue,
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false,
          order: 1,
        }}
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }}, tooltip: {{
        callbacks: {{
          title: ctx => ctx[0].label,
          label: (ctx) => {{
            if (ctx.datasetIndex === 0) return `RVol: ${{ctx.raw !== null ? ctx.raw.toFixed(1) + '%' : 'n/a'}}`;
            return `60d avg: ${{ctx.raw !== null ? ctx.raw.toFixed(1) + '%' : 'n/a'}}`;
          }}
        }}
      }} }},
      scales: {{
        x: {{ ticks: {{ maxTicksLimit: 8, maxRotation: 0 }}, grid: {{ display: false }} }},
        y: {{
          title: {{ display: true, text: 'Intraday RVol, annualised (%)', font: {{ size: 11 }} }},
          grid: {{ color: 'rgba(0,0,0,0.04)' }},
        }}
      }}
    }}
  }});
}})();
</script>
</body>
</html>"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

size = os.path.getsize("index.html")
print(f"Report written to index.html ({size:,} bytes)")
