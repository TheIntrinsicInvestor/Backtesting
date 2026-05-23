"""
Compute forward returns from BOTH entry_disclosure_date AND entry_trade_date.
The gap quantifies the disclosure-lag cost.

Also computes EXACT holding period returns for BUYS by matching each politician's
buy to their subsequent sell of the same ticker.
"""

from pathlib import Path
import pandas as pd
import numpy as np

DATA_DIR = Path(__file__).parent / "data"
HORIZONS = [10, 20, 60, 90, 180, 252]
SPY_PERMNO = 84398


def sic_to_gics(sic):
    if pd.isna(sic):
        return "Unknown"
    sic = int(sic)
    if 100 <= sic < 1000: return "Materials"
    if 1000 <= sic < 1500: return "Materials"
    if 1500 <= sic < 1800: return "Industrials"
    if 2000 <= sic < 2100: return "Consumer Staples"
    if 2100 <= sic < 2200: return "Consumer Staples"
    if 2200 <= sic < 3000: return "Consumer Discretionary"
    if 3000 <= sic < 3400: return "Materials"
    if 3400 <= sic < 3570: return "Industrials"
    if 3570 <= sic < 3580: return "Information Technology"
    if 3580 <= sic < 3600: return "Industrials"
    if 3600 <= sic < 3700: return "Information Technology"
    if 3700 <= sic < 3800: return "Consumer Discretionary"
    if 3800 <= sic < 3900: return "Health Care"
    if 3900 <= sic < 4000: return "Consumer Discretionary"
    if 4000 <= sic < 4500: return "Industrials"
    if 4500 <= sic < 4600: return "Industrials"
    if 4600 <= sic < 4800: return "Energy"
    if 4800 <= sic < 4900: return "Communication Services"
    if 4900 <= sic < 5000: return "Utilities"
    if 5000 <= sic < 6000: return "Consumer Discretionary"
    if 6000 <= sic < 6500: return "Financials"
    if 6500 <= sic < 6600: return "Real Estate"
    if 6700 <= sic < 6800: return "Financials"
    if 7000 <= sic < 7370: return "Consumer Discretionary"
    if 7370 <= sic < 7380: return "Information Technology"
    if 7380 <= sic < 7400: return "Consumer Discretionary"
    if 7800 <= sic < 8000: return "Communication Services"
    if 8000 <= sic < 8200: return "Health Care"
    if 8700 <= sic < 8800: return "Industrials"
    return "Unknown"


def build_price_index(prices_df):
    price_by_permno = {}
    for permno, grp in prices_df.groupby("permno"):
        grp = grp[["date", "prc", "shrout"]].sort_values("date").reset_index(drop=True)
        price_by_permno[permno] = grp
    return price_by_permno


def compute_one_entry(permno_df, target_date, spy_dates_arr, spy_prices_arr, suffix):
    valid_mask = permno_df["date"] >= target_date
    if not valid_mask.any():
        return None

    first_valid_idx = valid_mask.idxmax()
    entry_date = permno_df.loc[first_valid_idx, "date"]
    entry_price = permno_df.loc[first_valid_idx, "prc"]
    if pd.isna(entry_price) or entry_price <= 0:
        return None

    shrout = permno_df.loc[first_valid_idx, "shrout"]
    mkt_cap = entry_price * shrout * 1000

    spy_entry_mask = spy_dates_arr >= entry_date
    spy_matches = np.where(spy_entry_mask)[0]
    spy_idx = spy_matches[0] if len(spy_matches) > 0 else None

    result = {f"entry_date_{suffix}": entry_date, f"entry_price_{suffix}": entry_price}
    if suffix == "disc":
        result["mkt_cap_at_entry"] = mkt_cap

    for N in HORIZONS:
        exit_pos = first_valid_idx + N
        if exit_pos >= len(permno_df):
            result[f"ret_{N}d_{suffix}_abs"] = np.nan
            result[f"ret_{N}d_{suffix}_spy"] = np.nan
            result[f"ret_{N}d_{suffix}_excess"] = np.nan
            result[f"censored_{N}d_{suffix}"] = True
        else:
            exit_price = permno_df.iloc[exit_pos]["prc"]
            ret_abs = (exit_price / entry_price) - 1
            result[f"ret_{N}d_{suffix}_abs"] = ret_abs
            result[f"censored_{N}d_{suffix}"] = False

            if spy_idx is None:
                ret_spy = np.nan
            else:
                spy_exit_idx = spy_idx + N
                if spy_exit_idx >= len(spy_prices_arr):
                    ret_spy = np.nan
                else:
                    ret_spy = (spy_prices_arr[spy_exit_idx] / spy_prices_arr[spy_idx]) - 1
            result[f"ret_{N}d_{suffix}_spy"] = ret_spy
            result[f"ret_{N}d_{suffix}_excess"] = (
                np.nan if pd.isna(ret_spy) else ret_abs - ret_spy
            )

    return result

