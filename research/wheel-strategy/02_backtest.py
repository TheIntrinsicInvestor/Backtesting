"""
02_backtest.py
--------------
Run the Wheel Strategy backtest across all 20 parameter combinations.

Parameters swept:
  Delta targets : 10, 20, 30, 40, 50 (signed delta, i.e. 0.10, 0.20, ...)
  DTE windows   : 15, 30, 45, 60 days

Strategy logic:
  Phase 1 (Short Cash-Secured Put):
    - Sell put at target delta and DTE
    - Close at 50% profit target OR expiration
    - If expires ITM: assignment -> enter Phase 2
    - If expires OTM: keep premium -> back to Phase 1

  Phase 2 (Covered Call):
    - Hold 100 shares at cost basis (put strike)
    - Sell call at same target delta and DTE
    - Close at 50% profit target OR expiration
    - If expires OTM: keep premium -> sell new call (stay Phase 2)
    - If expires ITM: shares called away -> back to Phase 1

Starting capital: $50,000
Execution: bid-ask midpoint, no commissions, no slippage.
Minimum option mid-price: $0.05

Output: data/backtest_results.parquet  (one row per combo)
        data/equity_curves.parquet     (daily equity per combo)
        data/trade_log.parquet         (every individual trade)
"""

import pandas as pd
import numpy as np
import os
from itertools import product

DATA_DIR       = "data"
STARTING_CAP   = 50_000.0
PROFIT_TARGET  = 0.50        # 50% of premium received
MIN_MID        = 0.05        # filter illiquid deep OTM

DELTAS = [0.10, 0.20, 0.30, 0.40, 0.50]
DTES   = [15, 30, 45, 60]
DTE_TOLERANCE = 10  # search within ±10 days of target DTE

# ── Load data ─────────────────────────────────────────────────────────────────
print("Loading option data...")
opts   = pd.read_parquet(os.path.join(DATA_DIR, "spy_options.parquet"))
prices = pd.read_parquet(os.path.join(DATA_DIR, "spy_prices.parquet"))
prices = prices.set_index("date")["spy_close"]

# Pre-index options by date for fast lookup
opts_by_date = {d: grp for d, grp in opts.groupby("date")}
all_dates = sorted(prices.index)

print(f"Loaded {len(opts):,} option records across {len(all_dates)} trading days")


# ── Option selection helper ───────────────────────────────────────────────────
def find_option(date, cp_flag, target_delta, target_dte):
    """Return the best matching option row for given parameters."""
    if date not in opts_by_date:
        return None
    pool = opts_by_date[date]
    pool = pool[
        (pool["cp_flag"] == cp_flag) &
        (pool["dte"].between(target_dte - DTE_TOLERANCE, target_dte + DTE_TOLERANCE)) &
        (pool["mid"] >= MIN_MID)
    ]
    if pool.empty:
        return None
    # Select row with delta closest to target
    pool = pool.copy()
    pool["delta_dist"] = (pool["delta"].abs() - target_delta).abs()
    return pool.loc[pool["delta_dist"].idxmin()]


