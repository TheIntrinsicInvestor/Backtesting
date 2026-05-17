# The Intrinsic Investor

Personal research site publishing systematic market research and options strategy backtests. Built with plain HTML/CSS/JS — no framework, no build step.

**Live site:** [theintrinsicinvestor.com](https://theintrinsicinvestor.com)

---

## Structure

```
/
├── index.html                                      # Homepage
├── about.html                                      # About page
├── research/
│   ├── index.html                                  # Research index
│   ├── 0dte-gamma-trap/                            # 0DTE GEX & intraday SPX vol dynamics
│   ├── earnings-vol-cycle/                         # Earnings vol premium across S&P 500 (2010-2024)
│   ├── etf-factor-sector-rotation-strategy/        # Factor & sector rotation parameter study
│   ├── fomc-iv-study/                              # FOMC IV event study (2018-2024)
│   ├── iran-iv-study/                              # IV behaviour around Iran geopolitical events
│   ├── leveraged-etf-strategy/                     # Leveraged ETF decay carry trade
│   ├── short-straddle/                             # Short straddle across Magnificent Seven
│   └── wheel-strategy/                             # Wheel strategy on SPY
└── options-payoff/                                 # Options payoff visualiser tool
```

Each report folder contains an `index.html` (the published report) and, where applicable, the Python scripts used to pull and process the data.

---

## Published Reports

| Report | Key Finding |
|---|---|
| The Gamma Trap: 0DTE Options & Intraday SPX Dynamics | Negative GEX days show 62% higher intraday RVol vs high GEX days (p<0.0001) |
| The Earnings Vol Premium: IV Dynamics Across the S&P 500 | 68.7% win rate selling straddles at earnings; avg +$30/trade across 35,862 events |
| The FOMC Vol Crush: IV Dynamics Around Fed Decisions | Post-announcement straddle sell wins 67% (driven by hike cycles); pre-meeting sell has negative Sharpe |
| Factor & Sector Rotation: Parameter Optimisation | Rotation strategy underperforms SPY B&H on risk-adjusted basis across all tested configs |
| Iran Geopolitical IV Event Study | IV spikes significantly pre-event; mean-reverts within 5 days |
| Exploiting Leveraged ETF Decay | Structural volatility decay premium exists but drawdowns are severe |
| Selling Earnings Volatility (Mag7 Straddles) | Edge exists pre-earnings; post-earnings IV crush less consistent |
| SPY Wheel Strategy Backtest | Underperforms SPY B&H on CAGR; reduces drawdown modestly |

---

## Deployment

Hosted on GitHub Pages, connected to this repo. Push to `main` and the site deploys automatically within ~60 seconds.

---

## What is not in this repo

- `_backups/` — local dated snapshots, excluded via `.gitignore`
- `*.parquet` — raw data files pulled from WRDS/OptionMetrics, excluded via `.gitignore`
- `__pycache__/` — Python cache files, excluded via `.gitignore`

---

## Data sources

All institutional data accessed via WRDS (Wharton Research Data Services) through LSE Library access.

- OptionMetrics / IvyDB — options pricing and implied volatility surface data
- IBES Actuals — earnings announcement dates and EPS estimates
- CRSP — equity daily returns and S&P 500 constituent history
- Compustat — equity fundamentals
- TAQ (TAQMSEC) — intraday trade and quote data
- yfinance — supplementary ETF price data
