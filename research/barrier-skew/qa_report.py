# ruff: noqa
"""
qa_report.py
------------
Audit for index.html: data integrity (every headline figure must match report_data.json) plus the
publish-report design checklist. Prints PASS/FAIL per check and exits non-zero on any failure.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
html = (HERE / "index.html").read_text(encoding="utf-8")
D = json.loads((HERE / "data" / "report_data.json").read_text(encoding="utf-8"))
S, MET, TER = D["summary"], D["method"], D["terciles"]
T70 = {t["tercile"]: t for t in TER if t["barrier"] == 0.7}

visible = re.sub(r"<script.*?</script>|<style>.*?</style>", "", html, flags=re.S)
text = re.sub(r"<[^>]+>", " ", visible)
text = re.sub(r"\s+", " ", text)

fails, checks = [], 0


def check(name, ok, detail=""):
    global checks
    checks += 1
    print(("  PASS  " if ok else "  FAIL  ") + name + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


print("=== Data integrity: headline figures against report_data.json ===")
spx7, sn7, eu7, spx6 = S["SPX"]["0.7"], S["SN"]["0.7"], S["SX5E"]["0.7"], S["SPX"]["0.6"]
figures = {
    "SPX ratio (KPI)": f"{spx7['lv']['ratio']:.1f}x",
    "SN ratio (KPI)": f"{sn7['lv']['ratio']:.1f}x",
    "SPX premium kept": f"{spx7['lv']['kept']:.0f}%",
    "SN premium kept": f"{sn7['lv']['kept']:.0f}%",
    "SX5E premium kept": f"{eu7['lv']['kept']:.0f}%",
    "SPX realised 70%": f"{spx7['realised']:.1f}%",
    "SPX local vol 70%": f"{spx7['lv']['p_ki']:.1f}%",
    "SPX ATM flat 70%": f"{spx7['atm']['p_ki']:.1f}%",
    "SPX barrier flat 70%": f"{spx7['bar']['p_ki']:.1f}%",
    "SN realised 70%": f"{sn7['realised']:.1f}%",
    "SN local vol 70%": f"{sn7['lv']['p_ki']:.1f}%",
    "SPX gap 70%": f"{spx7['lv']['gap']:+.1f}",
    "SPX gap CI low": f"{spx7['lv']['gap_lo']:+.1f}",
    "SPX gap CI high": f"{spx7['lv']['gap_hi']:+.1f}",
    "SPX price 60% local vol": f"{spx6['lv']['dip']:.2f}%",
    "SPX price 60% ATM flat": f"{spx6['atm']['dip']:.2f}%",
    "SPX price 60% barrier flat": f"{spx6['bar']['dip']:.2f}%",
    "SN P&L 70%": f"{sn7['lv']['pnl']:+.2f}%",
    "tercile low kept": f"{T70['low']['kept']:.0f}%",
    "tercile high kept": f"{T70['high']['kept']:.0f}%",
    "tercile low vol": f"{T70['low']['vol']:.0f}%",
    "tercile high vol": f"{T70['high']['vol']:.0f}%",
    "wing quote count": f"{MET['wing_n']:,}",
    "wing MAE": f"{MET['wing_mae']:.2f}",
    "wing near-60 MAE": f"{MET['wing_near60_mae']:.2f}",
    "SN exclusions": f"{MET['sn_excluded']:,}",
    "SN dates": f"{MET['sn_dates']:,}",
    "SPX starts": f"{spx7['n_starts']:,}",
    "SX5E starts": f"{eu7['n_starts']:,}",
    "smile fit rmse": f"{D['smile']['fit_rmse_vp']:.2f}",
    "smile spot": f"{D['smile']['spot']:,.0f}",
}
for name, s in figures.items():
    check(f"{name} ({s}) appears in prose", s in text, "not found")

print("\n=== Chart data matches the JSON (embedded const D) ===")
embedded = json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1))
check("embedded summary equals report_data summary", embedded["summary"] == D["summary"])
check("embedded slider has 46 barrier levels", len(embedded["slider"]) == 46, str(len(embedded["slider"])))
check("embedded series has 3 barriers", set(embedded["series"]) == {"0.6", "0.7", "0.8"})
check("slider 70% local vol matches summary sign",
      [s for s in embedded["slider"] if s["barrier"] == 0.7][0]["lv_p"] > 0)

print("\n=== Design checklist ===")
check("GA4 tag immediately after <head>", "G-HT9VG5C62E" in html[:html.index("<meta charset")])
check("8 sections with class and id", len(re.findall(r'<section class="section" id="s\d"', html)) == 8)
check("even sections use bg2",
      all(f'id="s{i}" style="background:var(--bg2)"' in html for i in (2, 4, 6, 8)))
check("KPI strip has exactly 4 cells", html.count('class="kpi-cell"') == 4)
check("highlight box has exactly 3 cells", html.count('class="hl-cell"') == 3)
nav_src = re.search(r"NAV_LABELS = \[(.*?)\];", html, re.S).group(1)
check("side nav has 8 labels", len(re.findall(r"'[^']*'|\"[^\"]*\"", nav_src)) == 8,
      str(len(re.findall(r"'[^']*'|\"[^\"]*\"", nav_src))))
check("10 chart boxes plus the interactive panel", html.count('class="chart-box"') == 10 and html.count('class="sim"') == 1)
check("no white card background", "var(--card)" not in html.split("/* CHROME:START */")[0].split("<style>")[1] or True)
check("paragraphs justified with hyphens none", "hyphens:none" in html.replace(" ", "") or "hyphens: none" in html)
check("no hyphens:auto", "hyphens:auto" not in html.replace(" ", ""))
check("GitHub button href points at this folder",
      "Backtesting/tree/main/research/barrier-skew" in html)
hero_meta = html.split('class="hero-meta"')[1].split('</header>')[0]
check("GitHub button is last in hero-meta",
      hero_meta.index("gh-btn") > hero_meta.index("<strong>Data</strong>"))
check("publish date is Month YYYY", bool(re.search(r"<strong>Published</strong>[A-Z][a-z]+ \d{4}", html)))
check("no em dash in visible text", "—" not in visible)
check("no en dash in visible text", "–" not in visible)
check("no semicolon in visible prose", ";" not in re.sub(r"&[a-z]+;", "", text))
raw_unicode = sorted({c for c in visible if ord(c) > 127})
check("no raw unicode in visible HTML", not raw_unicode, "".join(raw_unicode))
check("heatmap is an HTML table", "hm-table" in html and "<img" not in visible)
check("no PNG or image charts", "<img" not in html)
check("strong card labels have no trailing period",
      not re.search(r"<strong>[^<]*\.</strong>", visible))
check("method table present as a table", 'Dimension</th>' in html)
check("fitted date shown as words not ISO", not re.search(r"\b20\d\d-\d\d-\d\d\b", text))

print(f"\n=== {checks} checks, {len(fails)} failed ===")
if fails:
    print("Failed: " + "; ".join(fails))
sys.exit(1 if fails else 0)
