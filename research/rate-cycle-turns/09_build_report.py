"""
09_build_report.py
-------------------
Generate the complete standalone HTML report for the Rate Cycle Turns study.
Reads from all chart JSON files produced by scripts 06 and 07, plus turns.parquet.

Output: index.html
"""
import json
import pandas as pd
from pathlib import Path

CHARTS = Path("charts")

def load(name):
    with open(CHARTS / name) as f:
        return json.load(f)

eq        = load("data_regime_equity.json")
curve_reg = load("data_regime_curve.json")
ind_reg   = load("data_regime_industries.json")
fac_reg   = load("data_regime_factors.json")
tx_index  = load("data_transition_index.json")
tx_vix    = load("data_transition_vix.json")
tx_curve  = load("data_transition_curve.json")
tx_sec    = load("data_transition_sectors.json")
tx_fac    = load("data_transition_factors.json")
heatmap   = load("data_transition_heatmap.json")

turns = pd.read_parquet("data/turns.parquet")
turns["date"] = pd.to_datetime(turns["date"])
turns = turns.sort_values("date").reset_index(drop=True)

REGIME_ORDER  = ["Hiking", "Cutting", "Hold-Elevated", "Hold-ZLB"]
REGIME_LABELS = {"Hiking": "Hiking", "Cutting": "Cutting",
                  "Hold-Elevated": "Hold (Elevated)", "Hold-ZLB": "Hold (Zero Lower Bound)"}
WINDOW  = list(range(-30, 91))
IDX_T0  = WINDOW.index(0)

# ── KPI / headline values (sourced directly from the JSON the charts read) ──
n_turns_total = len(turns)
n_hike = tx_index["first_hike_n"]
n_cut  = tx_index["first_cut_n"]

fh_t90 = tx_index["first_hike_mean"][-1]
fc_t90 = tx_index["first_cut_mean"][-1]
ins95_t90  = tx_index["insurance_1995"][-1]
ins19_t90  = tx_index["insurance_2019"][-1]
covid_t90  = tx_index["covid_2020_outlier"][-1]
soft_avg_t90 = round((ins95_t90 + ins19_t90 + covid_t90) / 3, 1)

best_regime  = max(REGIME_ORDER, key=lambda r: eq["spx"][r]["sharpe"])
best_sharpe  = eq["spx"][best_regime]["sharpe"]
best_ann_ret = eq["spx"][best_regime]["ann_return"]
worst_regime = min(REGIME_ORDER, key=lambda r: eq["spx"][r]["sharpe"])
worst_sharpe = eq["spx"][worst_regime]["sharpe"]
worst_ann_ret = eq["spx"][worst_regime]["ann_return"]

vix_fh_t0  = tx_vix["first_hike_mean"][IDX_T0]
vix_fc_t0  = tx_vix["first_cut_mean"][IDX_T0]
vix_fh_t90 = tx_vix["first_hike_mean"][-1]
vix_fc_t90 = tx_vix["first_cut_mean"][-1]

t10y2y_fh_90 = tx_curve["first_hike_t10y2y_delta"][-1]
t10y2y_fc_90 = tx_curve["first_cut_t10y2y_delta"][-1]
dgs10_fh_90  = tx_curve["first_hike_dgs10_delta"][-1]
dgs10_fc_90  = tx_curve["first_cut_dgs10_delta"][-1]

sec_fc = {ind: v["first_cut"][-1]  for ind, v in tx_sec["industries"].items()}
sec_fh = {ind: v["first_hike"][-1] for ind, v in tx_sec["industries"].items()}
worst_cut_sector = min(sec_fc, key=sec_fc.get)
best_cut_sector  = max(sec_fc, key=sec_fc.get)
positive_cut_sectors = [ind for ind, v in sec_fc.items() if v > 100]

fac_fc = {f: v["first_cut"][-1]  for f, v in tx_fac["factors"].items()}
fac_fh = {f: v["first_hike"][-1] for f, v in tx_fac["factors"].items()}

FAC_NAMES = {"Mkt-RF": "Market", "SMB": "Size (SMB)", "HML": "Value (HML)",
             "RMW": "Quality (RMW)", "CMA": "Conservative Inv. (CMA)", "MOM": "Momentum"}
IND_NAMES = {"NoDur": "Consumer Non-Durables", "Durbl": "Consumer Durables", "Manuf": "Manufacturing",
             "Enrgy": "Energy", "Chems": "Chemicals", "BusEq": "Business Equipment (Tech)",
             "Telcm": "Telecom", "Utils": "Utilities", "Shops": "Wholesale/Retail",
             "Hlth": "Healthcare", "Money": "Finance", "Other": "Other"}

# ── Colour helpers (chart-patterns.md) ───────────────────────────────────────
_C_RED, _C_PARCH, _C_GREEN = (254, 202, 202), (247, 244, 236), (187, 247, 208)

def _lerp(t, lo, hi):
    return '#{:02x}{:02x}{:02x}'.format(*(int(lo[i] + t * (hi[i] - lo[i])) for i in range(3)))

def diverging_color(v, abs_max):
    if v is None or abs_max == 0:
        return "#f7f4ec"
    t = max(0., min(1., abs(v) / abs_max))
    return _lerp(t, _C_PARCH, _C_RED) if v < 0 else _lerp(t, _C_PARCH, _C_GREEN)

def pct(x, decimals=1, sign=True):
    fmt = f"{{:+.{decimals}f}}%" if sign else f"{{:.{decimals}f}}%"
    return fmt.format(x)

def lvl_delta(level, decimals=1):
    return pct(level - 100, decimals)

# ── Per-turn checkpoint table (s4) ───────────────────────────────────────────
CP_COLS = [("spx_T-30", "T-30"), ("spx_T-5", "T-5"), ("spx_T+5", "T+5"),
           ("spx_T+30", "T+30"), ("spx_T+90", "T+90")]
