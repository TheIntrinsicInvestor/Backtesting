"""
04_factors_industries.py
------------------------
Download Fama-French 5-factor + Momentum and 12-Industry daily portfolios
from Kenneth French's Dartmouth data library. No WRDS required.

URLs (confirmed working):
  5-factor daily : .../F-F_Research_Data_5_Factors_2x3_daily_CSV.zip
  Momentum daily : .../F-F_Momentum_Factor_daily_CSV.zip
  12-industry    : .../12_Industry_Portfolios_daily_CSV.zip

All raw values are percentages; divided by 100 on output.
Dates are YYYYMMDD integers in the raw CSV files.

Outputs: data/ff_factors.parquet, data/ff_industries.parquet
"""
import io, zipfile, requests
import pandas as pd
from pathlib import Path

DATA  = Path("data")
DATA.mkdir(exist_ok=True)
FF_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"

FACTORS_CACHE    = DATA / "ff_factors.parquet"
INDUSTRIES_CACHE = DATA / "ff_industries.parquet"
START, END = "1994-01-01", "2025-12-31"


def fetch_ff_zip(filename: str) -> bytes:
    url = FF_BASE + filename
    print(f"  GET {url} ...", end=" ", flush=True)
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    print(f"{len(r.content) // 1024} KB")
    return r.content


def parse_ff_zip(content: bytes) -> pd.DataFrame:
    """Parse a Fama-French ZIP into a daily returns DataFrame."""
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        text = zf.read(csv_name).decode("latin-1")

    lines = text.splitlines()
    header_cols = None
    data_lines  = []
    in_data     = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_data:
                break  # blank line ends the daily section
            continue

        parts = [p.strip() for p in stripped.split(",")]

        # Header row: first element is empty, rest are named columns
        if not in_data and parts[0] == "" and len(parts) > 1:
            if any(c.isalpha() for c in "".join(parts[1:])):
                header_cols = ["date"] + [p for p in parts[1:] if p]
                continue

        # Data rows: first element is 8-digit date integer
        first = parts[0].replace(" ", "")
        if first.isdigit() and len(first) == 8:
            in_data = True
            data_lines.append(stripped)

    if not data_lines:
        raise ValueError("No data rows found in FF file")

    df = pd.read_csv(io.StringIO("\n".join(data_lines)), header=None)

    n = df.shape[1]
    if header_cols and len(header_cols) == n:
        df.columns = header_cols
    else:
        df.columns = ["date"] + [f"col{j}" for j in range(n - 1)]

    df["date"] = pd.to_datetime(
        df["date"].astype(str).str.strip(), format="%Y%m%d", errors="coerce"
    )
    df = df.dropna(subset=["date"])

    ret_cols = [c for c in df.columns if c != "date"]
    for col in ret_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce") / 100.0

    # Drop FF placeholder rows (-99.99 -> -0.9999 after /100)
    df = df[~(df[ret_cols] < -0.99).any(axis=1)]

    return df.sort_values("date").reset_index(drop=True)


# ── 5 Factors + Momentum ────────────────────────────────────────────────────
if FACTORS_CACHE.exists():
    factors = pd.read_parquet(FACTORS_CACHE)
    print(f"Factors cache hit — {len(factors):,} rows")
else:
    print("Downloading Fama-French 5 factors (daily)...")
    raw5   = parse_ff_zip(fetch_ff_zip("F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"))
    print("Downloading Momentum factor (daily)...")
    rawmom = parse_ff_zip(fetch_ff_zip("F-F_Momentum_Factor_daily_CSV.zip"))

    # Momentum column may be named "Mom" or "MOM" — normalise to MOM
    mom_col = [c for c in rawmom.columns if c.lower() not in ("date", "rf")][0]
    rawmom  = rawmom[["date", mom_col]].rename(columns={mom_col: "MOM"})

    factors = pd.merge(raw5, rawmom, on="date", how="inner")
    factors = factors[(factors["date"] >= START) & (factors["date"] <= END)]
    factors = factors.reset_index(drop=True)
    factors.to_parquet(FACTORS_CACHE, index=False)
    print(f"Saved {len(factors):,} rows to {FACTORS_CACHE}")

print(f"Factors: {len(factors):,} rows, "
      f"{factors['date'].min().date()} to {factors['date'].max().date()}")
print(f"Columns: {list(factors.columns)}")

# Spot check: Mkt-RF annualised mean should be ~7-8% (positive equity premium)
mkt_col = [c for c in factors.columns if "mkt" in c.lower()][0]
ann_mkt = factors[mkt_col].mean() * 252 * 100
print(f"Mkt-RF annualised mean: {ann_mkt:.1f}% (expect ~7-8%)")

# ── 12 Industry Portfolios ──────────────────────────────────────────────────
if INDUSTRIES_CACHE.exists():
    industries = pd.read_parquet(INDUSTRIES_CACHE)
    print(f"\nIndustries cache hit — {len(industries):,} rows")
else:
    print("\nDownloading 12-Industry Portfolios (daily, value-weighted)...")
    industries = parse_ff_zip(fetch_ff_zip("12_Industry_Portfolios_daily_CSV.zip"))
    industries = industries[(industries["date"] >= START) & (industries["date"] <= END)]
    industries = industries.reset_index(drop=True)
    industries.to_parquet(INDUSTRIES_CACHE, index=False)
    print(f"Saved {len(industries):,} rows to {INDUSTRIES_CACHE}")

print(f"\nIndustries: {len(industries):,} rows, "
      f"{industries['date'].min().date()} to {industries['date'].max().date()}")
print(f"Columns (12 industries): {list(industries.columns)}")

# Null check
ind_ret_cols = [c for c in industries.columns if c != "date"]
nulls = industries[ind_ret_cols].isnull().sum().sum()
print(f"Null cells in industries: {nulls}")
print("Done.")
