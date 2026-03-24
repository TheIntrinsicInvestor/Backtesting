# The Intrinsic Investor

Personal research site publishing systematic market research and options strategy backtests. Built with plain HTML/CSS/JS — no framework, no build step.

**Live site:** [theintrinsicinvestor.com](https://theintrinsicinvestor.com)

---

## Structure

```
/
├── index.html                        # Homepage
├── about.html                        # About page
├── research/
│   ├── index.html                    # Research index
│   ├── iran-iv-study/                # IV behaviour around Iran geopolitical events
│   ├── leveraged-etf-strategy/       # Leveraged ETF decay carry trade
│   ├── short-straddle/               # Short straddle across Magnificent Seven
│   └── wheel-strategy/               # Wheel strategy on SPY
└── options-payoff/                   # Options payoff visualiser tool
```

Each report folder contains an `index.html` (the published report) and, where applicable, the Python scripts used to pull and process the data.

---

## Deployment

Hosted on Netlify, connected to this repo. Push to `main` and the site deploys automatically.

---

## What is not in this repo

- `_backups/` — local dated snapshots, excluded via `.gitignore`
- `*.parquet` — raw data files pulled from WRDS/OptionMetrics, excluded via `.gitignore`
- `__pycache__/` — Python cache files, excluded via `.gitignore`

---

## Data sources

All research data accessed via WRDS (Wharton Research Data Services) through LSE Library access.

- OptionMetrics / IvyDB — options pricing and implied volatility
- IBES Actuals — earnings announcement dates
- Compustat — equity and ETF price data
- yfinance — underlying price data
