# BUILD PLAN — "Rate Cycle Turns" Report (execution-ready for Sonnet)

> Status: **NOT STARTED.** This file is a self-contained handoff. A fresh session can execute it
> without re-exploring the codebase. Read `CLAUDE.md` (root) first for site rules; everything else
> needed is inlined below. Deliver scripts per Brian's batch-delivery preference (DAG-batches OK).

---

## 1. Context & goal

Build the next report for theintrinsicinvestor.com: **"Rate Cycle Turns."** It extends the existing
**FOMC IV Study** from single-meeting vol dynamics to **multi-year Fed rate cycles** — how equities,
implied vol, sectors, style factors, and the yield curve behave across hiking / cutting / pause
regimes, with the spotlight on the **transition window around cycle turns** (first cut after a hiking
cycle; first hike after a cutting/ZLB cycle).

Audience: macro-aware investment-analyst (B) and vol/derivatives (C) recruiters. The site's edge is
**honest decomposition**, not a claim of secret alpha. Output is one self-contained
`research/rate-cycle-turns/index.html` (Chart.js CDN only), wired into the homepage + research listing.

## 2. Decisions locked (from interview — do not re-litigate)

| Decision | Choice |
|---|---|
| Dimensions | ALL FOUR: (1) equity index & vol, (2) sector rotation, (3) style factors, (4) rates & yield curve |
| Sample period | Full modern era **1994-2025** (~8-10 turns; COVID-2020 isolated as outlier) |
| Strategy backtest | **Research first.** Build descriptive study, THEN show Brian results and ask whether a tradeable rule is worth a backtest. If yes, add SPDR sector ETFs as the tradeable layer. Do NOT build `08` unprompted. |
| Data backbone | **Institutional: CRSP v2 + Fama-French.** Sectors use FF **industry portfolios** (same Dartmouth fetch as the style factors — full history to 1994, no ETF truncation). No yfinance in the analytical backbone. |

### Framing defaults (Brian to confirm/adjust — proceed with these unless told otherwise)
- **Core unit:** lead with **transition windows** (−30 to +90 trading days around each turn, normalized),
  with full-period **regime buckets** as the supporting backbone.
- **"Turn" definition:** first cut after a sustained hold/hike; first hike after a sustained hold/cut.
  **Insurance cuts (1995, 2019)** and the **2020 emergency cuts** are isolated/flagged, not blended into main aggregates.
- **Headline thesis:** *"Preemptive vs reactive matters more than direction"* — cuts are bullish only when
  the Fed is ahead of a slowdown (soft-landing), not chasing a recession. Direction alone is a weak predictor.

### Honest limitations to surface in the report
- ~8-10 turns over 30 years is a **small sample** — wide confidence intervals; state up front.
- No two cycles share starting conditions (inflation, valuation, geopolitics).
- COVID-2020 isolated per `feedback_covid_outliers` memory (null bars + flat cumulative line).
- FF industry labels are NOT 1:1 with 11 GICS sectors (FF "Money" approximately = Financials + Real Estate;
  "BusEq" approximately = Tech + parts of Comms). Disclose mapping in methodology.
- IV/OptionMetrics begins ~1996, so 1994-95 turns lack the vol overlay — flag it.
- MOVE (bond vol) not free on FRED; rates-vol angle uses 2s10s curve + yield levels; MOVE optional/caveated.

---

## 3. Pipeline — clone the FOMC IV 8-script structure

Folder: `research/rate-cycle-turns/` with `data/` (parquet cache) and `charts/` (JSON) subfolders.
Every script: numbered, parquet-cached (`if CACHE.exists(): read else pull+write`), prints row counts +
date coverage. Reference template scripts live in `research/fomc-iv-study/01_..08_*.py`.

### Phase A — regime definition + data pulls (PARALLELIZABLE across agents)

- **`01_rate_regimes.py`** (no WRDS, fast) — FOMC decisions 1994-2025. Easiest: hardcode the meeting
  list in the `fomc-iv-study/01_fomc_events.py` format (date, prior_upper, actual_change_bps, notes),
  OR derive changes from FRED `DFEDTARU`. Classify each meeting Hike/Hold/Cut; classify spans into
  regimes {Hiking, Cutting, Hold-elevated, Hold-ZLB}; identify **turn dates** + tag insurance/emergency.
  Outputs `data/regimes.parquet`, `data/turns.parquet`.
  *Known turns (verify): first hikes 1999-06, 2004-06, 2015-12, 2022-03; first cuts 1995-07(insurance),
  2001-01, 2007-09, 2019-07(insurance), 2020-03(emergency/outlier), 2024-09.*

- **`02_fred_macro.py`** (no WRDS) — FRED via `pandas_datareader` (pattern below): `VIXCLS`, `DGS2`,
  `DGS10`, `T10Y2Y`, `DFEDTARU`, `DFEDTARL`. Output `data/macro.parquet`.

