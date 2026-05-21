"""
Compute forward returns from BOTH entry_disclosure_date AND entry_trade_date.
The gap quantifies the disclosure-lag cost: politicians' own alpha (trade-date entry)
versus disclosure-follower alpha (disclosure-date entry).

Processes events_buy.parquet AND events_sell.parquet if both exist.
Outputs event_returns_buy.parquet and event_returns_sell.parquet.

Columns added per horizon N in [10, 20, 60, 90, 180, 252]:
  ret_{N}d_disc_abs / _spy / _excess / censored_{N}d_disc   (entry on disclosure_date)
  ret_{N}d_trade_abs / _spy / _excess / censored_{N}d_trade (entry on trade_date)
Plus: entry_date_disc, entry_date_trade, mkt_cap_at_entry (disc-date entry).
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
    """Compute returns for one entry-date choice (disc or trade)."""
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


def compute_event_returns(row, price_by_permno, spy_dates_arr, spy_prices_arr):
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
        # Tag trade fields as NaN for downstream code
        for N in HORIZONS:
            combined[f"ret_{N}d_trade_abs"] = np.nan
            combined[f"ret_{N}d_trade_spy"] = np.nan
            combined[f"ret_{N}d_trade_excess"] = np.nan
            combined[f"censored_{N}d_trade"] = True
        combined["entry_date_trade"] = pd.NaT

    # Disclosure lag in calendar days
    if pd.notna(combined.get("entry_date_trade")):
        combined["disc_trade_lag_days"] = (combined["entry_date_disc"] - combined["entry_date_trade"]).days
    else:
        combined["disc_trade_lag_days"] = np.nan

    # Return DURING the lag period -- what the follower misses
    p_trade = combined.get("entry_price_trade")
    p_disc = combined.get("entry_price_disc")
    if p_trade is not None and p_disc is not None and p_trade > 0:
        combined["ret_during_lag"] = (p_disc / p_trade) - 1
    else:
        combined["ret_during_lag"] = np.nan

    # SPY return during the same lag window (for excess-during-lag)
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
    return combined


def process_file(events_path, out_path, prices, ticker_map, price_by_permno, spy_dates_arr, spy_prices_arr):
    print(f"\n=== Processing {events_path.name} -> {out_path.name} ===")
    events = pd.read_parquet(events_path)
    events["entry_disclosure_date"] = pd.to_datetime(events["entry_disclosure_date"])
    events["entry_trade_date"] = pd.to_datetime(events["entry_trade_date"])

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
        ret_data = compute_event_returns(row, price_by_permno, spy_dates_arr, spy_prices_arr)
        if ret_data is None:
            skipped += 1
            continue
        combined = row.to_dict()
        combined.update(ret_data)
        rows.append(combined)

    results = pd.DataFrame(rows)
    print(f"  Events processed: {len(rows)}, dropped (no price match): {skipped}")

    n_not_censored_60_disc = results["censored_60d_disc"].eq(False).sum()
    pct_60 = 100 * n_not_censored_60_disc / len(results) if len(results) > 0 else 0
    print(f"  Coverage at 60d disc (not censored): {n_not_censored_60_disc}/{len(results)} ({pct_60:.1f}%)")

    primary = results[(results["threshold"] == 3) & (results["window_days"] == 30)]
    if len(primary) > 0:
        m_disc = primary["ret_60d_disc_excess"].mean()
        m_trade = primary["ret_60d_trade_excess"].mean()
        print(f"  Primary (3+,30d) mean 60d excess: disc={m_disc:+.4f}  trade={m_trade:+.4f}  gap={m_trade - m_disc:+.4f}")

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

    files = [
        (DATA_DIR / "events_buy.parquet",  DATA_DIR / "event_returns_buy.parquet"),
        (DATA_DIR / "events_sell.parquet", DATA_DIR / "event_returns_sell.parquet"),
    ]
    for events_path, out_path in files:
        if not events_path.exists():
            print(f"Skipping {events_path.name} (does not exist)")
            continue
        process_file(events_path, out_path, prices, ticker_map, price_by_permno, spy_dates_arr, spy_prices_arr)


if __name__ == "__main__":
    main()