abs_max_spx = max(abs(row[k]) for row in heatmap for k, _ in CP_COLS if row[k] is not None)

TURN_TYPE_LABEL = {
    "first_hike": "First hike", "first_cut": "First cut (reactive)",
    "first_cut_insurance": "First cut (insurance)", "first_cut_emergency": "First cut (emergency)",
}

heatmap_rows_html = ""
for row in heatmap:
    flag = ""
    if row["is_insurance"]:
        flag = ' <span style="font-size:.65rem;color:var(--blue2)">[insurance]</span>'
    elif row["is_outlier"]:
        flag = ' <span style="font-size:.65rem;color:var(--red2)">[outlier]</span>'
    cells = ""
    for key, label in CP_COLS:
        v = row[key]
        if v is None:
            cells += '<td style="text-align:center;color:var(--hint)">--</td>'
        else:
            bg = diverging_color(v, abs_max_spx)
            cells += f'<td style="text-align:center;background:{bg}">{pct(v)}</td>'
    vix_t0 = row["vix_T+0"]
    t10y2y_90 = row["t10y2y_delta_T+90"]
    t10y2y_str = f"{t10y2y_90:+.2f}" if t10y2y_90 is not None else "--"
    heatmap_rows_html += (
        f'<tr><td>{row["turn_date"]}{flag}</td>'
        f'<td>{TURN_TYPE_LABEL.get(row["turn_type"], row["turn_type"])}</td>'
        f'{cells}'
        f'<td style="text-align:center">{vix_t0:.1f}</td>'
        f'<td style="text-align:center">{t10y2y_str}</td></tr>\n'
    )

# ── Regime stats table (s3) ───────────────────────────────────────────────────
regime_rows_html = ""
for r in REGIME_ORDER:
    s = eq["spx"][r]
    regime_rows_html += (
        f'<tr><td>{REGIME_LABELS[r]}</td><td style="text-align:right">{s["n_days"]:,}</td>'
        f'<td style="text-align:right">{pct(s["ann_return"])}</td>'
        f'<td style="text-align:right">{s["ann_vol"]:.1f}%</td>'
        f'<td style="text-align:right">{s["sharpe"]:+.2f}</td>'
        f'<td style="text-align:right">{s["max_drawdown"]:.1f}%</td></tr>\n'
    )
covid_eq = eq["spx"]["Cutting_covid_outlier"]
regime_rows_html += (
    f'<tr style="opacity:.6"><td>COVID outlier (9 days)</td><td style="text-align:right">{covid_eq["n_days"]}</td>'
    f'<td style="text-align:right">n/a*</td><td style="text-align:right">n/a*</td>'
    f'<td style="text-align:right">n/a*</td><td style="text-align:right">{covid_eq["max_drawdown"]:.1f}%</td></tr>\n'
)

# ── Sector / factor by-regime heatmaps (s5, s6) ───────────────────────────────
def heatmap_table_html(data, names, abs_max=30):
    rows = ""
    for key in data:
        cells = "".join(
            f'<td class="hm-cell" style="background:{diverging_color(data[key][r]["ann_return"], abs_max)}">'
            f'{pct(data[key][r]["ann_return"])}</td>'
            for r in REGIME_ORDER
        )
        rows += f'<tr><td class="hm-row-label">{names.get(key, key)}</td>{cells}</tr>\n'
    cols = "".join(f'<th class="hm-col">{REGIME_LABELS[r]}</th>' for r in REGIME_ORDER)
    return (f'<div class="hm-wrap"><table class="hm-table"><thead><tr><th class="hm-corner"></th>{cols}'
            f'</tr></thead><tbody>{rows}</tbody></table></div>')

industry_hm_html = heatmap_table_html(ind_reg, IND_NAMES, abs_max=30)
factor_hm_html   = heatmap_table_html(fac_reg, FAC_NAMES, abs_max=15)

# ── Turns table (s2) ──────────────────────────────────────────────────────────
turns_rows_html = ""
for _, t in turns.iterrows():
    flag = ""
    if t["is_insurance"]:
        flag = '<span style="color:var(--blue2)">Insurance (excl. main)</span>'
    elif t["is_outlier"]:
        flag = '<span style="color:var(--red2)">Outlier, excl. main</span>'
    else:
        flag = '<span style="color:var(--green2)">Main aggregate</span>'
    note = t["notes"].replace("; ", ", ").replace("OUTLIER, ", "outlier: ")
    turns_rows_html += (
        f'<tr><td>{t["date"].strftime("%Y-%m-%d")}</td>'
        f'<td>{TURN_TYPE_LABEL.get(t["turn_type"], t["turn_type"])}</td>'
        f'<td>{flag}</td><td>{note}</td></tr>\n'
    )

print(f"Loaded {n_turns_total} turns, {n_hike} main hikes, {n_cut} main cuts")
print(f"Best regime: {best_regime} (Sharpe {best_sharpe:+.2f}, ann.ret {best_ann_ret:+.1f}%)")
print(f"Worst regime: {worst_regime} (Sharpe {worst_sharpe:+.2f}, ann.ret {worst_ann_ret:+.1f}%)")

