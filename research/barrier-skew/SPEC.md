# Barrier-Skew Study: Methodology Spec

*Draft 1, 2026-09-22. For Brian's review before any pipeline script is written.*

## 1. Question

A 1-year down-and-in put (DIP) is the risk an investor sells inside a reverse convertible or autocallable. Its price depends on how likely the underlying is to touch the barrier. We ask three things:

1. **How far apart are the models?** Knock-in probability and price under flat volatility vs under a model that fits the full implied volatility surface (local volatility).
2. **Which model was closer to reality?** Compare each model's knock-in probability with what actually happened over 1996 to 2025.
3. **Who got paid?** Sell-and-hold P&L of the DIP seller when it is priced at each model's value.

No barrier option has a public market price, so "mispricing" throughout means the gap between models. Only question 2 has an external benchmark (realised outcomes), and that benchmark measures real-world probability, which is expected to differ from risk-neutral probability by a risk premium. The report must say this in plain words.

## 2. Product

| Parameter | Value |
|---|---|
| Type | Down-and-in put, strike 100% of initial spot |
| Tenor | 1 year (252 trading days) |
| Barriers | 60%, 70%, 80% of initial spot |
| Monitoring | Daily closes (the common retail convention) |
| Payoff | If any close ≤ barrier: max(K − S_T, 0). Else 0 |
| Start dates | Weekly (Wednesday, next trading day if a holiday) |

## 3. Universe

| Underlying | Start dates | Approx. starts |
|---|---|---|
| SPX | 1996-01 to 2024-12 | 1,500 |
| SX5E (IvyDB Europe) | 2002-01 to 2022-02 | 1,050 |
| Single names | 1996-01 to 2024-12 | 10 per date |

**Single-name rule (point in time, no hindsight):** at each start date, take the 10 common stocks with the highest total option volume over the trailing 63 trading days (`opvold`), restricted to **S&P 500 members on that date** (`crsp.dsp500list_v2` via the `opcrsphist` link) and to names with a 365-day surface that day. The index filter removes meme names (GME, AMC and MARA were top 12 by volume in June 2024) and delisted placeholder tickers, and it mirrors the large caps banks actually write notes on.

## 4. Data

| Input | US source | Europe source |
|---|---|---|
| Implied vol surface (11 tenors, ±10 to 90 delta) | `optionm_all.vsurfd{yr}` | `optionm_europe.volatility_surface_{yr}` |
| Zero curve | `optionm_all.zerocd` | `optionm_europe.zero_curve` (EUR) |
| Carry (dividends) | `idxdvd` (SPX), `fwdprd{yr}` (stocks) | `index_dividend`, `forward_price` |
| Wing check (raw quotes) | `opprcd{yr}` (SPX only, sample dates) | none |
| Realised path | `crsp.dsp500_v2.spindx` (SPX), `crsp.dsf_v2` split-adjusted (stocks) | `security_price` |
| Universe | `opvold`, `dsp500list_v2`, `opcrsphist` | none |

Every pull is cached to `.parquet` on first run and never re-pulled. Coverage was verified on 2026-09-22 (`02_data_availability.py`, `availability_log.txt`).

**Delistings:** a stock delisted for cause during the product life counts as knocked in, with the payoff at the CRSP delisting price. A cash merger ends the path at the deal price and is treated as held to maturity at that price.

## 5. Models

**Flat volatility (two versions, because a desk has to pick one number):**
- *ATM flat:* the 1y at-the-money forward vol.
- *Barrier-strike flat:* the 1y vol at the barrier strike.

Priced in closed form (Reiner-Rubinstein), with the Broadie-Glasserman-Kou shift to correct for daily rather than continuous monitoring.

**Local volatility (Dupire):**
1. Convert the delta grid to strikes, then fit **SSVI** (Gatheral-Jacquier 2014) across all tenors. SSVI is chosen over per-tenor fits because it rules out calendar and butterfly arbitrage by construction. Arbitrage checks are logged per date, and dates that fail are dropped and counted.
2. Get the local vol surface from the fitted total variance with Gatheral's formula.
3. Solve the pricing PDE (Crank-Nicolson, about 400 space points × 252 daily steps) for three quantities: the vanilla put, the down-and-out put (DIP = vanilla − DOP), and the **one-touch probability** (the risk-neutral knock-in probability). Each solve takes milliseconds on your CPU.

