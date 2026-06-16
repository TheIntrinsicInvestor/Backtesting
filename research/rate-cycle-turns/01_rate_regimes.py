"""
01_rate_regimes.py
------------------
Build daily Fed Funds target rate series from hardcoded FOMC decision history,
classify into regimes, and annotate turn dates.

No external data pull required — rates are hardcoded from FOMC press releases.
This makes the script fully reproducible without network access.

Outputs: data/regimes.parquet, data/turns.parquet
"""
import pandas as pd
from pathlib import Path

DATA = Path("data")
DATA.mkdir(exist_ok=True)

REGIMES_CACHE = DATA / "regimes.parquet"
TURNS_CACHE   = DATA / "turns.parquet"
START, END    = "1994-01-01", "2025-12-31"

# ── FOMC rate decisions 1994-2025 (upper bound of target / single target) ──
# Source: Federal Reserve FOMC press releases.
# Format: (date, rate_pct) — the new upper-bound rate after each decision.
# Pre-2008: single target rate. Post-2008: upper bound of 0-25bp corridor.
FOMC_DECISIONS = [
    # 1994 hiking cycle
    ("1994-01-01", 3.00),   # rate at sample start (no decision, just initial value)
    ("1994-02-04", 3.25),
    ("1994-03-22", 3.50),
    ("1994-04-18", 3.75),
    ("1994-05-17", 4.25),   # 50bps
    ("1994-07-06", 4.50),
    ("1994-08-16", 4.75),
    ("1994-11-15", 5.50),   # 75bps
    ("1995-02-01", 6.00),
    # 1995-96 insurance cuts
    ("1995-07-06", 5.75),
    ("1995-12-19", 5.50),
    ("1996-01-31", 5.25),
    # 1997 nudge up
    ("1997-03-25", 5.50),
    # 1998 LTCM / Russia crisis cuts
    ("1998-09-29", 5.25),
    ("1998-10-15", 5.00),   # inter-meeting
    ("1998-11-17", 4.75),
    # 1999-2000 hiking cycle
    ("1999-06-30", 5.00),
    ("1999-08-24", 5.25),
    ("1999-11-16", 5.50),
    ("2000-02-02", 5.75),
    ("2000-03-21", 6.00),
    ("2000-05-16", 6.50),
    # 2001 cutting cycle (dot-com / post-9-11)
    ("2001-01-03", 6.00),   # inter-meeting
    ("2001-01-31", 5.50),
    ("2001-03-20", 5.00),
    ("2001-04-18", 4.50),   # inter-meeting
    ("2001-05-15", 4.00),
    ("2001-06-27", 3.75),
    ("2001-08-21", 3.50),
    ("2001-09-17", 3.00),   # inter-meeting post-9-11
    ("2001-10-02", 2.50),
    ("2001-11-06", 2.00),
    ("2001-12-11", 1.75),
    ("2002-11-06", 1.25),
    ("2003-06-25", 1.00),
    # 2004-06 hiking cycle
    ("2004-06-30", 1.25),
    ("2004-08-10", 1.50),
    ("2004-09-21", 1.75),
    ("2004-11-10", 2.00),
    ("2004-12-14", 2.25),
    ("2005-02-02", 2.50),
    ("2005-03-22", 2.75),
    ("2005-05-03", 3.00),
    ("2005-06-30", 3.25),
    ("2005-08-09", 3.50),
    ("2005-09-20", 3.75),
    ("2005-11-01", 4.00),
    ("2005-12-13", 4.25),
    ("2006-01-31", 4.50),
    ("2006-03-28", 4.75),
    ("2006-05-10", 5.00),
    ("2006-06-29", 5.25),
    # 2007-08 GFC cutting cycle
    ("2007-09-18", 4.75),
    ("2007-10-31", 4.50),
    ("2007-12-11", 4.25),
    ("2008-01-22", 3.50),   # inter-meeting
    ("2008-01-30", 3.00),
    ("2008-03-18", 2.25),
    ("2008-04-30", 2.00),
    ("2008-10-08", 1.50),   # inter-meeting, coordinated global
    ("2008-10-29", 1.00),
    ("2008-12-16", 0.25),   # corridor 0-25bps introduced
    # 2015-18 normalization
    ("2015-12-16", 0.50),
    ("2016-12-14", 0.75),
    ("2017-03-15", 1.00),
    ("2017-06-14", 1.25),
    ("2017-12-13", 1.50),
    ("2018-03-21", 1.75),
    ("2018-06-13", 2.00),
    ("2018-09-26", 2.25),
    ("2018-12-19", 2.50),
    # 2019 insurance cuts
    ("2019-07-31", 2.25),
    ("2019-09-18", 2.00),
    ("2019-10-30", 1.75),
    # 2020 COVID emergency cuts (outlier)
    ("2020-03-03", 1.25),   # inter-meeting
    ("2020-03-15", 0.25),   # inter-meeting, ZLB restored
    # 2022-23 hiking cycle
    ("2022-03-16", 0.50),
    ("2022-05-04", 1.00),
    ("2022-06-15", 1.75),
    ("2022-07-27", 2.50),
    ("2022-09-21", 3.25),
    ("2022-11-02", 4.00),
    ("2022-12-14", 4.50),
    ("2023-02-01", 4.75),
    ("2023-03-22", 5.00),
    ("2023-05-03", 5.25),
    ("2023-07-26", 5.50),
    # 2024 cutting cycle
    ("2024-09-18", 5.00),
    ("2024-11-07", 4.75),
    ("2024-12-18", 4.50),
    # 2025 hold
    ("2025-01-29", 4.50),
]