# ── HTML ───────────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-HT9VG5C62E"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-HT9VG5C62E');</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rate Cycle Turns | The Intrinsic Investor</title>
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
body::before{{content:'';position:fixed;top:0;left:0;right:0;height:2px;background:#0f2220;z-index:9997}}
#progress-bar{{position:fixed;top:0;left:0;height:2px;width:0%;
  background:linear-gradient(90deg,#1a5c52,#2d9d8f);z-index:9998;transition:width .1s linear}}
nav{{position:sticky;top:0;z-index:100;height:62px;display:flex;align-items:center;
  justify-content:space-between;padding:0 2rem;
  background:#0f2220;
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
.hm-wrap{{overflow-x:auto;margin:1.5rem 0}}
.hm-table{{border-collapse:collapse;width:100%;font-family:var(--mono);font-size:.72rem}}
.hm-table thead th,.hm-table tbody td{{border:1px solid var(--border)}}
.hm-corner{{background:var(--bg2)}}
.hm-col{{background:var(--ink);color:#fff;font-size:.62rem;font-weight:600;
  text-transform:uppercase;letter-spacing:.03em;padding:6px 8px;text-align:center}}
.hm-row-label{{background:var(--bg2);color:var(--muted);font-size:.7rem;
  font-family:var(--font);padding:6px 10px;white-space:nowrap}}
.hm-cell{{text-align:center;color:var(--ink);padding:5px 8px;white-space:nowrap}}
.hm-cell:hover{{filter:brightness(.94)}}
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
nav{{border-bottom-color:rgba(255,255,255,.08)!important}}
nav.scrolled{{box-shadow:0 1px 24px rgba(0,0,0,.2)!important}}
.nav-logo{{color:#fff!important}}
.nav-links a{{color:rgba(255,255,255,.7)!important}}
.nav-links a:hover{{color:#fff!important}}
.nav-links a::after{{background:#2d9d8f!important}}
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
  <a href="#s1"><span class="sn-label">Background</span><div class="sn-dot"></div></a>
  <a href="#s2"><span class="sn-label">Data &amp; Regimes</span><div class="sn-dot"></div></a>
  <a href="#s3"><span class="sn-label">Returns by Regime</span><div class="sn-dot"></div></a>
  <a href="#s4"><span class="sn-label">Transition Window</span><div class="sn-dot"></div></a>
  <a href="#s5"><span class="sn-label">Sector Rotation</span><div class="sn-dot"></div></a>
  <a href="#s6"><span class="sn-label">Style Factors</span><div class="sn-dot"></div></a>
  <a href="#s7"><span class="sn-label">Rates &amp; Curve</span><div class="sn-dot"></div></a>
  <a href="#s8"><span class="sn-label">Methodology</span><div class="sn-dot"></div></a>
</div>

<!-- Hero -->
<header class="hero">
  <div class="hero-inner">
    <div class="hero-tag">Rate Cycle Event Study</div>
    <h1>Rate Cycle Turns: <em>Why Preemptive Beats Reactive in Fed Policy</em></h1>
    <p class="hero-sub">
      Extending the FOMC vol study from single meetings to full hiking, cutting, and hold regimes.
      Equities, sectors, style factors, and the yield curve, across eleven cycle turns since 1994,
      with the spotlight on the trading days around the turn itself.
    </p>
    <div class="hero-meta">
      <div class="hero-meta-item"><strong>Author</strong>Brian Liew, BSc Accounting and Finance, LSE</div>
      <div class="hero-meta-item"><strong>Published</strong>June 2026</div>
      <div class="hero-meta-item"><strong>Period</strong>1994 to 2025, n={n_turns_total} cycle turns</div>
      <div class="hero-meta-item"><strong>Data</strong>CRSP, Fama-French, FRED</div>
      <a href="https://github.com/TheIntrinsicInvestor/Backtesting/tree/main/research/rate-cycle-turns" target="_blank" rel="noopener" class="gh-btn">
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
    <div class="kpi-label">Cycle Turns (1994-2025)</div>
    <div class="kpi-value blue">{n_turns_total}</div>
    <div class="kpi-sub">{n_hike} hikes, {n_cut} reactive cuts, 3 isolated (insurance/outlier)</div>
  </div>
  <div class="kpi-cell">
    <div class="kpi-label">SPX at T+90, Reactive Cut</div>
    <div class="kpi-value red">{lvl_delta(fc_t90)}</div>
    <div class="kpi-sub">n=2 avg: 2001, 2007 (2024 truncated)</div>
  </div>
  <div class="kpi-cell">
    <div class="kpi-label">SPX at T+90, Insurance/Outlier Cut</div>
    <div class="kpi-value green">{lvl_delta(soft_avg_t90)}</div>
    <div class="kpi-sub">n=3 avg: 1995, 2019, 2020 (COVID)</div>
  </div>
  <div class="kpi-cell">
    <div class="kpi-label">Best Regime Sharpe</div>
    <div class="kpi-value blue">{best_sharpe:+.2f}</div>
    <div class="kpi-sub">{REGIME_LABELS[best_regime]}, ann. return {pct(best_ann_ret)}</div>
  </div>
  </div>
</div>

<!-- Section 1: Background -->
<section class="section" id="s1">
  <div class="container">
    <div class="section-label"><span class="section-counter">01</span><span>Background</span></div>
    <h2>A single FOMC meeting is a vol event. A cycle turn is a regime change</h2>
    <p>
      The FOMC Vol Crush study (the prior report in this series) showed that implied volatility around
      individual Fed meetings is mostly noise resolution: a predictable build and crush with little
      tradeable edge once transaction costs are accounted for. This report asks a different question.
      Forget single meetings: what happens to equities, sectors, style factors, and the yield curve in
      the months around the moment a multi-year hiking or cutting cycle actually turns?
    </p>
    <p>
      The starting hypothesis, and the one this report tests, is that <strong>direction alone is a weak
      predictor</strong>. A rate cut is not inherently bullish or bearish: a preemptive, insurance-style
      cut made while the economy is still healthy (1995, 2019) behaves nothing like a reactive cut made
      because a recession is already underway (2001, 2007, 2024). The Fed being <em>ahead of</em> a
      slowdown versus <em>chasing</em> one matters more than whether the policy rate is going up or down.
    </p>
    <div class="callout amber">
      <strong>Small sample, stated up front.</strong> There are only {n_turns_total} identifiable cycle
      turns in 32 years of Fed history, and no two share starting conditions (inflation backdrop,
      valuation, geopolitics). Every average in this report is built from {n_hike} or {n_cut} or fewer
      observations. Treat point estimates as directional, not precise, and read the per-turn detail
      tables alongside the averages.
    </div>
  </div>
</section>

<!-- Section 2: Data & Regime Definition -->
<section class="section" id="s2" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="section-counter">02</span><span>Data &amp; Regime Definition</span></div>
    <h2>Classifying 32 years of Fed policy into four regimes and {n_turns_total} turns</h2>
    <p>
      The daily Fed funds target rate from 1994 to 2025 is built from hardcoded FOMC decision history
      (no FRED dependency, fully reproducible) and classified into four regimes: <strong>Hiking</strong>,
      <strong>Cutting</strong>, <strong>Hold (Elevated)</strong>, and <strong>Hold (Zero Lower Bound)</strong>.
      A "turn" is the first hike after a sustained hold or cutting period, or the first cut after a
      sustained hold or hiking period. Each regime label can recur (Hold-Elevated appears in four separate
      multi-year spans), and each occurrence is treated as its own contiguous spell for drawdown purposes.
    </p>
    <p>
      Two cut types are isolated from the main first_hike/first_cut aggregates rather than blended in:
      <strong>insurance cuts</strong> (1995, 2019), made preemptively with no recession that followed, and
      the <strong>2020 COVID emergency cut</strong>, a structural outlier on every dimension (a 9-trading-day
      regime spell, VIX above 75). All three are shown individually throughout this report, never averaged
      into the main reactive-cut statistics.
    </p>
    <table class="data-table">
      <thead><tr><th>Date</th><th>Turn type</th><th>Aggregation</th><th>Context</th></tr></thead>
      <tbody>
{turns_rows_html}      </tbody>
    </table>
  </div>
</section>

<!-- Section 3: Returns by Regime -->
<section class="section" id="s3">
  <div class="container">
    <div class="section-label"><span class="section-counter">03</span><span>Returns by Regime</span></div>
    <h2>The calm after the hike, not the hike itself, is where the market makes money</h2>
    <p>
      Across the full 1994-2025 sample, the S&amp;P 500's best risk-adjusted regime is
      <strong>{REGIME_LABELS[best_regime]}</strong> (Sharpe {best_sharpe:+.2f}, annualised return
      {pct(best_ann_ret)}), not Hiking itself. The worst is <strong>{REGIME_LABELS[worst_regime]}</strong>
      (Sharpe {worst_sharpe:+.2f}, annualised return {pct(worst_ann_ret)}), dragged down by the 2001
      dot-com unwind and the 2007-09 GFC, both of which fall inside Cutting regimes. Hiking itself is
      mildly positive (Sharpe {eq["spx"]["Hiking"]["sharpe"]:+.2f}): markets tend to tolerate a Fed that
      is removing accommodation in a healthy economy.
    </p>
    <table class="data-table">
      <thead><tr><th>Regime</th><th style="text-align:right">Trading days</th>
        <th style="text-align:right">Ann. return</th><th style="text-align:right">Ann. vol</th>
        <th style="text-align:right">Sharpe</th><th style="text-align:right">Max drawdown</th></tr></thead>
      <tbody>
{regime_rows_html}      </tbody>
    </table>
    <div class="chart-box">
      <div class="chart-title">SPX annualised return and Sharpe by regime (COVID excluded)</div>
      <canvas id="regimeChart" height="90"></canvas>
    </div>
    <div class="callout amber">
      <strong>Annualising a 9-day window is not meaningful as a rate.</strong> The COVID outlier spell
      lasted nine trading days. Extrapolated to an annual rate it shows {pct(covid_eq["ann_return"])},
      a mathematically valid but practically meaningless number from compounding nine days of extreme
      moves. It is shown in the table for completeness only and excluded from every chart and average.
    </div>
  </div>
</section>

<!-- Section 4: The Transition Window -->
<section class="section" id="s4" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="section-counter">04</span><span>The Transition Window</span></div>
    <h2>Reactive cuts hurt equities for 90 days. Preemptive cuts and hikes mostly don't</h2>
    <p>
      Each turn is re-indexed to trading days T-30 through T+90 around the announcement, with the SPX
      level rebased so T0 (the turn date) equals 100. Averaging across the reactive first-cuts, the
      index is at {lvl_delta(fc_t90)} by T+90. That T+90 average covers 2001 and 2007 only: the 2024
      cut is tracked through T+72 before the CRSP daily index data ends, so it never reaches the
      90-day mark. Averaging across the {n_hike} first-hikes, it is roughly flat at {lvl_delta(fh_t90)}.
      The two isolated insurance cuts and the
      COVID emergency cut all finish higher: 1995 at {lvl_delta(ins95_t90)}, 2019 at {lvl_delta(ins19_t90)},
      and the COVID V-shaped recovery at {lvl_delta(covid_t90)}.
    </p>
    <div class="chart-box">
      <div class="chart-title">SPX level around each turn type, T-30 to T+90 (T0 = 100)</div>
      <canvas id="transitionIndexChart" height="90"></canvas>
      <div class="chart-legend">
        <span><span class="legend-line" style="background:#dc2626"></span>First cut, reactive (n={n_cut})</span>
        <span><span class="legend-line" style="background:#1a5c52"></span>First hike (n={n_hike})</span>
        <span><span class="legend-line" style="background:#2563eb;border-top:2px dashed #2563eb"></span>Insurance cut 1995</span>
        <span><span class="legend-line" style="background:#7E3AF2;border-top:2px dashed #7E3AF2"></span>Insurance cut 2019</span>
        <span><span class="legend-line" style="background:#9ca3af;border-top:2px dashed #9ca3af"></span>COVID 2020 (outlier)</span>
      </div>
    </div>
    <p>
      VIX tells a consistent story. Around reactive cuts, implied vol starts already elevated
      ({vix_fc_t0:.1f} at T0) and keeps climbing ({vix_fc_t90:.1f} by T+90): the market is pricing in
      the stress before and after, because the Fed is responding to a problem that is still unfolding.
      Around hikes, vol starts lower ({vix_fh_t0:.1f} at T0) and drifts down further ({vix_fh_t90:.1f} by
      T+90), consistent with a Fed acting from a position of relative calm.
    </p>
    <div class="chart-box">
      <div class="chart-title">VIX level around each turn type, T-30 to T+90</div>
      <canvas id="transitionVixChart" height="90"></canvas>
      <div class="chart-legend">
        <span><span class="legend-line" style="background:#dc2626"></span>First cut, reactive (n={n_cut})</span>
        <span><span class="legend-line" style="background:#1a5c52"></span>First hike (n={n_hike})</span>
      </div>
    </div>
    <h3>Every turn, individually</h3>
    <p>
      With {n_turns_total} total turns, hiding behind group averages would understate how much the
      individual cases vary. The 2022 hike, into an inflation shock, is the single worst hike outcome
      (T+90 {pct(next(r["spx_T+90"] for r in heatmap if r["turn_date"]=="2022-03-16"))}). 2024's reactive
      cut, by contrast, is positive through T+60, with its T+90 value unavailable because CRSP daily index
      data ends 2024-12-31, truncating that window.
    </p>
    <div style="overflow-x:auto">
    <table class="data-table">
      <thead><tr><th>Turn date</th><th>Type</th>
        <th style="text-align:center">SPX T-30</th><th style="text-align:center">SPX T-5</th>
        <th style="text-align:center">SPX T+5</th><th style="text-align:center">SPX T+30</th>
        <th style="text-align:center">SPX T+90</th>
        <th style="text-align:center">VIX T0</th><th style="text-align:center">2s10s &Delta; T+90</th></tr></thead>
      <tbody>
{heatmap_rows_html}      </tbody>
    </table>
    </div>
    <div class="callout blue">
      <strong>Reading the table.</strong> SPX columns show percent change from the turn date (T0 = 0%).
      The 2s10s column shows the change in the 10Y-2Y spread (percentage points) from T0 to T+90:
      positive means the curve steepened.
    </div>
  </div>
</section>

<!-- Section 5: Sector Rotation -->
<section class="section" id="s5">
  <div class="container">
    <div class="section-label"><span class="section-counter">05</span><span>Sector Rotation</span></div>
    <h2>Defensive sectors hold up through reactive cuts. Cyclicals and tech do not</h2>
    <p>
      Sectors are the Fama-French 12 industry portfolios (full daily history to 1994 from the same
      Dartmouth source as the style factors), not SPDR sector ETFs, since the ETFs only launch in
      December 1998 and would truncate the 1994-95 and 1999-2000 hiking cycles. The industry labels are
      not a 1:1 match to the 11 GICS sectors: "BusEq" approximates Technology plus parts of
      Communication Services, and "Money" approximates Financials plus Real Estate.
    </p>
    <h3>By regime, full sample</h3>
    <p>
      The heatmap below shows annualised return by regime and industry (COVID excluded). Across every
      industry, Cutting is red and Hold-Elevated is green: there is no sector that escapes the
      regime-level pattern from Section 3, only degrees of it.
    </p>
    {industry_hm_html}
    <h3>Around the turn itself</h3>
    <p>
      In the reactive-cut window, <strong>{IND_NAMES[worst_cut_sector]}</strong> is the
      worst performer at T+90 ({lvl_delta(sec_fc[worst_cut_sector])}), consistent with the dot-com bust
      and the 2008 financial crisis both falling inside this group. Only {len(positive_cut_sectors)} of 12
      industries are still positive at T+90: <strong>{" and ".join(IND_NAMES[s] for s in positive_cut_sectors)}</strong>
      ({", ".join(lvl_delta(sec_fc[s]) for s in positive_cut_sectors)}). Utilities fits the classic
      defensive story, but Energy holding up is more likely specific to the oil-price backdrop of these
      episodes than a structural pattern. Around hikes, sector dispersion is far more muted:
      every industry stays within roughly {min(abs(round(v-100,1)) for v in sec_fh.values()):.0f} to
      {max(abs(round(v-100,1)) for v in sec_fh.values()):.0f} percentage points of flat.
    </p>
    <div class="chart-box">
      <div class="chart-title">Sector level at T+90 by turn type (T0 = 100)</div>
      <canvas id="sectorTransitionChart" height="100"></canvas>
      <div class="chart-legend">
        <span><span class="legend-dot" style="background:#1a5c52"></span>First hike (n={n_hike})</span>
        <span><span class="legend-dot" style="background:#dc2626"></span>First cut, reactive (n=2 at T+90)</span>
      </div>
    </div>
    <div class="callout amber">
      <strong>Read sector rotation cautiously.</strong> Twelve industries times a handful of turns means
      each cell in the transition chart is one or a few episodes. The defensive-sector pattern around
      reactive cuts is intuitive and consistent with the GFC and dot-com episodes specifically, not a
      law that holds in every future reactive cut.
    </div>
  </div>
</section>

<!-- Section 6: Style Factors -->
<section class="section" id="s6" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="section-counter">06</span><span>Style Factors</span></div>
    <h2>Quality and value factors rise into reactive cuts, even as the market falls</h2>
    <p>
      Using the Fama-French five factors plus momentum (Mkt-RF, SMB, HML, RMW, CMA, MOM), the clearest
      pattern in the whole report shows up here. In the reactive-cut transition window, the
      market factor falls {lvl_delta(fac_fc["Mkt-RF"])} by T+90, but Quality (RMW) rises
      {lvl_delta(fac_fc["RMW"])}, Value (HML) rises {lvl_delta(fac_fc["HML"])}, and Conservative
      Investment (CMA) rises {lvl_delta(fac_fc["CMA"])}. A flight to quality and value, funded out of
      the market factor, is the dominant rotation around reactive cuts. Around hikes, factor moves are
      smaller and less directional in either group.
    </p>
    <h3>By regime, full sample</h3>
    <p>
      Momentum's regime pattern is the standout caution here: best in Hold-Elevated (Sharpe
      {fac_reg["MOM"]["Hold-Elevated"]["sharpe"]:+.2f}) and worst in Hold-ZLB (Sharpe
      {fac_reg["MOM"]["Hold-ZLB"]["sharpe"]:+.2f}), consistent with the well-documented momentum-crash
      risk during the sharp market reversals that mark the start of zero-rate recovery periods.
    </p>
    {factor_hm_html}
    <div class="chart-box">
      <div class="chart-title">Style factor level at T+90 by turn type (T0 = 100)</div>
      <canvas id="factorTransitionChart" height="90"></canvas>
      <div class="chart-legend">
        <span><span class="legend-dot" style="background:#1a5c52"></span>First hike (n={n_hike})</span>
        <span><span class="legend-dot" style="background:#dc2626"></span>First cut, reactive (n=2 at T+90)</span>
      </div>
    </div>
  </div>
</section>

<!-- Section 7: Rates & Curve -->
<section class="section" id="s7">
  <div class="container">
    <div class="section-label"><span class="section-counter">07</span><span>Rates &amp; Curve</span></div>
    <h2>The 2s10s curve steepens hard after reactive cuts, flattens through hikes</h2>
    <p>
      The 10Y-2Y spread moves in opposite directions around the two turn types. Around first hikes it
      flattens by {t10y2y_fh_90:+.2f} points from T0 to T+90, the textbook tightening response as
      short rates rise faster than long rates. Around reactive first cuts it steepens by
      {t10y2y_fc_90:+.2f} points, as the Fed cuts the front end faster than long yields fall, the
      classic post-recession-onset steepening. The 10-year level itself rises {dgs10_fh_90:+.2f} points
      around hikes and falls {abs(dgs10_fc_90):.2f} points around reactive cuts.
    </p>
    <div class="chart-box">
      <div class="chart-title">10Y-2Y spread change from T0, by turn type</div>
      <canvas id="curveTransitionChart" height="90"></canvas>
      <div class="chart-legend">
        <span><span class="legend-line" style="background:#1a5c52"></span>First hike (n={n_hike})</span>
        <span><span class="legend-line" style="background:#dc2626"></span>First cut, reactive (n={n_cut})</span>
      </div>
    </div>
    <h3>Curve and vol levels by regime</h3>
    <table class="data-table">
      <thead><tr><th>Regime</th><th style="text-align:right">Avg 10Y</th><th style="text-align:right">Avg 2Y</th>
        <th style="text-align:right">Avg 10Y-2Y</th><th style="text-align:right">10Y-2Y range</th>
        <th style="text-align:right">Avg VIX</th><th style="text-align:right">Max VIX</th></tr></thead>
      <tbody>
{"".join(f'<tr><td>{REGIME_LABELS[r]}</td><td style="text-align:right">{curve_reg[r]["avg_dgs10"]:.2f}%</td>'
         f'<td style="text-align:right">{curve_reg[r]["avg_dgs2"]:.2f}%</td>'
         f'<td style="text-align:right">{curve_reg[r]["avg_t10y2y"]:+.2f}</td>'
         f'<td style="text-align:right">{curve_reg[r]["min_t10y2y"]:+.2f} to {curve_reg[r]["max_t10y2y"]:+.2f}</td>'
         f'<td style="text-align:right">{curve_reg[r]["avg_vix"]:.1f}</td>'
         f'<td style="text-align:right">{curve_reg[r]["max_vix"]:.1f}</td></tr>' for r in REGIME_ORDER)}
      </tbody>
    </table>
    <div class="callout blue">
      <strong>2s10s, not 10Y-3M.</strong> The classic recession-signal spread is 10Y-3M, but DGS2 (2-year)
      is the more standard cross-cycle slope measure and what is used throughout this report. The curve
      inverted (min_t10y2y &lt; 0) at points during both Hiking and Hold-Elevated, consistent with
      inversions preceding the 2001 and 2007 recessions.
    </div>
  </div>
</section>

<!-- Section 8: Methodology & Conclusions -->
<section class="section" id="s8" style="background:var(--bg2)">
  <div class="container">
    <div class="section-label"><span class="section-counter">08</span><span>Methodology &amp; Conclusions</span></div>
    <h2>What this is, what it isn't, and what to take away</h2>
    <table class="method-table">
      <thead><tr><th>Dimension</th><th>Detail</th></tr></thead>
      <tbody>
        <tr><td>Equity index</td><td>CRSP daily index file (crsp.dsi): sprtrn (S&amp;P 500 total return)
          and vwretd (CRSP value-weighted). Coverage 1994-01-03 to 2024-12-31, one year short of the
          CRSP v2 daily-file cutoff because crsp.dsi has not yet been extended to 2025.</td></tr>
        <tr><td>Sectors</td><td>Fama-French 12 industry portfolios, daily, Dartmouth data library.
          Not a 1:1 mapping to GICS sectors (see Section 5).</td></tr>
        <tr><td>Style factors</td><td>Fama-French 5 factors (Mkt-RF, SMB, HML, RMW, CMA) plus the
          momentum factor, daily, Dartmouth data library.</td></tr>
        <tr><td>Rates &amp; vol</td><td>FRED: VIXCLS, DGS2, DGS10, T10Y2Y, DFEDTARU/L. Fed funds target
          rate pre-corridor (pre-Dec 2008) is hardcoded from FOMC press releases, not FRED-sourced.</td></tr>
        <tr><td>Regime definition</td><td>Four buckets (Hiking, Cutting, Hold-Elevated, Hold-ZLB) from
          manually verified FOMC decision spans. A regime label can recur in non-adjacent date ranges,
          and drawdown is computed per contiguous spell, never bridging a regime change.</td></tr>
        <tr><td>Turn definition</td><td>First hike after a sustained hold or cut, first cut after a
          sustained hold or hike. Insurance cuts (1995, 2019) and the 2020 COVID emergency cut are isolated,
          not blended into the main first_hike/first_cut aggregates.</td></tr>
        <tr><td>Transition window</td><td>Trading days T-30 to T+90 around each turn date. Equity,
          sector, and factor series are cumulative-return-normalised so T0 = 100. VIX is the raw level.
          Curve series are level changes (percentage points) from T0, not normalised ratios.</td></tr>
      </tbody>
    </table>
    <h3>Conclusions</h3>
    <div class="callout green">
      <strong>Why matters more than what.</strong> The clearest finding across every dimension (equity,
      sectors, factors, the curve) is that reactive cuts and preemptive cuts are different animals. A
      cut made because the economy already broke is bearish for 90 days. A cut made to extend the cycle,
      or a hike made into a healthy economy, is not.
    </div>
    <div class="callout green">
      <strong>Quality and value, not defensives broadly, lead the reactive-cut rotation.</strong> RMW and
      CMA rise even as the market factor falls around reactive cuts. That is a more specific, more
      actionable signal than the loose "rotate defensive" narrative usually attached to Fed cuts.
    </div>
    <div class="callout amber">
      <strong>Eleven turns is not enough to trade on alone.</strong> Every average in this report has a
      single-digit sample size. The 2022 hike (into an inflation shock) and the 2024 cut (a clean
      soft-landing case with a truncated data window) show how much within-group variation a single
      macro backdrop can introduce. This report is descriptive, not a backtested strategy: per the
      site's research-first approach, a tradeable signal test was deliberately deferred pending exactly
      this kind of review.
    </div>
    <div class="callout red">
      <strong>Not investment advice.</strong> Historical regime statistics are not forward return
      forecasts. The Fed's own framework, the starting level of rates, and the macro backdrop all differ
      from any of the {n_turns_total} episodes studied here.
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
// Progress bar + nav.scrolled
const _nav = document.querySelector('nav');
window.addEventListener('scroll', () => {{
  const el  = document.getElementById('progress-bar');
  const pct = window.scrollY / (document.body.scrollHeight - window.innerHeight) * 100;
  el.style.width = Math.min(pct, 100) + '%';
  _nav.classList.toggle('scrolled', window.scrollY > 40);
}}, {{ passive: true }});

// Scroll reveal
const io = new IntersectionObserver(entries => {{
  entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }});
}}, {{ threshold: 0.07 }});
document.querySelectorAll('.section').forEach(s => io.observe(s));

// Side nav active state
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

// Chart defaults
Chart.defaults.font.family = 'Inter, sans-serif';
Chart.defaults.color = '#4a6460';
const GRID = {{ color: 'rgba(15,34,32,.05)', drawBorder: false }};
const TICK = {{ color: '#8aaba6', font: {{ size: 10 }} }};

// Chart: Returns by regime (s3)
new Chart(document.getElementById('regimeChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps([REGIME_LABELS[r] for r in REGIME_ORDER])},
    datasets: [
      {{ label: 'Ann. return (%)', data: {json.dumps([eq["spx"][r]["ann_return"] for r in REGIME_ORDER])},
        backgroundColor: {json.dumps(["#dc2626" if eq["spx"][r]["ann_return"] < 0 else "#1a5c52" for r in REGIME_ORDER])},
        borderRadius: 2, yAxisID: 'y' }},
      {{ type: 'line', label: 'Sharpe', data: {json.dumps([eq["spx"][r]["sharpe"] for r in REGIME_ORDER])},
        borderColor: '#2563eb', borderWidth: 2, pointRadius: 4, pointBackgroundColor: '#2563eb',
        yAxisID: 'y2' }}
    ]
  }},
  options: {{
    responsive: true, interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ position: 'top', labels: {{ boxWidth: 24 }} }} }},
    scales: {{
      x: {{ grid: {{ display: false }}, ticks: TICK }},
      y:  {{ grid: GRID, ticks: {{ ...TICK, callback: v => v + '%' }}, title: {{ display: true, text: 'Ann. return (%)', font: {{ size: 10 }} }} }},
      y2: {{ grid: {{ display: false }}, ticks: TICK, title: {{ display: true, text: 'Sharpe', font: {{ size: 10 }} }}, position: 'right' }}
    }}
  }}
}});

