"""
02_fred_macro.py
----------------
Pull macro rates and VIX via the official FRED API. 1994-01-01 to 2025-12-31.

Requires FRED_API_KEY env var (free key: https://fred.stlouisfed.org/docs/api/api_key.html).
Uses api.stlouisfed.org/fred/series/observations (JSON), not the fredgraph.csv
export endpoint, which has been suffering server-side outages.

Series pulled:
  VIXCLS   -> vix       CBOE Volatility Index
  DGS2     -> dgs2       2-Year Treasury yield
  DGS10    -> dgs10      10-Year Treasury yield
  T10Y2Y   -> t10y2y     10Y-2Y spread
  DFEDTARU -> fed_upper  Fed funds target range upper bound
  DFEDTARL -> fed_lower  Fed funds target range lower bound

Output: data/macro.parquet
Columns: date, vix, dgs2, dgs10, t10y2y, fed_upper, fed_lower
"""
import os
import requests
import pandas as pd
from pathlib import Path

DATA  = Path("data")
DATA.mkdir(exist_ok=True)
CACHE = DATA / "macro.parquet"
START, END = "1994-01-01", "2025-12-31"

API_KEY = os.environ.get("FRED_API_KEY")

SERIES = {
    "VIXCLS":   "vix",
    "DGS2":     "dgs2",
    "DGS10":    "dgs10",
    "T10Y2Y":   "t10y2y",
    "DFEDTARU": "fed_upper",
    "DFEDTARL": "fed_lower",
}

if CACHE.exists():
    df = pd.read_parquet(CACHE)
    print(f"Cache hit — {len(df):,} rows, "
          f"{df['date'].min().date()} to {df['date'].max().date()}")
else:
    if not API_KEY:
        raise SystemExit(
            "FRED_API_KEY not set. Get a free key at "
            "https://fred.stlouisfed.org/docs/api/api_key.html and run:\n"
            '  $env:FRED_API_KEY = "your_key_here"'
        )

    print("Pulling macro data via FRED API...")
    frames = {}
    for series_id, col in SERIES.items():
        print(f"  {series_id} -> {col} ...", end=" ", flush=True)
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": series_id,
                "api_key": API_KEY,
                "file_type": "json",
                "observation_start": START,
                "observation_end": END,
            },
            timeout=30,
        )
        r.raise_for_status()
        obs = r.json()["observations"]
        s = pd.DataFrame(obs)[["date", "value"]].rename(columns={"value": col})
        s["date"] = pd.to_datetime(s["date"])
        s[col] = pd.to_numeric(s[col], errors="coerce")  # FRED uses "." for missing
        s = s.dropna(subset=[col]).reset_index(drop=True)
        frames[col] = s.set_index("date")
        print(f"{len(s):,} rows, {s['date'].min().date()} to {s['date'].max().date()}")

    combined = pd.concat(list(frames.values()), axis=1).reset_index()
    combined = combined.rename(columns={"index": "date"})
    combined["date"] = pd.to_datetime(combined["date"])
    combined = combined.sort_values("date").reset_index(drop=True)
    combined = combined[["date", "vix", "dgs2", "dgs10", "t10y2y",
                          "fed_upper", "fed_lower"]]

    # DFEDTARU/DFEDTARL (target range) only exist from 2008-12-16 onward (corridor
    # regime). Pre-corridor, backfill from regimes.parquet's single target_rate.
    REGIMES_PATH = DATA / "regimes.parquet"
    if REGIMES_PATH.exists():
        reg = pd.read_parquet(REGIMES_PATH)[["date", "target_rate"]]
        reg["date"] = pd.to_datetime(reg["date"])
        combined = combined.merge(reg, on="date", how="left")
        combined["fed_upper"] = combined["fed_upper"].fillna(combined["target_rate"])
        combined["fed_lower"] = combined["fed_lower"].fillna(combined["target_rate"])
        combined = combined.drop(columns=["target_rate"])
        print("Backfilled pre-corridor fed_upper/fed_lower from regimes.parquet")
    else:
        print("WARNING: regimes.parquet not found; pre-2008 fed_upper/fed_lower will be NaN")

    combined.to_parquet(CACHE, index=False)
    df = combined
    print(f"\nSaved {len(df):,} rows to {CACHE}")

print(f"\nDate range: {df['date'].min().date()} to {df['date'].max().date()}")
print("Null counts:")
print(df.isnull().sum().to_string())
vix    = df["vix"].dropna()
dgs10  = df["dgs10"].dropna()
t10y2y = df["t10y2y"].dropna()
print(f"\nVIX   : {len(vix):,} non-null, {vix.min():.1f} to {vix.max():.1f}")
print(f"DGS10 : {len(dgs10):,} non-null, {dgs10.min():.2f}% to {dgs10.max():.2f}%")
print(f"T10Y2Y: {len(t10y2y):,} non-null, {t10y2y.min():.2f} to {t10y2y.max():.2f}")
print("Done.")
