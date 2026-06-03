# Plan: "The Selective Walk-Down" — Earnings Sandbagging Report

> **Supersedes the original quarterly plan.** That version (quarterly EPS, T-90 window,
> "Anatomy of the Walk-Down", no drift analysis) was abandoned after the data came in.
> Quarterly estimates show no walk-down (analysts set at T-89 and hold). We pivoted to
> **annual estimates (`fpi='1'`)** over a T-270 window, which carries a real signal, and
> the narrative changed to **"The Selective Walk-Down"**. Scripts 01–05 are complete and
> their data is final. This plan covers the remaining build (returns + analysis + report).

## Context

Quant research report for theintrinsicinvestor.com on **earnings sandbagging**: the
practice where S&P 500 firms let analysts' annual EPS estimates drift down before
reporting so they can "beat" a lowered bar. Scope settled with Brian:

- **Universe:** S&P 500. **Range:** 2015–2025. **EPS:** annual (`fpi='1'`).
- **Narrative:** "The Selective Walk-Down" — lead with the paradox (the *median* event
  walks UP +0.7%), then reveal the walk-down is deployed *selectively* on the firms that
  would otherwise miss.
- **This report has a tradeable section** (unlike the original pure-critique plan). The
  trade thesis is muted announcement reaction **and** post-print drift fade for
  manufactured beats. Honesty rule applies: end with a clear viable/not-viable verdict.

The walk-down is measured via daily point-in-time consensus reconstruction from
`ibes.det_epsus` (script 04, already built and vectorised — do not revert).

## What is already done (scripts 01–05, data final)

`01_universe.py`, `02_earnings_dates.py`, `02b`/`02d` IBES fallbacks, `03_detail_pull.py`,
`04_reconstruct_walkdown.py`, `05_mktcap_pull.py`. Outputs in `data/`:
`sp500_constituents`, `earnings_dates`, `det_epsus_raw`, `walkdown_curve`,
`walkdown_events`, `mktcap`, and `mktcap_by_year/prices_*.parquet` (daily price panel,
full universe 2014–2025).

**Locked reconstruction params (in script 04):** annual `fpi='1'`, `STALE_DAYS=365`,
`ORIG_WINDOW=(-280,-260)`, `FINAL_WINDOW=(-7,-2)`, `ANALYST_FLOOR=3`, `SMALL_BASE=$0.10`.
Note: `ibes.det_epsus` has **no `estdats` column**; `anndats` is the estimate issue date.

### Key results (single source of truth = the parquet, then `analysis.json`)

- 6,131 included events. Classes: genuine_beat 4,009, manufactured_beat 849, miss 1,273.
- **Manufactured beat rate = 849 / 4,858 beats = 17.5%.**
- Walk bins: down(<−2%) 1,838 (30.0%) · flat 1,864 (30.4%) · up(>+2%) 2,429 (39.6%).
- Cross-tab (walk bin × class): manufactured = 709 down / 140 flat / **0 up**.
- Manufactured cohort: median walk −6.4%, mean −10.6%, **median 17 analysts** (well-covered).
- Genuine cohort: median walk +3.0%, mean +9.8%.

## Approach for the remaining build

Three scripts, renumbered DAG **06 → 07 → 08**. WRDS scripts use the standard
`builtins.input`/`getpass` monkey-patch and run with
`$env:WRDS_USERNAME="hoovyalert"; $env:PGPASSWORD=...`. `data/*.parquet` gitignored;
`charts/*.json` (or `analysis.json`) committed so the report regenerates from JSON alone.
Deliver in DAG-batches (batch delivery approved); do **not** push or publish until Brian
reviews.

### Data gap to close (small)

The descriptive pipeline never pulled returns. The daily price panel already exists
locally; the only missing piece is the **benchmark** — SPY (permno 84398) is not in the
universe files.

- **Caveat:** returns are price-only (no `dlyret`), so dividends are excluded. Acceptable
  for a short event study; consistent with the congressional-herd report. Disclose it.
- **Censoring:** CRSP v2 ends 2025-12-31, so late-2025 announcements lack a full T+60
  window. Flag and exclude censored events from drift stats.

### Script DAG

| # | File | Source / pattern | Output |
|---|---|---|---|
| 06 | `06_event_returns.py` | **NEW** — reuse WRDS auth + `dsf_v2` query from `05_mktcap_pull.py`; reuse `build_price_index` + `compute_one_entry` (SPY-excess) from `congressional-herd/03_forward_returns.py` | `data/spy_prices.parquet`, `data/event_returns.parquet` |
| 07 | `07_analysis.py` | **NEW** — aggregate `walkdown_events` + `event_returns` into one JSON (single source of truth) | `data/analysis.json` |
| 08 | `08_build_report.py` | copy structure from `earnings-vol-cycle/07_build_report.py`; follow `.claude/report-template.md` | `index.html` |

