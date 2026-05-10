"""
01_fomc_events.py
-----------------
Hardcode all FOMC meeting dates (2018-2024) with two classification layers:

  PRIMARY — decision_type:
    "Hike"  : rates raised (actual_change_bps > 0)
    "Hold"  : no rate change
    "Cut"   : rates lowered (actual_change_bps < 0)

  SECONDARY — comm_surprise (communication / dot-plot surprise):
    "Hawkish" : statement, dot plot, or press conference materially more
                hawkish than market expected
    "Dovish"  : materially more dovish than expected
    "Neutral" : no significant guidance surprise

The comm_surprise layer captures what actually moved markets: many "in-line"
rate decisions had large guidance surprises (Jun 2021 hawkish dot shift,
Dec 2023 dovish pivot, Jan 2024 hawkish walkback, etc.).

Emergency and degenerate meetings are flagged separately.

Sources:
  - Rate decisions: Federal Reserve press releases
  - Expected changes: CME FedWatch Tool historical data
  - Communication classification: dot plot changes, statement language,
    press conference tone, and same-day equity/rates market reaction

Output: data/fomc_events.parquet
        data/fomc_events.csv
"""

import os
import pandas as pd

os.makedirs("data", exist_ok=True)

# ── FOMC meeting records ───────────────────────────────────────────────────────
# Fields:
#   date              : announcement date
#   prior_upper       : upper bound of target range BEFORE this meeting (%)
#   actual_change_bps : rate change delivered (bps; negative = cut)
#   expected_bps      : CME FedWatch implied expected change at T-1 (bps)
#   comm_surprise     : communication/dot-plot surprise (Hawkish/Dovish/Neutral)
#   is_emergency      : True for unscheduled emergency meetings
#   is_outlier        : True for COVID emergency cuts + degenerate Mar 18 2020
#   notes             : rationale for comm_surprise classification

