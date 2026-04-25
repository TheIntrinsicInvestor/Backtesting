# Handoff — 0DTE Gamma Trap Report Update

**Date:** April 2026
**Branch:** main
**Report:** The Gamma Trap — `/research/0dte-gamma-trap/`

---

## What changed

### 1. Regime classification reworked (04_analysis.py)

The old split used the 33rd percentile of positive days as the Low/High GEX boundary, which produced an asymmetric High GEX bucket (top two-thirds of positive days). This was methodologically weak: "High GEX" included too many moderate-GEX days, diluting the signal.

New classification uses a **median split of positive days**:

| Regime | Definition |
|---|---|
| Negative GEX | gex < 0 |
| Low GEX | 0 <= gex < median of positive days |
| High GEX | gex >= median of positive days |

Low and High GEX now have equal sample sizes (~186 days each), making the comparison symmetric.

### 2. Updated key numbers

| Metric | Old (33rd pct) | New (median) |
|---|---|---|
| High GEX mean RVol | 9.4% | 8.2% |
| Vol premium (Neg vs High) | +42% | +62% |
| t-statistic | 7.66 | 10.96 |
| p-value | <0.0001 | <0.0001 |
| R² | 0.054 | 0.054 |

### 3. Em dashes removed (06_build_report.py)

All `&#8212;`, `&mdash;`, and literal `—` removed from report prose and chart titles. Replacements:
- Chart titles: `Chart N — ...` became `Chart N: ...`
- Parenthetical asides: `— that ... —` became `(that ...)`
- Sentence continuations: replaced with commas or semicolons

### 4. Files changed

- `research/0dte-gamma-trap/04_analysis.py` — regime logic, threshold variable renamed p33 -> p50
- `research/0dte-gamma-trap/06_build_report.py` — prose updates, em dash removal
- `research/0dte-gamma-trap/charts/*.json` — regenerated with new regime data
- `research/0dte-gamma-trap/index.html` — rebuilt (~160KB)

---

## Next steps

No immediate follow-up needed. The report is live and methodologically consistent.

Possible future improvements:
- Intraday GEX updates (would require tick-level options data)
- Four-regime version (Negative / Low / Mid / High) if more granular analysis is wanted
- Reverse causality test using open-of-day GEX snapshot vs same-day vol
