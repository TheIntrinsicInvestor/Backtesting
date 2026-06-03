# Plan: "The Walk-Down" — Earnings Sandbagging Report

## Context

New quant research report for theintrinsicinvestor.com exposing **earnings sandbagging**: the practice where S&P 500 companies guide analysts' EPS estimates downward in the weeks before reporting so they can "beat" a lowered bar. The report quantifies (a) the shape of the consensus walk-down curve and (b) what fraction of reported "beats" are *manufactured* (beat the final pre-announcement consensus but would have *missed* the original ~90-day-prior consensus).

Settled in the requirements conversation:
- **Universe:** S&P 500. **Range:** 2015-2025. **EPS:** quarterly only.
- **No post-earnings drift analysis** — this is a pure critique of the earnings-beat narrative, in the spirit of the congressional-herd piece.
- **Narrative spine: "Anatomy of the Walk-Down" (analytical)** — lead with the curve shape, then reveal the manufactured-beat statistic.
- **Walk-down measured via daily point-in-time consensus reconstruction from `ibes.det_epsus`** (individual analyst estimates), not the 3-point monthly `statsum` snapshots. The smooth daily curve is the visual centrepiece.

Lives in new folder `research/sandbagging/`. Reuses most of the `earnings-vol-cycle` pipeline; the one genuinely new component is the `det_epsus` reconstruction.

## Approach

Copy-and-modify the proven `earnings-vol-cycle` scripts for universe, earnings dates, and report-building; write two new scripts for the detail-estimate pull and the walk-down reconstruction. All WRDS scripts use the standard `builtins.input`/`getpass` monkey-patch (see CLAUDE.md) and run with `$env:WRDS_USERNAME="hoovyalert"; $env:PGPASSWORD=...`. `data/*.parquet` is gitignored and regenerated locally; `charts/*.json` is committed so the report is regenerable from JSONs alone. **Deliver one script at a time and wait for Brian to confirm each ran before writing the next.**

### Script DAG (`research/sandbagging/`)

| # | File | Source | Output | Key changes |
|---|---|---|---|---|
| 01 | `01_universe.py` | copy + modify `earnings-vol-cycle/01_universe.py` | `data/sp500_constituents.parquet` | `START="2014-10-01"` (T-90 buffer before first 2015 event), `END="2025-12-31"` |
| 02 | `02_earnings_dates.py` | copy + modify | `data/earnings_dates.parquet` | `START="2014-07-01"`, `END="2025-12-31"`; keep `statsum` consensus cols for cross-check |
| 02b | `02b_ibes_ticker_fallback.py` | copy as-is, adjust dates | appends to `earnings_dates.parquet` | recover unmatched permnos by IBES ticker |
| 02d | `02d_ibes_ibesid_fallback.py` | copy as-is, adjust dates | appends to `earnings_dates.parquet` | keep hardcoded IBES canonical pairs (TELW, HPLD, SMIC, etc.) |
| 03 | `03_detail_pull.py` | **NEW** | `data/det_epsus_raw.parquet` | Pull `ibes.det_epsus` `fpi='6'`, `measure='EPS'`, `fpedats` in event quarters, tickers = union of *post-fallback* earnings tickers. **Chunk by year / ticker batches (~150-200)** — table is millions of rows. Cols: `ticker, estimator, analys, fpi, fpedats, value, anndats, estdats, actdats, revdats, pdf`. Cache early-exit. |
| 04 | `04_reconstruct_walkdown.py` | **NEW (engine)** | `data/walkdown_curve.parquet`, `data/walkdown_events.parquet` | PIT reconstruction, curve build, orig/final snapping, classification + `included` flag. Pure pandas, vectorized. |
| 05 | `05_mktcap_pull.py` | copy + slim `earnings-vol-cycle/05_price_pull.py` | `data/mktcap.parquet` | One `abs(prc)*shrout` snapshot per event near `anndats` (NOT a daily panel) |
| 06 | `06_analysis.py` | copy structure (reuse `safe_list`, `qcut`, groupby->JSON), new logic | `data/sandbagging_analysed.parquet` + `charts/data_*.json` | aggregate curve + classifications into chart JSONs + KPIs |
| 07 | `07_build_report.py` | copy + heavily modify | `index.html` | reuse all CSS/`:root`/nav/hero/kpi-strip/section scaffold/Chart.js defaults/heatmap lerp helpers/scroll+sidenav JS; replace copy, KPIs, sections, canvas inits |

Note: the OptionMetrics `03_secid_mapper.py` / `04_iv_pull.py` slots from the earnings-vol-cycle pipeline are intentionally dropped (no IV in this report); numbers 03/04 are repurposed for det-pull / reconstruct.

### The novel piece — PIT consensus reconstruction (script 04)

`ibes.det_epsus` key columns: `ticker`, `estimator` (broker), `analys` (analyst), `fpi`, `fpedats` (join key to `pends`), `value` (the EPS estimate), `anndats`/`estdats` (issue date = as-of key), `actdats`/`revdats`, `pdf`, `measure`.

**Activeness rule** — on calendar day `D`, an analyst's estimate is active iff: (1) issued on/before `D` (`anndats <= D`, fall back to `estdats`); (2) it is that `(estimator, analys)`'s most recent estimate for `(ticker, fpedats, fpi)` as of `D`; (3) not stale: `(D - anndats) <= STALE_DAYS` (default **120**; det has no per-row withdraw date, so a staleness window stands in). Then `consensus(D) = mean of latest active estimate per analyst`, `n_analysts(D) = distinct active analysts`.