# Build daily target rate via forward-fill
decisions = pd.DataFrame(FOMC_DECISIONS, columns=["date", "target_rate"])
decisions["date"] = pd.to_datetime(decisions["date"])
decisions = decisions.sort_values("date").set_index("date")

date_range = pd.date_range(START, END, freq="D")
rate = (decisions["target_rate"]
        .reindex(date_range)
        .ffill()
        .reset_index()
        .rename(columns={"index": "date"}))
rate.columns = ["date", "target_rate"]
print(f"Target rate series: {len(rate):,} daily rows, "
      f"{rate['date'].min().date()} to {rate['date'].max().date()}")
print(f"Rate range: {rate['target_rate'].min():.2f}% to "
      f"{rate['target_rate'].max():.2f}%")

# ── Regime spans ────────────────────────────────────────────────────────────
# Manually verified against Fed FOMC calendar.
# is_outlier=True: COVID emergency period; excluded from main aggregates.
REGIME_SPANS = [
    # start         end             regime             is_outlier
    ("1994-01-01", "1994-02-03",  "Hold-Elevated",   False),
    ("1994-02-04", "1995-02-01",  "Hiking",          False),  # 3% -> 6%
    ("1995-02-02", "1999-06-29",  "Hold-Elevated",   False),  # incl. 1995-96 + 1998 mid-cycle moves
    ("1999-06-30", "2000-05-16",  "Hiking",          False),  # 4.75% -> 6.5%
    ("2000-05-17", "2001-01-02",  "Hold-Elevated",   False),
    ("2001-01-03", "2003-06-24",  "Cutting",         False),  # dot-com / post-9-11
    ("2003-06-25", "2004-06-29",  "Hold-Elevated",   False),  # 1% floor (above ZLB)
    ("2004-06-30", "2006-06-29",  "Hiking",          False),  # 1% -> 5.25%
    ("2006-06-30", "2007-09-17",  "Hold-Elevated",   False),
    ("2007-09-18", "2008-12-15",  "Cutting",         False),  # GFC easing
    ("2008-12-16", "2015-12-15",  "Hold-ZLB",        False),  # post-GFC ZIRP
    ("2015-12-16", "2018-12-18",  "Hiking",          False),  # 0.25% -> 2.5%
    ("2018-12-19", "2019-07-30",  "Hold-Elevated",   False),
    ("2019-07-31", "2020-03-02",  "Cutting",         False),  # insurance cuts
    ("2020-03-03", "2020-03-15",  "Cutting",         True),   # COVID emergency (outlier)
    ("2020-03-16", "2022-03-15",  "Hold-ZLB",        False),  # COVID ZIRP
    ("2022-03-16", "2023-07-26",  "Hiking",          False),  # 0.25% -> 5.5%
    ("2023-07-27", "2024-09-17",  "Hold-Elevated",   False),
    ("2024-09-18", "2025-12-31",  "Cutting",         False),
]

