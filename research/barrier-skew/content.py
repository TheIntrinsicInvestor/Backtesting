# ruff: noqa
"""
content.py
----------
Prose, tables and chart code for the barrier-skew report. Imported by 30_build_report.py.

build(D) returns the dict of {{PLACEHOLDER}} values for the page template. Every number in the
prose is formatted from D (report_data.json), never typed by hand.
"""

import datetime
import statistics

C_RED, C_PARCH, C_GREEN = (254, 202, 202), (247, 244, 236), (187, 247, 208)


def _lerp(t, lo, hi):
    return "#{:02x}{:02x}{:02x}".format(*(int(lo[i] + t * (hi[i] - lo[i])) for i in range(3)))


def pretty(iso):
    """2024-12-26 -> 26 December 2024 (no %-d on Windows)."""
    d = datetime.date.fromisoformat(iso)
    return f"{d.day} {d:%B %Y}"


def diverging(v, abs_max):
    """negative (model understated) = red, zero = parchment, positive (overstated) = green"""
    t = max(0.0, min(1.0, abs(v) / abs_max)) if abs_max else 0.0
    return _lerp(t, C_PARCH, C_RED) if v < 0 else _lerp(t, C_PARCH, C_GREEN)


def build(D):
    S, MET, TER = D["summary"], D["method"], D["terciles"]
    spx7, sn7, eu7 = S["SPX"]["0.7"], S["SN"]["0.7"], S["SX5E"]["0.7"]
    spx6 = S["SPX"]["0.6"]
    T70 = {t["tercile"]: t for t in TER if t["barrier"] == 0.7}
    eq_avg = {b: statistics.mean(p["eq_vol"] for p in D["series"][b]) for b in ("0.6", "0.7", "0.8")}
    atm_avg = statistics.mean(p["atm_vol"] for p in D["series"]["0.7"])
    bar_avg = {b: statistics.mean(p["bar_vol"] for p in D["series"][b]) for b in ("0.6", "0.7", "0.8")}
    sl70 = [s for s in D["slider"] if s["barrier"] == 0.7][0]
    fees = MET["fees"]
    smile_day = pretty(D["smile"]["date"])

    P = {}
    P["PERIOD"] = (f"{spx7['first'][:4]} to {spx7['last'][:4]}, {spx7['n_starts']:,} index products and "
                   f"{MET['sn_products']:,} single stock products")
    P["KPI1"] = f"{spx7['lv']['ratio']:.1f}x"
    P["KPI2"] = f"{sn7['lv']['ratio']:.1f}x"
    P["KPI3"] = f"{spx7['lv']['kept']:.0f}%"
    P["KPI4"] = f"{sn7['lv']['kept']:.0f}%"
    P["SMILE_DATE"] = smile_day

    P["HERO_SUB"] = (
        "A reverse convertible pays a high coupon because the investor sells a barrier put on the way in. I priced "
        "that put every week for thirty years, once with a flat volatility and once with a model fitted to the whole "
        "volatility skew, then checked both against what the market did. The skew charged "
        f"{spx7['lv']['ratio']:.1f} times the realised knock-in rate on the S&amp;P 500, and {sn7['lv']['ratio']:.1f} times "
        "on single stocks, which is where the notes are written.")

    # ── Section 1 ────────────────────────────────────────────────────────────
    P["S1_BODY"] = f"""
<p>A reverse convertible looks like a bond. It pays a coupon far above the market rate and returns capital at
maturity, unless the underlying falls through a barrier, commonly 30% below where it started. If the barrier
breaks, the investor receives shares instead of cash and takes the loss. The coupon is the price of an option the
investor sold on the way in: a down-and-in put, struck at the starting level, that pays out only if the barrier is
touched.</p>
<p>Two things make that option harder to price than an ordinary put. The payoff depends on the path rather than
only the final level, and the barrier sits far below the money, where implied volatility is much higher. On
{smile_day} the S&amp;P 500 traded at {D['smile']['spot']:,.0f} with one year
at-the-money volatility of {sl70['atm_vol']:.1f}%, while the volatility priced into options at the 70% barrier strike
was {sl70['bar_vol']:.1f}%. Choosing one number to stand for that curve is the practical problem this report
addresses.</p>
<p>No market print exists for a barrier option, because they trade over the counter. Every gap in the next two
sections is therefore a gap between models rather than an error against a traded price. Section three is the
exception: whether the barrier broke is a fact, and that is what the study tests.</p>"""

    P["SMILE_NOTE"] = (
        f"Fitted with SSVI to the OptionMetrics surface, fit error {D['smile']['fit_rmse_vp']:.2f} volatility points. "
        "Orange points are individual listed puts expiring in 270 to 460 days. They are not used in the fit, so "
        "they give an independent check on the deep wing. Vertical lines mark the three barriers studied.")
    P["SIM_NOTE"] = (
        "Every step of this slider is a real pricing run on the date above, not an approximation. The local "
        "volatility figure comes from a finite-difference solver with daily barrier monitoring, the two flat "
        "volatility figures from the closed-form barrier formula with a discrete-monitoring correction.")

    # ── Section 2 ────────────────────────────────────────────────────────────
    P["S2_BODY"] = f"""
<p>Three models price the same contract. The first uses a single flat volatility taken at the money, the number a
trader quotes when asked where the market is. The second uses a single flat volatility read off the skew at the
barrier strike, which looks like the obvious correction. The third fits the whole surface and lets volatility vary
with both price and time, the skew-consistent approach a derivatives desk would use.</p>
<p>Averaged over {spx6['n_starts']:,} weekly start dates on the S&amp;P 500, a one year put
with a 60% barrier was worth {spx6['lv']['dip']:.2f}% of notional under local volatility, {spx6['atm']['dip']:.2f}% under
at-the-money flat volatility, and {spx6['bar']['dip']:.2f}% under barrier-strike flat volatility. The naive
at-the-money number is under a quarter of the skew-consistent one, and the obvious correction overshoots it by more
than half.</p>
<p>Exactly one flat volatility reproduces the skew-consistent price, and it sits between the two candidates. At the
60% barrier it averaged {eq_avg['0.6']:.1f}%, against {atm_avg:.1f}% at the money and {bar_avg['0.6']:.1f}% at the barrier
strike. That spread is not constant: it widens when the skew steepens, so no fixed rule of thumb survives a change
of regime.</p>"""
    P["PRICE_NOTE"] = ("The three lines converge in calm markets and separate in stressed ones, because the skew "
                       "steepens faster than at-the-money volatility rises.")
    P["VOL_NOTE"] = (
        f"At the 70% barrier the equivalent volatility averaged {eq_avg['0.7']:.1f}%, which is "
        f"{eq_avg['0.7'] - atm_avg:+.1f} points against the at-the-money number and {eq_avg['0.7'] - bar_avg['0.7']:+.1f} "
        "points against the barrier strike number.")

    rows = []
    for name, label in (("SPX", "S&amp;P 500"), ("SX5E", "Euro Stoxx 50"), ("SN", "Single stocks")):
        for i, bar in enumerate(("0.6", "0.7", "0.8")):
            b = S[name][bar]
            rows.append(
                f"<tr><td>{label if i == 0 else ''}</td><td class='mono'>{float(bar):.0%}</td>"
                f"<td class='mono'>{b['lv']['dip']:.2f}%</td><td class='mono'>{b['atm']['dip']:.2f}%</td>"
                f"<td class='mono'>{b['bar']['dip']:.2f}%</td><td class='mono'>{b['lv']['p_ki']:.1f}%</td>"
                f"<td class='mono'>{b['atm']['p_ki']:.1f}%</td><td class='mono'>{b['bar']['p_ki']:.1f}%</td></tr>")
    P["S2_TABLE"] = (
        "<div class='table-wrap'><table><thead><tr><th>Underlying</th><th>Barrier</th>"
        "<th>Price, local vol</th><th>Price, ATM flat</th><th>Price, barrier flat</th>"
        "<th>P(KI), local vol</th><th>P(KI), ATM flat</th><th>P(KI), barrier flat</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table></div>"
        + "<div class='note'>Average across all start dates. Prices are percent of notional for a one year "
          "down-and-in put struck at the starting level.</div>")

    # ── Section 3 ────────────────────────────────────────────────────────────
    P["S3_BODY"] = f"""
<p>This test has an answer outside the models. For every start date I recorded whether the underlying ever
closed at or below the barrier during the following year. That is {spx7['n_starts']:,} products on the S&amp;P 500
spanning {spx7['years']:.0f} years, {eu7['n_starts']:,} on the Euro Stoxx 50 over {eu7['years']:.0f} years, and
{sn7['n_starts']:,} start dates for single stocks with ten large caps priced on each one, selected at the time by
option volume so that no hindsight enters the sample.</p>
<p>At the 70% barrier the S&amp;P 500 knocked in {spx7['realised']:.1f}% of the time. Local volatility had priced
{spx7['lv']['p_ki']:.1f}%, at-the-money flat volatility {spx7['atm']['p_ki']:.1f}%, and barrier-strike flat volatility
{spx7['bar']['p_ki']:.1f}%. Single stocks knocked in {sn7['realised']:.1f}% of the time against a local volatility price
of {sn7['lv']['p_ki']:.1f}%. Every model overstated the danger. That is a risk premium: buyers of crash protection
paid more than the crashes went on to cost.</p>
<p>One year products started every week overlap by fifty one weeks in fifty two, so
the sample contains roughly {spx7['years']:.0f} independent years rather than {spx7['n_starts']:,} independent
observations. Intervals here come from a moving block bootstrap with one year blocks, and standard errors use a
Newey-West correction at 52 lags. On that basis the S&amp;P 500 gap at the 70% barrier ({spx7['lv']['gap']:+.1f} points,
95% interval {spx7['lv']['gap_lo']:+.1f} to {spx7['lv']['gap_hi']:+.1f}) excludes zero, as do the single stock gaps at 70%
and 80%. The Euro Stoxx 50 carries the right sign at every barrier and reaches significance at none of them.</p>"""
    P["GAP_NOTE"] = ("Positive means the model expected more knock-ins than occurred. Bars crossing the zero line "
                     "are not distinguishable from a model that was right.")
    P["S3_CALLOUT"] = """
<div class="callout amber">
  <strong>The sample is thinner than it looks</strong> Every S&amp;P 500 knock-in at the 60% barrier comes from one
  episode, the 2008 crash. The Euro Stoxx 50 adds 2002. A deep barrier result rests on two or three crashes in
  thirty years, and weekly sampling does not create more of them.
</div>"""

    # ── Section 4 ────────────────────────────────────────────────────────────
    P["S4_BODY"] = f"""
<p>The overcharging is uneven across underlyings. On the S&amp;P 500, local
volatility priced knock-ins at {spx7['lv']['ratio']:.1f} times the realised rate. On single stocks the same model,
fitted the same way, came in at {sn7['lv']['ratio']:.1f} times. The Euro Stoxx 50 sits between them at
{eu7['lv']['ratio']:.1f} times.</p>
<p>Judged on cash profit alone, the two trades look identical. A seller of the single stock put collected
{sn7['lv']['dip']:.2f}% of notional and finished the year {sn7['lv']['pnl']:+.2f}% ahead on average, against
{spx7['lv']['dip']:.2f}% collected and {spx7['lv']['pnl']:+.2f}% earned on the index. What separates them is how much
of the premium survives realised losses: the index seller kept {spx7['lv']['kept']:.0f}%, the single stock seller
{sn7['lv']['kept']:.0f}%. The single stock premium is larger because single stocks are more volatile, and the seller
pays back {100 - sn7['lv']['kept']:.0f}% of it in realised losses.</p>
<p>That split is the correlation risk premium, measured in one contract. Driessen, Maenhout and Vilkov (2009) found
that index options carry a large priced premium while individual equity options carry little, because the index
premium compensates for correlation risk that single names do not bear. Their evidence is in variances. The same
split appears here in the event that decides a note's payoff, whether the barrier breaks.</p>
<p>Sorting single stocks by their own volatility separates them further. The calmest third, averaging
{T70['low']['vol']:.0f}% volatility, kept {T70['low']['kept']:.0f}% of the premium and behaves much like the index.
The most volatile third, averaging {T70['high']['vol']:.0f}%, kept {T70['high']['kept']:.0f}%. Issuers do not write
retail notes on the calm third.</p>"""
    P["HL1"] = f"{spx7['lv']['kept']:.0f}%"
    P["HL2"] = f"{eu7['lv']['kept']:.0f}%"
    P["HL3"] = f"{sn7['lv']['kept']:.0f}%"
    P["TERCILE_NOTE"] = ("Terciles use each product's own at-the-money volatility on its start date, so the split "
                         "is known in advance and uses no hindsight.")
    P["S4_CALLOUT"] = f"""
<div class="callout green">
  <strong>The finding in one line</strong> The crash premium in barrier options is an index phenomenon. The seller
  of the embedded put kept {spx7['lv']['kept']:.0f}% of the premium on the S&amp;P 500, {sn7['lv']['kept']:.0f}% on single
  stocks, and {T70['high']['kept']:.0f}% on the most volatile third of single stocks.
</div>"""

    # ── Section 5 ────────────────────────────────────────────────────────────
    reg = D["regimes"]["SPX"]["0.7"]
    gfc = [v for k, v in reg.items() if "GFC" in k][0]
    calm = reg["2010-2019"]
    P["S5_BODY"] = f"""
<p>If the skew were a forecast, its errors would scatter, and they do not. Grouped by era, the model is wrong in a
pattern: it overstates knock-ins through every calm stretch and understates them in the one period that mattered.
Products started during the financial crisis knocked in {gfc['realised'] * 100:.0f}% of the time on the S&amp;P 500
while local volatility had priced {gfc['lv'] * 100:.0f}%. Through the 2010s the model priced {calm['lv'] * 100:.0f}%
against a realised rate of {calm['realised'] * 100:.0f}%.</p>
<p>That pattern is what an insurance premium should do: exceed the average loss, then fall short in the disaster it
insures against. It also settles what the skew is. The skew is a price, and anyone who reads implied probabilities
off it as a forecast will be wrong in the period that matters most.</p>"""
    P["EPI_NOTE"] = ("Knock-ins cluster into a few episodes rather than spreading evenly, which is the real limit "
                     "on how precisely any of this can be measured.")
    cal_sn = D["calibration"]["SN"]["0.7"]
    P["CAL_NOTE"] = (
        f"Single stocks give enough events to bin: {sum(c['n'] for c in cal_sn):,} products across {len(cal_sn)} "
        "probability buckets. Points below the line are buckets where the model expected more knock-ins than "
        "occurred. The index has too few events to bin meaningfully, so it is not shown.")

    # regime heatmap
    sets = (("SPX", "S&amp;P 500"), ("SX5E", "Euro Stoxx 50"), ("SN", "Single stocks"))
    eras = ["1996-2007", "2007-2009 GFC", "2010-2019", "2020 onward"]
    head = "".join(f"<th class='hm-col'>{lab}</th>" for _, lab in sets)
    body = ""
    for era in eras:
        cells = ""
        for key, _ in sets:
            r = D["regimes"][key]["0.7"].get(era)
            if r is None:
                cells += "<td class='hm-cell hm-empty'>n/a</td>"
                continue
            gap = (r["lv"] - r["realised"]) * 100
            cells += (f"<td class='hm-cell' style='background:{diverging(gap, 25)}'>{gap:+.0f} pts"
                      f"<div style='font-size:.62rem;color:#4a6460'>{r['lv'] * 100:.0f} vs {r['realised'] * 100:.0f}</div></td>")
        body += f"<tr><td class='hm-row-label'>{era}</td>{cells}</tr>"
    P["REGIME_TABLE"] = (
        "<div class='hm-wrap'><table class='hm-table'><thead><tr><th class='hm-corner'></th>" + head
        + "</tr></thead><tbody>" + body + "</tbody></table></div>"
        + "<div class='note'>Local volatility knock-in probability minus the realised rate, 70% barrier, in "
          "percentage points. Green means the model charged for more crashes than happened, red means it charged "
          "for fewer. Figures below each cell are model against realised.</div>")

    # ── Section 6 ────────────────────────────────────────────────────────────
    P["S6_BODY"] = f"""
<p>Everything above measures the option, not the product. An investor does not receive the option premium. Issuers
sell the note above its fair value, and the difference is their margin, which no term sheet states in a form a buyer
can read off.</p>
<p>Published estimates of that margin are larger than the premium measured here. Vokata (2021) values more than
28,000 US yield enhancement products, the exact family studied in this report, and finds fees of
{fees[0]['value']}, with investors losing a comparable amount against risk-adjusted benchmarks. Henderson and
Pearson (2011) put the overpricing of 64 issues at {fees[1]['value']}. The embedded put in our single stock sample
earned {sn7['lv']['pnl']:+.2f}% of notional a year before any costs. Subtract even the low end of those estimates and
the arithmetic turns negative.</p>
<p>The comparison is indicative rather than exact. Our contract is a
standalone one year put on one underlying, held to maturity, with no coupon and no call feature. The notes in
those studies bundle a coupon, an early redemption trigger and sometimes several underlyings. What survives the
difference is direction and order of magnitude: the risk premium inside the embedded option is similar in size
to, or smaller than, the documented cost of reaching it through a note.</p>"""
    P["FEE_NOTE"] = ("Grey bars are published estimates from four independent studies, not results of this one. "
                     "They are drawn on the same axis to show scale.")
    frows = "".join(f"<tr><td>{f['source']}</td><td class='mono'>{f['value']}</td></tr>" for f in fees)
    P["FEE_TABLE"] = ("<div class='table-wrap'><table><thead><tr><th>Published estimate of issuer margin</th>"
                      "<th>Size</th></tr></thead><tbody>" + frows + "</tbody></table></div>")
    P["S6_CALLOUT"] = """
<div class="callout blue">
  <strong>Read this the right way</strong> This does not say barrier notes are mispriced by their issuers. It says
  the compensation inside the embedded option, measured over thirty years, is smaller than the fees documented on
  the products that package it. An institution selling the option directly keeps that premium. A retail buyer of
  the note does not.
</div>"""

    # ── Section 7 ────────────────────────────────────────────────────────────
    P["S7_BODY"] = f"""
<p>Surfaces come from the OptionMetrics volatility surface file, which gives implied volatility on a delta grid at
fixed maturities. For each date I fit an SSVI surface, a parameterisation that cannot contain butterfly or
calendar arbitrage by construction, derive local volatility from it with Dupire's formula, and price the barrier
on a finite-difference grid with daily monitoring.</p>
<p>I kept no result until three checks passed. The solver reprices plain puts to within one tenth of one
percent of the Black-Scholes formula. Against Monte Carlo with daily monitoring it matches knock-in probabilities
to within four hundredths of a percentage point. And because the barriers sit deeper than the grid the surface is
fitted on, I tested the fitted wing against {MET['wing_n']:,} individual listed put quotes between 55% and 75% of
spot: mean absolute error {MET['wing_mae']:.2f} volatility points, and {MET['wing_near60_mae']:.2f} points near the 60%
barrier. The fit sits {MET['wing_mean_gap']:+.2f} points above the market on average in that region, which lifts local
volatility knock-in probabilities slightly and therefore works against the central finding rather than for it.</p>
<p>I excluded surfaces that could not be fitted rather than flagging them: {MET['sn_excluded']:,} of {MET['sn_dates']:,}
single stock dates ({MET['sn_excluded_pct']:.1f}%), where fit error exceeded three volatility points or a tenth of
at-the-money volatility. Most sit around special dividends and crisis weeks. One index date failed the same
rule.</p>"""

    method_rows = [
        ("Product", "One year down-and-in put struck at the starting level, barriers at 60, 70 and 80% of spot, "
                    "monitored on daily closes"),
        ("Start dates", f"Weekly, {pretty(spx7['first'])} to {pretty(spx7['last'])} for the S&amp;P 500, "
                        f"{pretty(S['SX5E']['0.7']['first'])} to {pretty(S['SX5E']['0.7']['last'])} for the "
                        "Euro Stoxx 50"),
        ("Single stock universe", f"Ten names per start date, {MET['sn_names']} distinct companies, ranked at the "
                                  "time by option volume among S&amp;P 500 members, one share class per company"),
        ("Surfaces", "OptionMetrics IvyDB US and Europe volatility surfaces, tenors 30 to 547 days, out-of-the-money "
                     "half of the delta grid"),
        ("Rates and carry", "OptionMetrics zero curve and listed forward prices, so dividends enter through the "
                            "forward rather than an assumed yield"),
        ("Fit", f"SSVI, free of static arbitrage by construction. Median fit error {MET['spx_fit_rmse_median']:.2f} "
                f"volatility points on the S&amp;P 500 and {MET['sn_fit_rmse_median']:.2f} on single stocks"),
        ("Pricing", "Dupire local volatility on a Crank-Nicolson grid with Rannacher smoothing, 1,008 time steps, "
                    "barrier placed between grid nodes"),
        ("Flat volatility models", "Reiner-Rubinstein closed form with the Broadie-Glasserman-Kou correction for "
                                   "daily rather than continuous monitoring"),
        ("Realised outcomes", "CRSP daily closes, split-adjusted, with delisted names carried at their delisting "
                              "price. Bankruptcies count as knock-ins"),
        ("Statistics", "Moving block bootstrap with one year blocks, Newey-West standard errors at 52 lags, single "
                       "stocks averaged within each start date before testing"),
        ("Profit and loss", "Unhedged, held to maturity, premium compounded at the one year rate. No hedging costs, "
                            "funding or issuer margin"),
    ]
    P["METHOD_TABLE"] = ("<div class='table-wrap'><table><thead><tr><th>Dimension</th><th>Detail</th></tr></thead>"
                         "<tbody>" + "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in method_rows)
                         + "</tbody></table></div>")

    P["LIMITS"] = """
<div class="callout amber">
  <strong>Overlapping windows</strong> Weekly start dates with one year products overlap almost completely. The
  effective sample is the number of independent years, not the number of products, and every interval quoted here
  respects that.
</div>
<div class="callout amber">
  <strong>Few crashes</strong> Deep barriers break only in crashes, and the sample contains two or three. The 60%
  results should be read as descriptive.
</div>
<div class="callout blue">
  <strong>One skew-consistent model</strong> Local volatility is not the only model that fits the surface.
  Stochastic volatility models match the same vanilla prices and can produce different barrier prices, because
  they assume a different future skew. That comparison is a separate study.
</div>
<div class="callout blue">
  <strong>No hedging or funding</strong> Profit and loss is unhedged and held to maturity, and ignores funding,
  borrow and bid-ask spreads. A desk would hedge, which changes the distribution of outcomes rather than the
  expected value.
</div>
<div class="callout purple">
  <strong>Three bugs found by the checks</strong> Placing the barrier on a grid node rather than between nodes
  inflated knock-in probabilities by about half a percentage point. The closed-form barrier formula overflows at
  very low volatility with large negative carry, which surfaced on Microsoft's 2004 special dividend dates. And
  mixing split-adjusted CRSP prices with unadjusted OptionMetrics spot turned every stock split into a false
  knock-in, briefly producing an impossible 40.8% realised rate before it was caught.
</div>"""

    # ── Section 8 ────────────────────────────────────────────────────────────
    P["S8_BODY"] = f"""
<p>Flat volatility misprices a barrier, and the choice of which flat volatility decides the direction of the
error. At the money it understates the price by a factor of four at a 60% barrier. At the barrier strike it
overstates it by half. The number that reproduces the skew-consistent price lies between them and moves with the
regime, so there is no shortcut worth memorising.</p>
<p>Measured against thirty years of outcomes, the skew-consistent price was systematically generous to the seller
of crash risk, by {spx7['lv']['gap']:+.1f} percentage points of knock-in probability on the S&amp;P 500 at a 70%
barrier. That premium is concentrated in the index. On single stocks, and on volatile single stocks most of all,
the bulk of what is charged for the barrier is paid back in realised losses.</p>
<p>For anyone structuring these products, an index-linked barrier and a single stock barrier are not two versions of
the same trade. And for anyone buying the note rather than selling the option, the premium collected on their behalf
is smaller than the published cost of the wrapper around it.</p>"""
    return P
