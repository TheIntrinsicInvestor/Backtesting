"""
05_event_study.py
-----------------
Event study engine. For each event:
  1. Maps T0 to nearest trading day (next if weekend/holiday)
  2. Extracts IV window T-20 to T+30 trading days
  3. Applies hybrid event filter: keep event if any instrument moved ≥1.5%
     on T0 or T+1 (confirms market reacted)
  4. Normalises IV to 100 at T-20 for cross-event comparability

Special handling:
  - Event 1 (2003-03-20): USO unavailable by design (launched April 2006).
    XLE/XOM/CVX analysed; USO marked as N/A, not excluded.
  - Event 15 (2026-02-28): Zero IV data in OptionMetrics (WRDS cutoff
    2025-08-29). Marked as DATA_UNAVAILABLE — excluded from IV analysis
    but noted in report as an ongoing, incomplete observation.
  - One null USO IV row (identified in 03_iv_pull.py) is dropped.

Outputs:
  data/event_iv_profiles.parquet  — normalised IV by event/ticker/t_day
  data/event_metadata.parquet     — per-event status, filter results
"""

import os
import numpy as np
import pandas as pd
from events import EVENTS

os.makedirs("data", exist_ok=True)

# ── Load cached data ──────────────────────────────────────────────────────────
iv = pd.read_parquet("data/iv_raw.parquet")
prices = pd.read_parquet("data/prices_raw.parquet")

iv["date"] = pd.to_datetime(iv["date"])
prices["date"] = pd.to_datetime(prices["date"])

# Drop the one null USO IV row
iv = iv.dropna(subset=["impl_volatility"]).reset_index(drop=True)

# ── Build trading day calendar from XLE prices (most complete series) ─────────
trading_days = sorted(prices.loc[prices["ticker"] == "XLE", "date"].tolist())
td_index = {d: i for i, d in enumerate(trading_days)}

def nearest_trading_day(dt):
    """Return dt if it is a trading day, else the next trading day."""
    dt = pd.Timestamp(dt)
    for offset in range(10):
        candidate = dt + pd.Timedelta(days=offset)
        if candidate in td_index:
            return candidate
    return None

# ── Price lookup helpers ──────────────────────────────────────────────────────
price_pivot = prices.pivot(index="date", columns="ticker", values="return")

def get_return(ticker, date):
    try:
        val = price_pivot.loc[date, ticker]
        return float(val) if pd.notna(val) else None
    except KeyError:
        return None

# ── IV lookup helpers ─────────────────────────────────────────────────────────
iv_pivot = iv.pivot_table(index="date", columns="ticker", values="impl_volatility")

def get_iv(ticker, date):
    try:
        val = iv_pivot.loc[date, ticker]
        return float(val) if pd.notna(val) else None
    except KeyError:
        return None

# ── Main event study loop ─────────────────────────────────────────────────────
all_profiles = []
metadata_rows = []