MEETINGS = [
    # ── 2018 ─────────────────────────────────────────────────────────────────
    {"date": "2018-01-31", "prior_upper": 1.50, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; standard language; no dot plot update"},
    {"date": "2018-03-21", "prior_upper": 1.50, "actual_change_bps": 25,
     "expected_bps": 25, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hike to 1.50-1.75%; dot plot unchanged at 3 hikes for 2018"},
    {"date": "2018-05-02", "prior_upper": 1.75, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; inflation described as near symmetric goal; no surprises"},
    {"date": "2018-06-13", "prior_upper": 1.75, "actual_change_bps": 25,
     "expected_bps": 25, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hike to 1.75-2.00%; dot plot raised to 4 hikes in 2018 (from 3); hawkish guidance"},
    {"date": "2018-08-01", "prior_upper": 2.00, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; trade war uncertainty noted; statement largely unchanged"},
    {"date": "2018-09-26", "prior_upper": 2.00, "actual_change_bps": 25,
     "expected_bps": 25, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hike to 2.00-2.25%; 'accommodative' removed from statement but expected"},
    {"date": "2018-11-08", "prior_upper": 2.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; midterm election day; no dot plot; uneventful"},
    {"date": "2018-12-19", "prior_upper": 2.25, "actual_change_bps": 25,
     "expected_bps": 25, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hike to 2.25-2.50%; dot plot still showed 2 hikes in 2019 vs market pricing ~1; S&P -1.5%"},

    # ── 2019 ─────────────────────────────────────────────────────────────────
    {"date": "2019-01-30", "prior_upper": 2.50, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Dovish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; major dovish pivot: 'patient' introduced, removed rate-hike bias; 10Y yields fell 10bps"},
    {"date": "2019-03-20", "prior_upper": 2.50, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Dovish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; dot plot removed all 2019 hikes; QT end date set (Sep); more dovish than expected"},
    {"date": "2019-05-01", "prior_upper": 2.50, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; transitory inflation framing; no material guidance change"},
    {"date": "2019-06-19", "prior_upper": 2.50, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Dovish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; 'patient' dropped; 'act as appropriate' added; cuts clearly signalled; S&P +0.5%"},
    {"date": "2019-07-31", "prior_upper": 2.50, "actual_change_bps": -25,
     "expected_bps": -25, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Cut to 2.00-2.25%; Powell called it 'mid-cycle adjustment' not start of long easing cycle; market disappointed, S&P -1.1%"},
    {"date": "2019-09-18", "prior_upper": 2.25, "actual_change_bps": -25,
     "expected_bps": -25, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Cut to 1.75-2.00%; repo market stress backdrop; 3 dissents; neutral communication"},
    {"date": "2019-10-30", "prior_upper": 2.00, "actual_change_bps": -25,
     "expected_bps": -25, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Cut to 1.50-1.75%; statement indicated pause; removed 'act as appropriate'; hawkish signal vs cut expectations"},
    {"date": "2019-12-11", "prior_upper": 1.75, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; bar for changes 'high'; dot plot showed no cuts in 2020; neutral"},

    # ── 2020 ─────────────────────────────────────────────────────────────────
    {"date": "2020-01-29", "prior_upper": 1.75, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; COVID not yet a US market concern; repo facility mentioned"},
    {"date": "2020-03-03", "prior_upper": 1.75, "actual_change_bps": -50,
     "expected_bps":  0, "comm_surprise": "Dovish",
     "is_emergency": True,  "is_outlier": True,
     "notes": "EMERGENCY: COVID pandemic; market expected hold; emergency 50bps cut; major surprise"},
    {"date": "2020-03-15", "prior_upper": 1.25, "actual_change_bps": -100,
     "expected_bps": -50, "comm_surprise": "Dovish",
     "is_emergency": True,  "is_outlier": True,
     "notes": "EMERGENCY: Cut to 0.00-0.25%; QE restarted ($700bn); larger than expected; coordinated global action"},
    {"date": "2020-03-18", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": True,
     "notes": "Scheduled meeting; rates already at ZLB from emergency actions; degenerate observation"},
    {"date": "2020-04-29", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Dovish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; outcome-based forward guidance strengthened; committed to ZLB until recovery"},
    {"date": "2020-06-10", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Dovish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; dot plot: rates at zero through 2022; first dot plot since pandemic"},
    {"date": "2020-07-29", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; AIT framework in development; statement largely unchanged"},
    {"date": "2020-09-16", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Dovish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; AIT formally adopted; rates at zero until max employment AND 2%+ inflation; major dovish framework shift"},
    {"date": "2020-11-05", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; post-election; vaccine trials advancing; no material language change"},
    {"date": "2020-12-16", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; QE pace maintained; outcome-based guidance; no surprises"},

    # ── 2021 ─────────────────────────────────────────────────────────────────
    {"date": "2021-01-27", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; recovery underway; taper discussion 'not the time'; neutral"},
    {"date": "2021-03-17", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; dot plot: still zero through 2023; slightly hawkish vs prior but within expectations"},
    {"date": "2021-04-28", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; transitory inflation framing; taper 'not yet'; uneventful"},
    {"date": "2021-06-16", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; dot plot shifted to 2 hikes by 2023 liftoff vs zero prior; major hawkish surprise; 10Y +8bps, S&P -0.5%"},
    {"date": "2021-07-28", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; taper discussion acknowledged; 'substantial further progress' criteria discussed"},
    {"date": "2021-09-22", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; taper 'soon' — more concrete than expected; dot plot split on 2022 hike; hawkish tilt"},
    {"date": "2021-11-03", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; taper announced at $15bn/month as expected; neutral"},
    {"date": "2021-12-15", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; taper doubled to $30bn/month; dot plot: 3 hikes in 2022 vs market pricing 1-2; major hawkish surprise"},

    # ── 2022 ─────────────────────────────────────────────────────────────────
    {"date": "2022-01-26", "prior_upper": 0.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; Powell press conference hawkish: 'lots of room to raise without hurting labour market'; balance sheet runoff discussed; S&P -1.9%"},
    {"date": "2022-03-16", "prior_upper": 0.25, "actual_change_bps": 25,
     "expected_bps": 25, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hike to 0.25-0.50%; liftoff; dot plot showed 7 hikes in 2022 total, more aggressive than expected"},
    {"date": "2022-05-04", "prior_upper": 0.50, "actual_change_bps": 50,
     "expected_bps": 50, "comm_surprise": "Dovish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hike 50bps; Powell explicitly ruled out 75bps at press conference — major dovish surprise; S&P +3.0%"},
    {"date": "2022-06-15", "prior_upper": 1.00, "actual_change_bps": 75,
     "expected_bps": 50, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hike 75bps vs 50bps expected; rate decision AND guidance hawkish; CPI 8.6% on Jun 10 shifted some to 75bps late"},
    {"date": "2022-07-27", "prior_upper": 1.75, "actual_change_bps": 75,
     "expected_bps": 75, "comm_surprise": "Dovish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hike 75bps as expected; Powell said 'at some point appropriate to slow'; dovish communication; S&P +2.6%"},
    {"date": "2022-09-21", "prior_upper": 2.25, "actual_change_bps": 75,
     "expected_bps": 75, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hike 75bps; dot plot: terminal rate raised to 4.6% vs 3.8% prior; more hikes in 2023; hawkish dots"},
    {"date": "2022-11-02", "prior_upper": 3.00, "actual_change_bps": 75,
     "expected_bps": 75, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hike 75bps; statement noted cumulative tightening lags; mixed signals at press conference"},
    {"date": "2022-12-14", "prior_upper": 3.25, "actual_change_bps": 50,
     "expected_bps": 50, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Step-down to 50bps; dot plot terminal rate raised to 5.1% vs 4.6% prior; Powell pushes back on pivot narrative"},

    # ── 2023 ─────────────────────────────────────────────────────────────────
    {"date": "2023-02-01", "prior_upper": 4.50, "actual_change_bps": 25,
     "expected_bps": 25, "comm_surprise": "Dovish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hike 25bps; Powell explicitly used 'disinflation' — first time; market took as dovish signal; S&P +1.5%"},
    {"date": "2023-03-22", "prior_upper": 4.75, "actual_change_bps": 25,
     "expected_bps": 25, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hike 25bps; SVB crisis (Mar 10); statement noted banking stress but continued; neutral net tone"},
    {"date": "2023-05-03", "prior_upper": 5.00, "actual_change_bps": 25,
     "expected_bps": 25, "comm_surprise": "Dovish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hike 25bps; statement added 'may be appropriate to hold' — clear pause signal; dovish communication"},
    {"date": "2023-06-14", "prior_upper": 5.25, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "First pause (skip); but dot plot showed 2 more hikes in 2023 vs market expecting 1; hawkish dots"},
    {"date": "2023-07-26", "prior_upper": 5.25, "actual_change_bps": 25,
     "expected_bps": 25, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Resumed hiking; 5.25-5.50%; last hike of cycle; neutral communication"},
    {"date": "2023-09-20", "prior_upper": 5.50, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; dot plot reduced 2024 cuts to 2 (from 4); higher-for-longer; hawkish vs market expectations"},
    {"date": "2023-11-01", "prior_upper": 5.50, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Dovish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; Powell: 'not thinking about raising rates'; market took as dovish pivot signal; 10Y -20bps"},
    {"date": "2023-12-13", "prior_upper": 5.50, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Dovish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; dot plot: 3 cuts in 2024 vs market pricing ~2; Powell did not push back; major dovish pivot; S&P +1.4%"},

    # ── 2024 ─────────────────────────────────────────────────────────────────
    {"date": "2024-01-31", "prior_upper": 5.50, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; Powell walked back March cut: 'not likely'; market had March cut ~80% priced; hawkish surprise"},
    {"date": "2024-03-20", "prior_upper": 5.50, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; maintained 3 cuts in dot plot; in-line with expectations"},
    {"date": "2024-05-01", "prior_upper": 5.50, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Dovish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; QT pace slowed ($60bn to $25bn); Powell: 'unlikely to hike'; dovish lean"},
    {"date": "2024-06-12", "prior_upper": 5.50, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; dot plot cut to 1 cut in 2024 vs 3 expected (after Dec 2023 pivot); major hawkish surprise on dots"},
    {"date": "2024-07-31", "prior_upper": 5.50, "actual_change_bps":  0,
     "expected_bps":  0, "comm_surprise": "Dovish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Hold; Powell signalled September cut clearly: 'the time is coming'; dovish communication"},
    {"date": "2024-09-18", "prior_upper": 5.50, "actual_change_bps": -50,
     "expected_bps": -25, "comm_surprise": "Dovish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Cut 50bps vs 25bps consensus; rate decision AND communication both dovish; FedWatch ~50/50 on eve"},
    {"date": "2024-11-07", "prior_upper": 5.00, "actual_change_bps": -25,
     "expected_bps": -25, "comm_surprise": "Neutral",
     "is_emergency": False, "is_outlier": False,
     "notes": "Cut 25bps; post-election; in-line; neutral communication"},
    {"date": "2024-12-18", "prior_upper": 4.75, "actual_change_bps": -25,
     "expected_bps": -25, "comm_surprise": "Hawkish",
     "is_emergency": False, "is_outlier": False,
     "notes": "Cut 25bps; dot plot: only 2 cuts in 2025 vs 4 expected; hawkish guidance surprise; S&P -3.0%"},
]

# ── Build DataFrame ────────────────────────────────────────────────────────────
df = pd.DataFrame(MEETINGS)
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date").reset_index(drop=True)

# Primary classification
def decision_type(bps):
    if bps > 0:
        return "Hike"
    elif bps < 0:
        return "Cut"
    else:
        return "Hold"

df["decision_type"] = df["actual_change_bps"].apply(decision_type)
df["year"] = df["date"].dt.year
df["surprise_bps"] = df["actual_change_bps"] - df["expected_bps"]
df["post_upper"] = df["prior_upper"] + df["actual_change_bps"] / 100

# ── Summary ────────────────────────────────────────────────────────────────────
print(f"Total meetings: {len(df)}")
print(f"Date range: {df['date'].min().date()} to {df['date'].max().date()}")
print()

print("PRIMARY — decision_type breakdown:")
print(df["decision_type"].value_counts().to_string())
print()

print("SECONDARY — comm_surprise breakdown (all meetings):")
print(df["comm_surprise"].value_counts().to_string())
print()

print("SECONDARY — comm_surprise breakdown within Hold meetings:")
holds = df[df["decision_type"] == "Hold"]
print(holds["comm_surprise"].value_counts().to_string())
print(f"  (n={len(holds)} hold meetings)")
print()

print("SECONDARY — comm_surprise breakdown within Hike meetings:")
hikes = df[df["decision_type"] == "Hike"]
print(hikes["comm_surprise"].value_counts().to_string())
print(f"  (n={len(hikes)} hike meetings)")
print()

print("SECONDARY — comm_surprise breakdown within Cut meetings:")
cuts = df[df["decision_type"] == "Cut"]
print(cuts["comm_surprise"].value_counts().to_string())
print(f"  (n={len(cuts)} cut meetings)")
print()

print("Outlier meetings:")
print(df[df["is_outlier"]][["date", "decision_type", "actual_change_bps", "comm_surprise", "notes"]].to_string(index=False))
print()

print("Hawkish comm surprises:")
print(df[df["comm_surprise"] == "Hawkish"][["date", "decision_type", "actual_change_bps", "notes"]].to_string(index=False))
print()

print("Dovish comm surprises:")
print(df[df["comm_surprise"] == "Dovish"][["date", "decision_type", "actual_change_bps", "notes"]].to_string(index=False))

# ── Save ──────────────────────────────────────────────────────────────────────
df.to_parquet("data/fomc_events.parquet", index=False)
df.to_csv("data/fomc_events.csv", index=False)
print(f"\nSaved {len(df)} rows to data/fomc_events.parquet and data/fomc_events.csv")
