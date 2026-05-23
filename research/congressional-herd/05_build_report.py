"""
Build research/congressional-herd/index.html from chart JSON files.
A pointed critique of disclosure-based congressional trading strategies,
built around the disclosure-lag thesis.
"""

import datetime
import json
from pathlib import Path

HERE = Path(__file__).parent
CHARTS = HERE / "charts"
OUT = HERE / "index.html"


def load(name):
    with open(CHARTS / name) as f:
        return json.load(f)


lag         = load("lag_histogram.json")
largest     = load("largest_herds.json")
top_buys    = load("top_herded_tickers.json")
sector      = load("sector_breakdown.json")
party_ch    = load("party_chamber.json")
tvd         = load("trade_vs_disc_returns.json")
committee   = load("committee_jurisdiction.json")
etf         = load("etf_performance.json")
kpi         = load("kpi_strip.json")
curve       = load("forward_returns_curve.json")
sens        = load("sensitivity_heatmap.json")
sell_sens   = load("sell_sensitivity_heatmap.json")
sells       = load("sell_herd_returns.json")
cum         = load("cumulative_returns.json")



# ── Formatters ────────────────────────────────────────────────────────────────

def pct(v, decimals=1, signed=True):
    if v is None:
        return "N/A"
    fmt = f"{{:+.{decimals}f}}%" if signed else f"{{:.{decimals}f}}%"
    return fmt.format(v * 100)


def fmt(v, decimals=2, signed=True):
    if v is None:
        return "N/A"
    fmt = f"{{:+.{decimals}f}}" if signed else f"{{:.{decimals}f}}"
    return fmt.format(v)


def js_array(lst):
    def _v(x):
        if x is None:
            return "null"
        if isinstance(x, str):
            return json.dumps(x)
        return repr(x) if isinstance(x, float) else str(x)
    return "[" + ", ".join(_v(x) for x in lst) + "]"


# ── Heatmap color (sensitivity) ───────────────────────────────────────────────

_C_RED   = (254, 202, 202)
_C_PARCH = (247, 244, 236)
_C_GREEN = (187, 247, 208)


def _lerp(t, lo, hi):
    return "#{:02x}{:02x}{:02x}".format(
        int(lo[0] + t * (hi[0] - lo[0])),
        int(lo[1] + t * (hi[1] - lo[1])),
        int(lo[2] + t * (hi[2] - lo[2])),
    )


def _cell_color(v):
    if v is None:
        return "#f7f4ec"
    t = max(0.0, min(1.0, v))
    if t < 0.5:
        return _lerp(t * 2, _C_RED, _C_PARCH)
    return _lerp((t - 0.5) * 2, _C_PARCH, _C_GREEN)


def _cell_color_excess(v):
    if v is None:
        return "#f7f4ec"
    # Scale [-0.02, 0.02] to [0.0, 1.0] for the lerp
    t = (v + 0.02) / 0.04
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return _lerp(t * 2, _C_RED, _C_PARCH)
    return _lerp((t - 0.5) * 2, _C_PARCH, _C_GREEN)


def build_sens_table():
    thresholds = sens["thresholds"]
    windows    = sens["windows"]
    rows_me    = sens["mean_excess"]
    rows_n     = sens["n_events"]
    cols = "".join(f'<th class="hm-col">{w}d</th>' for w in windows)
    html = f"""
<div class="chart-title" style="margin-top:2rem;text-align:center;">Sensitivity Heatmap (10-day Mean Excess Return vs SPY)</div>
<div class="hm-wrap">
<table class="hm-table">
  <thead>
    <tr>
      <th class="hm-corner">Min politicians</th>
      {cols}
    </tr>
  </thead>
  <tbody>"""
    for i, thr in enumerate(thresholds):
        html += f'\n    <tr>\n      <td class="hm-row-label">{thr}+</td>'
        for j, win in enumerate(windows):
            me  = rows_me[i][j]
            n   = rows_n[i][j]
            bg  = _cell_color_excess(me)
            txt = (f"{me * 100:+.2f}%" if me is not None else "&#8212;")
            sub = f'<br><span style="font-size:.65rem;color:#8aa49e">n={n}</span>'
            html += f'\n      <td class="hm-cell" style="background:{bg}">{txt}{sub}</td>'
        html += "\n    </tr>"
    html += "\n  </tbody>\n</table>\n</div>"
    return html


def build_sell_sens_table():
    thresholds = sell_sens["thresholds"]
    windows    = sell_sens["windows"]
    rows_me    = sell_sens["mean_excess"]
    rows_n     = sell_sens["n_events"]
    cols = "".join(f'<th class="hm-col">{w}d</th>' for w in windows)
    html = f"""
<div class="chart-title" style="margin-top:2rem;text-align:center;">Sell Sensitivity Heatmap (10-day Mean Excess Return vs SPY)</div>
<div class="hm-wrap">
<table class="hm-table">
  <thead>
    <tr>
      <th class="hm-corner">Min politicians</th>
      {cols}
    </tr>
  </thead>
  <tbody>"""
    for i, thr in enumerate(thresholds):
        html += f'\n    <tr>\n      <td class="hm-row-label">{thr}+</td>'
        for j, win in enumerate(windows):
            me  = rows_me[i][j]
            n   = rows_n[i][j]
            bg  = _cell_color_excess(me)
            txt = (f"{me * 100:+.2f}%" if me is not None else "&#8212;")
            sub = f'<br><span style="font-size:.65rem;color:#8aa49e">n={n}</span>'
            html += f'\n      <td class="hm-cell" style="background:{bg}">{txt}{sub}</td>'
        html += "\n    </tr>"
    html += "\n  </tbody>\n</table>\n</div>"
    return html


# ── Largest herds table ──────────────────────────────────────────────────────

def build_largest_herds_table():
    html = """
<table class="data-table">
  <thead>
    <tr>
      <th>Ticker</th>
      <th>Window start</th>
      <th style="text-align:right">Politicians</th>
      <th>Names</th>
      <th style="text-align:right">10d excess vs SPY</th>
    </tr>
  </thead>
  <tbody>"""
    for row in largest:
        excess = row["excess_10d"]
        if excess is None:
            exc_str = '<span style="color:var(--hint)">Censored</span>'
            exc_color = ""
        elif excess >= 0:
            exc_str = f'+{excess * 100:.1f}%'
            exc_color = 'color:var(--green2)'
        else:
            exc_str = f'{excess * 100:.1f}%'
            exc_color = 'color:var(--red2)'
        html += f"""
    <tr>
      <td style="font-family:var(--mono);font-weight:600">{row['ticker']}</td>
      <td style="font-family:var(--mono)">{row['window_start']}</td>
      <td style="text-align:right;font-family:var(--mono)">{row['politician_count']}</td>
      <td style="font-size:.75rem;color:var(--muted)">{row['politicians_preview']}</td>
      <td style="text-align:right;font-family:var(--mono);{exc_color}">{exc_str}</td>
    </tr>"""
    html += "\n  </tbody>\n</table>"
    return html


def build_sector_table():
    html = """
<table class="data-table">
  <thead>
    <tr>
      <th>Sector</th>
      <th style="text-align:right">n</th>
      <th style="text-align:right">Win rate</th>
      <th style="text-align:right">Mean 10d excess</th>
    </tr>
  </thead>
  <tbody>"""
    for row in sector:
        wr  = f"{row['win_rate_10d'] * 100:.1f}%"
        exc = row["mean_excess_10d"]
        if exc >= 0:
            exc_str   = f'+{exc * 100:.1f}%'
            exc_color = 'color:var(--green2)'
        else:
            exc_str   = f'{exc * 100:.1f}%'
            exc_color = 'color:var(--red2)'
        html += f"""
    <tr>
      <td>{row['sector']}</td>
      <td style="text-align:right;font-family:var(--mono)">{row['n_events']}</td>
      <td style="text-align:right;font-family:var(--mono)">{wr}</td>
      <td style="text-align:right;font-family:var(--mono);{exc_color}">{exc_str}</td>
    </tr>"""
    html += "\n  </tbody>\n</table>"
    return html


