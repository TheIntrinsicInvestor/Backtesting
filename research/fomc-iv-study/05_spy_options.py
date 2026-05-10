"""
05_spy_options.py
-----------------
Pull ATM SPY straddle prices for both strategy entry/exit dates.

Strategy A — Pre-Meeting:
  Entry : T-1 (last trading day before FOMC announcement)
  Exit  : T+1 (first trading day after announcement)

Strategy B — Post-Announcement:
  Entry : T+1
  Exits : T+2, T+3, T+5, T+10 (trading days after announcement)

For each meeting, a single expiry is selected: the nearest weekly expiry
at least 14 calendar days after the FOMC date, ensuring coverage through T+10.
The same strike (ATM at entry) is used for all exit lookups.
Falls back to intrinsic value when market price unavailable at exit.

SPY secid: 109820  (from 02_secid_mapper.py)

Output: data/spy_straddles.parquet
"""

import os
import wrds
import pandas as pd
import numpy as np
from datetime import timedelta

os.makedirs("data", exist_ok=True)

CACHE = "data/spy_straddles.parquet"
SPY_SECID = 109820

# ── Load dependencies ─────────────────────────────────────────────────────────
events = pd.read_parquet("data/fomc_events.parquet")
events["date"] = pd.to_datetime(events["date"])

# Build trading calendar from SPX IV data
iv_raw = pd.read_parquet("data/iv_raw.parquet")
trading_days = pd.DatetimeIndex(
    sorted(iv_raw[iv_raw["ticker"] == "SPX"]["date"].unique())
)

def find_tday(fomc_date, offset):
    """Return trading day at offset from fomc_date. offset=0 is announcement day."""
    ts = pd.Timestamp(fomc_date)
    idx = trading_days.searchsorted(ts)
    # If fomc_date is not a trading day (emergency on weekend), snap to next
    if idx < len(trading_days) and trading_days[idx] != ts:
        pass  # idx already points to first day >= fomc_date
    target_idx = idx + offset
    if 0 <= target_idx < len(trading_days):
        return trading_days[target_idx]
    return None

# ── Build date map per meeting ────────────────────────────────────────────────
OFFSETS = [-1, 0, 1, 2, 3, 5, 10]

meeting_dates = {}
for _, row in events.iterrows():
    fd = row["date"]
    dates = {}
    for off in OFFSETS:
        d = find_tday(fd, off)
        if d is not None:
            dates[off] = d
    meeting_dates[fd] = dates

# Collect all (date, year) pairs to pull
all_needed = set()
for fd, dates in meeting_dates.items():
    for d in dates.values():
        all_needed.add((d, d.year))

dates_by_year = {}
for d, yr in all_needed:
    dates_by_year.setdefault(yr, set()).add(d)

if os.path.exists(CACHE):
    print(f"Cache found at {CACHE} — skipping WRDS query.")
    results = pd.read_parquet(CACHE)
    print(f"Loaded {len(results):,} records.")