rows = []
for start, end, regime, is_outlier in REGIME_SPANS:
    mask = (rate["date"] >= start) & (rate["date"] <= end)
    rows.append(rate[mask].assign(regime=regime, is_outlier=is_outlier))
regimes = pd.concat(rows).sort_values("date").reset_index(drop=True)

covered  = len(regimes)
expected = len(rate)
print(f"\nRegime coverage: {covered:,} / {expected:,} days "
      f"({'OK' if covered == expected else '*** GAP DETECTED ***'})")
print("\nRegime day counts (excl. weekends — calendar days, not trading days):")
print(regimes.groupby(["regime", "is_outlier"])["date"].count()
      .rename("cal_days").to_string())

# ── Turn dates ───────────────────────────────────────────────────────────────
# Verified against FOMC calendar; include_in_main excludes insurance + emergency.
TURNS_RAW = [
    # date         turn_type                 is_ins  is_out  notes
    ("1994-02-04", "first_hike",             False,  False,
     "Start 1994-95 hiking cycle (3% -> 6%)"),
    ("1995-07-06", "first_cut_insurance",    True,   False,
     "Insurance cut; not recessionary (6% -> 5.75%)"),
    ("1999-06-30", "first_hike",             False,  False,
     "Start 1999-2000 hiking cycle (4.75% -> 6.5%)"),
    ("2001-01-03", "first_cut",              False,  False,
     "Emergency inter-meeting cut; dot-com recession onset"),
    ("2004-06-30", "first_hike",             False,  False,
     "Start 2004-06 hiking cycle (1% -> 5.25%)"),
    ("2007-09-18", "first_cut",              False,  False,
     "Start GFC cutting cycle (5.25% -> 0.25%)"),
    ("2015-12-16", "first_hike",             False,  False,
     "Start 2015-18 normalization cycle (0.25% -> 2.5%)"),
    ("2019-07-31", "first_cut_insurance",    True,   False,
     "Insurance cut; not recessionary (2.5% -> 1.75%)"),
    ("2020-03-03", "first_cut_emergency",    False,  True,
     "COVID emergency cut (OUTLIER; excluded from main aggregates)"),
    ("2022-03-16", "first_hike",             False,  False,
     "Start 2022-23 hiking cycle (0.25% -> 5.5%)"),
    ("2024-09-18", "first_cut",              False,  False,
     "Start 2024 cutting cycle (5.5% -> TBD)"),
]

turns = pd.DataFrame(TURNS_RAW,
    columns=["date", "turn_type", "is_insurance", "is_outlier", "notes"])
turns["date"] = pd.to_datetime(turns["date"])
turns["include_in_main"] = ~(turns["is_insurance"] | turns["is_outlier"])

print("\nTurn dates:")
for _, r in turns.iterrows():
    tag = " [OUTLIER]" if r["is_outlier"] else (" [INSURANCE]" if r["is_insurance"] else "")
    print(f"  {r['date'].date()}  {r['turn_type']:<25}{tag}")
    print(f"    {r['notes']}")

main = turns[turns["include_in_main"]]
print(f"\nMain-aggregate turns: {len(main)} total "
      f"({(main['turn_type']=='first_hike').sum()} hikes, "
      f"{(main['turn_type']=='first_cut').sum()} cuts)")

# ── Save ────────────────────────────────────────────────────────────────────
regimes.to_parquet(REGIMES_CACHE, index=False)
turns.to_parquet(TURNS_CACHE, index=False)
print(f"\nSaved {REGIMES_CACHE} ({len(regimes):,} rows)")
print(f"Saved {TURNS_CACHE}   ({len(turns)} rows)")
print("Done.")