- **`03_equity_index.py`** (WRDS) — CRSP v2 `dsf_v2`: SPY/SPX-proxy daily total return 1994-2025.
  Output `data/equity.parquet`.

- **`04_factors_industries.py`** (no WRDS) — Fama-French Dartmouth CSV fetch (new helper). Pull the
  5-factor daily + Momentum (Mkt-RF, SMB, HML, RMW, CMA, MOM) AND the **12-industry** (or 10-industry)
  daily portfolios. Outputs `data/ff_factors.parquet`, `data/ff_industries.parquet`.
  *Daily 5-factor URL:* `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip`
  *Momentum daily:* `...F-F_Momentum_Factor_daily_CSV.zip`
  *12-industry daily:* `...12_Industry_Portfolios_daily_CSV.zip`
  (Parse: skip header text rows, dates as YYYYMMDD, values are percent — divide by 100.)

- **`05_iv_pull.py`** (WRDS) — OptionMetrics `optionm_all.vsurfd{year}`: SPX (secid 108105) 30-day
  ATM (delta=50) IV, 1996-2025. Output `data/iv.parquet`. Mirror `fomc-iv-study/03_iv_pull.py`.

### Phase B — analysis (depends on ALL of A)

- **`06_regime_stats.py`** — Per-regime stats (annualized return, Sharpe, vol, max drawdown) for index,
  each FF industry, each style factor, curve level/slope. COVID isolated. Outputs `charts/data_regime_*.json`.
- **`07_transition_study.py`** — Event-window aggregation (−30..+90 trading days, normalized to
  baseline=100 like `fomc-iv-study/06_event_study.py`) around each turn, split by first-cut vs first-hike,
  for index / VIX / sectors / factors / curve. Outputs `charts/data_transition_*.json`.
- **`08_signal_test.py` — CONDITIONAL, do NOT build until Brian approves after seeing Phase B.**
  One simple rule, honestly evaluated (`feedback_strategy_analysis`: conclude "not viable" if it fails).

### Phase C — build + wire

- **`09_build_report.py`** — Assemble `index.html`. Load all `charts/*.json`, embed as JS constants
  (single-source-of-truth per CLAUDE.md data-integrity rule), render KPI strip, heatmap-as-HTML-table,
  ~9 sections, Chart.js canvases, labeled side nav. Clone `research/0dte-gamma-trap/index.html` skeleton
  + `.claude/report-template.md`. GA4 tag, justified text, no white cards, no em dashes/semicolons,
  HTML entities for Unicode, GitHub Code button → `.../tree/main/research/rate-cycle-turns`,
  publish date "June 2026".
- **Wiring:** add entry to `REPORTS` array in root `index.html` (≈ lines 160-241) and
  `research/index.html`; `status:"published"` ONLY after QA passes (start as WIP).

### Report sections (HTML)
1. Background — why cycles not just meetings; preemptive-vs-reactive thesis
2. Data & regime definition — sample, taxonomy, turn list, sample-size caveat
3. Returns by regime — index Sharpe/return/vol by regime (backbone)
4. The transition window — −30/+90 around first-cuts vs first-hikes (money section)
5. Sector rotation — FF industries by regime + around turns; does rate-sensitivity narrative hold?
6. Style factors — value/mom/quality/size/low-vol by regime; does rotation advice survive?
7. Rates & curve — 2s10s, yield levels, curve behaviour around turns
8. (Conditional) Signal test — one honest rule, or explicit "no robust edge found"
9. Methodology table + limitations + conclusions

---

## 4. Execution strategy (Sonnet, parallel agents)

Real parallelism is **Phase A** (independent pulls). Analysis (`06`/`07`) and the HTML build (`09`) are
single coherent artifacts — keep sequential/single-agent for consistency.

- **Agent 1 (no-WRDS):** write + run `01_rate_regimes.py`, `02_fred_macro.py`.
- **Agent 2 (no-WRDS):** write + run `04_factors_industries.py` (FF fetch helper).
- **Agent 3 (WRDS):** write + run `03_equity_index.py`, `05_iv_pull.py` (grouped to avoid concurrent
  WRDS connection issues). If WRDS auth fails, hand runnable scripts to Brian.
- **Converge → Agent 4:** write + run `06_regime_stats.py`, `07_transition_study.py`.
- **STOP — show Brian Phase B results, decide on `08`.**
- **Agent 5 (build):** write + run `09_build_report.py`, wire homepage + research listing, run `.\serve.ps1` QA.

First step on resume: create `data/` and `charts/` subfolders (mkdir was deferred this session).

---

## 5. Reusable code patterns (copy these — already verified in repo)