// Chart: Transition index (s4)
new Chart(document.getElementById('transitionIndexChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(WINDOW)},
    datasets: [
      {{ label: 'First cut, reactive', data: {json.dumps(tx_index["first_cut_mean"])}, borderColor: '#dc2626', borderWidth: 2.5, pointRadius: 0, fill: false, tension: 0.3 }},
      {{ label: 'First hike', data: {json.dumps(tx_index["first_hike_mean"])}, borderColor: '#1a5c52', borderWidth: 2.5, pointRadius: 0, fill: false, tension: 0.3 }},
      {{ label: 'Insurance cut 1995', data: {json.dumps(tx_index["insurance_1995"])}, borderColor: '#2563eb', borderWidth: 1.5, borderDash: [4,3], pointRadius: 0, fill: false, tension: 0.3 }},
      {{ label: 'Insurance cut 2019', data: {json.dumps(tx_index["insurance_2019"])}, borderColor: '#7E3AF2', borderWidth: 1.5, borderDash: [4,3], pointRadius: 0, fill: false, tension: 0.3 }},
      {{ label: 'COVID 2020 (outlier)', data: {json.dumps(tx_index["covid_2020_outlier"])}, borderColor: '#9ca3af', borderWidth: 1.5, borderDash: [2,2], pointRadius: 0, fill: false, tension: 0.3 }}
    ]
  }},
  options: {{
    responsive: true, interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ grid: GRID, ticks: {{ ...TICK, callback: (v,i) => {{ const l = {json.dumps(WINDOW)}[i]; return l % 10 === 0 ? 'T' + (l>=0?'+':'') + l : ''; }} }} }},
      y: {{ grid: GRID, ticks: TICK, title: {{ display: true, text: 'SPX level (T0=100)', font: {{ size: 10 }} }} }}
    }}
  }}
}});

