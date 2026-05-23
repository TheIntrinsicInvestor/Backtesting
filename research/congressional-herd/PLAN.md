# Congressional Herding Signal — Backtest & Report Plan

## Context

**Why this report exists.** The thesis: when multiple US politicians (House + Senate) buy the same stock within a short window, that "herd" reflects shared information advantage — committee disclosures, regulatory tip-offs, contract awards, legislative timing — and predicts forward returns. The IDA on full Capitol Trades data (35,150 clean buy/sell trades, 2023-05-22 → 2026-05-11, 199 politicians, 1,960 tickers) confirmed **540 herding events** at the primary threshold (3+ politicians, 30-day rolling window, buy direction). The signal is dense enough to backtest.

**What this plan delivers.** A full backtest pipeline + published HTML report at `research/congressional-herd/` mirroring the `earnings-vol-cycle` structure: event-level forward returns, portfolio simulation, sensitivity sweeps, cross-sectional breakdowns (party / chamber / politician / sector), and an explicit viability verdict.

**Key methodological choices locked in via interview:**
- **Direction:** Buy-side herds only (long entries)
- **Entry:** Day the N-th politician's trade is *disclosed* (Capitol Trades "Filed" date) — not the trade date itself, to avoid look-ahead bias. Requires re-scraping Capitol Trades to capture disclosure dates.
- **Holding periods:** 10d, 20d, 10d, 90d, 180d, 252d
- **Benchmark:** Absolute return + excess-over-SPY (both reported)
- **Universe filter:** Drop ETFs and mutual funds; keep N/A-excluded; keep all market caps
- **Price source:** WRDS CRSP `dsf` (gold-standard, handles delistings)
- **Portfolio sim:** Equal-weight + herd-size-weighted (both)
- **Verdict bar:** Decide after seeing results — build script reports all metrics; editorial pass writes the verdict manually

---

## Inputs already in place

| File | Status | Notes |
|---|---|---|
| `research/congressional-herd/data/all_trades.parquet` | Exists | 35,274 rows, columns: `name, party, chamber, state, issuer, ticker, trade_date, owner, tx_type, size`. Missing: `disclosure_date`. |
| `research/congressional-herd/scrape_capitol_trades.py` | Exists | Working scraper. **Needs an edit** to also capture the "Filed" / disclosure date column from Capitol Trades. |
| `research/congressional-herd/ida_herding.py` | Exists | Updated to read parquet. Confirms 540 events at (3+, 30d, buy). |

## New scripts to write (in order)

Mirrors the `research/earnings-vol-cycle/01_universe.py … 07_build_report.py` numbered-stage convention.

### `00_rescrape_disclosure_dates.py`
**Purpose:** Re-scrape Capitol Trades to capture the disclosure ("Filed") date alongside trade date. The current scraper drops this column.
**Action:** Open `scrape_capitol_trades.py` → inspect `parse_row()` (around line 92) and the per-page HTML structure → add a `disclosure_date` field to the returned dict. The "Filed" date appears in the same `<td>` row as trade_date on Capitol Trades.
**Output:** Overwrites `data/all_trades.parquet` with the new `disclosure_date` column added.
**Runtime:** ~9 minutes (same as original scrape; 368 pages × 1.5s rate limit).
**Validation:** print `df[['trade_date', 'disclosure_date']].head()` and confirm disclosure_date ≥ trade_date for ≥99% of rows.

### `01_events.py`
**Purpose:** Build the herding events table from the trades parquet. This is the core event constructor that downstream scripts read.
**Inputs:** `data/all_trades.parquet`
**Logic:**
1. Filter: `tx_type == "buy"`, `ticker != "N/A"`, ticker not in ETF/mutual-fund blacklist (build blacklist by checking issuer field for "FUND", "ETF", "TRUST", "INDEX" — also explicitly: SPY, QQQ, VTI, VOO, IWM, EEM, GLD, TLT, etc. Reuse the parsing already in `ida_herding.py:find_herding_events`).
2. Use the same rolling-window detection logic from `ida_herding.py:find_herding_events`, parameterised on (threshold, window_days).
3. For each event, compute and persist:
   - `ticker`
   - `window_start` — trade date of 1st politician
   - `entry_trade_date` — trade date of the N-th politician (the one who triggers the threshold)
   - `entry_disclosure_date` — disclosure date of that same N-th politician (this is the **realistic entry date** for the backtest; T+1 open on this date is the actual fill)
   - `politician_count`, `politicians` (sorted list), `parties_in_herd` (set), `chambers_in_herd` (set)
   - `is_bipartisan` — True if both Dem and Rep present
   - `total_dollar_size` — sum of midpoint of each `size` range (parse the e.g. "50K-100K" range strings into midpoints)