Align det to existing events on `ticker` AND `fpedats == pends`; `anndats` of the event = T=0. Build consensus on a daily grid T-90..T-2. **Validation check:** reconstructed consensus at `statpers` dates should match `statsum_epsus` — assert closeness as a sanity test.

**Vectorize:** sort det by analyst + `anndats`, forward-fill each analyst's latest estimate onto the offset grid (avoid per-day triple loops).

### Output schemas

- `walkdown_curve.parquet` (long): `permno, ticker, anndats, pends, offset (-90..-2), consensus_eps, n_analysts`.
- `walkdown_events.parquet` (one row/event): `permno, ticker, anndats, pends, year, quarter, sector, mktcap_m, actual_eps, orig_consensus, orig_n_analysts, final_consensus, final_n_analysts, walkdown_abs, walkdown_pct, beat_vs_orig, beat_vs_final, classification, included`.
  - **Snapping:** `orig` = curve point nearest -90 within `[-95,-85]`; `final` = largest offset <= -2 within `[-7,-2]` (avoids T-1/T-0 leakage). Report drops for missing orig/final.

### Manufactured-beat classification + exclusions (set once in script 04)

- **genuine beat:** `actual > orig_consensus`
- **manufactured beat:** `actual > final_consensus` AND `actual <= orig_consensus`
- **miss:** `actual <= final_consensus`

**Exclusions** (`included=False`): `orig_consensus<=0` or `final_consensus<=0` or `actual_eps<=0`; sign flip orig->final; small-base `abs(orig_consensus) < $0.05`. **Analyst floor:** `orig_n_analysts >= 5` AND `final_n_analysts >= 5`.

**Headline rate** = `manufactured / (genuine + manufactured)` ("of all reported beats, what fraction are manufactured"); secondary = `manufactured / all included`.

### Curve normalization (centrepiece chart)

On the included set only. Index each event's consensus to **100 at T-90** (`consensus(D)/orig*100`); aggregate as **median across events per offset** + mean line + p25-p75 IQR ribbon (clone the IV-profile chart block). Provide `pct_change` arrays as an alt framing. Robustness: also show raw `consensus(D)-orig` in cents among mega-caps to prove the walk-down is real in absolute terms, not a normalization artifact.

### Chart JSONs (committed to `charts/`)

1. `data_walkdown_curve.json` — **centrepiece**: `offsets`, `median/mean/p25/p75` (indexed-100), `pct_change`, `n_events`.
2. `data_manufactured_breakdown.json` — `categories [Genuine, Manufactured, Miss]`, `counts`, `pct_of_all`, `pct_of_beats`, scalar `manufactured_beat_rate`.
3. `data_sector_walkdown.json` — `sectors`, `walkdown_median_pct`, `manufactured_rate`, `n_events` (heatmap centred at 0, reuse Python lerp renderer).
4. `data_mktcap_breakdown.json` — `quintiles`, `walkdown_median_pct`, `manufactured_rate`, `median_mktcap_m`, `n_events`.
5. `data_time_trend.json` — by year: `labels`, `manufactured_rate`, `walkdown_median_pct`, `beat_rate_vs_final`, `beat_rate_vs_orig`, `n_events` (COVID quarter flagged).
6. `data_kpis.json` — 4 hero KPIs: `n_events`, `manufactured_beat_rate`, `median_walkdown_pct`, `pct_events_walked_down`.

### Report sections (`index.html`)

Hero tag "Earnings Guidance Study". KPI strip from `data_kpis.json`. Side-nav `NAV_LABELS` + section ids synced to 7 entries.

1. **Anatomy of the Walk-Down** — mechanism + centrepiece curve; headline median walk-down.
2. **The Manufactured Beat** — define classes, chart 2, headline stat in amber callout.
3. **Who walks down hardest — Sector** (chart 3).
4. **Coverage and size — Market cap** (chart 4).
5. **Has it gotten worse? — Time trend** (chart 5).
6. **Methodology** — CRSP PIT membership, `actu_epsus`/`det_epsus`, PIT reconstruction in prose, orig=T-90/final=T-2 snapping, exclusions, normalization, `statsum` cross-check, `STALE_DAYS` sensitivity note.
7. **Conclusions** — walk-down systematic; large minority of beats manufactured; concentration by sector/size; caveats (analyst-id stability, staleness-window sensitivity, GICS not PIT, descriptive not causal).

Apply all design rules from CLAUDE.md: GA4 tag after `<head>`, `var(--bg2)` chart boxes (no white cards), HTML-table heatmaps (no PNG), justified text `hyphens:none`, no em dashes/semicolons in visible text, HTML entities for Unicode, GitHub Code button in `hero-meta` pointing at `.../tree/main/research/sandbagging`, "Published Month YYYY". Data-integrity rule: prose cites the JS constants exactly.

## Verification

- After **04**, assert reconstructed consensus at `statpers` dates ~= `statsum_epsus.meanest` (PIT sanity check); print event counts, drop reasons, included/excluded tallies.
- After **06**, spot-check headline manufactured-beat rate and median walk-down against `walkdown_events.parquet` directly.
- After **07**, run `.\serve.ps1` and open `http://localhost:8000/research/sandbagging/` locally; verify every charted number matches the prose and KPI strip before any push.
- Run `STALE_DAYS` at 90/120/150 once to confirm the headline rate is not knife-edge; record the range in methodology.
- Do **not** add to the homepage / research listing until visual QA passes (status stays WIP, like congressional-herd did).

## Open parameters (sensible defaults, adjustable)

`STALE_DAYS=120`, analyst floor `=5`, small-base floor `=$0.05`, orig window `[-95,-85]`, final window `[-7,-2]`. mktcap = single snapshot per event (WRDS-light); coverage-tertile fallback available if the mktcap pull is undesirable.