### Script 06 — per-event market-adjusted returns

- Pull **only SPY (84398)**, 2014–2025, cache `data/spy_prices.parquet` (skip if cached).
- Concatenate `mktcap_by_year/prices_*.parquet` into one daily panel; index
  `permno -> sorted price frame`.
- For each included event, locate the trading-day index of `anndats`, then compute
  market-adjusted vs SPY over the same calendar window:
  - `car_reaction` = stock(T−1→T+1) − SPY(T−1→T+1)  (muted-reaction test)
  - `car_drift_60` = stock(T+1→T+60) − SPY(T+1→T+60)  (drift-fade test)
  - keep raw legs + `censored_drift` flag.
- Output `data/event_returns.parquet`: permno, anndats, classification, car_reaction,
  car_drift_60, censored_drift.

### Script 07 — aggregate to `analysis.json`

- **KPIs (4):** 17.5% manufactured beat rate; 849 manufactured beats; −6.4% median walk
  (mfg cohort); + one strategy KPI chosen after results.
- **Distribution series** — `walkdown_pct` histogram, three regimes, mfg shaded.
- **Hero: two-cohort walk curves** — offsets −270…−2, each event's consensus as % deviation
  from its own T-270 base, averaged by cohort (manufactured declines, genuine rises),
  indexed to 100 at start.
- **Cross-tab** — walk bin × classification counts.
- **Cohort profile** — analyst coverage (mfg median 17 vs others), sector tilt, near-miss
  concentration, size buckets via `mktcap.parquet`.
- **Strategy tables** — by cohort: mean/median `car_reaction` and `car_drift_60`, n, t-stat,
  hit rate; long-genuine/short-manufactured spread + naive Sharpe. Exclude censored from drift.

### Script 08 — `research/sandbagging/index.html`

Load `analysis.json`; write figures directly into JS constants (prose cites constants,
never the reverse). Follow `report-template.md` + `design-system.md`; canonical reference
`research/0dte-gamma-trap/index.html`. Section order:

1. **Study Design** — paradox hook (+0.7% walk-UP), class definitions, data + exclusions.
2. **The Selective Walk-Down** — distribution (30/30/40), **hero two-cohort curves**,
   cross-tab callout ("0 manufactured beats came from a firm that walked up").
3. **Who Gets Walked Down** — analyst-coverage finding (sandbagging at the *most*-covered
   names), sector tilt, near-miss concentration, size.
4. **Does It Pay? (Strategy)** — muted-reaction `highlight-box` + CAR(T−1→T+1) chart;
   drift `highlight-box` + CAR(T+1→T+60) chart + long-short table; "What these results
   mean"; brutally honest viability verdict (borrow, overlap, costs, censoring);
   `callout red` disclaimer.
5. **Methodology** — `method-table`: PIT params, price-only/dividend caveat, SPY benchmark,
   censoring, `STALE_DAYS` note.
6. **Conclusions** — 4 callouts + limitations.

Design rules (CLAUDE.md): GA4 tag after `<head>`, `var(--bg2)` boxes (no white cards),
HTML-table heatmaps, justified text `hyphens:none`, no em dashes/semicolons, HTML entities
for Unicode, GitHub Code button → `.../tree/main/research/sandbagging`, "Published Month YYYY".
Keep **WIP / unlisted** (no homepage or research-listing entry) until Brian reviews.

## Verification

1. **06:** `event_returns.parquet` rows ≈ included events minus censored; sanity-check
   mean `car_reaction` is small and genuine > manufactured.
2. **07:** `analysis.json` KPIs match the figures above exactly; two-cohort curves move in
   opposite directions; up-bin manufactured count = 0.
3. **08:** preview with `.\serve.ps1` (not deploy-to-verify); audit prose vs JS constants
   (KPI strip, callouts, conclusion, methodology all agree); confirm hero renders and the
   strategy verdict is explicit.
4. Do **not** add to homepage / research listing until visual QA passes (status stays WIP).

## Out of scope

- No edits to scripts 01–05 (data final; do not revert 04's vectorised reconstruction).
- No homepage/research-listing changes until published.
- Anthropic API-key rotation remains separate housekeeping, not part of this build.