4. Build full event grid: cartesian of thresholds × windows × directions: `thresholds=[2,3,4,5]`, `windows=[14,30,60]`, `direction="buy"`. Tag each event with its (threshold, window) origin for the sensitivity sweep.
5. Save to `data/events_buy.parquet`.

**Reuse:** `ida_herding.py:find_herding_events()` — copy as a helper. Don't import from `ida_herding.py` to avoid the print-heavy `main()` side effects.

### `02_price_pull.py`
**Purpose:** Pull WRDS CRSP daily prices for every unique ticker in `events_buy.parquet`, plus SPY (benchmark).
**Inputs:** `data/events_buy.parquet`
**Logic:**
1. Get unique ticker list (~500-700 after filtering).
2. Map tickers → CRSP permnos via `crsp.stocknames` (look up TICKER + active date range; resolve conflicts by latest namedt). Cache mapping to `data/ticker_permno_map.parquet`.
3. Pull `crsp.dsf` (daily stock file) for those permnos over [min(entry_disclosure_date) - 30, max(entry_disclosure_date) + 300] window. Columns: `date, permno, prc, ret, cfacpr, vol`. **Use `abs(prc)` since CRSP encodes bid-ask midpoint as negative.**
4. Also pull SPY (permno = 84398, per CLAUDE.md) over the same window for benchmark.
5. **Cache pattern (CLAUDE.md rule):** save to `data/crsp_prices.parquet` immediately, never re-pull if cache exists.

**WRDS auth boilerplate:** copy the `builtins.input` monkey-patch block verbatim from CLAUDE.md "WRDS non-interactive auth" section into the top of this script.

### `03_forward_returns.py`
**Purpose:** Compute forward returns for every event × holding period, both absolute and excess-over-SPY.
**Inputs:** `data/events_buy.parquet`, `data/crsp_prices.parquet`
**Logic:**
1. For each event, define entry as **first CRSP trading day on or after `entry_disclosure_date`** (handle weekends/holidays).
2. Compute prices: `P_entry`, `P_entry+10d`, `P_entry+20d`, `P_entry+10d`, `P_entry+90d`, `P_entry+180d`, `P_entry+252d` (in trading days, not calendar days).
3. Compute returns:
   - `ret_{N}d_abs` = (P_exit / P_entry) - 1
   - `ret_{N}d_spy` = SPY return over same window
   - `ret_{N}d_excess` = ret_abs - ret_spy
4. Flag events where the exit date exceeds the last available price date (right-censoring) — exclude from horizon-specific stats.
5. Add metadata columns useful for cross-sectional analysis: `sector` (from CRSP `crsp.stocknames` SIC code → GICS sector mapping; reuse the mapping pattern from `earnings-vol-cycle/01_universe.py`), `mkt_cap_at_entry` (from `prc * shrout` on entry date).
6. Save to `data/event_returns.parquet`.

### `04_analysis.py`
**Purpose:** Compute every statistic the report displays. Persist as JSON files in `charts/` for the build script to consume (mirrors `earnings-vol-cycle/06_analysis.py` pattern).
**Inputs:** `data/event_returns.parquet`
**Outputs (one JSON per chart/table):**

| File | Content |
|---|---|
| `charts/kpi_strip.json` | 4 headline numbers: # events at (3+, 30d), win rate at 10d, mean excess return at 10d, Sharpe of 10d excess returns. |
| `charts/forward_returns_curve.json` | Mean + 25th/75th percentile excess return at each horizon (10/20/60/90/180/252). For the mean/percentile band line chart. |
| `charts/sensitivity_heatmap.json` | Win rate at 10d horizon by (threshold ∈ {2,3,4,5}) × (window ∈ {14d, 30d, 10d}). 4×3 grid for sensitivity heatmap. |
| `charts/sector_breakdown.json` | Win rate at 10d + mean excess return by GICS sector (11 sectors). For sector bar chart. |
| `charts/mkt_cap_breakdown.json` | Win rate + mean excess by market cap quintile at entry. |
| `charts/party_chamber.json` | 4-way split: {Dem-only, Rep-only, Bipartisan, House-only, Senate-only, Both-chambers} × {win_rate, mean_excess, Sharpe, n_events} at 10d. |
| `charts/top_politicians.json` | Top 20 politicians by participation count; for each: n_events_participated, win_rate_when_participating, mean_excess_when_participating. (Filter min 10 events to avoid noise.) |
| `charts/portfolio_eq_weight.json` | Equity curve assuming $10K equal-weight per event, 10d hold, entered chronologically. Includes daily portfolio value vs SPY. |
| `charts/portfolio_size_weighted.json` | Same but weight = politician_count / sum(politician_counts in concurrent positions). |
| `charts/bipartisan_vs_partisan.json` | Bipartisan herd win rate / mean excess / Sharpe at 10d vs single-party. |
| `charts/largest_herds.json` | Top 10 single events by politician_count: ticker, date, n politicians, 10d excess return. For "largest events" table. |