def build_committee_table():
    """Show in-jurisdiction vs non-sector for categories with adequate samples."""
    html = """
<table class="data-table">
  <thead>
    <tr>
      <th>Committee category</th>
      <th>Cohort</th>
      <th style="text-align:right">n</th>
      <th style="text-align:right">Mean 10d excess</th>
      <th style="text-align:right">Win rate</th>
    </tr>
  </thead>
  <tbody>"""
    for c in committee["categories"]:
        cat = c["category"]
        for cohort_key, cohort_label in [
            ("in_jurisdiction", "In-jurisdiction (member on relevant cmte)"),
            ("non_sector", "Same members, buying other sectors"),
        ]:
            d = c.get(cohort_key, {})
            n = d.get("n", 0)
            me = d.get("mean_excess")
            wr = d.get("win_rate")
            if me is None:
                exc_str = '<span style="color:var(--hint)">n too small</span>'
                exc_color = ""
            elif me >= 0:
                exc_str = f'+{me * 100:.1f}%'
                exc_color = 'color:var(--green2)'
            else:
                exc_str = f'{me * 100:.1f}%'
                exc_color = 'color:var(--red2)'
            wr_str = f"{wr * 100:.1f}%" if wr is not None else "&#8212;"
            html += f"""
    <tr>
      <td>{cat if cohort_key == "in_jurisdiction" else ""}</td>
      <td style="font-size:.78rem;color:var(--muted)">{cohort_label}</td>
      <td style="text-align:right;font-family:var(--mono)">{n}</td>
      <td style="text-align:right;font-family:var(--mono);{exc_color}">{exc_str}</td>
      <td style="text-align:right;font-family:var(--mono)">{wr_str}</td>
    </tr>"""
    html += "\n  </tbody>\n</table>"
    return html


def build_top_sold_table():
    html = """
<table class="data-table">
  <thead>
    <tr>
      <th>Ticker</th>
      <th style="text-align:right">Sell herd count</th>
      <th style="text-align:right">Mean 10d excess</th>
      <th style="text-align:right">n with returns</th>
    </tr>
  </thead>
  <tbody>"""
    for row in sells["top_sold_tickers"]:
        exc = row["mean_excess_10d"]
        if exc is None:
            exc_str = '<span style="color:var(--hint)">N/A</span>'
            exc_color = ""
        elif exc >= 0:
            exc_str = f'+{exc * 100:.1f}%'
            exc_color = 'color:var(--green2)'
        else:
            exc_str = f'{exc * 100:.1f}%'
            exc_color = 'color:var(--red2)'
        html += f"""
    <tr>
      <td style="font-family:var(--mono);font-weight:600">{row['ticker']}</td>
      <td style="text-align:right;font-family:var(--mono)">{row['event_count']}</td>
      <td style="text-align:right;font-family:var(--mono);{exc_color}">{exc_str}</td>
      <td style="text-align:right;font-family:var(--mono)">{row['n_with_returns']}</td>
    </tr>"""
    html += "\n  </tbody>\n</table>"
    return html


# ── Chart data arrays for JS ─────────────────────────────────────────────────

lag_labels    = js_array(lag["bin_labels"])
lag_counts    = js_array(lag["counts"])

curve_labels  = js_array([f"{h}d" for h in curve["horizons"]])
curve_mean    = js_array(curve["mean_excess"])
curve_p25     = js_array(curve["p25_excess"])
curve_p75     = js_array(curve["p75_excess"])

tvd_labels    = js_array(cum["dates"])
tvd_disc      = js_array(cum["cum_disc"])
tvd_trade     = js_array(cum["cum_trade"])
tvd_spy       = js_array(cum["cum_spy_trade"])

sector_labels = js_array([r["sector"] for r in sector])
sector_exc    = js_array([r["mean_excess_10d"] for r in sector])

etf_nanc_d    = js_array(etf["series"]["NANC"]["dates"])
etf_nanc_v    = js_array(etf["series"]["NANC"]["values"])
etf_kruz_v    = js_array(etf["series"]["KRUZ"]["values"])
etf_spy_v     = js_array(etf["series"]["SPY"]["values"])

sells_curve_labels = js_array([f"{h}d" for h in sells["curve"]["horizons"]])
sells_curve_data   = js_array(sells["curve"]["mean_excess"])
sells_curve_p25    = js_array(sells["curve"]["p25_excess"])
sells_curve_p75    = js_array(sells["curve"]["p75_excess"])


# ── Pre-rendered HTML pieces ──────────────────────────────────────────────────

largest_html   = build_largest_herds_table()
sector_html    = build_sector_table()
sens_html      = build_sens_table()
committee_html = build_committee_table()
top_sold_html  = build_top_sold_table()
sell_sens_html = build_sell_sens_table()


# ── KPI / hero values ─────────────────────────────────────────────────────────

lag_median       = int(lag["median"])
lag_mean         = lag["mean"]
lag_n            = lag["n_valid"]
lag_over_45_pct  = lag["n_over_45"] / lag["n_valid"] * 100

lag_period_excess_str = pct(tvd["lag_period_mean_excess"])
lag_period_return_str = pct(tvd["lag_period_mean_return"])
lag_period_winrate    = tvd["lag_period_win_rate"] * 100

kpi_n   = kpi["n_events"]
kpi_wr  = kpi["win_rate_10d"] * 100
kpi_exc = pct(kpi["mean_excess_10d"])
kpi_sharpe = fmt(kpi["sharpe_10d"])
kpi_t   = fmt(kpi["t_stat_10d"])

# ETF stats
nanc = etf["series"]["NANC"]
kruz = etf["series"]["KRUZ"]
spy  = etf["series"]["SPY"]
nanc_cum_str = pct(nanc["cum_return"])
kruz_cum_str = pct(kruz["cum_return"])
spy_cum_str  = pct(spy["cum_return"])
nanc_sharpe  = fmt(nanc["sharpe"])
kruz_sharpe  = fmt(kruz["sharpe"])
spy_sharpe   = fmt(spy["sharpe"])
etf_start    = etf["start_date"]

# Sells
sell_n = sells["kpi"]["n_events"]
sell_exc = pct(sells["kpi"]["mean_excess_10d"])
sell_t = fmt(sells["kpi"]["t_stat_10d"])
sell_wr = sells["kpi"]["win_rate_10d"] * 100

max_date_str = etf["series"]["SPY"]["dates"][-1]
max_date_obj = datetime.datetime.strptime(max_date_str, "%Y-%m-%d")
max_year = max_date_obj.strftime("%Y")
max_month = max_date_obj.strftime("%b")


# ── HTML ─────────────────────────────────────────────────────────────────────

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Disclosure-Lag Trap: Why Following Congress Doesn't Work | The Intrinsic Investor</title>
<meta property="og:title" content="The Disclosure-Lag Trap: Why Following Congress Doesn't Work">
<meta property="og:description" content="A pointed critique of NANC, KRUZ, and the disclosure-tracking industry. Built on 35,343 STOCK Act filings, the data shows the signal cannot survive the 27-day disclosure lag.">
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
  --red:#E02424;   --red2:#dc2626;   --red-bg:#fef2f2;   --red-border:#fca5a5;
  --blue:#1e40af;  --blue2:#2563eb;  --blue-bg:#eff6ff;  --blue-border:#bfdbfe;
  --amber:#E3A008; --amber-bg:#fffbeb; --amber-border:#fcd34d;
  --purple:#7E3AF2; --purple-bg:#f5f3ff; --purple-border:#c4b5fd;
  --font:'Inter',sans-serif; --serif:'Fraunces',serif; --mono:'JetBrains Mono',monospace;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--ink);font-family:var(--font);font-size:1rem;line-height:1.7;overflow-x:hidden}}