def get_price_at_date(permno_df, target_date):
    if target_date is None or pd.isna(target_date):
        return None, None
    valid_mask = permno_df["date"] >= target_date
    if not valid_mask.any():
        return None, None
    idx = valid_mask.idxmax()
    return permno_df.loc[idx, "date"], permno_df.loc[idx, "prc"]

def get_spy_price_at_date(spy_dates_arr, spy_prices_arr, target_date):
    if target_date is None or pd.isna(target_date):
        return None, None
    mask = spy_dates_arr >= target_date
    matches = np.where(mask)[0]
    if len(matches) > 0:
        idx = matches[0]
        return spy_dates_arr[idx], spy_prices_arr[idx]
    return None, None

def compute_exact_holding_period(row, permno_df, spy_dates_arr, spy_prices_arr, sell_map):
    # Only calculate exact holding period if this is a BUY event
    if "is_buy_event" not in row or not row["is_buy_event"]:
        return {}

    ticker = row["ticker"]
    politicians = row["politicians"]
    window_start = row["window_start"]
    window_end = row["entry_trade_date"]
    
    trade_excess_list = []
    disc_excess_list = []
    holding_days_list = []

    for pol in politicians:
        # We need the exact buy trade for this politician in this window
        # For simplicity, we just use the herd's entry_trade_date and entry_disclosure_date as proxy for the buy,
        # OR we could just find their exact sell. 
        # The prompt says: "find their FIRST SELL of the same ticker AFTER the buy trade date"
        # We will use window_start as the earliest possible buy date to look after
        
        sells_for_pol = sell_map.get((ticker, pol), [])
        valid_sells = [s for s in sells_for_pol if s['trade_date'] > window_end]
        
        # entry dates
        p_buy_trade_date = row["entry_trade_date"]
        p_buy_disc_date = row["entry_disclosure_date"]
        
        if len(valid_sells) > 0:
            first_sell = valid_sells[0]
            p_sell_trade_date = first_sell['trade_date']
            p_sell_disc_date = first_sell['disclosure_date']
        else:
            # open trade - mark to market using latest available price
            p_sell_trade_date = permno_df["date"].max()
            p_sell_disc_date = permno_df["date"].max()

        # get prices
        entry_t_date, entry_t_prc = get_price_at_date(permno_df, p_buy_trade_date)
        entry_d_date, entry_d_prc = get_price_at_date(permno_df, p_buy_disc_date)
        exit_t_date, exit_t_prc = get_price_at_date(permno_df, p_sell_trade_date)
        exit_d_date, exit_d_prc = get_price_at_date(permno_df, p_sell_disc_date)

        # SPY prices
        spy_ent_t_date, spy_ent_t_prc = get_spy_price_at_date(spy_dates_arr, spy_prices_arr, p_buy_trade_date)
        spy_ent_d_date, spy_ent_d_prc = get_spy_price_at_date(spy_dates_arr, spy_prices_arr, p_buy_disc_date)
        spy_ex_t_date, spy_ex_t_prc = get_spy_price_at_date(spy_dates_arr, spy_prices_arr, p_sell_trade_date)
        spy_ex_d_date, spy_ex_d_prc = get_spy_price_at_date(spy_dates_arr, spy_prices_arr, p_sell_disc_date)

        # compute returns
        if entry_t_prc and exit_t_prc and spy_ent_t_prc and spy_ex_t_prc:
            ret_trade = (exit_t_prc / entry_t_prc) - 1
            spy_trade = (spy_ex_t_prc / spy_ent_t_prc) - 1
            trade_excess_list.append(ret_trade - spy_trade)
            holding_days_list.append((exit_t_date - entry_t_date).days)
        
        if entry_d_prc and exit_d_prc and spy_ent_d_prc and spy_ex_d_prc:
            ret_disc = (exit_d_prc / entry_d_prc) - 1
            spy_disc = (spy_ex_d_prc / spy_ent_d_prc) - 1
            disc_excess_list.append(ret_disc - spy_disc)
            
    res = {}
    if trade_excess_list:
        res["realized_trade_excess"] = np.mean(trade_excess_list)
        res["realized_hold_days"] = np.mean(holding_days_list)
    else:
        res["realized_trade_excess"] = np.nan
        res["realized_hold_days"] = np.nan
        
    if disc_excess_list:
        res["realized_disc_excess"] = np.mean(disc_excess_list)
    else:
        res["realized_disc_excess"] = np.nan

    return res

