# Handoff — The Gamma Trap (0DTE GEX & Intraday Vol)

## Status
**Finalized & Published.** `index.html` live at `/research/0dte-gamma-trap/`. Build script `06_build_report.py` now produces the polished, final version automatically.

---

## Completed Fixes (Apr 2026)

The following issues were identified and resolved:
1.  **Date Consistency:** Reconciled all date references to "Jan 2022 – Dec 2024" (722 trading days). While GEX data reached Aug 2025, the merged RVol dataset truncated at Dec 2024; the report now dynamically pulls dates from the merged data to ensure 100% accuracy.
2.  **Visual Automation:** All "post-generation" manual polish (dark tooltips, box plots, gridline styling) has been folded into `06_build_report.py`. The script is now the single source of truth.
3.  **KPI Accuracy:** Verified KPI strip matches analysis output (+42% vol premium, t=7.66).
4.  **Structural Polish:** Fixed section counter numbering (01–07) and ensured side-nav labels match headers exactly.

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
| Sample | 722 trading days, Jan 2022 – Dec 2024 |

---

## Scripts

| Script | Purpose | Output |
|---|---|---|
| `01_data_check.py` | Verifies SPX secid (108105), TAQ table name, column names | Prints only |
| `02_gex_pull.py` | SPX 0DTE GEX via Black-Scholes inversion from OptionMetrics | `data/gex_daily.parquet` |
| `03_intraday_pull.py` | CRSP Parkinson vol (Phase 1) + TAQ 30-min bucket profile (Phase 2) | `data/rvol_daily.parquet`, `data/rvol_profile.parquet` |
| `04_analysis.py` | Merge, regime classification, Welch t-test, Kruskal-Wallis, OLS | `data/combined.parquet`, `data/bucket_by_regime.parquet` |
| `05_charts.py` | Builds 5 Chart.js JSON files | `charts/data_*.json` |
| `06_build_report.py` | Generates the full polished HTML report | `index.html` |

---

## Design System

The report follows the "Parchment & Teal" standard established in the ETF rotation study:
- Light frosted glass nav + paper grain overlay
- `hero-tag` + `hero-meta-item` hero pattern
- Box-plot distribution (Chart 2) using floating bars
- Dark theme tooltips for all Chart.js components
- Labeled `#side-nav` with IntersectionObserver highlight