# ── Single backtest run ───────────────────────────────────────────────────────
def run_backtest(target_delta, target_dte):
    capital        = STARTING_CAP
    phase          = 1          # 1 = short put, 2 = covered call
    shares         = 0          # shares held in Phase 2
    cost_basis     = 0.0        # strike at which we were assigned
    open_trade     = None       # current open option position dict
    trades         = []
    equity_curve   = []

    for date in all_dates:
        spot = prices.get(date)
        if spot is None:
            continue

        # Mark-to-market current position
        mtm = capital
        if open_trade is not None:
            current_opt = None
            if date in opts_by_date:
                pool = opts_by_date[date]
                match = pool[
                    (pool["cp_flag"]      == open_trade["cp_flag"]) &
                    (pool["exdate"]       == open_trade["exdate"]) &
                    (pool["strike_price"] == open_trade["strike_price"])
                ]
                if not match.empty:
                    current_opt = match.iloc[0]

            if current_opt is not None:
                current_mid = current_opt["mid"]
            else:
                # Use intrinsic value as proxy
                if open_trade["cp_flag"] == "P":
                    current_mid = max(0, open_trade["strike"] - spot)
                else:
                    current_mid = max(0, spot - open_trade["strike"])

            unrealised = (open_trade["premium"] - current_mid) * 100
            if phase == 2:
                unrealised += (spot - cost_basis) * 100  # mark shares
            mtm += unrealised

        equity_curve.append({"date": date, "equity": mtm, "phase": phase})

        if open_trade is None:
            # Open new position
            cp = "P" if phase == 1 else "C"
            opt = find_option(date, cp, target_delta, target_dte)
            if opt is None:
                continue

            open_trade = {
                "entry_date"   : date,
                "cp_flag"      : cp,
                "exdate"       : opt["exdate"],
                "strike_price" : opt["strike_price"],
                "strike"       : opt["strike"],
                "premium"      : opt["mid"],
                "target_mid"   : opt["mid"] * (1 - PROFIT_TARGET),
            }
            capital += opt["mid"] * 100  # collect premium
            continue

        # Check 50% profit target
        current_opt = None
        if date in opts_by_date:
            pool = opts_by_date[date]
            match = pool[
                (pool["cp_flag"]      == open_trade["cp_flag"]) &
                (pool["exdate"]       == open_trade["exdate"]) &
                (pool["strike_price"] == open_trade["strike_price"])
            ]
            if not match.empty:
                current_opt = match.iloc[0]

        if current_opt is not None and current_opt["mid"] <= open_trade["target_mid"]:
            # Close at profit target
            pnl = (open_trade["premium"] - current_opt["mid"]) * 100
            capital += pnl - open_trade["premium"] * 100  # net: premium already collected
            trades.append({
                "entry_date" : open_trade["entry_date"],
                "exit_date"  : date,
                "cp_flag"    : open_trade["cp_flag"],
                "strike"     : open_trade["strike"],
                "premium"    : open_trade["premium"],
                "exit_mid"   : current_opt["mid"],
                "pnl"        : pnl,
                "exit_reason": "profit_target",
                "phase"      : phase,
            })
            open_trade = None
            # Stay in same phase, open new position next day
            continue

        # Check expiration
        if date >= open_trade["exdate"]:
            itm = (open_trade["cp_flag"] == "P" and spot < open_trade["strike"]) or \
                  (open_trade["cp_flag"] == "C" and spot > open_trade["strike"])

            if not itm:
                # Expires worthless
                pnl = open_trade["premium"] * 100
                capital += 0  # premium already collected; option expires worthless
                trades.append({
                    "entry_date" : open_trade["entry_date"],
                    "exit_date"  : date,
                    "cp_flag"    : open_trade["cp_flag"],
                    "strike"     : open_trade["strike"],
                    "premium"    : open_trade["premium"],
                    "exit_mid"   : 0,
                    "pnl"        : pnl,
                    "exit_reason": "expired_otm",
                    "phase"      : phase,
                })
                open_trade = None

            else:
                # ITM: assignment / call-away
                if open_trade["cp_flag"] == "P":
                    # Assigned: buy 100 shares at strike
                    cost = open_trade["strike"] * 100
                    capital -= cost
                    shares     = 100
                    cost_basis = open_trade["strike"]
                    phase = 2
                    pnl = (open_trade["premium"] * 100) - max(0, open_trade["strike"] - spot) * 100
                    trades.append({
                        "entry_date" : open_trade["entry_date"],
                        "exit_date"  : date,
                        "cp_flag"    : open_trade["cp_flag"],
                        "strike"     : open_trade["strike"],
                        "premium"    : open_trade["premium"],
                        "exit_mid"   : max(0, open_trade["strike"] - spot),
                        "pnl"        : pnl,
                        "exit_reason": "assigned",
                        "phase"      : 1,
                    })
                else:
                    # Shares called away
                    proceeds = open_trade["strike"] * 100
                    capital  += proceeds - cost_basis * 100  # realise stock P&L
                    capital  += open_trade["premium"] * 100  # call premium already collected
                    shares    = 0
                    phase     = 1
                    pnl = (open_trade["strike"] - cost_basis + open_trade["premium"]) * 100
                    trades.append({
                        "entry_date" : open_trade["entry_date"],
                        "exit_date"  : date,
                        "cp_flag"    : open_trade["cp_flag"],
                        "strike"     : open_trade["strike"],
                        "premium"    : open_trade["premium"],
                        "exit_mid"   : max(0, spot - open_trade["strike"]),
                        "pnl"        : pnl,
                        "exit_reason": "called_away",
                        "phase"      : 2,
                    })
                open_trade = None

    # Final equity includes any remaining position value
    if phase == 2 and shares > 0:
        final_spot = prices.iloc[-1]
        capital += shares * final_spot - cost_basis * shares

    return {
        "trades"      : pd.DataFrame(trades),
        "equity_curve": pd.DataFrame(equity_curve),
        "final_equity": capital,
    }


