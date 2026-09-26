# ruff: noqa
"""
06_pull_wing_check.py
---------------------
Batch A, script 4. Raw listed SPX put quotes, used to test the fitted surface's deep wing.

The OptionMetrics 1y surface stops at the 10-delta put (about 70-75% of spot), above the
60% barrier. On 20 evenly spaced start dates we pull every listed SPX put expiring 270-460
days out, so 10_price_all can compare the SSVI wing at 60-75% moneyness with real quotes
(the spec's gate: within 1.5 vol points).

Output: wing_quotes (date, exdate, strike, bid, offer, iv, volume, oi, moneyness)
"""

import common as C
import pandas as pd

starts = pd.to_datetime(C.cached("start_dates_us")["start"])
sample = starts[::75][:20]
print("  sample dates:", ", ".join(str(d.date()) for d in sample))

q = C.cached("wing_quotes")
if q is None:
    db = C.connect()
    parts = []
    for yr, g in sample.groupby(sample.dt.year):
        d = ",".join(f"'{x.date()}'" for x in g)
        part = db.raw_sql(f"""
            SELECT date, exdate, strike_price / 1000.0 AS strike, best_bid, best_offer,
                   impl_volatility, volume, open_interest, am_settlement
            FROM optionm_all.opprcd{yr}
            WHERE secid = {C.SPX_SECID} AND cp_flag = 'P' AND date IN ({d})
              AND exdate BETWEEN date + 270 AND date + 460 AND best_bid > 0""")
        print(f"    {yr}: {len(part):,}")
        parts.append(part)
    db.close()
    q = pd.concat(parts, ignore_index=True)
    spot = C.cached("spx_spot")
    spot["date"] = pd.to_datetime(spot["date"])
    q["date"] = pd.to_datetime(q["date"])
    q = q.merge(spot.rename(columns={"close": "spot"}), on="date")
    q["moneyness"] = q["strike"] / q["spot"]
    q = C.save(q[(q.moneyness >= 0.45) & (q.moneyness <= 1.05)], "wing_quotes")

print("\n=== Checks: deepest quoted put per date (270-460 day expiries) ===")
q["date"] = pd.to_datetime(q["date"])
s = q.groupby("date").agg(expiries=("exdate", "nunique"), quotes=("strike", "size"),
                          min_mny=("moneyness", "min"),
                          n_below_75=("moneyness", lambda m: (m < 0.75).sum()),
                          n_55_65=("moneyness", lambda m: ((m >= 0.55) & (m <= 0.65)).sum()),
                          iv_ok=("impl_volatility", lambda v: v.notna().mean()))
print(s.to_string())
print(f"\n  dates with a quote in 55-65% moneyness: {(s.n_55_65 > 0).sum()} of {len(s)}")
print("\n=== 06 complete ===")