body::after{{content:'';position:fixed;inset:0;pointer-events:none;z-index:9999;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='250' height='250'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.80' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='250' height='250' filter='url(%23noise)' opacity='0.07'/%3E%3C/svg%3E");mix-blend-mode:multiply;opacity:.5}}
#progress-bar{{position:fixed;top:0;left:0;height:2px;width:0%;background:linear-gradient(90deg,#1a5c52,#2d9d8f);z-index:9998;transition:width .1s linear}}
nav{{position:fixed;top:2px;left:0;right:0;z-index:900;display:flex;align-items:center;justify-content:space-between;padding:.85rem 2.5rem;background:rgba(247,244,236,0.92);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);transition:box-shadow .3s}}
nav.scrolled{{box-shadow:0 1px 24px rgba(15,34,32,.06)}}
.nav-logo{{font-family:var(--serif);font-size:1.05rem;font-weight:600;color:var(--ink);text-decoration:none;letter-spacing:-.01em}}
.nav-links{{list-style:none;display:flex;gap:2rem}}
.nav-links a{{font-size:.85rem;color:var(--muted);text-decoration:none;position:relative;padding-bottom:2px;transition:color .2s}}
.nav-links a::after{{content:'';position:absolute;bottom:-1px;left:0;right:0;height:1px;background:var(--accent);transform:scaleX(0);transform-origin:left;transition:transform .25s cubic-bezier(.4,0,.2,1)}}
.nav-links a:hover{{color:var(--ink)}}
.nav-links a:hover::after{{transform:scaleX(1)}}
#side-nav{{position:fixed;right:0;top:50%;transform:translateY(-50%);z-index:50;display:flex;flex-direction:column;gap:2px;padding:10px 6px}}
#side-nav a{{display:flex;align-items:center;justify-content:flex-end;gap:7px;text-decoration:none;padding:5px 8px;border-radius:4px;transition:background .2s}}
#side-nav a:hover{{background:rgba(26,92,82,.07)}}
.sn-label{{font-size:.67rem;font-weight:500;color:var(--hint);white-space:nowrap;letter-spacing:.02em;font-family:var(--font);transition:color .2s;text-align:right}}
.sn-dot{{width:5px;height:5px;border-radius:50%;background:var(--border);flex-shrink:0;transition:all .2s}}
#side-nav a.active .sn-label{{color:var(--accent);font-weight:600}}
#side-nav a.active .sn-dot{{background:var(--accent);transform:scale(1.5)}}
#side-nav a:hover .sn-label{{color:var(--ink)}}
#side-nav a:hover .sn-dot{{background:var(--muted)}}
@media(max-width:980px){{#side-nav{{display:none}}}}
@keyframes fadeUp{{from{{opacity:0;transform:translateY(18px)}}to{{opacity:1;transform:translateY(0)}}}}
.hero{{position:relative;overflow:hidden;background:var(--ink);color:#fff;padding:8rem 2.5rem 5rem}}
.hero::before{{content:'';position:absolute;inset:0;pointer-events:none;background-image:repeating-linear-gradient(-55deg,transparent,transparent 40px,rgba(255,255,255,.013) 40px,rgba(255,255,255,.013) 41px)}}
.hero-inner{{max-width:800px;margin:0 auto;position:relative}}
.hero-tag{{display:inline-block;font-family:var(--mono);font-size:.7rem;font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:rgba(255,255,255,.5);border:1px solid rgba(255,255,255,.18);padding:3px 10px;border-radius:2px;margin-bottom:1.4rem;animation:fadeUp .6s ease both}}
.hero h1{{font-family:var(--serif);font-size:clamp(1.9rem,4.2vw,3rem);font-weight:600;line-height:1.13;letter-spacing:-.02em;color:#fff;margin-bottom:1.2rem;animation:fadeUp .6s .1s ease both}}
.hero h1 em{{color:rgba(255,255,255,.65);font-style:italic}}
.hero-sub{{font-size:1.05rem;color:rgba(255,255,255,.65);max-width:640px;line-height:1.65;animation:fadeUp .6s .2s ease both;text-align:left;hyphens:none}}
.hero-meta{{display:flex;flex-wrap:wrap;gap:.6rem 1.6rem;margin-top:2rem;animation:fadeUp .6s .3s ease both;align-items:center}}
.hero-meta-item{{font-size:.8rem;color:rgba(255,255,255,.45);font-family:var(--mono)}}
.hero-meta-item strong{{display:block;font-size:.6rem;text-transform:uppercase;letter-spacing:.08em;color:rgba(255,255,255,.3);margin-bottom:1px}}
.gh-btn{{display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);font-size:.68rem;color:rgba(255,255,255,.5);text-decoration:none;border:1px solid rgba(255,255,255,.2);padding:3px 9px;border-radius:3px;transition:all .2s;letter-spacing:.02em;align-self:center}}
.gh-btn:hover{{color:#fff;border-color:rgba(255,255,255,.5);background:rgba(255,255,255,.08)}}
.kpi-strip{{background:var(--ink);border-top:1px solid rgba(255,255,255,.06);padding:2rem 2.5rem 2.5rem}}
.kpi-grid{{max-width:900px;margin:0 auto;display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.06);border-radius:4px;overflow:hidden}}
.kpi-cell{{background:rgba(15,34,32,.6);padding:1.4rem 1.2rem;text-align:center}}
.kpi-label{{font-family:var(--mono);font-size:.62rem;text-transform:uppercase;letter-spacing:.1em;color:rgba(255,255,255,.35);margin-bottom:.5rem}}
.kpi-value{{font-family:var(--serif);font-size:2rem;font-weight:600;line-height:1;margin-bottom:.4rem}}
.kpi-value.blue{{color:#93c5fd}}
.kpi-value.green{{color:#6ee7b7}}
.kpi-value.red{{color:#fca5a5}}
.kpi-value.amber{{color:#fcd34d}}
.kpi-sub{{font-family:var(--font);font-size:.7rem;color:rgba(255,255,255,.3);line-height:1.4}}
@media(max-width:600px){{.kpi-grid{{grid-template-columns:repeat(2,1fr)}}}}
.section{{opacity:0;transform:translateY(16px);transition:opacity .55s ease,transform .55s ease;padding:4rem 2.5rem}}
.section.visible{{opacity:1;transform:none}}
.container{{max-width:900px;margin:0 auto}}
.section-label{{display:flex;align-items:center;gap:.6rem;margin-bottom:.8rem}}
.section-counter{{font-family:var(--mono);font-size:.68rem;font-weight:500;color:var(--hint);letter-spacing:.05em}}
.section-label>span:last-child{{font-family:var(--mono);font-size:.68rem;font-weight:500;color:var(--hint);text-transform:uppercase;letter-spacing:.06em}}
h2{{font-family:var(--serif);font-size:clamp(1.45rem,3vw,2rem);font-weight:600;line-height:1.2;letter-spacing:-.015em;color:var(--ink);margin-bottom:1.2rem}}
h2 em{{color:var(--accent);font-style:italic}}
h3{{font-family:var(--serif);font-size:1.15rem;font-weight:600;color:var(--ink);margin:2rem 0 .7rem}}
p{{color:var(--muted);margin-bottom:1rem;text-align:justify;hyphens:none;word-break:normal}}
.chart-box{{background:var(--bg2);border:1px solid var(--border);border-radius:4px;padding:1.5rem 1.5rem 1.2rem;margin:1.8rem 0}}
.chart-title{{font-family:var(--mono);font-size:.72rem;font-weight:500;text-transform:uppercase;letter-spacing:.07em;color:var(--hint);margin-bottom:1rem}}
.chart-legend{{display:flex;flex-wrap:wrap;gap:.5rem 1.2rem;margin-top:.9rem}}
.chart-legend span{{font-size:.72rem;color:var(--hint);display:flex;align-items:center;gap:.35rem;font-family:var(--font)}}
.legend-dot{{display:inline-block;width:10px;height:10px;border-radius:50%}}
.legend-line{{display:inline-block;width:16px;height:2px}}
.highlight-box{{background:var(--ink);color:#fff;border-radius:4px;padding:2rem 1.5rem;margin:1.8rem 0;display:grid;grid-template-columns:repeat(3,1fr);gap:1px}}
.hb-val{{font-family:var(--serif);font-size:2.1rem;font-style:italic;color:#2d9d8f;line-height:1;margin-bottom:.4rem}}
.hb-label{{font-family:var(--mono);font-size:.62rem;text-transform:uppercase;letter-spacing:.08em;color:rgba(255,255,255,.4)}}
.callout{{border-radius:3px;padding:.9rem 1.1rem;margin:1.2rem 0;font-size:.88rem;color:var(--ink);line-height:1.6}}
.callout strong{{display:inline}}
.callout.green{{background:var(--green-bg);border-left:3px solid var(--green-border)}}
.callout.amber{{background:var(--amber-bg);border-left:3px solid var(--amber-border)}}
.callout.red{{background:var(--red-bg);border-left:3px solid var(--red-border)}}
.callout.blue{{background:var(--blue-bg);border-left:3px solid var(--blue-border)}}
.callout.purple{{background:var(--purple-bg);border-left:3px solid var(--purple-border)}}
.data-table{{width:100%;border-collapse:collapse;font-size:.85rem;margin:1rem 0}}
.data-table th{{background:var(--ink);color:rgba(255,255,255,.7);font-family:var(--mono);font-size:.65rem;text-transform:uppercase;letter-spacing:.06em;padding:.6rem .8rem;text-align:left;font-weight:500}}
.data-table td{{padding:.55rem .8rem;border-bottom:1px solid var(--border);color:var(--muted)}}
.data-table tr:last-child td{{border-bottom:none}}
.data-table tr:hover td{{background:var(--bg2)}}
.method-table{{width:100%;border-collapse:collapse;font-size:.85rem;margin:1rem 0}}
.method-table th{{background:var(--ink);color:rgba(255,255,255,.7);font-family:var(--mono);font-size:.65rem;text-transform:uppercase;letter-spacing:.06em;padding:.6rem .8rem;text-align:left;font-weight:500}}
.method-table td{{padding:.55rem .8rem;border-bottom:1px solid var(--border);color:var(--muted);vertical-align:top}}
.method-table td:first-child{{width:170px;font-weight:500;color:var(--ink);white-space:nowrap}}
.method-table tr:last-child td{{border-bottom:none}}
.hm-wrap{{overflow-x:auto;margin:1rem 0}}
.hm-table{{border-collapse:collapse;font-family:var(--mono);font-size:.75rem;margin:0 auto}}
.hm-table thead th,.hm-table tbody td{{border:1px solid var(--border)}}
.hm-corner{{background:var(--bg2);padding:7px 12px}}
.hm-col{{background:var(--ink);color:#fff;font-size:.68rem;font-weight:600;text-transform:uppercase;letter-spacing:.04em;padding:7px 16px;text-align:center}}
.hm-row-label{{background:var(--bg2);color:var(--muted);font-size:.72rem;font-family:var(--font);padding:7px 12px;white-space:nowrap}}
.hm-cell{{text-align:center;color:var(--ink);padding:8px 16px;white-space:nowrap;min-width:90px}}
.hm-primary{{outline:2px solid var(--accent);outline-offset:-2px}}
.industry-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:.9rem;margin:1.5rem 0}}
.industry-card{{background:var(--bg2);border:1px solid var(--border);border-radius:3px;padding:1rem 1.1rem}}
.industry-card .ic-name{{font-family:var(--mono);font-weight:600;color:var(--ink);font-size:.85rem;margin-bottom:.3rem}}
.industry-card .ic-claim{{font-size:.78rem;color:var(--muted);line-height:1.5}}
@media(max-width:640px){{.industry-grid{{grid-template-columns:1fr}}.highlight-box{{grid-template-columns:1fr}}}}
footer{{background:var(--ink);color:rgba(255,255,255,.4);padding:2.5rem 2.5rem}}
.footer-inner{{max-width:900px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem}}
.footer-name{{font-family:var(--serif);font-size:.95rem;color:rgba(255,255,255,.6)}}
.footer-right{{display:flex;gap:1.4rem;font-size:.8rem}}
.footer-right a{{color:rgba(255,255,255,.4);text-decoration:none;transition:color .2s}}
.footer-right a:hover{{color:#fff}}
@media(prefers-reduced-motion:reduce){{*,*::before,*::after{{animation-duration:.01ms!important;transition-duration:.01ms!important}}}}
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

<div id="side-nav" aria-label="Page sections"></div>

<header class="hero">
  <div class="hero-inner">
    <div class="hero-tag">Congressional Trading Critique</div>
    <h1>The Disclosure-Lag Trap: <em>Why Following Congress Doesn't Work</em></h1>
    <p class="hero-sub">
      The Stop Trading on Congressional Knowledge Act gives politicians up to 45 days to disclose their trades. Across 29,071 STOCK Act filings, the median disclosure lag is 27 days. By the time the signal becomes visible, the trade information has been stale for nearly a month. This report shows that the disclosure-following industry, including the NANC and KRUZ ETFs, is selling beta dressed as alpha.
    </p>
    <div class="hero-meta">
      <div class="hero-meta-item"><strong>Author</strong>Brian Liew, BSc Accounting and Finance, LSE</div>
      <div class="hero-meta-item"><strong>Published</strong>May 2025</div>
      <div class="hero-meta-item"><strong>Period</strong>2023 to {max_year}, n={kpi_n} herding events</div>
      <div class="hero-meta-item"><strong>Data</strong>Capitol Trades, CRSP, congress-legislators, Yahoo Finance</div>
      <a href="https://github.com/TheIntrinsicInvestor/Backtesting/tree/main/research/congressional-herd" target="_blank" rel="noopener" class="gh-btn">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
        GitHub Code
      </a>
    </div>
  </div>
</header>

<div class="kpi-strip">
  <div class="kpi-grid">
    <div class="kpi-cell">
      <div class="kpi-label">Median disclosure lag</div>
      <div class="kpi-value amber">{lag_median} days</div>
      <div class="kpi-sub">29,071 valid STOCK Act filings</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">Excess during lag (vs SPY)</div>
      <div class="kpi-value red">{lag_period_excess_str}</div>
      <div class="kpi-sub">n=131. Politicians underperform too</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">Aggregate signal (10d)</div>
      <div class="kpi-value red">{kpi_exc}</div>
      <div class="kpi-sub">n={kpi_n}, t={kpi_t}, indistinguishable from zero</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">KRUZ vs SPY (cumulative)</div>
      <div class="kpi-value red">{pct(kruz['cum_excess_vs_spy'])}</div>
      <div class="kpi-sub">Republican-tracking ETF, Feb 2023 to {max_month} {max_year}</div>
    </div>
  </div>
</div>

<!-- Section 1: The Premise -->
<section class="section" id="s1">
  <div class="container">
    <div class="section-label"><span class="section-counter">01</span><span>The Premise</span></div>
    <h2>An industry built on <em>seeing what politicians see</em></h2>
    <p>
      The Stop Trading on Congressional Knowledge Act of 2012 was meant to deter insider trading by members of Congress and their families by requiring public disclosure of every individual security trade within 45 days. The premise was accountability. Within a few years, the disclosure feed itself became a product. Capitol Trades aggregates the filings into a clean searchable database. Quiver Quantitative monetises the same data behind a subscription paywall. Unusual Whales pushes filings to options-trading retail. r/WallStreetBets has long-running threads dedicated to Nancy Pelosi's portfolio.
    </p>
    <p>
      The two pure-play ETFs are the clearest expression of the thesis. Subversive Capital's Unusual Whales Subversive Democratic Trading ETF (ticker NANC) launched in February 2023 to systematically mirror Democratic members' trades. Its Republican counterpart, KRUZ, does the same for Republican filings. Both charge 0.75% in annual fees. Both pitch themselves on the implicit claim that congressional trading contains information that retail investors can profitably follow.
    </p>
    <div class="industry-grid">
      <div class="industry-card">
        <div class="ic-name">NANC (Subversive Capital)</div>
        <div class="ic-claim">Systematically tracks Democratic members' disclosed trades. 0.75% expense ratio. Marketed on the implicit premise that following Pelosi and her colleagues delivers alpha.</div>
      </div>
      <div class="industry-card">
        <div class="ic-name">KRUZ (Subversive Capital)</div>
        <div class="ic-claim">Republican-side equivalent. 0.75% expense ratio. Same disclosure-driven mechanism, opposite political universe.</div>
      </div>
      <div class="industry-card">
        <div class="ic-name">Quiver Quantitative</div>
        <div class="ic-claim">Subscription product packaging the same public STOCK Act feed with charts, alerts, and politician scorecards.</div>
      </div>
      <div class="industry-card">
        <div class="ic-name">Unusual Whales, Capitol Trades, r/wsb threads</div>
        <div class="ic-claim">Free trackers and retail communities built around the narrative that congressional disclosures contain actionable signal.</div>
      </div>
    </div>
    <p>
      This report tests that premise against the data. The conclusion is that the disclosure-following industry is selling a structurally broken product. Not because politicians have no edge, but because the disclosure machinery destroys any edge that might exist before the public can act on it.
    </p>
  </div>
</section>

<!-- Section 2: The 28-Day Dead Zone -->
<section class="section" id="s2" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="section-counter">02</span><span>The Dead Zone</span></div>
    <h2>By the time you see the trade, <em>it is nearly a month old</em></h2>
    <p>
      The first problem with disclosure-driven strategies is the disclosure timeline itself. The STOCK Act allows up to 45 days between trade execution and public filing, and members routinely use most of that window. Across 29,071 valid disclosures in this dataset, the median lag from trade to disclosure is 27 calendar days. The mean is 31 days. Roughly one in fifteen filings ({lag_over_45_pct:.1f}%) exceeds the 45-day statutory limit, with the worst offenders disclosing months late.
    </p>
    <div class="chart-box">
      <div class="chart-title">Distribution of disclosure lag (days from trade to public filing)</div>
      <div style="position:relative;height:300px">
        <canvas id="lagChart"></canvas>
      </div>
      <div class="chart-legend">
        <span><span class="legend-dot" style="background:#1a5c52"></span>Filings per 5-day bin</span>
        <span><span class="legend-line" style="background:#dc2626"></span>45-day STOCK Act limit</span>
      </div>
    </div>
    <div class="highlight-box">
      <div>
        <div class="hb-val">{lag_median}d</div>
        <div class="hb-label">Median disclosure lag</div>
      </div>
      <div>
        <div class="hb-val">{int(lag['p90'])}d</div>
        <div class="hb-label">90th percentile lag</div>
      </div>
      <div>
        <div class="hb-val">{lag_over_45_pct:.1f}%</div>
        <div class="hb-label">Filed late (over 45d)</div>
      </div>
    </div>
    <p>
      The implication for any disclosure-driven strategy is direct. A signal triggered by a politician's filing is, on average, reacting to information that is already four weeks old. Whatever price impact the original trade might have had through information leakage, order flow, or follow-the-smart-money behaviour, that impact has had four weeks to play out in the open market before anyone outside the politician's circle can see it. The follower buys at a post-leak price, not the politician's price.
    </p>
    <div class="callout amber">
      <strong>Why this matters.</strong> A signal that is structurally delayed by 27 days has to compete against a market that prices new information in hours. The disclosure lag is not noise around an otherwise clean signal. It is the signal arriving too late to be useful.
    </div>
  </div>
</section>

<!-- Section 3: What Congress Actually Buys -->
<section class="section" id="s3">
  <div class="container">
    <div class="section-label"><span class="section-counter">03</span><span>What They Actually Buy</span></div>
    <h2>The same mega-caps <em>everyone else already owns</em></h2>
    <p>
      Even setting the disclosure lag aside, the second problem is the universe of stocks Congress actually trades. If congressional members held genuine informational advantages, you would expect their high-conviction herds to concentrate in less-followed securities where private information is more likely to matter. Instead, the data shows the opposite. The most herded names in the 2023 to {max_year} sample are Microsoft, Apple, Google, Nvidia, JPMorgan, and Amazon. These are the most analysed equities in global markets. There is no information edge to be had in MSFT that is not already priced into a stock owned by every index fund on earth.
    </p>
    <p>
      The party composition reinforces the point. Of the {party_ch['bipartisan']['n']} herding events with complete party data at the primary threshold, {party_ch['bipartisan']['share_of_total'] * 100:.0f}% involve both parties buying simultaneously. There are essentially no exclusively Democratic or exclusively Republican high-conviction herds. Whatever drives the herding, it is not partisan-specific information. Both sides of the aisle converge on the same large-cap names independently, which is what you would expect if the underlying behaviour were a function of mainstream financial advisor recommendations and brand-name familiarity rather than committee-jurisdiction or insider channels.
    </p>
    <div class="highlight-box">
      <div>
        <div class="hb-val">{kpi_n}</div>
        <div class="hb-label">Herding events (3+ pols, 30d)</div>
      </div>
      <div>
        <div class="hb-val">{party_ch['bipartisan']['share_of_total'] * 100:.0f}%</div>
        <div class="hb-label">Bipartisan (both parties present)</div>
      </div>
      <div>
        <div class="hb-val">{sector[0]['n_events'] if sector else 0}</div>
        <div class="hb-label">Information Tech herds (largest cluster)</div>
      </div>
    </div>

    <h3>Largest individual herding events</h3>
    {largest_html}

    <h3>10-day excess returns by sector</h3>
    {sector_html}

    <div class="callout purple">
      <strong>Sector concentration.</strong> Information Technology is the most-herded sector: {sector[0]['n_events']} events at {sector[0]['mean_excess_10d'] * 100:+.1f}% mean excess versus SPY. Despite larger sample sizes at the 10-day horizon, no sector demonstrates strong, sustained alpha. Real Estate and Energy do not even produce enough herds at the 3+ threshold to compute statistics.
    </div>
  </div>
</section>

<!-- Section 4: Trade-date vs Disclosure-date -->
<section class="section" id="s4" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="section-counter">04</span><span>The Smoking Gun</span></div>
    <h2>Even the politicians do not <em>beat the market</em></h2>
    <p>
      The standard pushback against disclosure-lag critiques is that politicians clearly profit from their trades, and even if the public misses some of that gain, what remains might still be a worthwhile signal. To check this realistically, the analysis maps each individual politician's buy trade within a herd to their subsequent sell trade for the same stock, or marks it to market if the position is still open. We then compare the politician's exact holding period return against what a follower would earn by mirroring the exact same entries and exits, but delayed by the disclosure lag.
    </p>
    <p>
      Over the median 26-day initial lag window, the herded stocks rose {lag_period_return_str} in absolute terms. That sounds informative until you compare against the market. SPY rose {pct(tvd['lag_period_mean_return'] - tvd['lag_period_mean_excess'])} over the same windows. The herded stocks actually underperformed the index by {lag_period_excess_str} during the politicians' own initial holding window. Only {lag_period_winrate:.1f}% of these stocks beat SPY during the lag period, meaning {100 - lag_period_winrate:.1f}% underperformed even before any follower could enter.
    </p>
    <div class="highlight-box">
      <div>
        <div class="hb-val">{lag_period_excess_str}</div>
        <div class="hb-label">Mean excess vs SPY during lag</div>
      </div>
      <div>
        <div class="hb-val">{lag_period_winrate:.0f}%</div>
        <div class="hb-label">Win rate during lag</div>
      </div>
      <div>
        <div class="hb-val">{int(tvd['realized_hold_days'])}d</div>
        <div class="hb-label">Average holding period</div>
      </div>
    </div>
    <div class="chart-box">
      <div class="chart-title">Cumulative Nominal Return (1 Unit per Trade): Trade vs Disclosure Entry</div>
      <div style="position:relative;height:300px">
        <canvas id="tvdChart"></canvas>
      </div>
      <div class="chart-legend">
        <span><span class="legend-line" style="background:#dc2626"></span>Trade-date entry</span>
        <span><span class="legend-line" style="background:#1a5c52"></span>Disclosure-date entry</span>
        <span><span class="legend-line" style="background:#1e40af"></span>SPY (benchmark)</span>
      </div>
    </div>
    <p>
      The cumulative P&L chart above models the total nominal profit if you had allocated $1,000 into every congressional stock pick over their exact holding periods. Across {tvd['realized_n']} such trades, politicians generated ${cum['cum_trade'][-1] * 1000:,.0f} in aggregate profit. A hypothetical follower mirroring those exact trades but entering on the disclosure date would make ${cum['cum_disc'][-1] * 1000:,.0f}. However, allocating those exact same dollars into the S&P 500 (SPY) over the identical holding periods generated ${cum['cum_spy_trade'][-1] * 1000:,.0f}.
    </p>
    <p>
      What this means is that the disclosure-follower is not missing alpha. They are missing a chunk of pure market beta. Congress is buying stocks that go up because the market goes up, not because their picks beat the market. In fact, politicians underperformed SPY in absolute dollars. NANC and KRUZ simply deliver a beta-heavy, mega-cap-tilted basket dressed up as an information-based product.
    </p>
    <div class="callout red">
      <strong>The premise fails on its own terms.</strong> If politicians had a real edge, their realized return should beat SPY over their true holding periods. The mean realized excess return is negative. The disclosure lag does not need to be defended or measured. There is no alpha behind it to begin with.
    </div>
  </div>
</section>

<!-- Section 5: Committee Jurisdiction Test -->
<section class="section" id="s5">
  <div class="container">
    <div class="section-label"><span class="section-counter">05</span><span>Committee Jurisdiction</span></div>
    <h2>No edge where you would expect one <em>to actually exist</em></h2>
    <p>
      If congressional alpha exists anywhere, the strongest theoretical case is jurisdiction-specific information. Members on the House Financial Services Committee see proposed banking legislation before the public. Senate Armed Services members see defense procurement details. House Energy and Commerce members see EPA rule-makings months in advance. This is the academic literature's main remaining defense of the politician-trading thesis, and it is testable.
    </p>
    <p>
      For each herding event in the primary sample, the analysis joins to congress-legislators committee-membership data (184 of 201 trader names matched, 91.5%). An event is flagged "in-jurisdiction" if the ticker falls in the committee's sectoral jurisdiction and at least one herd member sits on that committee. The cleanest test cohort is Information Technology, where {committee['categories'][3]['in_jurisdiction']['n']} herd events involve members on Judiciary, Commerce, or Oversight committees with technology jurisdiction. Those in-jurisdiction tech herds posted mean 10-day excess returns of {committee['categories'][3]['in_jurisdiction']['mean_excess']*100:+.1f}%. The same members buying outside their committee's jurisdiction did slightly better, at {committee['categories'][3]['out_jurisdiction']['mean_excess']*100:+.1f}% mean excess.
    </p>

    {committee_html}

    <div class="callout amber">
      <strong>Small-sample caution.</strong> Energy, Defense, and several other categories have too few in-jurisdiction events at the 3+ threshold to support inference. The IT cohort is the only well-sampled test, and it points the wrong direction for the jurisdictional-information hypothesis.
    </div>
    <p>
      The cleanest reading is that there is no detectable jurisdiction-specific edge in the data where the data permit a test. Members who sit on technology-related committees and herd into technology stocks do worse than when they herd into stocks outside their jurisdiction. This is the opposite of what an information-advantage hypothesis predicts.
    </p>
  </div>
</section>

<!-- Section 6: The ETF Wrappers -->
<section class="section" id="s6" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="section-counter">06</span><span>The ETF Wrappers</span></div>
    <h2>NANC, KRUZ, and the <em>products selling the story</em></h2>
    <p>
      Two ETFs operationalise the congressional-trading premise. NANC, launched February 2023 by Subversive Capital, tracks disclosed Democratic-side trades. KRUZ does the same for Republican filings. Both charge 0.75% annually. Both have over 22 months of post-inception data to evaluate.
    </p>
    <div class="chart-box">
      <div class="chart-title">NANC, KRUZ, SPY rebased to 100 (Feb 2023 inception of NANC and KRUZ)</div>
      <div style="position:relative;height:340px">
        <canvas id="etfChart"></canvas>
      </div>
      <div class="chart-legend">
        <span><span class="legend-line" style="background:#1e40af"></span>NANC (Democrat trades)</span>
        <span><span class="legend-line" style="background:#dc2626"></span>KRUZ (Republican trades)</span>
        <span><span class="legend-line" style="background:#1a5c52"></span>SPY (benchmark)</span>
      </div>
    </div>
    <div class="highlight-box">
      <div>
        <div class="hb-val">{nanc_cum_str}</div>
        <div class="hb-label">NANC cumulative (Sharpe {nanc_sharpe})</div>
      </div>
      <div>
        <div class="hb-val">{spy_cum_str}</div>
        <div class="hb-label">SPY cumulative (Sharpe {spy_sharpe})</div>
      </div>
      <div>
        <div class="hb-val">{kruz_cum_str}</div>
        <div class="hb-label">KRUZ cumulative (Sharpe {kruz_sharpe})</div>
      </div>
    </div>
    <p>
      The headline numbers tell two stories. NANC's {nanc_cum_str} cumulative return narrowly beat SPY's {spy_cum_str} in absolute terms, but its risk-adjusted return (Sharpe {nanc_sharpe}) trailed SPY's {spy_sharpe}. NANC took more risk to deliver a modestly higher return, which is consistent with a portfolio that overweights tech mega-caps. Tech crushed the market in 2023 and {max_year}. A portfolio that herds into the same names Congress herds into, also herds into the names that drove the bull market. That is sector beta, not informational alpha.
    </p>
    <p>
      KRUZ is the sharper indictment. The Republican-tracking ETF returned {kruz_cum_str} cumulative over the same period, trailing SPY by roughly 20 percentage points. Sharpe of {kruz_sharpe} is significantly below SPY's {spy_sharpe}. If congressional information were valuable, KRUZ should at minimum match the index. It does not. Investors paying 0.75% annually to follow Republican members' trades have underperformed by a margin that swamps the expense ratio many times over.
    </p>
    <div class="callout red">
      <strong>If you are paying 0.75% in fees for this, stop.</strong> NANC's cumulative outperformance is sector beta, not alpha. Risk-adjusted, it loses to SPY at lower cost. KRUZ has underperformed SPY by approximately 20 points over 22 months. Both wrappers are wrapping disclosure data that, on the evidence in Sections 02 to 05, has no informational content for outside investors.
    </div>
  </div>
</section>

<!-- Section 7: Aggregate Backtest -->
<section class="section" id="s7">
  <div class="container">
    <div class="section-label"><span class="section-counter">07</span><span>Aggregate Backtest</span></div>
    <h2>What you actually get from <em>mechanically following the feed</em></h2>
    <p>
      Pulling everything together, the aggregate backtest mechanically buys every herding event on the first trading day on or after the disclosure date and holds for 10 days. Across {kpi_n} events with complete return data in the primary parameter set (3+ politicians, 30-day rolling window), the win rate is {kpi_wr:.1f}%. Mean 10-day excess return versus SPY is {kpi_exc}. Sharpe is {kpi_sharpe}. The t-statistic of {kpi_t} is well within noise.
    </p>
    <div class="chart-box">
      <div class="chart-title">Mean excess return vs SPY by holding horizon (with IQR band)</div>
      <div style="position:relative;height:300px">
        <canvas id="curveChart"></canvas>
      </div>
      <div class="chart-legend">
        <span><span class="legend-dot" style="background:#1a5c52"></span>Mean excess return</span>
        <span><span class="legend-line" style="background:#e2ddd0"></span>IQR (25th to 75th percentile)</span>
        <span><span class="legend-line" style="background:rgba(220,38,38,.5)"></span>Zero line</span>
      </div>
    </div>
    <p>
      No parameter combination in the 4&#215;3 sensitivity grid produces a meaningfully positive edge. Tightening the threshold to 4 or 5 politicians reduces the sample size to where any apparent signal is dominated by noise. Loosening to 2 politicians produces the largest samples but excess returns remain anchored near zero. Furthermore, even the tiny fractions of a percent of positive excess return seen in some cells would likely be entirely wiped out by bid-ask spreads, slippage, and trading commissions in a real-world retail environment. The structural conclusion from Section 04 plays out exactly as expected in the aggregate strategy result.
    </p>
    {sens_html}
  </div>
</section>

<!-- Section 8: Sells -->
<section class="section" id="s8" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="section-counter">08</span><span>The Sell Side</span></div>
    <h2>Just as noisy as the buys, <em>with no edge to be found</em></h2>
    <p>
      The buy-side signal is conclusively null. Applying the exact same primary definition (3+ politicians, 30-day rolling window) to disclosed <em>sales</em> rather than buys produces {sell_n} sell-herding events with complete 10-day returns. If politicians possessed genuine insider edge, we would expect stocks to underperform SPY following a sell herd as negative catalysts materialize. 
    </p>
    <p>
      Instead, the mean 10-day excess return after a sell-herd is {sell_exc}, with a {sell_wr:.1f}% win rate and a t-statistic of {sell_t}. This means the stocks actually slightly <em>outperformed</em> the index after the politicians dumped them. The sell signal is just as noisy and devoid of alpha as the buy signal.
    </p>
    <div class="chart-box">
      <div class="chart-title">Mean excess return vs SPY after sell herd, by holding horizon</div>
      <div style="position:relative;height:260px">
        <canvas id="sellChart"></canvas>
      </div>
      <div class="chart-legend">
        <span><span class="legend-dot" style="background:#1a5c52"></span>Mean excess return (positive = stock beat SPY after sell)</span>
        <span><span class="legend-line" style="background:#e2ddd0"></span>IQR (25th to 75th percentile)</span>
        <span><span class="legend-line" style="background:rgba(220,38,38,.5)"></span>Zero line</span>
      </div>
    </div>

    {sell_sens_html}

    <p>
      Even if there were a theoretical edge hidden in the noise, it could not be operationalised. The median 27-day disclosure lag means the news is nearly a month old by the time a follower can act. Furthermore, capitalising on a sell signal requires shorting individual equities, which carries borrow fees, recall risk, and tax inefficiency that would easily consume any marginal alpha. The wrappers tracking this space (NANC and KRUZ) are long-only and cannot even express these trades.
    </p>
    <div class="callout red">
      <strong>The final nail in the coffin.</strong> The sell-side result conclusively mirrors the buy-side result: there is no statistically significant edge. Tracking congressional stock sales is not a viable strategy.
    </div>
  </div>
</section>

<!-- Section 9: Methodology + Conclusions -->
<section class="section" id="s9">
  <div class="container">
    <div class="section-label"><span class="section-counter">09</span><span>Methodology and Verdict</span></div>
    <h2>The literature has known this for over a decade. <em>The industry keeps selling it anyway.</em></h2>
    <p>
      Eggers and Hainmueller (2013) examined 16 years of congressional trades and found that, on a portfolio-weighted basis, members of Congress earned returns indistinguishable from random selection within their stated investment universe. Belmont and Tilelli (2022) updated the analysis and reached substantially the same conclusion. The academic consensus has held for over a decade. The disclosure-tracking industry has not noticeably contracted in response. NANC and KRUZ launched in 2023 to the explicit pitch that they capture an edge that the literature already demonstrated does not exist.
    </p>
    <p>
      The results in this report, built on 35,343 STOCK Act filings and 10-day forward returns across {kpi_n} high-conviction buy herds, are consistent with that consensus. The 27-day median disclosure lag is the proximate killer of any informational edge, but the deeper finding is that even at the politicians' own entry point, the herded stocks underperform SPY. There is no edge to be lost. The retail-facing wrappers (NANC, KRUZ, Pelosi-tracker subscriptions) are selling investors a beta-heavy mega-cap portfolio wrapped in a narrative about insider access.
    </p>

    <table class="method-table">
      <thead><tr><th>Dimension</th><th>Detail</th></tr></thead>
      <tbody>
        <tr><td>Trade data</td><td>35,343 individual-equity disclosures from 201 politicians, May 2023 to May 2026, scraped from Capitol Trades (STOCK Act feed)</td></tr>
        <tr><td>Herding events</td><td>Rolling window over disclosure dates; 12 threshold-window combinations; primary = 3 politicians, 30-day window; ETFs and mutual funds excluded</td></tr>
        <tr><td>Price data</td><td>CRSP daily stock files via WRDS through {max_date_str}; ETF data (NANC, KRUZ, SPY) from Yahoo Finance after CRSP coverage proved insufficient for newer ETFs</td></tr>
        <tr><td>Return calculation</td><td>Two parallel entries: disclosure-date (first trading day on or after publication) and trade-date (first trading day on or after execution). Returns at 10, 20, 60, 90, 180, 252 calendar days</td></tr>
        <tr><td>Lag-period return</td><td>Stock return from trade date to disclosure date, minus SPY return over same window; measures what followers cannot capture</td></tr>
        <tr><td>Committee data</td><td>unitedstates/congress-legislators YAML (committee-membership-current, legislators-current); 184 of 201 trader names matched (91.5%)</td></tr>
        <tr><td>Statistical tests</td><td>One-sample t-test of 10-day excess return against zero, primary combination; Sharpe annualised as mean/std &#215; sqrt(252/horizon); p-values omitted because results are clearly non-significant</td></tr>
        <tr><td>Out of scope</td><td>Politicians' own trades evaluated against pre-trade prices (would require pre-trade-date price benchmarks); IPO-related disclosures and ESOP grants; options trades; non-US equities; disclosures filed after 2025-12-31 (CRSP price coverage limit)</td></tr>
      </tbody>
    </table>

    <div class="callout red">
      <strong>Verdict on NANC and KRUZ.</strong> Both wrappers are paying 0.75% annually to deliver beta-tilted exposure to mega-cap equities, dressed in a disclosure-tracking narrative that the underlying data does not support. KRUZ has underperformed SPY by approximately 20 percentage points cumulatively over the nearly three-year comparison window. NANC has outperformed SPY by roughly 15 percentage points in absolute terms but its Sharpe ratio (1.46) is identical to SPY's, confirming it adds no risk-adjusted value above a plain index fund. Neither product captures any informational edge that survives the disclosure lag.
    </div>
    <div class="callout amber">
      <strong>Sample-window limitation.</strong> The CRSP price data extends through December 2025, giving a usable backtest window of approximately 2.5 years and a primary sample of n={kpi_n} events. The qualitative direction of every result (null buy signal, null sell signal, no committee-jurisdiction edge, KRUZ underperformance) is consistent with the academic literature on longer samples. A definitive replication on 5+ years of post-cutoff data would not be expected to change the verdict, but it would tighten the confidence intervals.
    </div>
    <div class="callout blue">
      <strong>What this report does not claim.</strong> It does not claim that politicians never have informational advantages on individual trades. It claims that the disclosure-based wrappers and tracking products sold to retail investors do not capture any such advantages if they exist. The two questions are different and the literature consensus on the second one has been stable for over a decade.
    </div>
    <div class="callout purple">
      <strong>Disclaimer.</strong> This is independent research published for educational and analytical purposes only. It does not constitute investment advice or a recommendation to buy or sell any security. All performance figures are historical and gross of transaction costs and taxes. NANC and KRUZ are referenced as the two pure-play products in the disclosure-tracking category; mention does not imply any further relationship with their issuers.
    </div>
  </div>
</section>

<div style="background:#eef7f5;border-left:3px solid #1a5c52;padding:1.2rem 1.5rem;margin:0 auto 2rem;border-radius:0 3px 3px 0;max-width:900px">
  <span style="font-family:var(--mono);font-size:.65rem;text-transform:uppercase;letter-spacing:.1em;color:var(--accent);font-weight:600;display:block;margin-bottom:.5rem">For the desk</span>
  <p style="font-family:var(--mono);font-size:.78rem;color:var(--muted);margin:0;text-align:left;hyphens:none">
    Median disclosure lag {lag_median}d (mean {lag_mean:.1f}d, p90 {int(lag['p90'])}d, {lag_over_45_pct:.1f}% late). Lag-period excess vs SPY {lag_period_excess_str} (n=131, win rate {lag_period_winrate:.1f}%): even politicians' own entry underperforms the index. Aggregate buy backtest (3+, 30d, 10d hold): n={kpi_n}, mean excess {kpi_exc}, Sharpe {kpi_sharpe}, t={kpi_t}. Sell-side n={sell_n}, mean excess {sell_exc}, t={sell_t} (completely null). NANC cum +{nanc['cum_return'] * 100:.1f}% Sharpe {nanc_sharpe} vs SPY +{spy['cum_return'] * 100:.1f}% Sharpe {spy_sharpe}; KRUZ cum +{kruz['cum_return'] * 100:.1f}% Sharpe {kruz_sharpe}. IT in-jurisdiction n={committee['categories'][3]['in_jurisdiction']['n']} mean excess {committee['categories'][3]['in_jurisdiction']['mean_excess']*100:+.1f}%. Verdict: NANC and KRUZ should not be held.
  </p>
</div>

<footer>
  <div class="footer-inner">
    <div class="footer-name">The Intrinsic Investor</div>
    <div class="footer-right">
      <span style="color:rgba(255,255,255,.35)">&copy; 2025 Brian Liew</span>
      <a href="https://www.linkedin.com/in/brian-liew" target="_blank">LinkedIn</a>
      <a href="https://github.com/TheIntrinsicInvestor" target="_blank">GitHub</a>
      <a href="mailto:brianliew99@gmail.com">Email</a>
    </div>
  </div>

  <div style="text-align:center;font-size:0.75rem;color:rgba(255,255,255,0.4);margin-top:1.5rem;font-family:var(--font, \'Inter\', sans-serif);width:100%;">For research purposes only. Not financial advice.</div>
</footer>

<script>
const _nav = document.querySelector('nav');
window.addEventListener('scroll', () => {{
  const el  = document.getElementById('progress-bar');
  const p = window.scrollY / (document.body.scrollHeight - window.innerHeight) * 100;
  el.style.width = Math.min(p, 100) + '%';
  _nav.classList.toggle('scrolled', window.scrollY > 40);
}}, {{ passive: true }});

const io = new IntersectionObserver(entries => {{
  entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }});
}}, {{ threshold: 0.07 }});
document.querySelectorAll('.section').forEach(s => io.observe(s));

const NAV_LABELS = ['Premise', 'Dead Zone', 'What They Buy', 'Smoking Gun', 'Committee', 'ETF Wrappers', 'Backtest', 'Sell Side', 'Methodology'];
const sideNav  = document.getElementById('side-nav');
const sections = document.querySelectorAll('.section[id]');
sections.forEach((s, i) => {{
  const a = document.createElement('a');
  a.href = '#' + s.id;
  a.innerHTML = '<span class="sn-label">' + (NAV_LABELS[i] || '') + '</span><span class="sn-dot"></span>';
  sideNav.appendChild(a);
}});
const navItems = sideNav.querySelectorAll('a');
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

Chart.defaults.font.family = 'Inter, sans-serif';
Chart.defaults.color = '#4a6460';
const GRID = {{ color: 'rgba(15,34,32,.05)', drawBorder: false }};
const TICK = {{ color: '#8aaba6', font: {{ size: 10 }} }};

// Section 02: lag histogram
const lagLabels = {lag_labels};
const lagCounts = {lag_counts};
new Chart(document.getElementById('lagChart'), {{
  type: 'bar',
  data: {{
    labels: lagLabels,
    datasets: [{{
      label: 'Filings',
      data: lagCounts,
      backgroundColor: lagLabels.map((l, i) => {{
        // bins are 0-5, 5-10, ..., 45-50 is index 9 (45-day STOCK Act limit boundary)
        return i < 9 ? 'rgba(26,92,82,.78)' : 'rgba(220,38,38,.65)';
      }}),
      borderWidth: 0,
      borderRadius: 2,
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => ctx.parsed.y.toLocaleString() + ' filings' }} }},
      annotation: {{}}
    }},
    scales: {{
      x: {{
        ticks: {{ ...TICK, maxRotation: 0, autoSkip: true, maxTicksLimit: 12 }},
        grid: {{ display: false }},
        title: {{ display: true, text: 'Days from trade to disclosure', color: '#4a6460', font: {{ size: 10 }} }}
      }},
      y: {{
        ticks: TICK,
        grid: GRID,
        title: {{ display: true, text: 'Filings per 5-day bin', color: '#4a6460', font: {{ size: 10 }} }}
      }}
    }}
  }}
}});

// Section 04: realized returns
const tvdLabels = {tvd_labels};
const tvdDisc = {tvd_disc};
const tvdTrade = {tvd_trade};
const tvdSpy = {tvd_spy};
new Chart(document.getElementById('tvdChart'), {{
  type: 'line',
  data: {{
    labels: tvdLabels,
    datasets: [
      {{
        label: 'Trade-date entry',
        data: tvdTrade.map(v => v === null ? null : v * 100),
        borderColor: '#dc2626', backgroundColor: 'transparent',
        borderWidth: 2, pointRadius: 0, tension: 0.2,
      }},
      {{
        label: 'Disclosure-date entry',
        data: tvdDisc.map(v => v === null ? null : v * 100),
        borderColor: '#1a5c52', backgroundColor: 'transparent',
        borderWidth: 2, pointRadius: 0, tension: 0.2,
      }},
      {{
        label: 'SPY (benchmark)',
        data: tvdSpy.map(v => v === null ? null : v * 100),
        borderColor: '#1e40af', backgroundColor: 'transparent',
        borderWidth: 2, pointRadius: 0, tension: 0.2,
      }},
      {{
        label: 'Zero',
        data: tvdLabels.map(() => 0),
        borderColor: 'rgba(220,38,38,.4)', borderWidth: 1, borderDash: [4, 3], pointRadius: 0,
      }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: ctx => {{
            if (ctx.datasetIndex === 3) return null;
            return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(2) + '%';
          }}
        }}
      }}
    }},
    scales: {{
      x: {{ ticks: TICK, grid: GRID }},
      y: {{
        ticks: {{ ...TICK, callback: v => v.toFixed(1) + '%' }},
        grid: GRID,
        title: {{ display: true, text: 'Mean excess return vs SPY', color: '#4a6460', font: {{ size: 10 }} }}
      }}
    }}
  }}
}});

// Section 06: ETF chart
const etfDates = {etf_nanc_d};
const nancV = {etf_nanc_v};
const kruzV = {etf_kruz_v};
const spyV  = {etf_spy_v};
new Chart(document.getElementById('etfChart'), {{
  type: 'line',
  data: {{
    labels: etfDates,
    datasets: [
      {{
        label: 'NANC',
        data: nancV,
        borderColor: '#1e40af', backgroundColor: 'transparent', borderWidth: 2,
        pointRadius: 0, tension: 0.2,
      }},
      {{
        label: 'KRUZ',
        data: kruzV,
        borderColor: '#dc2626', backgroundColor: 'transparent', borderWidth: 2,
        pointRadius: 0, tension: 0.2,
      }},
      {{
        label: 'SPY',
        data: spyV,
        borderColor: '#1a5c52', backgroundColor: 'transparent', borderWidth: 2,
        pointRadius: 0, tension: 0.2,
      }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ position: 'top', labels: {{ font: {{ family: 'Inter', size: 11 }}, boxWidth: 18 }} }},
      tooltip: {{ callbacks: {{ label: ctx => ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) }} }}
    }},
    scales: {{
      x: {{ ticks: {{ ...TICK, maxTicksLimit: 10, font: {{ family: 'JetBrains Mono', size: 9 }} }}, grid: GRID }},
      y: {{
        ticks: {{ ...TICK, callback: v => v.toFixed(0) }},
        grid: GRID,
        title: {{ display: true, text: 'Index value (Feb 2023 = 100)', color: '#4a6460', font: {{ size: 10 }} }}
      }}
    }}
  }}
}});

// Section 07: forward returns curve
const curveLabels = {curve_labels};
const curveMean = {curve_mean};
const curveP25 = {curve_p25};
const curveP75 = {curve_p75};
new Chart(document.getElementById('curveChart'), {{
  type: 'line',
  data: {{
    labels: curveLabels,
    datasets: [
      {{
        label: 'IQR upper',
        data: curveP75.map(v => v === null ? null : v * 100),
        borderColor: 'transparent',
        backgroundColor: 'rgba(26,92,82,.10)',
        fill: '+1', pointRadius: 0, tension: 0.35,
      }},
      {{
        label: 'IQR lower',
        data: curveP25.map(v => v === null ? null : v * 100),
        borderColor: 'transparent',
        backgroundColor: 'rgba(26,92,82,.10)',
        fill: false, pointRadius: 0, tension: 0.35,
      }},
      {{
        label: 'Mean excess return',
        data: curveMean.map(v => v === null ? null : v * 100),
        borderColor: '#1a5c52', backgroundColor: 'transparent',
        borderWidth: 2, pointRadius: 5,
        pointBackgroundColor: '#1a5c52', tension: 0.35,
      }},
      {{
        label: 'Zero',
        data: curveLabels.map(() => 0),
        borderColor: 'rgba(220,38,38,.4)', borderWidth: 1, borderDash: [4, 3], pointRadius: 0,
      }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: ctx => {{
            if (ctx.datasetIndex === 3) return null;
            return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + '%';
          }}
        }}
      }}
    }},
    scales: {{
      x: {{ ticks: TICK, grid: GRID }},
      y: {{
        ticks: {{ ...TICK, callback: v => v.toFixed(0) + '%' }},
        grid: GRID,
        title: {{ display: true, text: 'Excess return vs SPY', color: '#4a6460', font: {{ size: 10 }} }}
      }}
    }}
  }}
}});

// Section 08: sell-side curve
const sellLabels = {sells_curve_labels};
const sellData = {sells_curve_data};
const sellP25 = {sells_curve_p25};
const sellP75 = {sells_curve_p75};

new Chart(document.getElementById('sellChart'), {{
  type: 'line',
  data: {{
    labels: sellLabels,
    datasets: [
      {{
        label: 'Mean excess return',
        data: sellData.map(v => v === null ? null : v * 100),
        borderColor: '#1a5c52', backgroundColor: '#1a5c52',
        borderWidth: 2, pointRadius: 5, pointHoverRadius: 7,
        tension: 0.1, z: 10
      }},
      {{
        label: 'P75',
        data: sellP75.map(v => v === null ? null : v * 100),
        borderColor: 'transparent', backgroundColor: 'transparent',
        pointRadius: 0, pointHoverRadius: 0, tension: 0.1
      }},
      {{
        label: 'IQR (25th to 75th percentile)',
        data: sellP25.map(v => v === null ? null : v * 100),
        borderColor: 'transparent', backgroundColor: 'rgba(215,210,195,.4)',
        fill: '-1', pointRadius: 0, pointHoverRadius: 0, tension: 0.1
      }},
      {{
        label: 'Zero',
        data: Array(sellLabels.length).fill(0),
        borderColor: 'rgba(220,38,38,.4)', borderWidth: 1, borderDash: [4,4],
        pointRadius: 0, pointHoverRadius: 0, fill: false
      }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        backgroundColor: 'rgba(15,34,32,.95)',
        titleFont: {{ family: "'Geist Mono', monospace", size: 11 }},
        bodyFont: {{ family: "'Inter', sans-serif", size: 12 }},
        padding: 10, cornerRadius: 4,
        callbacks: {{
          label: function(ctx) {{
            if(ctx.dataset.label==='Zero' || ctx.dataset.label==='P75') return null;
            let val = ctx.parsed.y;
            if(ctx.dataset.label.includes('IQR')) {{
              let p75 = ctx.chart.data.datasets[1].data[ctx.dataIndex];
              return `IQR: ${{(val).toFixed(1)}}% to ${{(p75).toFixed(1)}}%`;
            }}
            return `${{ctx.dataset.label}}: ${{val > 0 ? '+' : ''}}${{val.toFixed(2)}}%`;
          }}
        }}
      }}
    }},
    scales: {{
      x: {{ ticks: TICK, grid: {{ display: false }} }},
      y: {{
        ticks: {{ ...TICK, callback: v => v.toFixed(0) + '%' }},
        grid: GRID,
        title: {{ display: true, text: 'Excess return vs SPY', color: '#4a6460', font: {{ size: 10 }} }}
      }}
    }}
  }}
}});
</script>
</body>
</html>
"""

OUT.write_text(HTML, encoding="utf-8")
print(f"Written: {OUT}")