# ── Run all 20 combinations ───────────────────────────────────────────────────
all_results = []
all_equity  = []
all_trades  = []

combos = list(product(DELTAS, DTES))
print(f"\nRunning {len(combos)} parameter combinations...")

for delta, dte in combos:
    label = f"{int(delta*100)}d_{dte}dte"
    print(f"  Running {label}...", end=" ")

    result = run_backtest(delta, dte)
    trades_df = result["trades"]
    equity_df = result["equity_curve"]

    # Metrics
    n_trades     = len(trades_df)
    total_pnl    = result["final_equity"] - STARTING_CAP
    total_ret    = total_pnl / STARTING_CAP
    n_years      = len(all_dates) / 252
    ann_ret      = (1 + total_ret) ** (1 / n_years) - 1
    daily_rets   = equity_df["equity"].pct_change().dropna()
    sharpe       = daily_rets.mean() / daily_rets.std() * np.sqrt(252) if daily_rets.std() > 0 else 0
    cum          = equity_df["equity"] / STARTING_CAP
    drawdowns    = cum / cum.cummax() - 1
    max_dd       = drawdowns.min()
    win_rate     = (trades_df["pnl"] > 0).mean() if n_trades > 0 else 0
    calmar       = ann_ret / abs(max_dd) if max_dd != 0 else 0

    all_results.append({
        "delta"       : int(delta * 100),
        "dte"         : dte,
        "label"       : label,
        "n_trades"    : n_trades,
        "total_pnl"   : round(total_pnl, 2),
        "total_ret_pct": round(total_ret * 100, 1),
        "ann_ret_pct" : round(ann_ret * 100, 2),
        "sharpe"      : round(sharpe, 2),
        "max_dd_pct"  : round(max_dd * 100, 1),
        "win_rate_pct": round(win_rate * 100, 0),
        "calmar"      : round(calmar, 2),
    })

    equity_df["combo"] = label
    all_equity.append(equity_df)

    trades_df["combo"] = label
    all_trades.append(trades_df)

    print(f"total return {total_ret*100:.1f}%  sharpe {sharpe:.2f}  max dd {max_dd*100:.1f}%")

# ── Save ──────────────────────────────────────────────────────────────────────
results_df = pd.DataFrame(all_results).sort_values("total_ret_pct", ascending=False)
equity_df  = pd.concat(all_equity,  ignore_index=True)
trades_df  = pd.concat(all_trades,  ignore_index=True)

results_df.to_parquet(os.path.join(DATA_DIR, "backtest_results.parquet"), index=False)
equity_df.to_parquet( os.path.join(DATA_DIR, "equity_curves.parquet"),    index=False)
trades_df.to_parquet( os.path.join(DATA_DIR, "trade_log.parquet"),         index=False)

print(f"\n{'='*60}")
print("RESULTS RANKED BY TOTAL RETURN")
print(results_df[["label","total_ret_pct","ann_ret_pct","sharpe","max_dd_pct","win_rate_pct"]].to_string(index=False))
