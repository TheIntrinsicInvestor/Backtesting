# Barrier-Skew: sourced numbers and findings

## Issuer fees on the real products (for the P&L section)

The study measures what the embedded down-and-in put paid its seller. Retail investors do not
receive that premium gross: the note is sold above its fair value. Published estimates:

| Source | Market and sample | Estimate |
|---|---|---|
| Vokata, "Engineering Lemons", *Journal of Financial Economics* 142(2), 2021 (WP: ssrn.com/abstract=3223427) | US, 28,000+ yield enhancement products (high-coupon note plus a short put: reverse convertibles and autocallables), 2006-2015 | "on average, YEPs charge 6-7% in annual fees and subsequently lose 6-7% relative to risk-adjusted benchmarks" (abstract, verbatim). Average offered yield 12% p.a. |
| Henderson and Pearson, "The dark side of financial innovation", *JFE* 100(2), 2011 | US, 64 SPARQS issues | Offering prices on average almost 8% above fair value estimated with option pricing |
| Wallmeier and Diethelm (2009), multi-asset barrier reverse convertibles, Switzerland | April 2007 issues | Overpriced by 3.4% on average, rising with complexity |
| Stoimenov and Wilkens (2005), German market, secondary prices | Reverse convertibles / discount certificates | Premium 3.04% (reverse convertibles), 4.20% (discount certificates) |

Reading for our report: our SPX 70% result (seller earns about +3.4% of notional per year at local
vol prices, before fees) is *smaller than the fee Vokata documents on the products retail actually
buys*. Note the comparison is indicative, not like-for-like: our product is a standalone 1y DIP on an
index, theirs are single-stock notes with coupons and call features. State that caveat explicitly.

## Related literature on why index and single-name premia differ

- Driessen, Maenhout and Vilkov, "The price of correlation risk: evidence from equity options",
  *Journal of Finance* 64(3), 2009 (onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2009.01467.x):
  average implied correlation 46.7% vs realised 28.7% over 1996-2003, which they read as a large
  negative correlation risk premium precisely because individual variance risk is *not* priced in
  their sample. The index variance risk premium is attributed to the price of correlation risk.
  Prediction for us: the premium we measure on SPX and SX5E barriers should largely disappear on
  single-name barriers. Our study tests that directly on the knock-in event, not on variance.
  (Checked 2026-09-23 against the published abstract and the authors' working paper.)
- Standard result that risk-neutral densities are more negatively skewed than physical ones
  (crash risk premium). Our gap is the barrier-specific version of this.

## Findings (2026-09-23, all three sets scored)

1y down-and-in put struck at spot, daily close monitoring, weekly starts. Unusable surface fits
excluded (rmse > 3 vol points or > 10% of ATM vol): 1 index date, 620 single-name dates (4.1%).

| Set | Barrier | Realised KI | Local vol P(KI) | Ratio | LV price | Seller P&L | Premium kept | Win rate |
|---|---|---|---|---|---|---|---|---|
| SPX (1,507 starts, 30 yrs) | 60% | 3.5% | 8.8% | 2.54 | 3.54% | +2.47% | 70% | 97% |
| | 70% | 6.4% | 16.0% | 2.51 | 4.93% | +3.38% | 69% | 94% |
| | 80% | 16.7% | 28.6% | 1.72 | 6.24% | +3.61% | 58% | 88% |
| SX5E (1,044 starts, 21 yrs) | 60% | 6.9% | 11.2% | 1.62 | 4.62% | +2.26% | 49% | 93% |
| | 70% | 14.3% | 19.9% | 1.40 | 6.39% | +3.11% | 49% | 87% |
| | 80% | 28.9% | 34.7% | 1.20 | 8.05% | +3.00% | 37% | 79% |
| Single names (1,496 starts, 10 names each) | 60% | 18.0% | 23.4% | 1.30 | 9.67% | +2.71% | 28% | 77% |
| | 70% | 26.7% | 35.7% | 1.33 | 11.70% | +3.45% | 29% | 77% |
| | 80% | 39.6% | 52.1% | 1.32 | 13.09% | +3.99% | 30% | 77% |

"Premium kept" = seller P&L / local vol price: the share of the premium the seller keeps after
paying realised knock-in losses.

Headline readings:
1. Every set overstates knock-ins, but the **relative** overstatement is far larger on the index
   (2.5x on SPX at 60-70%) than on single names (1.3x flat across barriers). This is the barrier
   version of Driessen-Maenhout-Vilkov: the premium lives in the index, not in single stocks.
2. **Premium retention is the sharper number.** An index barrier seller keeps about 70% of the
   premium; a single-name seller keeps under 30%. Absolute P&L looks similar (+3 to +4%) only
   because single-name premiums are 2-3x larger.
3. **Fees swamp the single-name premium.** Vokata's 6-7% annual fee on US yield enhancement notes
   (which are single-stock products) exceeds the +3.45% the embedded put earned before fees.
   Independent route to Vokata's "negative returns" conclusion via barrier probabilities.
4. ATM flat vol being closest to realised is an **SPX-specific** coincidence (gap +1.6pp at 70%).
   On single names ATM flat is +7.1pp, barely better than local vol's +8.9pp.
5. The skew is an insurance price, not a forecast. SPX 70% by regime (realised / local vol):
   1996-2007 6/14, GFC 40/25, 2010-2019 0/16, 2020- 3/17. The model **understates** in the crash
   and overstates everywhere else.

Statistical strength (block bootstrap 95% on the gap):
- SPX 70% +9.6pp [+2.6, +15.1]; 60% and 80% touch zero.
- Single names 70% +8.9pp [+0.5, +15.9]; 80% +12.6pp [+4.0, +20.3]; 60% touches zero.
- SX5E: correct sign everywhere, no barrier significant.

Caveats to carry into the report: overlapping 1y windows (about 30 independent years, few crash
episodes; every SPX 60% knock-in is 2008), the fitted wing sits about 0.4 vp above market, single
names are large caps chosen by option volume, and P&L ignores hedging, funding and issuer margin.

## Bugs found and fixed during the build (worth a methodology footnote)

- Barrier on a PDE grid node shifts the effective barrier half a cell: knock-in probabilities came
  out about 0.5pp too high until the barrier was placed midway between nodes.
- Closed-form barrier terms overflow at very low vol with large negative carry (Microsoft's 2004
  special dividend). Both the price and the probability now evaluate in log space.
- **Split adjustment**: CRSP paths are split-adjusted, OptionMetrics spot is not. Mixing them made
  every post-start split (6,613 of 14,340 single-name products) look like an instant knock-in and
  produced an absurd 40.8% realised knock-in rate at the 60% barrier. Start level is now read from
  the same series as the path.
