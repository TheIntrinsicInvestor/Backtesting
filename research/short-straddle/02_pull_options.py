"""
02_pull_options.py
------------------
For each earnings event, pull the ATM straddle price from OptionMetrics IvyDB.

Entry: ATM straddle at the nearest weekly expiry covering the earnings date,
       priced ~15-30 min before market close on the announcement day.
       We use the end-of-day mid-price on the announcement date as a proxy.

Exit:  Mid-price at end of the following trading day (after IV crush).

Data pulled from optionm.opprcd{year} (daily option price tables).
Underlying prices from optionm.secprd{year}.

Output: data/straddle_prices.parquet
"""

import wrds
import pandas as pd
import numpy as np
import os
from datetime import timedelta

DATA_DIR = "data"

# ── Load earnings dates ───────────────────────────────────────────────────────
earnings = pd.read_parquet(os.path.join(DATA_DIR, "earnings_dates.parquet"))

# ── WRDS secid map for Mag 7 ──────────────────────────────────────────────────
# OptionMetrics uses numeric secids, not tickers.
# These are the stable OptionMetrics secids for each stock.
SECID_MAP = {
    "AAPL" : 101594,
    "MSFT" : 102357,
    "NVDA" : 105054,
    "AMZN" : 101231,
    "GOOGL": 108105,
    "META" : 121015,
    "TSLA" : 116380,
}

earnings["secid"] = earnings["ticker"].map(SECID_MAP)

# ── Connect to WRDS ───────────────────────────────────────────────────────────
print("Connecting to WRDS...")
db = wrds.Connection()

records = []

for _, row in earnings.iterrows():
    ticker    = row["ticker"]
    secid     = row["secid"]
    ann_date  = pd.Timestamp(row["ann_date"])
    exit_date = ann_date + timedelta(days=1)
    year      = ann_date.year

    # Pull options for ann_date and exit_date from that year's price table
    dates_str = f"'{ann_date.date()}', '{exit_date.date()}'"

    query = f"""
        SELECT o.date, o.exdate, o.cp_flag, o.strike_price, o.best_bid,
               o.best_offer, o.impl_volatility, o.delta, u.close AS spot
        FROM optionm.opprcd{year} o
        JOIN optionm.secprd{year} u
          ON o.secid = u.secid AND o.date = u.date
        WHERE o.secid = {secid}
          AND o.date IN ({dates_str})
          AND o.ss_flag = 0
          AND o.best_bid > 0
          AND o.best_offer > 0
          AND o.exdate > o.date
        ORDER BY o.date, o.exdate, o.cp_flag, o.strike_price
    """

    try:
        opts = db.raw_sql(query, date_cols=["date", "exdate"])
    except Exception as e:
        print(f"  ERROR pulling {ticker} {ann_date.date()}: {e}")
        continue

    if opts.empty:
        print(f"  WARNING: No options found for {ticker} on {ann_date.date()}")
        continue

    opts["mid"] = (opts["best_bid"] + opts["best_offer"]) / 2

    # Find nearest weekly expiry >= ann_date + 1 (must cover earnings)
    min_expiry = ann_date + timedelta(days=1)
    future_expiries = opts[opts["exdate"] >= min_expiry]["exdate"].unique()
    if len(future_expiries) == 0:
        print(f"  WARNING: No valid expiry for {ticker} {ann_date.date()}")
        continue
    target_expiry = sorted(future_expiries)[0]  # nearest expiry

    # Get spot price on ann_date
    spot_entry = opts[(opts["date"] == ann_date)]["spot"].iloc[0]

    # Select ATM call and put: strike closest to spot at target expiry on ann_date
    entry_opts = opts[
        (opts["date"]   == ann_date) &
        (opts["exdate"] == target_expiry)
    ].copy()

    entry_opts["strike_dist"] = (entry_opts["strike_price"] / 1000 - spot_entry).abs()
    atm_strike = entry_opts.groupby("cp_flag")["strike_dist"].idxmin()

    if "C" not in atm_strike.index or "P" not in atm_strike.index:
        print(f"  WARNING: Missing call or put for {ticker} {ann_date.date()}")
        continue

    call_entry = entry_opts.loc[atm_strike["C"]]
    put_entry  = entry_opts.loc[atm_strike["P"]]

    straddle_entry = call_entry["mid"] + put_entry["mid"]
    strike_used    = call_entry["strike_price"] / 1000
    iv_entry       = (call_entry["impl_volatility"] + put_entry["impl_volatility"]) / 2

    # Exit: same strike and expiry on exit_date
    exit_opts = opts[
        (opts["date"]          == exit_date) &
        (opts["exdate"]        == target_expiry) &
        (opts["strike_price"]  == call_entry["strike_price"])
    ].copy()

    if len(exit_opts) < 2:
        # Fall back to intrinsic value if exit price not available
        spot_exit = opts[opts["date"] == exit_date]["spot"].iloc[0] if not opts[opts["date"] == exit_date].empty else spot_entry
        intrinsic = abs(spot_exit - strike_used)
        straddle_exit = intrinsic
        exit_type = "intrinsic"
    else:
        call_exit = exit_opts[exit_opts["cp_flag"] == "C"]["mid"].values[0]
        put_exit  = exit_opts[exit_opts["cp_flag"] == "P"]["mid"].values[0]
        straddle_exit = call_exit + put_exit
        spot_exit = exit_opts["spot"].iloc[0]
        exit_type = "market"

    # Realised move
    realised_move_pct = abs(spot_exit - spot_entry) / spot_entry * 100
    implied_move_pct  = straddle_entry / spot_entry * 100

    records.append({
        "ticker"           : ticker,
        "ann_date"         : ann_date,
        "exit_date"        : exit_date,
        "expiry"           : target_expiry,
        "strike"           : strike_used,
        "spot_entry"       : spot_entry,
        "spot_exit"        : spot_exit,
        "straddle_entry"   : straddle_entry,
        "straddle_exit"    : straddle_exit,
        "iv_entry"         : iv_entry,
        "implied_move_pct" : implied_move_pct,
        "realised_move_pct": realised_move_pct,
        "pnl_per_contract" : (straddle_entry - straddle_exit) * 100,  # 1 contract = 100 shares
        "exit_type"        : exit_type,
    })

    print(f"  {ticker} {ann_date.date()} | entry ${straddle_entry:.2f} | "
          f"implied {implied_move_pct:.1f}% | realised {realised_move_pct:.1f}% | "
          f"P&L ${(straddle_entry - straddle_exit)*100:.0f}")

db.close()

# ── Save ──────────────────────────────────────────────────────────────────────
results = pd.DataFrame(records)
print(f"\nTotal events processed: {len(results)}")
results.to_parquet(os.path.join(DATA_DIR, "straddle_prices.parquet"), index=False)
print(f"Saved to {DATA_DIR}/straddle_prices.parquet")