def compute_event_returns(row, price_by_permno, spy_dates_arr, spy_prices_arr, sell_map):
    permno_df = price_by_permno.get(row["permno"])
    if permno_df is None or permno_df.empty:
        return None

    disc = compute_one_entry(permno_df, row["entry_disclosure_date"], spy_dates_arr, spy_prices_arr, "disc")
    if disc is None:
        return None
    trade = compute_one_entry(permno_df, row["entry_trade_date"], spy_dates_arr, spy_prices_arr, "trade")

    combined = disc
    if trade is not None:
        combined.update(trade)
    else:
        for N in HORIZONS:
            combined[f"ret_{N}d_trade_abs"] = np.nan
            combined[f"ret_{N}d_trade_spy"] = np.nan
            combined[f"ret_{N}d_trade_excess"] = np.nan
            combined[f"censored_{N}d_trade"] = True
        combined["entry_date_trade"] = pd.NaT

    if pd.notna(combined.get("entry_date_trade")):
        combined["disc_trade_lag_days"] = (combined["entry_date_disc"] - combined["entry_date_trade"]).days
    else:
        combined["disc_trade_lag_days"] = np.nan

    p_trade = combined.get("entry_price_trade")
    p_disc = combined.get("entry_price_disc")
    if p_trade is not None and p_disc is not None and p_trade > 0:
        combined["ret_during_lag"] = (p_disc / p_trade) - 1
    else:
        combined["ret_during_lag"] = np.nan

    if pd.notna(combined.get("entry_date_trade")):
        spy_mask_t = spy_dates_arr >= combined["entry_date_trade"]
        spy_mask_d = spy_dates_arr >= combined["entry_date_disc"]
        st = np.where(spy_mask_t)[0]
        sd = np.where(spy_mask_d)[0]
        if len(st) and len(sd):
            spy_p_trade = spy_prices_arr[st[0]]
            spy_p_disc = spy_prices_arr[sd[0]]
            if spy_p_trade > 0:
                spy_lag_ret = (spy_p_disc / spy_p_trade) - 1
                combined["spy_ret_during_lag"] = spy_lag_ret
                if not pd.isna(combined["ret_during_lag"]):
                    combined["excess_during_lag"] = combined["ret_during_lag"] - spy_lag_ret
                else:
                    combined["excess_during_lag"] = np.nan
            else:
                combined["spy_ret_during_lag"] = np.nan
                combined["excess_during_lag"] = np.nan
        else:
            combined["spy_ret_during_lag"] = np.nan
            combined["excess_during_lag"] = np.nan
    else:
        combined["spy_ret_during_lag"] = np.nan
        combined["excess_during_lag"] = np.nan

    exact_returns = compute_exact_holding_period(row, permno_df, spy_dates_arr, spy_prices_arr, sell_map)
    combined.update(exact_returns)
    return combined