else:
    print("Connecting to WRDS...")
    db = wrds.Connection(wrds_username=os.environ.get("WRDS_USERNAME"))

    # ── Pull raw options by year ───────────────────────────────────────────────
    raw_chunks = []
    for year in sorted(dates_by_year):
        dates_in_year = dates_by_year[year]
        dates_sql = ", ".join(f"'{d.date()}'" for d in sorted(dates_in_year))
        query = f"""
            SELECT o.date, o.exdate, o.cp_flag, o.strike_price,
                   o.best_bid, o.best_offer, o.impl_volatility, o.delta,
                   u.close AS spot
            FROM optionm_all.opprcd{year} o
            JOIN optionm_all.secprd{year} u
              ON o.secid = u.secid AND o.date = u.date
            WHERE o.secid = {SPY_SECID}
              AND o.date IN ({dates_sql})
              AND o.best_bid > 0
              AND o.best_offer > 0
              AND o.ss_flag = '0'
              AND o.exdate > o.date
            ORDER BY o.date, o.exdate, o.cp_flag, o.strike_price
        """
        print(f"  Querying opprcd{year} + secprd{year}...", end=" ", flush=True)
        chunk = db.raw_sql(query, date_cols=["date", "exdate"])
        print(f"{len(chunk):,} rows")
        raw_chunks.append(chunk)

    db.close()

    opts_all = pd.concat(raw_chunks, ignore_index=True)
    opts_all["mid"] = (opts_all["best_bid"] + opts_all["best_offer"]) / 2
    opts_all["strike"] = opts_all["strike_price"] / 1000

    print(f"\nTotal raw option rows: {len(opts_all):,}")

    # ── Process each meeting ──────────────────────────────────────────────────
    records = []

    for _, ev in events.iterrows():
        fomc_date = ev["date"]
        dates = meeting_dates[fomc_date]
        if -1 not in dates or 1 not in dates:
            print(f"  SKIP {fomc_date.date()}: missing T-1 or T+1 date")
            continue

        # Target expiry: at least 14 calendar days after FOMC date
        min_expiry = fomc_date + timedelta(days=14)

        def get_opts(trade_date, min_exp=min_expiry):
            return opts_all[
                (opts_all["date"] == trade_date) &
                (opts_all["exdate"] > min_exp)
            ].copy()

        def find_straddle(trade_date, forced_strike=None, forced_expiry=None):
            """
            Find ATM straddle on trade_date.
            If forced_strike/expiry provided, look for that specific contract.
            Returns (call_mid, put_mid, strike, expiry, spot, iv_avg, exit_type).
            """
            subset = get_opts(trade_date)
            if subset.empty:
                return None

            spot = subset["spot"].iloc[0]

            if forced_strike is not None and forced_expiry is not None:
                # Exit: look for exact strike/expiry
                leg = subset[
                    (subset["strike_price"] == forced_strike) &
                    (subset["exdate"] == forced_expiry)
                ]
                if len(leg[leg["cp_flag"] == "C"]) > 0 and len(leg[leg["cp_flag"] == "P"]) > 0:
                    c = leg[leg["cp_flag"] == "C"]["mid"].values[0]
                    p = leg[leg["cp_flag"] == "P"]["mid"].values[0]
                    iv = leg["impl_volatility"].mean()
                    return c, p, forced_strike / 1000, forced_expiry, spot, iv, "market"
                else:
                    # Fall back to intrinsic value
                    intrinsic = abs(spot - forced_strike / 1000)
                    return intrinsic / 2, intrinsic / 2, forced_strike / 1000, forced_expiry, spot, np.nan, "intrinsic"

            # Entry: find nearest weekly expiry >= min_expiry, then ATM strike
            available_expiries = sorted(subset["exdate"].unique())
            if not available_expiries:
                return None
            target_expiry = available_expiries[0]

            exp_subset = subset[subset["exdate"] == target_expiry].copy()
            exp_subset["dist"] = (exp_subset["strike"] - spot).abs()
            atm_strike_idx = exp_subset.groupby("cp_flag")["dist"].idxmin()

            if "C" not in atm_strike_idx or "P" not in atm_strike_idx:
                return None

            call = exp_subset.loc[atm_strike_idx["C"]]
            put  = exp_subset.loc[atm_strike_idx["P"]]
            iv = (call["impl_volatility"] + put["impl_volatility"]) / 2
            return call["mid"], put["mid"], call["strike"], target_expiry, spot, iv, "market"

        # ── Strategy A: Pre-Meeting (enter T-1, exit T+1) ─────────────────────
        entry_T_minus1 = find_straddle(dates[-1])
        if entry_T_minus1 is not None:
            call_e, put_e, strike_e, expiry_e, spot_e, iv_e, _ = entry_T_minus1
            straddle_entry = call_e + put_e
            strike_raw = int(round(strike_e * 1000))

            exit_T1 = find_straddle(dates[1],
                                    forced_strike=strike_raw,
                                    forced_expiry=expiry_e)
            if exit_T1 is not None:
                c_x, p_x, _, _, spot_x, iv_x, exit_type = exit_T1
                straddle_exit = c_x + p_x
                pnl = (straddle_entry - straddle_exit) * 100

                records.append({
                    "fomc_date"       : fomc_date,
                    "strategy"        : "pre_meeting",
                    "exit_offset"     : 1,
                    "entry_date"      : dates[-1],
                    "exit_date"       : dates[1],
                    "expiry"          : expiry_e,
                    "strike"          : strike_e,
                    "spot_entry"      : spot_e,
                    "spot_exit"       : spot_x,
                    "straddle_entry"  : straddle_entry,
                    "straddle_exit"   : straddle_exit,
                    "iv_entry"        : iv_e,
                    "iv_exit"         : iv_x,
                    "pnl_per_contract": pnl,
                    "exit_type"       : exit_type,
                })
                print(f"  Pre  {fomc_date.date()} | entry ${straddle_entry:.2f} "
                      f"| exit ${straddle_exit:.2f} | P&L ${pnl:+.0f} | {exit_type}")
            else:
                print(f"  Pre  {fomc_date.date()} | WARNING: no exit data at T+1")
        else:
            print(f"  Pre  {fomc_date.date()} | WARNING: no entry data at T-1")

        # ── Strategy B: Post-Announcement (enter T+1, exit T+2/3/5/10) ────────
        entry_T1 = find_straddle(dates[1])
        if entry_T1 is not None:
            call_e, put_e, strike_e, expiry_e, spot_e, iv_e, _ = entry_T1
            straddle_entry = call_e + put_e
            strike_raw = int(round(strike_e * 1000))

            for exit_off in [2, 3, 5, 10]:
                if exit_off not in dates:
                    continue
                exit_d = dates[exit_off]
                exit_res = find_straddle(exit_d,
                                         forced_strike=strike_raw,
                                         forced_expiry=expiry_e)
                if exit_res is not None:
                    c_x, p_x, _, _, spot_x, iv_x, exit_type = exit_res
                    straddle_exit = c_x + p_x
                    pnl = (straddle_entry - straddle_exit) * 100

                    records.append({
                        "fomc_date"       : fomc_date,
                        "strategy"        : "post_announcement",
                        "exit_offset"     : exit_off,
                        "entry_date"      : dates[1],
                        "exit_date"       : exit_d,
                        "expiry"          : expiry_e,
                        "strike"          : strike_e,
                        "spot_entry"      : spot_e,
                        "spot_exit"       : spot_x,
                        "straddle_entry"  : straddle_entry,
                        "straddle_exit"   : straddle_exit,
                        "iv_entry"        : iv_e,
                        "iv_exit"         : iv_x,
                        "pnl_per_contract": pnl,
                        "exit_type"       : exit_type,
                    })

    results = pd.DataFrame(records)
    results.to_parquet(CACHE, index=False)
    print(f"\nSaved {len(results):,} records to {CACHE}")

# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\nTotal records: {len(results)}")
print("\nRecord count by strategy / exit_offset:")
print(results.groupby(["strategy", "exit_offset"]).size().to_string())
print("\nIntrinsic fallbacks:")
print(results["exit_type"].value_counts().to_string())
print(f"\nPre-meeting straddle entry price range: "
      f"${results[results['strategy']=='pre_meeting']['straddle_entry'].min():.2f} "
      f"to ${results[results['strategy']=='pre_meeting']['straddle_entry'].max():.2f}")