**WRDS non-interactive auth** (every WRDS script; also in root CLAUDE.md):
```python
import builtins, getpass, os, wrds
_u = os.environ.get("WRDS_USERNAME", "hoovyalert")
_p = os.environ.get("PGPASSWORD", "")
def _ai(p=""):
    if "username" in p.lower(): v = _u
    elif "y/n" in p.lower():    v = "n"
    else:                       v = ""
    print(p + v); return v
builtins.input = _ai
getpass.getpass = lambda p="": _p
db = wrds.Connection(wrds_username=_u)
```
Run with: `$env:WRDS_USERNAME="hoovyalert"; $env:PGPASSWORD="<from local pgpass — never commit>"; python -u script.py > log.txt 2>&1`

**FRED pull + cache** (from `fomc-iv-study/04_vix_pull.py`):
```python
import pandas_datareader.data as web, os, pandas as pd
CACHE = "data/macro.parquet"
if os.path.exists(CACHE):
    df = pd.read_parquet(CACHE)
else:
    raw = web.DataReader(["VIXCLS","DGS2","DGS10","T10Y2Y","DFEDTARU","DFEDTARL"], "fred",
                         start="1994-01-01", end="2025-12-31")
    df = raw.reset_index()
    df.to_parquet(CACHE, index=False)
```

**Parquet cache guard** (ubiquitous; e.g. `sandbagging/05_mktcap_pull.py`):
```python
from pathlib import Path
CACHE = Path("data/equity.parquet")
if CACHE.exists():
    df = pd.read_parquet(CACHE); print(f"Cache hit — {len(df):,} rows"); raise SystemExit(0)
# ... pull ...
df.to_parquet(CACHE, index=False)
```

**CRSP v2 daily prices** (from `congressional-herd/02_price_pull.py`, `sandbagging/05_mktcap_pull.py`):
```python
q = """
  SELECT dlycaldt AS date, dlyprc AS prc, dlyret AS ret
  FROM crsp.dsf_v2
  WHERE permno = %(permno)s AND dlycaldt BETWEEN '1994-01-01' AND '2025-12-31'
        AND dlyret IS NOT NULL
"""
df = db.raw_sql(q, params={"permno": permno}, date_cols=["date"])
```
*CRSP v2 column map (legacy→v2): `date`→`dlycaldt`, `prc`→`dlyprc`, `ret`→`dlyret`, `vol`→`dlyvol`;
`crsp.stocknames_v2` has `cusip`(8) / `issuernm`; `crsp.msp500list_v2` has `mbrstartdt`/`mbrenddt`.*

**OptionMetrics IV** (mirror `fomc-iv-study/03_iv_pull.py`): SPX secid `108105`, table
`optionm_all.vsurfd{year}`, filter `days=30 AND delta=50 AND cp_flag='C'` (ATM), loop years 1996-2025.

**JS single-source-of-truth build** (from `fomc-iv-study/08_build_report.py`): pre-compute everything in
Python, `json.dumps()` each series into a JS constant, interpolate into the HTML f-string. Charts read
the constants only — prose must cite the same constants exactly (CLAUDE.md data-integrity rule).

**Design / wiring references:**
- Canonical skeleton: `research/0dte-gamma-trap/index.html`
- Reference docs: `.claude/design-system.md`, `.claude/report-template.md`, `.claude/chart-patterns.md`
- CSS vars: `--bg:#f7f4ec; --bg2:#f0ece2; --ink:#0f2220; --accent:#1a5c52; --green2:#059669; --red2:#dc2626; --blue2:#2563eb`; fonts Fraunces/Inter/JetBrains Mono; Chart.js 4.4.1.
- GA4 tag (right after `<head>`): `G-HT9VG5C62E`.
- REPORTS array entry shape: `{date, title, tag, meta, url:"/research/rate-cycle-turns/", status:"published"}`.

---

## 6. Verification (definition of done)
1. Each pull script prints row counts + date coverage; cache files land in `data/`.
2. `06`/`07` print regime/turn sample sizes + key stats; sanity-check signs (Hiking 2015-18 ann.
   return positive; COVID isolated).
3. `09` produces a single self-contained `index.html` (Chart.js CDN only).
4. **Data-integrity audit:** every prose figure matches its JS constant; KPI strip, callouts, conclusion,
   methodology table all agree.
5. Local QA via `.\serve.ps1` (NOT deploy-to-verify): charts render, side nav scrolls, justified text,
   no white card backgrounds, no em dashes/semicolons, HTML entities for Unicode.
6. Keep `status` WIP until QA passes; only then flip to `published`, `git add` specific files, push.

## 7. Housekeeping
- Never commit `*.parquet`, `.claude/`, `__pycache__/`, `_backups/`. (Add `data/` parquet to gitignore scope.)
- COVID-2020 per `feedback_covid_outliers`; brutal-honesty conclusion per `feedback_strategy_analysis` if `08` runs and fails.
- Confirmed WRDS cutoffs: CRSP v2 2025-12-31, OptionMetrics 2025-08-29.