**Validation gates (built as tests, all must pass before the main run):**
- The flat-vol PDE matches the closed form to within 0.5% of price.
- The local vol PDE reprices the input vanillas to within 0.25 vol points across the grid.
- On 20 sample SPX dates, the SSVI wing at 60% moneyness is within 1.5 vol points of raw `opprcd` quotes. If it fails, 60% SPX results are reported with an extrapolation warning, or dropped.

## 6. Measurements per start date

- Knock-in probability under ATM flat, barrier flat and local vol.
- DIP price (% of notional) under each model.
- *Barrier-equivalent vol:* the single flat vol that reproduces the local vol price (the "which flat vol?" sidebar).
- Realised: knocked in (1/0), payoff, date of first touch.
- Seller P&L = premium × (1 + r) − payoff, per model. Unhedged, sell-and-hold.

## 7. Statistics

1-year windows started weekly overlap by 51 of every 52 weeks, so SPX has roughly 29 independent observations, not 1,500. The analysis must respect this:

- Mean gap (model probability − realised frequency), with **Newey-West** standard errors at a 52-week lag.
- A **moving-block bootstrap** (1-year blocks) as a cross-check.
- A calibration plot: bin start dates by model probability and show the realised frequency per bin, with bootstrap bands.
- The effective sample size is stated next to every headline number.
- Results by regime (pre-2008, 2008 to 2009, 2010 to 2019, 2020 onward) are descriptive only, with no significance claims.
- Single names are pooled over names and dates, with standard errors clustered by start date.

## 8. Pipeline (delivered in DAG batches)

| Batch | Script | Runs where | Output |
|---|---|---|---|
| A: pulls | `03_pull_index.py` (SPX + SX5E surfaces, rates, carry, paths) | WRDS | parquet |
| | `04_universe.py` (point-in-time top 10) | WRDS | parquet |
| | `05_pull_single_names.py` (surfaces, forwards, CRSP paths, delistings) | WRDS | parquet |
| | `06_pull_wing_check.py` (raw SPX quotes, 20 dates) | WRDS | parquet |
| B: models | `pricer.py` + `test_pricer.py` (closed form, SSVI, Dupire, PDE) | local | tests pass |
| | `10_price_all.py` | local | per-date results parquet |
| C: analysis | `20_realised_and_stats.py` | local | stats JSON |
| D: report | `30_build_report.py` | local | `index.html` |

Estimated compute: about 32,000 PDE solve sets for the main run, roughly 15 to 45 minutes single-threaded. The WRDS pulls are the slow part (single-name surfaces over 30 years).

## 9. Report outline (draft)

1. Hero + KPI strip (the headline gap between the models and reality).
2. Primer: what a barrier is, why skew matters, flat vs local vol in one diagram.
3. The model gap over time (SPX, SX5E).
4. Which flat vol? The barrier-equivalent vol vs ATM and barrier-strike vol.
5. Implied vs realised knock-in probabilities (the core finding), with a calibration plot.
6. Index vs single names.
7. Seller P&L by model.
8. Limits and methodology table.

## 10. Known limits (disclose in the report)

- No traded barrier prices exist, so model gaps are not errors against a market price.
- Risk-neutral and real-world probabilities differ by design. A gap is a risk premium plus model error, and this study cannot fully separate the two.
- 29 years is few independent crash episodes. The 60% barrier may have very few knock-ins on SPX.
- Local vol is one skew-consistent model among several. Stochastic and local-stochastic vol give different barrier prices (sequel candidate).
- The OptionMetrics 1y surface is interpolated, and single-name 1y wings in the late 1990s rest on thin long-dated listings.
- Unhedged P&L ignores funding, issuer margin and hedging costs, which dominate real structured-product economics.

## 11. Decisions (Brian, 2026-09-22)

1. Single-name universe filtered to S&P 500 members on the start date.
2. No delta-hedged P&L in v1. Unhedged sell-and-hold only.
3. Daily-close monitoring only. No at-maturity barrier variant.