**Stats reported per cut, always:**
- n events
- Win rate (% with positive excess at horizon)
- Mean excess return
- Median excess return
- Std dev of excess returns
- Sharpe (mean / std, annualised by sqrt(252/horizon_days))
- t-stat vs zero (paired t-test on excess returns)

### `05_build_report.py`
**Purpose:** Assemble `index.html` from JSON inputs + HTML template. Mirrors `earnings-vol-cycle/07_build_report.py`.
**Inputs:** All JSONs in `charts/`
**Pattern:** Python f-string templating with inline `<script>` block embedding Chart.js + JSON data literals. No separate JS file. Copy structure from `research/earnings-vol-cycle/07_build_report.py` (887 lines is the reference scale).
**Output:** `research/congressional-herd/index.html`

---

## Report structure (mirrors Earnings Vol Premium)

| # | Section | Content |
|---|---|---|
| Hero | Title + KPI strip | "The Congressional Herding Signal: Does Politician Co-Trading Predict Forward Returns?" 4 KPIs: events analysed, win rate (10d), mean excess vs SPY, Sharpe. |
| 1 | Study Design | Hypothesis, dataset overview (2023-05 → 2026-05, 199 politicians, 1960 tickers), herding definition, entry rule (disclosure date), holding periods, universe filtering rationale, ETF/MF exclusion list. **Disclosure-lag note callout (amber):** explicitly call out the realistic-entry methodology. |
| 2 | Anatomy of a Herd | Distribution: herd size histogram (politician_count), bipartisan share, party mix bar, chamber mix, time-series of events per quarter. Largest 10 herds table. |
| 3 | Forward Returns Profile | Mean + 25/75 percentile line chart of excess returns across 10/20/60/90/180/252d horizons. Find the "sweet spot" horizon. |
| 4 | Sensitivity & Robustness | 4×3 heatmap: threshold × window, cell = win rate at 10d. Confirms (or denies) monotonic signal strength with herd size. |
| 5 | Cross-Section | Side-by-side bar charts: by sector, by market cap quintile, by party/chamber composition, top-20 politicians table. |
| 6 | Bipartisan vs Partisan | Highlight box: bipartisan herd stats vs single-party stats. Tests the "consensus = conviction" hypothesis. |
| 7 | Portfolio Backtest | Equity curve charts: equal-weight $10K-per-event, 10d hold, vs SPY. Position-weighted variant overlaid. Quarterly P&L bar chart. Drawdown chart. Per-year breakdown. |
| 8 | Methodology | Compact reference table (not paragraphs) — universe, period, source, herd definition, entry rule, exit rule, benchmark, exclusions, costs assumption (zero — disclose). |
| 9 | Conclusions & For The Desk | Verdict callout (colour set by build script per the brutality rule). "For the desk" callout (teal box, monospace label, per CLAUDE.md). Limitations: 3-year sample, no transaction costs, no borrow costs, possible Capitol Trades coverage skew. |

---

## Cross-cutting analyses to compute (drives the JSONs above)

| Dimension | What to compute |
|---|---|
| **Sensitivity** | Win rate at 10d × {threshold ∈ 2/3/4/5} × {window ∈ 14/30/10d} = 12 cells. Confirms herd-strength monotonicity. |
| **Bipartisan vs partisan** | At each threshold, split events into {all-Dem, all-Rep, bipartisan}. Compare win rate, mean excess, Sharpe. |
| **Sector** | Group by GICS sector (CRSP SIC → GICS mapping). Bar chart: win rate by sector. Test the "regulatory exposure" angle (Healthcare, Defense, Financials should over-index if thesis holds). |
| **Market cap** | Quintile cap at entry. Test whether the signal lives in small/mid caps (less efficient) or works in mega-caps too. |
| **Party** | Dem-led, Rep-led, mixed herds — separately. |
| **Chamber** | House-only, Senate-only, both. Senate has fewer members per state and more committee concentration; thesis predicts Senate herds stronger. |
| **Individual politicians** | Top 20 by participation count. For each: when this person joins a herd, what's the forward return? Identifies "star traders". |
| **Holding period** | Six horizons: 10/20/60/90/180/252 days. Identify peak signal horizon. |
| **Portfolio simulation** | Equal-weight $10K, 10d hold. Then position-weighted by herd size. Both compared to SPY buy-and-hold. |

---

## Files to be created / modified

