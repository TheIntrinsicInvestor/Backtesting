# Report Plan: sections, charts and the numbers each one uses

*For review before any HTML exists. Headline agreed: where the premium lives. P&L shown gross and
net of published fees. Folder: `research/barrier-skew/`, working title "The Barrier Premium".*

Every number below already exists in `data/` (stats_index.json, stats_sn.json, prices_*.parquet,
outcomes_*.parquet) unless marked NEW, which means script `25_report_data.py` has to compute it.
That script writes one `report_data.json` that the page's JS constants come from, so prose can
quote the constants exactly (project data-integrity rule).

## Hero and KPI strip

Lede: banks sell the crash risk inside reverse convertibles at prices set by the volatility skew.
Over 30 years, that skew charged 2.5x what the S&P 500 actually delivered, and 1.3x what single
stocks delivered. KPI strip (4 tiles):

| KPI | Value | Source |
|---|---|---|
| Index premium kept by the seller | 69% | stats_index SPX 0.7 |
| Single-name premium kept | 29% | stats_sn 0.7 |
| Model vs realised knock-ins, SPX | 2.5x | ratio, NOTES table |
| Published fee on the real notes | 6-7% p.a. | Vokata (2021) |

## 1. Primer: the put hiding inside a structured note

Prose: what a down-and-in put is, where it sits in a reverse convertible, why the barrier makes
skew matter (the price depends on the whole path, not just the final level).

- **Chart 1a (Chart.js line):** the SPX 1-year smile on one illustrative date, implied vol against
  moneyness, with vertical markers at the 60/70/80% barriers and at the deepest quoted point.
  Shows the wing the barrier sits in. NEW: pull one date's fitted curve plus its grid points.
- **Chart 1b (small grouped bar):** for that same date, knock-in probability under the three
  models. Concrete version of the abstract gap. NEW.

## 2. What the skew does to the price

- **Chart 2 (Chart.js line, 3 series):** SPX 70% barrier, 1996-2024 weekly: DIP price under local
  vol, ATM flat and barrier-strike flat, as % of notional. NEW (downsample to 4-week means to keep
  the payload small; state that in the caption).
- **Chart 3 (Chart.js line, 3 series):** the same dates: equivalent flat vol vs ATM vol vs
  barrier-strike vol. Makes the "which flat vol?" answer visual: the right number sits between the
  two, and the spread moves with the regime. NEW.
- Table: average price and probability by barrier for all three models, all three sets (the NOTES
  table).

## 3. Implied vs realised: the core test

- **Chart 4 (grouped bar, 3 panels or one chart with 9 groups):** realised knock-in rate vs the
  three models, for SPX / SX5E / single names at 60/70/80%.
- **Chart 5 (dot and range):** the gap (model minus realised) with 95% block-bootstrap intervals,
  one row per set and barrier. This is where significance is shown honestly: SPX 70%, single names
  70% and 80% exclude zero; SX5E does not.
- Prose states effective sample size next to every claim (about 30 independent years on SPX,
  21 on SX5E) and that all SPX 60% knock-ins come from 2008.

## 4. Where the premium lives (headline section)

- **Chart 6 (horizontal bar):** premium kept, by set and barrier: SPX about 70%, SX5E about 45%,
  single names about 29%.
- **Chart 7 (bar):** model-to-realised ratio by set: 2.5x SPX, 1.4x SX5E, 1.3x single names.
- NEW: single-name premium kept split by the name's ATM vol tercile, to show the result is not
  driven by the most volatile names.
- Prose ties this to Driessen, Maenhout and Vilkov (2009): the premium is an index phenomenon.

## 5. The skew is a price, not a forecast

- **Chart 8 (HTML heatmap table, diverging colours per chart-patterns.md):** rows = era
  (1996-2007, GFC, 2010-2019, 2020-), columns = set, cells = model probability minus realised.
  Red where the model understated (GFC), green where it overstated (the calm decades).
- **Chart 9 (bar):** knock-in count by start year, SPX and single names, showing the clustering
  into a few episodes. NEW (from outcomes_*).
- **Chart 10 (calibration, scatter with 45-degree line):** binned model probability vs realised
  frequency, single names (SPX bins are too sparse; say so).

## 6. What it means for someone buying the note

- **Chart 11 (waterfall or paired bar):** single-name seller P&L gross (+3.45%) then minus the
  published fee range (6-7%), ending negative. Index shown alongside for contrast.
- Prose: our measured premium is what the embedded put earned before costs. Published fee
  estimates (Vokata 6-7% p.a.; Henderson and Pearson about 8% of issue price; Wallmeier and
  Diethelm 3.4%; Stoimenov and Wilkens about 3%) exceed it on the single-stock notes retail
  actually buys. State clearly this is an indicative comparison, not a like-for-like one: our
  product is a standalone 1-year put, theirs are coupon notes with call features.

## 7. Methodology and limits

Compact reference table: data sources and coverage, product definition, the three models, the
validation gates and what they returned (PDE vs Monte Carlo, local vol repricing within 0.25 vp,
wing gate MAE 0.52 vp against 762 listed quotes), the exclusion rule, and the overlap-robust
statistics. Then the limits list from SPEC section 10, plus the three bugs found during the build
(barrier grid alignment, low-vol overflow, split adjustment) as evidence of the checks.

## Build order

1. `25_report_data.py` computes every NEW item above into `report_data.json`.
2. `30_build_report.py` writes `index.html` with JS data constants from that JSON.
3. Local preview via `.\serve.ps1`, then the `publish-report` skill's audit and design checklist.
4. Homepage and research-listing wiring only after you approve the built page.

## Open questions for the build

1. Working title: "The Barrier Premium" vs something more concrete like "What the Skew Charges for
   a Crash".
2. Whether to show SX5E throughout (it adds a second market but no significant result) or to keep
   it to one robustness section.
3. Whether the primer gets an interactive element (a barrier slider) or stays static.