// Chart: Transition VIX (s4)
new Chart(document.getElementById('transitionVixChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(WINDOW)},
    datasets: [
      {{ label: 'First cut, reactive', data: {json.dumps(tx_vix["first_cut_mean"])}, borderColor: '#dc2626', borderWidth: 2.5, pointRadius: 0, fill: false, tension: 0.3 }},
      {{ label: 'First hike', data: {json.dumps(tx_vix["first_hike_mean"])}, borderColor: '#1a5c52', borderWidth: 2.5, pointRadius: 0, fill: false, tension: 0.3 }}
    ]
  }},
  options: {{
    responsive: true, interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ grid: GRID, ticks: {{ ...TICK, callback: (v,i) => {{ const l = {json.dumps(WINDOW)}[i]; return l % 10 === 0 ? 'T' + (l>=0?'+':'') + l : ''; }} }} }},
      y: {{ grid: GRID, ticks: TICK, title: {{ display: true, text: 'VIX level', font: {{ size: 10 }} }} }}
    }}
  }}
}});

// Chart: Sector transition T+90 (s5)
new Chart(document.getElementById('sectorTransitionChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps([IND_NAMES[k] for k in sec_fh])},
    datasets: [
      {{ label: 'First hike', data: {json.dumps([round(v,1) for v in sec_fh.values()])}, backgroundColor: 'rgba(26,92,82,.75)', borderRadius: 2 }},
      {{ label: 'First cut, reactive', data: {json.dumps([round(v,1) for v in sec_fc.values()])}, backgroundColor: 'rgba(220,38,38,.7)', borderRadius: 2 }}
    ]
  }},
  options: {{
    responsive: true, indexAxis: 'y',
    plugins: {{ legend: {{ position: 'top', labels: {{ boxWidth: 24 }} }} }},
    scales: {{
      x: {{ grid: GRID, ticks: {{ ...TICK, callback: v => v }} , title: {{ display: true, text: 'Level at T+90 (T0=100)', font: {{ size: 10 }} }} }},
      y: {{ grid: {{ display: false }}, ticks: {{ ...TICK, font: {{ size: 9 }} }} }}
    }}
  }}
}});