for event in EVENTS:
    eid   = event["id"]
    label = event["label"]
    cluster = event["cluster"]
    instruments = event["instruments"]
    raw_date = pd.Timestamp(event["date"])

    meta = {
        "event_id":   eid,
        "label":      label,
        "cluster":    cluster,
        "raw_date":   raw_date,
        "t0_date":    None,
        "status":     "OK",
        "filter_pass": None,
        "filter_details": "",
        "notes":      "",
    }

    # ── Check for no-data events ──────────────────────────────────────────
    # Event 15: WRDS IV data ends 2025-08-29
    if raw_date > pd.Timestamp("2025-08-29"):
        meta["status"] = "DATA_UNAVAILABLE"
        meta["notes"] = (
            "WRDS OptionMetrics data ends 2025-08-29. "
            "This event (2026-02-28) has no IV data. "
            "Excluded from IV analysis; flagged as incomplete observation."
        )
        metadata_rows.append(meta)
        print(f"Event {eid:2d} [{label}]: DATA_UNAVAILABLE (no IV after 2025-08-29)")
        continue

    # ── Map event date to trading day ─────────────────────────────────────
    t0 = nearest_trading_day(raw_date)
    if t0 is None:
        meta["status"] = "NO_TRADING_DAY"
        meta["notes"] = f"Could not find a trading day near {raw_date.date()}"
        metadata_rows.append(meta)
        print(f"Event {eid:2d} [{label}]: NO_TRADING_DAY")
        continue

    meta["t0_date"] = t0
    if t0 != raw_date:
        meta["notes"] += f"T0 shifted from {raw_date.date()} to {t0.date()} (non-trading day). "

    t0_idx = td_index[t0]

    # ── Check window bounds ───────────────────────────────────────────────
    if t0_idx < 20:
        meta["status"] = "INSUFFICIENT_PRE_WINDOW"
        meta["notes"] += "Fewer than 20 trading days before T0 in price data."
        metadata_rows.append(meta)
        print(f"Event {eid:2d} [{label}]: INSUFFICIENT_PRE_WINDOW")
        continue

    t_minus_20 = trading_days[t0_idx - 20]
    t_plus_30  = trading_days[t0_idx + 30] if (t0_idx + 30) < len(trading_days) else None

    if t_plus_30 is None:
        # Truncated post-window — still include, flag it
        t_plus_30_idx = len(trading_days) - 1
        meta["notes"] += "Post-event window truncated (insufficient future data). "
    else:
        t_plus_30_idx = t0_idx + 30

    window_dates = trading_days[t0_idx - 20 : t_plus_30_idx + 1]

    # ── Hybrid event filter ───────────────────────────────────────────────
    # Keep event if ANY instrument moved ≥1.5% on T0 or T+1
    filter_details = []
    any_passes = False
    t1 = trading_days[t0_idx + 1] if (t0_idx + 1) < len(trading_days) else None

    for ticker in instruments:
        r0 = get_return(ticker, t0)
        r1 = get_return(ticker, t1) if t1 else None
        r0_str = f"{r0*100:+.2f}%" if r0 is not None else "N/A"
        r1_str = f"{r1*100:+.2f}%" if r1 is not None else "N/A"
        passes = (
            (r0 is not None and abs(r0) >= 0.015) or
            (r1 is not None and abs(r1) >= 0.015)
        )
        if passes:
            any_passes = True
        filter_details.append(f"{ticker}: T0={r0_str} T+1={r1_str} {'PASS' if passes else 'fail'}")

    meta["filter_pass"] = any_passes
    meta["filter_details"] = " | ".join(filter_details)

    if not any_passes:
        meta["status"] = "FILTERED_OUT"
        meta["notes"] += "No instrument moved ≥1.5% on T0 or T+1."
        metadata_rows.append(meta)
        print(f"Event {eid:2d} [{label}]: FILTERED_OUT")
        print(f"           {meta['filter_details']}")
        continue

    # ── Build normalised IV profile ───────────────────────────────────────
    event_profiles = []

    for ticker in instruments:
        iv_base = get_iv(ticker, t_minus_20)

        if iv_base is None:
            # Instrument unavailable for this event (e.g. USO in 2003)
            meta["notes"] += f"{ticker}: no IV at T-20 ({t_minus_20.date()}), marked N/A. "
            continue

        rows = []
        for t_day_offset in range(-20, t_plus_30_idx - t0_idx + 1):
            td_abs_idx = t0_idx + t_day_offset
            if td_abs_idx < 0 or td_abs_idx >= len(trading_days):
                continue
            td_date = trading_days[td_abs_idx]
            iv_val = get_iv(ticker, td_date)
            rows.append({
                "event_id":   eid,
                "ticker":     ticker,
                "t_day":      t_day_offset,
                "date":       td_date,
                "iv_raw":     iv_val,
                "iv_norm":    (iv_val / iv_base * 100) if iv_val is not None else None,
                "iv_base":    iv_base,
            })
        event_profiles.extend(rows)

    all_profiles.extend(event_profiles)
    metadata_rows.append(meta)

    n_instruments = len(set(r["ticker"] for r in event_profiles))
    print(f"Event {eid:2d} [{label}]: OK — {n_instruments} instruments, "
          f"T0={t0.date()}, T-20={t_minus_20.date()}")
    if meta["notes"]:
        print(f"           NOTE: {meta['notes'].strip()}")

# ── Serialise outputs ─────────────────────────────────────────────────────────
profiles_df = pd.DataFrame(all_profiles)
profiles_df.to_parquet("data/event_iv_profiles.parquet", index=False)
print(f"\nSaved {len(profiles_df):,} rows to data/event_iv_profiles.parquet")

meta_df = pd.DataFrame(metadata_rows)
meta_df.to_parquet("data/event_metadata.parquet", index=False)
print(f"Saved {len(meta_df)} event metadata rows to data/event_metadata.parquet")

# ── Summary table ─────────────────────────────────────────────────────────────
print("\n=== Event Study Summary ===")
summary = meta_df[["event_id", "label", "raw_date", "t0_date", "status", "filter_pass"]].copy()
summary["raw_date"] = summary["raw_date"].dt.date
summary["t0_date"] = summary["t0_date"].apply(lambda x: x.date() if pd.notna(x) and x is not None else "—")
print(summary.to_string(index=False))

ok_events = meta_df[meta_df["status"] == "OK"]
print(f"\nEvents included in analysis : {len(ok_events)}/{len(EVENTS)}")
print(f"Events filtered out         : {(meta_df['status'] == 'FILTERED_OUT').sum()}")
print(f"Events with no IV data      : {(meta_df['status'] == 'DATA_UNAVAILABLE').sum()}")

print("\n=== Filter details for passing events ===")
for _, row in ok_events.iterrows():
    print(f"\nEvent {row['event_id']:2d}: {row['label']}")
    for detail in row["filter_details"].split(" | "):
        print(f"  {detail}")
