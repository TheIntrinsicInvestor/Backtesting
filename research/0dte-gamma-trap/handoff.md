# Handoff — The Gamma Trap (0DTE GEX & Intraday Vol)

## Status
**Published.** `index.html` live at `/research/0dte-gamma-trap/`. Added to `research/index.html` listing and `index.html` homepage REPORTS array.

---

## ⚠ ACTION REQUIRED — Review for Errors at Next Session Start

**Brian spotted errors on first review. At the start of the next session, open the live report and go through every section carefully:**

1. Read all 7 sections end-to-end for factual errors, awkward phrasing, or number inconsistencies
2. Check the date range — hero says "Jan 2022 – Aug 2025" but body text in multiple places says "Jan 2022 to Dec 2024" — these must be reconciled (the data actually runs to Aug 2025)
3. Check all chart labels and legends are accurate
4. Verify the KPI strip numbers match the analysis output (handoff table above)
5. Check section counter alignment — all 7 sections should have counters 01–07
6. Fix any issues found, then re-verify the site renders correctly

---

---

## What Was Built

An empirical research report showing how SPX 0DTE dealer gamma exposure (GEX) creates two distinct intraday volatility regimes. The full pipeline runs against WRDS institutional data and outputs a self-contained `index.html`.

---

## Key Findings

| Metric | Value |
|---|---|
| Negative GEX mean intraday RVol | 13.3% annualised |
| High GEX mean intraday RVol | 9.4% annualised |
| Vol premium (neg vs high) | +42% |
| Welch t-statistic | 7.66 |
| p-value | <0.0001 |
| R² (GEX vs RVol, OLS) | 0.054 |
| Sample | 722 trading days, Jan 2022 – Aug 2025 |

---

## Scripts

All scripts are complete and have been run successfully.

| Script | Purpose | Output |
|---|---|---|
| `01_data_check.py` | Verifies SPX secid (108105), TAQ table name (`taqmsec.ctm_{date}`), column names | Prints only |
| `02_gex_pull.py` | SPX 0DTE GEX via Black-Scholes inversion from OptionMetrics | `data/gex_daily.parquet` |
| `03_intraday_pull.py` | CRSP Parkinson vol (Phase 1) + TAQ 30-min bucket profile (Phase 2) | `data/rvol_daily.parquet`, `data/rvol_profile.parquet` |
| `04_analysis.py` | Merge, regime classification, Welch t-test, Kruskal-Wallis, OLS | `data/combined.parquet`, `data/bucket_by_regime.parquet`, `data/lowess_pts.json` |
| `05_charts.py` | Builds 5 Chart.js JSON files | `charts/data_*.json` |
| `06_build_report.py` | Generates the full HTML report | `index.html` |

---

## Data Files (gitignored)

All parquet files in `data/` are cached. Do not delete — re-running WRDS pulls takes significant time.

- `data/gex_daily.parquet` — 887 rows (SPX 0DTE GEX per day)
- `data/rvol_daily.parquet` — 753 rows (CRSP Parkinson vol per day)
- `data/rvol_profile.parquet` — 390 rows (30-min bucket vol for 30 sampled days)
- `data/combined.parquet` — 722 rows (merged GEX + RVol with regime labels)
- `data/bucket_by_regime.parquet` — avg bucket vol by regime (for Chart 4)
- `data/lowess_pts.json` — empty (statsmodels not installed; scatter uses OLS line only)

---

## Critical Implementation Notes

**OptionMetrics doesn't provide gamma for SPX index options** — `impl_volatility`, `gamma`, `delta` are all NULL in `opprcd`. We compute IV via Brent's method on bid/offer mid-prices, then derive gamma from Black-Scholes. See `02_gex_pull.py` lines 38–66.

**TAQ table name is `taqmsec.ctm_{YYYYMMDD}`** (millisecond version), not `taq.ct_{date}`. Column for time is `time_m` (returns Python `datetime.time` object, not a string). Parse via `pd.Timestamp(f"2000-01-01 {t}")`.

**CRSP Parkinson vol uses SPY permno = 84398.** Parkinson formula: `sqrt(252 * 1/(4*ln(2))) * ln(askhi/bidlo)`. This replaces looping 887 TAQ queries with a single fast CRSP query.

**WRDS username:** `hoovyalert` — set via `WRDS_USERNAME` env var before running any script.

**Windows Unicode issue:** Print statements with `≤`, `→`, `≥` cause `UnicodeEncodeError` on Windows cp1252 console. Use ASCII equivalents (`<=`, `->`, `>=`) in any new print statements.

---

## Chart Improvements Made (post-generation)

The following were applied directly to `index.html` after `06_build_report.py` ran:

- Dark tooltip style (ink background, custom padding/radius) applied globally via `Chart.defaults`
- Animations disabled (`Chart.defaults.animation = false`)
- Lighter, thinner gridlines (0.75px, `rgba(0,0,0,0.05)`)
- Y-axis `%` suffix via tick callbacks on all charts
- **Chart 2** converted from simple median bars to a proper box plot using Chart.js floating bars — wide translucent bar = p10–p90, filled box = IQR (p25–p75), thin solid bar = median
- **Chart 3** regression line made dashed; slightly better point opacity
- **Chart 4** subtle area fill under each line; better tension
- **Chart 5** more transparent bars so rolling average line reads through cleanly

These changes are in `index.html` only — `06_build_report.py` still generates the pre-improvement version. If you regenerate, re-apply the chart improvements or fold them into the Python script.

---

## Published — Steps Completed

1. ✓ Added `<a class="report-row">` block to `research/index.html`
2. ✓ Added entry at position 0 of `REPORTS` array in `index.html` (homepage)
3. ✓ Reformatted `index.html` to match ETF rotation design system (light nav, side-nav, section counters, hero-meta-item, paper grain, progress bar)
4. ✓ Committed and pushed to GitHub Pages

## Design Notes

The report now uses the standard "Parchment & Teal" design system matching `research/etf-factor-sector-rotation-strategy/index.html`:
- Light frosted glass nav, paper grain, progress bar
- `hero-tag` + `hero-meta-item` hero pattern
- `section-counter` (01–07) numbered sections
- Labeled `#side-nav` with scroll-reveal
- Chart.js 4.4.1 with dark tooltip defaults