// Chart: Factor transition T+90 (s6)
new Chart(document.getElementById('factorTransitionChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps([FAC_NAMES[k] for k in fac_fh])},
    datasets: [
      {{ label: 'First hike', data: {json.dumps([round(v,1) for v in fac_fh.values()])}, backgroundColor: 'rgba(26,92,82,.75)', borderRadius: 2 }},
      {{ label: 'First cut, reactive', data: {json.dumps([round(v,1) for v in fac_fc.values()])}, backgroundColor: 'rgba(220,38,38,.7)', borderRadius: 2 }}
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ position: 'top', labels: {{ boxWidth: 24 }} }} }},
    scales: {{
      x: {{ grid: {{ display: false }}, ticks: {{ ...TICK, font: {{ size: 9 }} }} }},
      y: {{ grid: GRID, ticks: TICK, title: {{ display: true, text: 'Level at T+90 (T0=100)', font: {{ size: 10 }} }} }}
    }}
  }}
}});

// Chart: Curve transition (s7)
new Chart(document.getElementById('curveTransitionChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(WINDOW)},
    datasets: [
      {{ label: 'First hike', data: {json.dumps(tx_curve["first_hike_t10y2y_delta"])}, borderColor: '#1a5c52', borderWidth: 2.5, pointRadius: 0, fill: false, tension: 0.3 }},
      {{ label: 'First cut, reactive', data: {json.dumps(tx_curve["first_cut_t10y2y_delta"])}, borderColor: '#dc2626', borderWidth: 2.5, pointRadius: 0, fill: false, tension: 0.3 }}
    ]
  }},
  options: {{
    responsive: true, interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ position: 'top', labels: {{ boxWidth: 24 }} }} }},
    scales: {{
      x: {{ grid: GRID, ticks: {{ ...TICK, callback: (v,i) => {{ const l = {json.dumps(WINDOW)}[i]; return l % 10 === 0 ? 'T' + (l>=0?'+':'') + l : ''; }} }} }},
      y: {{ grid: GRID, ticks: TICK, title: {{ display: true, text: '10Y-2Y change from T0 (pts)', font: {{ size: 10 }} }} }}
    }}
  }}
}});
</script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"\nSaved index.html ({len(html):,} chars)")
print("Done.")