**Created:**
- `research/congressional-herd/01_events.py`
- `research/congressional-herd/02_price_pull.py`
- `research/congressional-herd/03_forward_returns.py`
- `research/congressional-herd/04_analysis.py`
- `research/congressional-herd/05_build_report.py`
- `research/congressional-herd/index.html` (output of `05_build_report.py`)
- `research/congressional-herd/charts/*.json` (multiple files)
- `research/congressional-herd/data/events_buy.parquet`
- `research/congressional-herd/data/crsp_prices.parquet`
- `research/congressional-herd/data/ticker_permno_map.parquet`
- `research/congressional-herd/data/event_returns.parquet`

**Modified:**
- `research/congressional-herd/scrape_capitol_trades.py` — add disclosure_date capture
- `research/congressional-herd/data/all_trades.parquet` — overwritten by re-scrape with new column
- `research/index.html` — add new report card once published
- `index.html` (homepage) — add new report card once published
- `CLAUDE.md` — update "Current Status" and add Congressional Herding to "Published Reports" table once shipped

---

## Critical existing files / patterns to reuse

| Reference | Why |
|---|---|
| `research/earnings-vol-cycle/06_analysis.py` | Closest analog for `04_analysis.py` — same shape (event-level returns → multi-JSON output for charts). |
| `research/earnings-vol-cycle/07_build_report.py` | Direct template for `05_build_report.py` — copy hero/KPI strip/section/heatmap/callout HTML patterns wholesale. |
| `research/earnings-vol-cycle/01_universe.py` | SIC → GICS sector mapping pattern. |
| `research/0dte-gamma-trap/index.html` | Canonical design source per CLAUDE.md — confirm CSS class names match. |
| `research/congressional-herd/ida_herding.py:find_herding_events()` | Already-tested herd-detection logic; copy into `01_events.py`. |
| CLAUDE.md "WRDS non-interactive auth" block | Required boilerplate at top of `02_price_pull.py`. |
| CLAUDE.md "Report Design Rules" + `.claude/design-system.md` + `.claude/report-template.md` + `.claude/chart-patterns.md` | Read these BEFORE building the report HTML. |

---

## Verification (end-to-end test plan)

1. **Re-scrape sanity check:** After `00_rescrape_disclosure_dates.py`, confirm `disclosure_date` column exists and `(disclosure_date - trade_date).dt.days.median()` is in the 20-45 day range (STOCK Act compliance window).
2. **Event reconstruction:** After `01_events.py`, confirm event count at (3+, 30d, buy) is roughly 507 (= 540 IDA events minus ~33 N/A) and drops further after ETF/MF exclusion. Print top 25 most-herded tickers; sanity-check they're real stocks (no SPY, QQQ).
3. **Price coverage:** After `02_price_pull.py`, confirm ≥95% of unique tickers in events have CRSP coverage. Log unmapped tickers explicitly.
4. **Returns integrity:** After `03_forward_returns.py`, spot-check 3 random events manually — compute the forward return by hand against CRSP and confirm match. Confirm SPY excess at 10d makes sense (sub-5% for typical events).
5. **Analysis sanity:** After `04_analysis.py`, open the JSONs. KPI win rate should be in the 50-65% range — anything above 70% suggests a bug (e.g., look-ahead bias).
6. **Report rendering:** Run `.\serve.ps1` → open `http://localhost:8000/research/congressional-herd/` → check:
   - All 8 sections render
   - All charts populate (no blank Chart.js boxes)
   - Sensitivity heatmap colors interpolate correctly
   - "For the desk" callout renders at bottom
   - Side nav highlights correctly on scroll
   - No raw Unicode in HTML (CLAUDE.md rule — use entities)
7. **Editorial pass before publish:** Read every prose paragraph against the chart it sits beside. Charts are ground truth (CLAUDE.md rule). Apply brutality rule on viability verdict — if Sharpe < 0.5 or excess returns aren't significantly positive, the conclusion must say "should not be carried out" explicitly.
8. **Publish:** Add report card to `index.html` homepage and `research/index.html` listing. Commit with `git add` on specific files only (never `-A`). Push to `main`. GitHub Pages live in ~60s.

---

## Order of operations for the executing session

1. Read `.claude/design-system.md`, `.claude/report-template.md`, `.claude/chart-patterns.md` for design rules
2. Read `research/earnings-vol-cycle/06_analysis.py` and `07_build_report.py` for templating reference
3. Edit `scrape_capitol_trades.py` → add disclosure_date capture → re-run scrape (~9 min in background)
4. Write `01_events.py` → run → confirm event count
5. Write `02_price_pull.py` → run (WRDS pull, may take 5-15 min) → confirm coverage
6. Write `03_forward_returns.py` → run → spot-check 3 events
7. Write `04_analysis.py` → run → review JSONs
8. Write `05_build_report.py` → run → open in browser
9. Editorial pass against charts; write the viability verdict
10. Update CLAUDE.md, root `index.html`, `research/index.html`; commit; push
