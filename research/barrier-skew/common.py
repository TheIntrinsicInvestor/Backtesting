# ruff: noqa
"""
common.py
---------
Shared constants, WRDS connection and cache helpers for the barrier-skew pipeline.
Import this FIRST in every WRDS script: it installs the non-interactive auth patch.
"""

import builtins, getpass, os
_u = os.environ["WRDS_USERNAME"]
_p = os.environ.get("PGPASSWORD", "")
def _ai(p=""):
    if "username" in p.lower(): v = _u
    elif "y/n" in p.lower(): v = "n"
    else: v = ""
    print(p + v); return v
builtins.input = _ai
getpass.getpass = lambda p="": _p

from pathlib import Path
import pandas as pd

DATA = Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)

SPX_SECID = 108105
SX5E_SECID = 504880
SX5E_EXCHANGE = 353          # the one exchange with full 2002-2023 SX5E price history
EUR_CCY = 814                # currency id on every SX5E surface row

US_FIRST, US_LAST_START = "1996-01-01", "2024-12-31"   # last start needs a full year of CRSP path (ends 2025-12-31)
EU_FIRST, EU_LAST_START = "2002-01-01", "2022-02-28"   # IvyDB Europe ends 2023-02-28
US_OPT_LAST = 2025                                     # last OptionMetrics US year table

N_NAMES, N_CANDIDATES = 10, 15   # final names per start date, candidates pulled to allow for bad surfaces
VOL_WEEKS = 13                   # trailing option-volume window (about 63 trading days)

# Out-of-the-money half of the delta grid: puts -10..-50, calls 10..45 (17 points per tenor)
OTM_US = "((cp_flag = 'P' AND delta >= -50) OR (cp_flag = 'C' AND delta < 50))"
OTM_EU = "((callput = 'P' AND delta >= -50) OR (callput = 'C' AND delta < 50))"
EU_NA = -99.98  # IvyDB Europe writes missing values as -99.99


def connect():
    import wrds
    return wrds.Connection(wrds_username=_u)


def cached(name):
    """Return the cached DataFrame, or None if it has not been pulled yet."""
    f = DATA / f"{name}.parquet"
    if f.exists():
        df = pd.read_parquet(f)
        print(f"  [cache] {name}: {len(df):,} rows")
        return df
    return None


def save(df, name):
    df.to_parquet(DATA / f"{name}.parquet", index=False)
    print(f"  [saved] {name}: {len(df):,} rows")
    return df


def weekly_starts(trading_days, first, last):
    """First trading day on or after each Wednesday, within the same week."""
    td = pd.DatetimeIndex(sorted(pd.to_datetime(trading_days).unique()))
    td = td[(td >= first) & (td <= last)]
    wk = pd.Series(td, index=td).groupby(td.to_period("W-SAT"))
    out = []
    for _, days in wk:
        on_or_after_wed = days[days.dt.dayofweek >= 2]
        if len(on_or_after_wed):
            out.append(on_or_after_wed.iloc[0])
    return pd.DatetimeIndex(out)