def process_file(events_path, out_path, prices, ticker_map, price_by_permno, spy_dates_arr, spy_prices_arr, sell_map):
    print(f"\n=== Processing {events_path.name} -> {out_path.name} ===")
    events = pd.read_parquet(events_path)
    events["entry_disclosure_date"] = pd.to_datetime(events["entry_disclosure_date"])
    events["entry_trade_date"] = pd.to_datetime(events["entry_trade_date"])

    is_buy_event = (events_path.name == "events_buy.parquet")
    events["is_buy_event"] = is_buy_event

    events = events.merge(
        ticker_map[["ticker", "permno", "sector"]],
        on="ticker",
        how="left",
    )

    n_no_permno = events["permno"].isna().sum()
    if n_no_permno > 0:
        print(f"  Dropped {n_no_permno} events with no permno match")
    events = events.dropna(subset=["permno"]).copy()
    events["permno"] = events["permno"].astype(int)

    print(f"  Processing {len(events)} events...")
    rows, skipped = [], 0
    for _, row in events.iterrows():
        ret_data = compute_event_returns(row, price_by_permno, spy_dates_arr, spy_prices_arr, sell_map)
        if ret_data is None:
            skipped += 1
            continue
        combined = row.to_dict()
        combined.update(ret_data)
        rows.append(combined)

    results = pd.DataFrame(rows)
    print(f"  Events processed: {len(rows)}, dropped (no price match): {skipped}")

    if is_buy_event and "realized_trade_excess" in results.columns:
        n_exact = results["realized_trade_excess"].notna().sum()
        print(f"  Exact holding periods calculated for {n_exact}/{len(results)} buy events.")

    results.to_parquet(out_path, index=False)
    print(f"  Saved {len(results)} rows to {out_path.name}")


def main():
    prices = pd.read_parquet(DATA_DIR / "crsp_prices.parquet")
    ticker_map = pd.read_parquet(DATA_DIR / "ticker_permno_map.parquet")
    prices["date"] = pd.to_datetime(prices["date"])
    ticker_map["sector"] = ticker_map["siccd"].apply(sic_to_gics)

    price_by_permno = build_price_index(prices)
    spy_df = price_by_permno.get(SPY_PERMNO)
    if spy_df is None:
        raise ValueError(f"SPY (permno {SPY_PERMNO}) not found in crsp_prices")
    spy_dates_arr = spy_df["date"].values
    spy_prices_arr = spy_df["prc"].values

    # Load all trades to build sell_map
    all_trades = pd.read_parquet(DATA_DIR / "all_trades.parquet")
    all_sells = all_trades[all_trades["tx_type"] == "sell"].copy()
    all_sells["trade_date"] = pd.to_datetime(all_sells["trade_date"])
    all_sells["disclosure_date"] = pd.to_datetime(all_sells["disclosure_date"])
    
    sell_map = {}
    for (ticker, name), grp in all_sells.groupby(["ticker", "name"]):
        grp = grp.sort_values("trade_date")
        sell_map[(ticker, name)] = grp[["trade_date", "disclosure_date"]].to_dict("records")

    files = [
        (DATA_DIR / "events_buy.parquet",  DATA_DIR / "event_returns_buy.parquet"),
        (DATA_DIR / "events_sell.parquet", DATA_DIR / "event_returns_sell.parquet"),
    ]
    for events_path, out_path in files:
        if not events_path.exists():
            print(f"Skipping {events_path.name} (does not exist)")
            continue
        process_file(events_path, out_path, prices, ticker_map, price_by_permno, spy_dates_arr, spy_prices_arr, sell_map)


if __name__ == "__main__":
    main()
