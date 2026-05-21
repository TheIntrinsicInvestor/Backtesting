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


def compute_event_returns(row, price_by_permno, spy_dates_arr, spy_prices_arr):
    permno = row["permno"]
    permno_df = price_by_permno.get(permno)
    if permno_df is None or permno_df.empty:
        return None

    entry_disclosure = row["entry_disclosure_date"]
    valid_mask = permno_df["date"] >= entry_disclosure
    if not valid_mask.any():
        return None

    first_valid_idx = valid_mask.idxmax()
    entry_date = permno_df.loc[first_valid_idx, "date"]
    entry_price = permno_df.loc[first_valid_idx, "prc"]

    if pd.isna(entry_price) or entry_price <= 0:
        return None

    shrout = permno_df.loc[first_valid_idx, "shrout"]
    mkt_cap_at_entry = entry_price * shrout * 1000

    permno_dates = permno_df["date"].values
    entry_pos = first_valid_idx

    spy_entry_mask = spy_dates_arr >= entry_date
    spy_matches = np.where(spy_entry_mask)[0]
    if len(spy_matches) == 0:
        spy_idx = None
    else:
        spy_idx = spy_matches[0]

    result = {
        "entry_date": entry_date,
        "mkt_cap_at_entry": mkt_cap_at_entry,
    }

    for N in HORIZONS:
        exit_pos = entry_pos + N
        if exit_pos >= len(permno_df):
            result[f"ret_{N}d_abs"] = np.nan
            result[f"ret_{N}d_spy"] = np.nan
            result[f"ret_{N}d_excess"] = np.nan
            result[f"censored_{N}d"] = True
        else:
            exit_price = permno_df.iloc[exit_pos]["prc"]
            ret_abs = (exit_price / entry_price) - 1
            result[f"ret_{N}d_abs"] = ret_abs
            result[f"censored_{N}d"] = False

            if spy_idx is None:
                ret_spy = np.nan
            else:
                spy_exit_idx = spy_idx + N
                if spy_exit_idx >= len(spy_prices_arr):
                    ret_spy = np.nan
                else:
                    ret_spy = (spy_prices_arr[spy_exit_idx] / spy_prices_arr[spy_idx]) - 1
            result[f"ret_{N}d_spy"] = ret_spy

            if pd.isna(ret_spy):
                result[f"ret_{N}d_excess"] = np.nan
            else:
                result[f"ret_{N}d_excess"] = ret_abs - ret_spy

    return result


def main():
    out_path = DATA_DIR / "event_returns.parquet"
    if out_path.exists():
        print("Cache exists — skipping")
        return

    events = pd.read_parquet(DATA_DIR / "events_buy.parquet")
    prices = pd.read_parquet(DATA_DIR / "crsp_prices.parquet")
    ticker_map = pd.read_parquet(DATA_DIR / "ticker_permno_map.parquet")

    events["entry_disclosure_date"] = pd.to_datetime(events["entry_disclosure_date"])
    prices["date"] = pd.to_datetime(prices["date"])

    ticker_map["sector"] = ticker_map["siccd"].apply(sic_to_gics)

    events = events.merge(
        ticker_map[["ticker", "permno", "sector"]],
        on="ticker",
        how="left",
    )

    n_no_permno = events["permno"].isna().sum()
    if n_no_permno > 0:
        print(f"Dropped {n_no_permno} events with no permno match")
    events = events.dropna(subset=["permno"]).copy()
    events["permno"] = events["permno"].astype(int)

    price_by_permno = build_price_index(prices)

    spy_df = price_by_permno.get(SPY_PERMNO)
    if spy_df is None:
        raise ValueError(f"SPY (permno {SPY_PERMNO}) not found in crsp_prices")
    spy_dates_arr = spy_df["date"].values
    spy_prices_arr = spy_df["prc"].values

    print(f"Processing {len(events)} events...")

    rows = []
    skipped = 0
    for _, row in events.iterrows():
        ret_data = compute_event_returns(row, price_by_permno, spy_dates_arr, spy_prices_arr)
        if ret_data is None:
            skipped += 1
            continue
        combined = row.to_dict()
        combined.update(ret_data)
        rows.append(combined)

    print(f"Events processed: {len(rows)}, dropped (no price match): {skipped}")

    results = pd.DataFrame(rows)

    total = len(results)
    n_not_censored_60 = results["censored_60d"].eq(False).sum()
    pct_60 = 100 * n_not_censored_60 / total if total > 0 else 0
    print(f"Coverage at 60d (not censored): {n_not_censored_60}/{total} ({pct_60:.1f}%)")

    primary = results[(results["threshold"] == 3) & (results["window_days"] == 30)]
    if len(primary) > 0:
        mean_excess = primary["ret_60d_excess"].mean()
        print(f"Primary combo (threshold=3, window=30): n={len(primary)}, mean 60d excess return = {mean_excess:.4f}")
    else:
        print("Primary combo (threshold=3, window=30): no events found")

    results.to_parquet(out_path, index=False)
    print(f"Saved {len(results)} rows to {out_path}")


if __name__ == "__main__":
    main()
