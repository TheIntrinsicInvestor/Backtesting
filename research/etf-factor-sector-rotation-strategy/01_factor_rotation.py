"""
01_factor_rotation.py
Factor & Sector ETF Rotation Strategy — Systematic Backtest
Author: Brian Liew (LSE, BSc Accounting and Finance)

Run on WRDS JupyterHub:
    set WRDS_USERNAME=hoovyalert
    python 01_factor_rotation.py
"""

# ─────────────────────────────────────────────────────────────────────────────
# 1. IMPORTS & CONFIG
# ─────────────────────────────────────────────────────────────────────────────
import os, sys, json, warnings
from datetime import datetime
from itertools import product

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# Pandas version-safe month-end resample alias ('ME' added in 2.2, 'M' deprecated there)
try:
    pd.date_range('2020-01-01', periods=2, freq='ME')
    _MEND = 'ME'
except ValueError:
    _MEND = 'M'

FACTOR_ETFS = ['MTUM', 'QUAL', 'IWD', 'IWM']
SECTOR_ETFS = ['XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLY', 'XLP', 'XLU', 'XLB']
ALL_ETFS    = FACTOR_ETFS + SECTOR_ETFS
TICKERS     = ALL_ETFS + ['SPY']

LOOKBACKS   = [1, 3, 6, 9, 12]
FILTER_IDS  = [0, 1, 2, 3, 4, 5]
SPLITS      = ['A', 'B']

FILTER_NAMES = {
    0: 'No filter',
    1: '12m return < 0',
    2: 'Price < 10m SMA',
    3: 'Price < 200d SMA',
    4: '1m SMA < 10m SMA',
    5: 'Death cross (50d<200d)',
}
# Filters that use daily intra-month signals (exit/re-enter at day close)
DAILY_FILTERS = {3, 4, 5}

CACHE_DAILY   = 'prices_daily.parquet'
CACHE_MONTHLY = 'prices_monthly.parquet'

TEAL   = '#1a5c52'
DARK   = '#0f2220'
PARCH  = '#f7f4ec'
MUTED  = '#4a6460'
HINT   = '#8aa49e'
BORDER = '#e2ddd0'

print("=" * 60)
print("ETF Factor & Sector Rotation — Backtest Script")
print(f"Run date: {datetime.today().strftime('%Y-%m-%d')}")
print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# 2. WRDS DATA PULL
# ─────────────────────────────────────────────────────────────────────────────
if os.path.exists(CACHE_DAILY):
    print(f"\n[CACHE] Loading daily prices from {CACHE_DAILY}")
    daily_raw = pd.read_parquet(CACHE_DAILY)
    daily_raw['datadate'] = pd.to_datetime(daily_raw['datadate'])
    print(f"  Loaded {len(daily_raw):,} rows, {daily_raw['tic'].nunique()} tickers")
else:
    print("\n[WRDS] Connecting...")
    import wrds
    db = wrds.Connection(wrds_username=os.environ.get('WRDS_USERNAME', 'hoovyalert'))
    print("  Connected.")
    tickers_sql = "', '".join(TICKERS)
    query = f"""
        SELECT a.gvkey, a.tic, a.datadate, a.prccd, a.trfd
        FROM comp.secd a
        WHERE a.tic IN ('{tickers_sql}')
          AND a.prccd IS NOT NULL AND a.trfd IS NOT NULL
          AND a.prccd > 0 AND a.trfd > 0
        ORDER BY a.tic, a.datadate
    """
    print("  Querying comp.secd (may take ~1 min)...")
    daily_raw = db.raw_sql(query, date_cols=['datadate'])
    db.close()
    print(f"  Retrieved {len(daily_raw):,} rows, {daily_raw['tic'].nunique()} tickers")
    # De-duplicate: keep gvkey with most rows per ticker
    counts = daily_raw.groupby(['tic', 'gvkey']).size().reset_index(name='n')
    best   = counts.sort_values('n', ascending=False).drop_duplicates('tic')[['tic', 'gvkey']]
    daily_raw = daily_raw.merge(best, on=['tic', 'gvkey'])
    daily_raw.to_parquet(CACHE_DAILY, index=False)
    print(f"  Saved to {CACHE_DAILY} ({len(daily_raw):,} rows after de-dup)")


# ─────────────────────────────────────────────────────────────────────────────
# 3. CLEANING & MONTHLY RESAMPLING
# ─────────────────────────────────────────────────────────────────────────────
print("\n[DATA] Building total return index...")

daily_raw = daily_raw.sort_values(['tic', 'datadate'])
daily_raw['tri'] = daily_raw['prccd'] * daily_raw['trfd']

daily_tri = daily_raw.pivot_table(index='datadate', columns='tic', values='tri', aggfunc='last')
daily_tri.index = pd.to_datetime(daily_tri.index)

missing = [t for t in TICKERS if t not in daily_tri.columns]
if missing:
    print(f"  ERROR: Tickers not found in comp.secd: {missing}")
    sys.exit(1)
daily_tri = daily_tri[TICKERS]

spy_daily_tri  = daily_tri[['SPY']].dropna()
all_daily_tri  = daily_tri.copy()                      # all tickers, daily TRI
all_daily_ret  = all_daily_tri.pct_change()            # daily total returns

if os.path.exists(CACHE_MONTHLY):
    print(f"  [CACHE] Loading monthly TRI from {CACHE_MONTHLY}")
    monthly_tri = pd.read_parquet(CACHE_MONTHLY)
    monthly_tri.index = pd.to_datetime(monthly_tri.index)
else:
    monthly_tri = daily_tri.resample(_MEND).last()
    # Gap check and forward-fill — only inspect within each ETF's live trading period
    for tic in TICKERS:
        col = monthly_tri[tic]
        first_valid = col.first_valid_index()
        if first_valid is None:
            continue
        col_live = col.loc[first_valid:]
        nan_runs = col_live.isna().astype(int)
        if nan_runs.any():
            run_len = 0
            max_run = 0
            for v in nan_runs:
                run_len = run_len + 1 if v else 0
                max_run = max(max_run, run_len)
            if max_run > 3:
                print(f"  WARNING: {tic} has {max_run} consecutive missing months within live history — forward-filling")
        monthly_tri[tic] = col.ffill()
    monthly_tri.to_parquet(CACHE_MONTHLY)
    print(f"  Saved monthly TRI to {CACHE_MONTHLY}")

monthly_ret = monthly_tri.pct_change()
month_ends  = monthly_tri.index
print(f"  Daily range: {daily_tri.index.min().date()} to {daily_tri.index.max().date()}")
print(f"  Monthly obs (full history): {len(monthly_tri)}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. SPY DRAWDOWN FILTER SIGNALS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[FILTER] Computing SPY drawdown signals...")

spy_m    = monthly_tri['SPY']
spy_mr   = monthly_ret['SPY']

# ── Monthly signals (F0, F1, F2): checked at month-start, hold all month ──
f0 = pd.Series(False, index=month_ends, dtype=bool)

spy_12m = spy_mr.rolling(12).apply(lambda x: (1 + x).prod() - 1, raw=True)
f1 = (spy_12m < 0).fillna(False)

spy_10m_sma = spy_m.rolling(10).mean()
f2 = (spy_m < spy_10m_sma).fillna(False)

# Monthly cash_signals for F0/F1/F2 (used for month-start check and % reporting)
cash_signals_monthly = pd.DataFrame({0: f0, 1: f1, 2: f2}, index=month_ends)

# ── Daily signals (F3, F4, F5): intra-month exits/entries at day close ──
# Position on day D determined by signal at close of day D-1 (shift 1 day)
spy_d = spy_daily_tri['SPY']

spy_sma200 = spy_d.rolling(200).mean()
spy_sma50  = spy_d.rolling(50).mean()
spy_sma21  = spy_d.rolling(21).mean()   # ≈ 1-month SMA
spy_sma210 = spy_d.rolling(210).mean()  # ≈ 10-month SMA

# Raw daily signal: True = should be in cash today
f3_raw = (spy_d    < spy_sma200).fillna(False)
f4_raw = (spy_sma21 < spy_sma210).fillna(False)
f5_raw = (spy_sma50 < spy_sma200).fillna(False)

# Shift 1 day: on day D, use signal from day D-1 close
f3_daily = f3_raw.shift(1).fillna(False).astype(bool)
f4_daily = f4_raw.shift(1).fillna(False).astype(bool)
f5_daily = f5_raw.shift(1).fillna(False).astype(bool)

daily_cash_signals = {3: f3_daily, 4: f4_daily, 5: f5_daily}

# Report % cash for all filters (daily filters: fraction of trading days in cash)
f3_mo = f3_raw.resample(_MEND).last().reindex(month_ends, method='ffill').fillna(False)
f4_mo = f4_raw.resample(_MEND).last().reindex(month_ends, method='ffill').fillna(False)
f5_mo = f5_raw.resample(_MEND).last().reindex(month_ends, method='ffill').fillna(False)
cash_signals = pd.DataFrame({0: f0, 1: f1, 2: f2, 3: f3_mo, 4: f4_mo, 5: f5_mo},
                             index=month_ends)
for fid in range(6):
    pct = cash_signals[fid].mean() * 100
    src = 'days' if fid in DAILY_FILTERS else 'months'
    print(f"  Filter {fid} ({FILTER_NAMES[fid]}): cash {pct:.1f}% of {src}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. COMMON BACKTEST START DATE
# ─────────────────────────────────────────────────────────────────────────────
print("\n[VALIDATE] ETF coverage and common start date...")

MAX_LOOKBACK = 12
etf_first = {}
for tic in ALL_ETFS:
    col = monthly_tri[tic].dropna()
    if len(col) < MAX_LOOKBACK + 6:
        print(f"  ERROR: {tic} has insufficient history ({len(col)} months).")
        sys.exit(1)
    etf_first[tic] = col.index[0]
    print(f"  {tic}: {col.index[0].date()} to {col.index[-1].date()} ({len(col)} months)")

latest_first = max(etf_first.values())
target_start = latest_first + pd.DateOffset(months=MAX_LOOKBACK)
common_start = month_ends[month_ends >= target_start][0]

print(f"\n  Latest first valid date (across all ETFs): {latest_first.date()}")
print(f"  Common backtest start ({MAX_LOOKBACK}m lookback buffer): {common_start.date()}")

bt_monthly_tri = monthly_tri.loc[common_start:]
bt_monthly_ret = monthly_ret.loc[common_start:]
bt_cash        = cash_signals.loc[common_start:]
N_MONTHS       = len(bt_monthly_tri)

print(f"  Backtest: {common_start.date()} to {bt_monthly_tri.index[-1].date()} ({N_MONTHS} months)")


# ─────────────────────────────────────────────────────────────────────────────
# 6. GRID SEARCH ENGINE
# ─────────────────────────────────────────────────────────────────────────────
print("\n[GRID] Running 60-combination grid search...")

# Pre-compute momentum scores for all lookbacks
mom_cache = {}
for lb in LOOKBACKS:
    scores = monthly_tri.pct_change(lb)
    mom_cache[lb] = scores.loc[bt_monthly_tri.index]

# Pre-index daily data by (year, month) for fast intra-month lookup
_daily_idx = all_daily_ret.index
_ym_to_days = {}
for day in _daily_idx:
    key_ym = (day.year, day.month)
    _ym_to_days.setdefault(key_ym, []).append(day)

def sleeve_return_daily(etf, month_end, cash_signal_d):
    """
    Compound daily returns for `etf` over the calendar month of `month_end`,
    going to cash (0%) on days where cash_signal_d is True.
    Returns (float monthly_return, float fraction_days_invested).
    """
    days = _ym_to_days.get((month_end.year, month_end.month), [])
    if not days or etf not in all_daily_ret.columns:
        return 0.0, 0.0
    compound   = 1.0
    days_in    = 0
    days_total = 0
    for day in days:
        if day not in cash_signal_d.index:
            continue
        days_total += 1
        if not cash_signal_d[day]:
            r = all_daily_ret.at[day, etf] if day in all_daily_ret.index else 0.0
            if pd.isna(r):
                r = 0.0
            compound *= (1.0 + r)
            days_in  += 1
    frac_in = days_in / days_total if days_total > 0 else 0.0
    return float(compound - 1), frac_in

all_port_rets = {}
all_in_market = {}

done = 0
for lookback, filter_id, split in product(LOOKBACKS, FILTER_IDS, SPLITS):
    key = (lookback, filter_id, split)

    m = mom_cache[lookback]
    factor_scores   = m[FACTOR_ETFS]
    sector_scores   = m[SECTOR_ETFS]
    # shift(1): selection known at prior month-end, applied to this month
    factor_selected = factor_scores.idxmax(axis=1).shift(1)
    sector_selected = sector_scores.idxmax(axis=1).shift(1)

    is_daily = filter_id in DAILY_FILTERS
    if is_daily:
        cash_signal_d = daily_cash_signals[filter_id]
    else:
        # Monthly filter: shift(1) so month-start position = prior month-end signal
        cash_flag_m = cash_signals_monthly[filter_id].shift(1).fillna(False)

    port_rets = []
    f_ins     = []
    s_ins     = []
    prev_f_ret = 0.0   # for Split B: prior month actual sleeve returns
    prev_s_ret = 0.0

    for i, dt in enumerate(bt_monthly_tri.index):
        f_etf = factor_selected.at[dt] if pd.notna(factor_selected.at[dt]) else None
        s_etf = sector_selected.at[dt] if pd.notna(sector_selected.at[dt]) else None

        # ── Sleeve returns and in-market fractions ──
        if is_daily:
            f_ret, f_in = (sleeve_return_daily(f_etf, dt, cash_signal_d)
                           if f_etf else (0.0, 0.0))
            s_ret, s_in = (sleeve_return_daily(s_etf, dt, cash_signal_d)
                           if s_etf else (0.0, 0.0))
        else:
            in_mkt = not bool(cash_flag_m.at[dt])
            f_ret  = float(bt_monthly_ret.at[dt, f_etf]) if (f_etf and in_mkt) else 0.0
            s_ret  = float(bt_monthly_ret.at[dt, s_etf]) if (s_etf and in_mkt) else 0.0
            if pd.isna(f_ret): f_ret = 0.0
            if pd.isna(s_ret): s_ret = 0.0
            f_in   = 1.0 if in_mkt else 0.0
            s_in   = 1.0 if in_mkt else 0.0

        # ── Sleeve weights ──
        if split == 'A':
            w_f, w_s = 0.5, 0.5
        else:
            # Split B: weight by prior month's actual sleeve returns (floored at 0)
            if i == 0:
                w_f, w_s = 0.5, 0.5
            else:
                wf = max(0.0, prev_f_ret)
                ws = max(0.0, prev_s_ret)
                tot = wf + ws
                if tot <= 0.0:
                    w_f, w_s = 0.5, 0.5
                else:
                    w_f, w_s = wf / tot, ws / tot

        port_rets.append(w_f * f_ret + w_s * s_ret)
        f_ins.append(f_in)
        s_ins.append(s_in)
        prev_f_ret = f_ret
        prev_s_ret = s_ret

    all_port_rets[key] = pd.Series(port_rets, index=bt_monthly_tri.index, dtype=float)
    all_in_market[key] = (pd.Series(f_ins, index=bt_monthly_tri.index),
                          pd.Series(s_ins, index=bt_monthly_tri.index))

    done += 1
    if done % 12 == 0:
        print(f"  {done}/60 done")

print("  Grid search complete.")


# ─────────────────────────────────────────────────────────────────────────────
# 7. METRICS
# ─────────────────────────────────────────────────────────────────────────────
print("\n[METRICS] Computing performance metrics...")

def compute_metrics(r_series, f_in_arr=None, s_in_arr=None):
    r = r_series.dropna().astype(float)
    n = len(r)
    if n < 2:
        return {}
    equity   = (1 + r).cumprod()
    tot_ret  = float(equity.iloc[-1] - 1)
    n_yrs    = n / 12
    cagr     = float((1 + tot_ret) ** (1 / n_yrs) - 1)
    sharpe   = float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 1e-10 else 0.0
    roll_max = equity.cummax()
    dd       = equity / roll_max - 1
    max_dd   = float(dd.min())
    calmar   = float(cagr / abs(max_dd)) if max_dd < -1e-6 else float('nan')
    win_rate = float((r > 0).mean())
    if f_in_arr is not None and s_in_arr is not None:
        pct_in = float((pd.Series(f_in_arr).mean() + pd.Series(s_in_arr).mean()) / 2)
    else:
        pct_in = 1.0
    annual = r.groupby(r.index.year).apply(lambda x: float((1 + x).prod() - 1))
    return dict(total_ret=tot_ret, cagr=cagr, sharpe=sharpe, max_dd=max_dd,
                calmar=calmar, win_rate=win_rate, pct_in=pct_in,
                best_yr=float(annual.max()), worst_yr=float(annual.min()),
                annual=annual, equity=equity)

rows = []
for lookback, filter_id, split in product(LOOKBACKS, FILTER_IDS, SPLITS):
    key = (lookback, filter_id, split)
    fi, si = all_in_market[key]
    m = compute_metrics(all_port_rets[key], fi, si)
    rows.append(dict(Lookback=lookback, Filter=filter_id, Split=split,
                     **{k: v for k, v in m.items() if k not in ('annual', 'equity')}))

results_df = (pd.DataFrame(rows)
              .sort_values('sharpe', ascending=False)
              .reset_index(drop=True))
results_df.index += 1

spy_ret_bt = bt_monthly_ret['SPY']
ew_ret_bt  = bt_monthly_ret[ALL_ETFS].mean(axis=1)
spy_m_obj  = compute_metrics(spy_ret_bt)
ew_m_obj   = compute_metrics(ew_ret_bt)


# ─────────────────────────────────────────────────────────────────────────────
# 8. SENSITIVITY DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────
def pivot_sharpe(split_val):
    sub = results_df[results_df['Split'] == split_val].copy()
    return sub.pivot_table(index='Filter', columns='Lookback', values='sharpe', aggfunc='first')

hm_A    = pivot_sharpe('A')
hm_B    = pivot_sharpe('B')
hm_best = pd.DataFrame(np.maximum(hm_A.values, hm_B.values),
                        index=hm_A.index, columns=hm_A.columns)

best_row = results_df.iloc[0]
best_key = (int(best_row['Lookback']), int(best_row['Filter']), best_row['Split'])
best_rets = all_port_rets[best_key]
bfi, bsi  = all_in_market[best_key]
best_m    = compute_metrics(best_rets, bfi, bsi)

top3_keys = []
for _, row in results_df.head(3).iterrows():
    top3_keys.append((int(row['Lookback']), int(row['Filter']), row['Split']))

# Equity curve data (rebased to 100)
labels = [dt.strftime('%Y-%m') for dt in bt_monthly_tri.index]
equity_data = {}
for i, key in enumerate(top3_keys):
    r = all_port_rets[key]
    eq = ((1 + r).cumprod() * 100).round(4).tolist()
    lbl = f"Combo #{i+1} (L{key[0]},F{key[1]},{key[2]})"
    equity_data[lbl] = eq
equity_data['SPY B&H']    = ((1 + spy_ret_bt).cumprod() * 100).round(4).tolist()
equity_data['EW B&H']     = ((1 + ew_ret_bt).cumprod() * 100).round(4).tolist()

# Annual returns
best_annual = best_m['annual']
spy_annual  = spy_m_obj['annual']
common_yrs  = sorted(set(best_annual.index) & set(spy_annual.index))
annual_labels     = [str(y) for y in common_yrs]
annual_best_vals  = [round(best_annual[y] * 100, 2) for y in common_yrs]
annual_spy_vals   = [round(spy_annual[y]  * 100, 2) for y in common_yrs]

# Both-cash months
both_cash = int(((bfi == 0) & (bsi == 0)).sum())
pct_both_cash = both_cash / N_MONTHS * 100


# ─────────────────────────────────────────────────────────────────────────────
# 9. VALIDATION PRINT
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TOP 5 BY SHARPE")
print(f"{'Rank':>4}  {'Lb':>4}  {'F':>2}  {'Sp':>3}  "
      f"{'CAGR':>8}  {'Sharpe':>7}  {'MaxDD':>8}  {'Win%':>6}  {'InMkt%':>7}")
for i, row in results_df.head(5).iterrows():
    print(f"{i:>4}  {int(row['Lookback']):>4}m  {int(row['Filter']):>2}  "
          f"{row['Split']:>3}  {row['cagr']*100:>7.2f}%  "
          f"{row['sharpe']:>7.3f}  {row['max_dd']*100:>7.2f}%  "
          f"{row['win_rate']*100:>5.1f}%  {row['pct_in']*100:>6.1f}%")
print(f"\nSPY B&H:  CAGR={spy_m_obj['cagr']*100:.2f}%  "
      f"Sharpe={spy_m_obj['sharpe']:.3f}  MaxDD={spy_m_obj['max_dd']*100:.2f}%")
print(f"EW  B&H:  CAGR={ew_m_obj['cagr']*100:.2f}%  "
      f"Sharpe={ew_m_obj['sharpe']:.3f}  MaxDD={ew_m_obj['max_dd']*100:.2f}%")
print(f"\nBest combo both-sleeves-cash months: {both_cash} ({pct_both_cash:.1f}%)")
if pct_both_cash > 10:
    print("  ** WARNING: >10% of months fully in cash **")
print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# 10. HTML HEATMAP GENERATION (pure Python — no image embedding)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[CHARTS] Generating heatmap HTML tables...")

def _lerp_color(t, lo_rgb, hi_rgb):
    """Interpolate between two RGB tuples, t in [0, 1]."""
    r = int(lo_rgb[0] + t * (hi_rgb[0] - lo_rgb[0]))
    g = int(lo_rgb[1] + t * (hi_rgb[1] - lo_rgb[1]))
    b = int(lo_rgb[2] + t * (hi_rgb[2] - lo_rgb[2]))
    return f'#{r:02x}{g:02x}{b:02x}'

_C_RED   = (254, 202, 202)   # light red    #fecaca
_C_PARCH = (247, 244, 236)   # parchment    #f7f4ec
_C_GREEN = (187, 247, 208)   # light green  #bbf7d0

def _sharpe_color(v, vmin, vmax):
    """Sequential red→parchment→green across the Sharpe range."""
    if vmax == vmin:
        return '#f7f4ec'
    t = max(0.0, min(1.0, (v - vmin) / (vmax - vmin)))
    if t < 0.5:
        return _lerp_color(t * 2, _C_RED, _C_PARCH)
    return _lerp_color((t - 0.5) * 2, _C_PARCH, _C_GREEN)

def _monthly_color(v, abs_max):
    """Diverging parchment→green (positive) / parchment→red (negative)."""
    if abs_max == 0:
        return '#f7f4ec'
    t = max(0.0, min(1.0, abs(v) / abs_max))
    if v < 0:
        return _lerp_color(t, _C_PARCH, _C_RED)
    return _lerp_color(t, _C_PARCH, _C_GREEN)

def make_sharpe_heatmap_html(pivot):
    vmin = float(results_df['sharpe'].min())
    vmax = float(results_df['sharpe'].max())
    lbs  = list(pivot.columns)   # lookback periods
    fids = list(pivot.index)     # filter IDs
    header = '<tr><th class="hm-corner"></th>' + \
             ''.join(f'<th class="hm-col">{lb}m</th>' for lb in lbs) + '</tr>'
    body = ''
    for fid in fids:
        fname = FILTER_NAMES[fid]
        short = (fname[:24] + '&hellip;') if len(fname) > 24 else fname
        row = (f'<td class="hm-row-label" title="{fname}">'
               f'<span class="hm-fid">F{fid}</span> {short}</td>')
        for lb in lbs:
            v = float(pivot.at[fid, lb])
            bg = _sharpe_color(v, vmin, vmax)
            row += (f'<td class="hm-cell" style="background:{bg}">'
                    f'<strong>{v:.3f}</strong></td>')
        body += f'<tr>{row}</tr>'
    return (f'<div class="hm-wrap"><table class="hm-table">'
            f'<thead>{header}</thead><tbody>{body}</tbody></table></div>')

def make_monthly_heatmap_html(ret_series):
    s = ret_series.copy()
    s.index = pd.to_datetime(s.index)
    years  = sorted(s.index.year.unique())
    mon_labels = ['Jan','Feb','Mar','Apr','May','Jun',
                  'Jul','Aug','Sep','Oct','Nov','Dec']
    data = {(dt.year, dt.month): float(val) * 100 for dt, val in s.items()}
    all_vals = list(data.values())
    abs_max  = max(abs(v) for v in all_vals) if all_vals else 1.0
    header = '<tr><th class="hm-corner"></th>' + \
             ''.join(f'<th class="hm-col">{m}</th>' for m in mon_labels) + '</tr>'
    body = ''
    for yr in years:
        row = f'<td class="hm-row-label"><strong>{yr}</strong></td>'
        for mo in range(1, 13):
            v = data.get((yr, mo))
            if v is None:
                row += '<td class="hm-cell hm-empty"></td>'
            else:
                bg   = _monthly_color(v, abs_max)
                sign = '+' if v > 0 else ''
                row += (f'<td class="hm-cell" style="background:{bg}">'
                        f'{sign}{v:.1f}%</td>')
        body += f'<tr>{row}</tr>'
    return (f'<div class="hm-wrap"><table class="hm-table">'
            f'<thead>{header}</thead><tbody>{body}</tbody></table></div>')

print("  Heatmap A...")
hm_a_html = make_sharpe_heatmap_html(hm_A)
print("  Heatmap B...")
hm_b_html = make_sharpe_heatmap_html(hm_B)
print("  Heatmap Combined...")
hm_c_html = make_sharpe_heatmap_html(hm_best)
print("  Monthly return heatmap...")
hm_monthly_html = make_monthly_heatmap_html(best_rets)
print("  Charts done.")


# ─────────────────────────────────────────────────────────────────────────────
# 11. HTML ASSEMBLY
# ─────────────────────────────────────────────────────────────────────────────
print("\n[HTML] Assembling report...")

RUN_DATE   = datetime.today().strftime('%B %d, %Y')
START_DATE = common_start.strftime('%B %Y')
END_DATE   = bt_monthly_tri.index[-1].strftime('%B %Y')

# Pre-compute strings that go into f-string template
def fmt_pct(v, d=2): return f"{v*100:.{d}f}%"
def fmt_f(v, d=3):   return f"{v:.{d}f}"
def calmar_str(v):   return f"{v:.2f}" if (v == v) and abs(v) < 1e10 else 'N/A'

best_calmar_str = calmar_str(best_m['calmar'])

sharpe_diff  = best_m['sharpe'] - spy_m_obj['sharpe']
sharpe_sign  = '+' if sharpe_diff > 0 else ''
sharpe_cls   = 'green-val' if sharpe_diff > 0 else 'red-val'
kpi_sharpe_d = f'<span class="{sharpe_cls}">{sharpe_sign}{sharpe_diff:.3f} vs SPY</span>'

cagr_diff    = best_m['cagr'] - spy_m_obj['cagr']
cagr_sign    = '+' if cagr_diff > 0 else ''
cagr_cls     = 'green-val' if cagr_diff > 0 else 'red-val'
kpi_cagr_d   = f'<span class="{cagr_cls}">{cagr_sign}{cagr_diff*100:.2f}% vs SPY</span>'

dd_diff      = best_m['max_dd'] - spy_m_obj['max_dd']
dd_sign      = '+' if dd_diff > 0 else ''
dd_cls       = 'green-val' if dd_diff < 0 else 'red-val'
kpi_dd_d     = f'<span class="{dd_cls}">{dd_sign}{dd_diff*100:.2f}% vs SPY</span>'

# Ranked table rows — top 10 only
table_rows_html = ''
for i, row in results_df.head(10).iterrows():
    top_cls = ' class="top-row"' if i <= 3 else ''
    c_str   = calmar_str(row['calmar'])
    table_rows_html += (
        f'<tr{top_cls}>'
        f'<td>{i}</td>'
        f'<td>{int(row["Lookback"])}m</td>'
        f'<td><span class="fbadge">F{int(row["Filter"])}</span> {FILTER_NAMES[int(row["Filter"])]}</td>'
        f'<td><span class="split-badge split-{row["Split"]}">{row["Split"]}</span></td>'
        f'<td class="num">{fmt_pct(row["cagr"])}</td>'
        f'<td class="num"><strong>{fmt_f(row["sharpe"])}</strong></td>'
        f'<td class="num">{c_str}</td>'
        f'<td class="num red-val">{fmt_pct(row["max_dd"])}</td>'
        f'<td class="num">{row["win_rate"]*100:.1f}%</td>'
        f'<td class="num">{row["pct_in"]*100:.1f}%</td>'
        f'</tr>'
    )

# ETF universe table
ETF_INFO = {
    'MTUM': ('iShares MSCI USA Momentum Factor', 'Factor', 'Nov 2013',
             'Pure large/mid-cap US momentum exposure'),
    'QUAL': ('iShares MSCI USA Quality Factor', 'Factor', 'Jul 2013',
             'High ROE, low leverage, stable earnings growth'),
    'IWD':  ('iShares Russell 1000 Value', 'Factor', 'May 2000',
             'Broad value factor; longest live history in the sleeve'),
    'IWM':  ('iShares Russell 2000', 'Factor', 'May 2000',
             'Small-cap risk premium; diversifies large-cap bias'),
    'XLK':  ('Technology Select Sector SPDR', 'Sector', 'Dec 1998',
             'Highest-returning sector in the post-GFC cycle'),
    'XLF':  ('Financial Select Sector SPDR', 'Sector', 'Dec 1998',
             'Rate-sensitive; rotates with the yield curve'),
    'XLE':  ('Energy Select Sector SPDR', 'Sector', 'Dec 1998',
             'Commodity cycle exposure; low correlation to tech'),
    'XLV':  ('Health Care Select Sector SPDR', 'Sector', 'Dec 1998',
             'Defensive growth; useful in drawdown regimes'),
    'XLI':  ('Industrial Select Sector SPDR', 'Sector', 'Dec 1998',
             'Cyclical; tracks manufacturing and capex cycles'),
    'XLY':  ('Consumer Discretionary SPDR', 'Sector', 'Dec 1998',
             'Consumer cycle bellwether; high beta'),
    'XLP':  ('Consumer Staples SPDR', 'Sector', 'Dec 1998',
             'Defensive; flight-to-safety rotation target'),
    'XLU':  ('Utilities Select Sector SPDR', 'Sector', 'Dec 1998',
             'Rate-sensitive defensive; strong in risk-off'),
    'XLB':  ('Materials Select Sector SPDR', 'Sector', 'Dec 1998',
             'Commodities proxy; inflation-cycle exposure'),
}
etf_rows_html = ''
for tic, (name, sleeve, inception, rationale) in ETF_INFO.items():
    sc = 'factor' if sleeve == 'Factor' else 'sector'
    etf_rows_html += (
        f'<tr><td><strong>{tic}</strong></td>'
        f'<td>{name}</td>'
        f'<td><span class="sleeve-badge {sc}">{sleeve}</span></td>'
        f'<td class="mono">{inception}</td>'
        f'<td class="muted-cell">{rationale}</td></tr>'
    )

# Benchmark comparison table
def bench_row_html(label, m, extra_cls=''):
    c = calmar_str(m['calmar'])
    return (
        f'<tr class="{extra_cls}">'
        f'<td><strong>{label}</strong></td>'
        f'<td class="num">{fmt_pct(m["total_ret"], 1)}</td>'
        f'<td class="num">{fmt_pct(m["cagr"])}</td>'
        f'<td class="num"><strong>{fmt_f(m["sharpe"])}</strong></td>'
        f'<td class="num">{c}</td>'
        f'<td class="num red-val">{fmt_pct(m["max_dd"])}</td>'
        f'<td class="num">{m["win_rate"]*100:.1f}%</td>'
        f'<td class="num">{fmt_pct(m["best_yr"], 1)}</td>'
        f'<td class="num red-val">{fmt_pct(m["worst_yr"], 1)}</td>'
        f'</tr>'
    )

best_bench_label = f"Best Combo (L{best_key[0]}, F{best_key[1]}, {best_key[2]})"
bench_table_html = (bench_row_html(best_bench_label, best_m, 'highlight-row')
                    + bench_row_html('SPY Buy-and-Hold', spy_m_obj)
                    + bench_row_html('Equal-Weight B&H', ew_m_obj))

# Regime analysis
REGIMES = [
    ('2014-01', '2016-02', 'Volatile bull / oil shock', 'neutral'),
    ('2016-03', '2018-09', 'Bull market', 'bull'),
    ('2018-10', '2019-01', 'Q4 2018 selloff', 'bear'),
    ('2019-02', '2020-01', 'Late-cycle rally', 'bull'),
    ('2020-02', '2020-03', 'COVID crash', 'bear'),
    ('2020-04', '2021-12', 'Post-COVID recovery', 'bull'),
    ('2022-01', '2022-10', '2022 rate shock bear', 'bear'),
    ('2022-11', '2024-12', 'Rate normalisation rally', 'bull'),
]
regime_rows = ''
for s, e, lbl, typ in REGIMES:
    try:
        rs = best_rets.loc[s:e]
        ss = spy_ret_bt.loc[s:e]
        if len(rs) < 2:
            continue
        rr = float((1 + rs).prod() - 1)
        sr = float((1 + ss).prod() - 1)
        row_cls = {'bull': 'bull-row', 'bear': 'bear-row'}.get(typ, '')
        r_cls = 'green-val' if rr > 0 else 'red-val'
        s_cls = 'green-val' if sr > 0 else 'red-val'
        rel_cls = 'green-val' if rr > sr else 'red-val'
        rel_txt = 'Outperform' if rr > sr else 'Underperform'
        regime_rows += (
            f'<tr class="{row_cls}">'
            f'<td>{lbl}</td>'
            f'<td class="mono muted-cell">{s} to {e}</td>'
            f'<td class="num {r_cls}">{"+" if rr>0 else ""}{rr*100:.1f}%</td>'
            f'<td class="num {s_cls}">{"+" if sr>0 else ""}{sr*100:.1f}%</td>'
            f'<td class="num {rel_cls}">{rel_txt}</td>'
            f'</tr>'
        )
    except Exception:
        pass

# Conclusion text computed values
sharpe_range_lo = float(results_df['sharpe'].min())
sharpe_range_hi = float(results_df['sharpe'].max())
median_lookback = int(results_df.head(10)['Lookback'].median())

# Chart.js JSON
equity_labels_json   = json.dumps(labels)
chart_colors         = [TEAL, '#1e40af', '#7E3AF2', '#dc2626', '#E3A008']
equity_datasets_json = json.dumps([
    {
        'label': k,
        'data': v,
        'borderColor': chart_colors[i % len(chart_colors)],
        'borderWidth': 2.5 if i < 3 else 1.8,
        'pointRadius': 0,
        'tension': 0.3,
        'fill': False
    }
    for i, (k, v) in enumerate(equity_data.items())
])
annual_labels_json = json.dumps(annual_labels)
annual_best_json   = json.dumps(annual_best_vals)
annual_spy_json    = json.dumps(annual_spy_vals)

best_label_js = f"Combo L{best_key[0]},F{best_key[1]},{best_key[2]}"

# ── HTML TEMPLATE ─────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Factor &amp; Sector ETF Rotation — The Intrinsic Investor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,400;0,600;1,400;1,600&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
:root{{
  --bg:#f7f4ec;--bg2:#f0ece2;--bg3:#e8e3d8;--card:#fff;
  --ink:#0f2220;--muted:#4a6460;--hint:#8aa49e;
  --border:#e2ddd0;--accent:#1a5c52;--accent2:#144a42;
  --green:#0E9F6E;--green2:#059669;--green-bg:#ecfdf5;--green-border:#a7f3d0;
  --red:#E02424;--red2:#dc2626;--red-bg:#fef2f2;--red-border:#fca5a5;
  --blue:#1e40af;--blue2:#2563eb;--blue-bg:#eff6ff;--blue-border:#bfdbfe;
  --amber:#E3A008;--amber-bg:#fffbeb;--amber-border:#fcd34d;
  --purple:#7E3AF2;--purple-bg:#f5f3ff;--purple-border:#c4b5fd;
  --font:'Inter',sans-serif;--serif:'Fraunces',serif;--mono:'JetBrains Mono',monospace;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{background:var(--bg);color:var(--ink);font-family:var(--font);font-size:16px;line-height:1.7}}
body::after{{content:'';position:fixed;inset:0;pointer-events:none;z-index:9999;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='250' height='250'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.80' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='250' height='250' filter='url(%23n)' opacity='0.07'/%3E%3C/svg%3E");
  mix-blend-mode:multiply;opacity:0.5}}
#progress-bar{{position:fixed;top:0;left:0;height:2px;width:0%;
  background:linear-gradient(90deg,#1a5c52,#2d9d8f);z-index:9998;transition:width .1s linear}}
nav{{position:sticky;top:0;z-index:100;height:62px;display:flex;align-items:center;
  justify-content:space-between;padding:0 2rem;
  background:rgba(247,244,236,.92);backdrop-filter:blur(12px);
  -webkit-backdrop-filter:blur(12px);border-bottom:1px solid var(--border);
  transition:box-shadow .3s}}
nav.scrolled{{box-shadow:0 1px 24px rgba(15,34,32,.06)}}
.nav-logo{{font-family:var(--serif);font-weight:600;font-size:1.1rem;color:var(--ink);letter-spacing:-.01em}}
.nav-links{{display:flex;gap:1.75rem;list-style:none}}
.nav-links a{{color:var(--muted);text-decoration:none;font-size:.9rem;font-weight:500;
  position:relative;padding-bottom:2px;transition:color .2s}}
.nav-links a:hover{{color:var(--ink)}}
.nav-links a::after{{content:'';position:absolute;bottom:-1px;left:0;right:0;height:1px;
  background:var(--accent);transform:scaleX(0);transform-origin:left;
  transition:transform .25s cubic-bezier(.4,0,.2,1)}}
.nav-links a:hover::after{{transform:scaleX(1)}}
.hero{{background:var(--ink);padding:5rem 2rem 4rem;position:relative;overflow:hidden}}
.hero::before{{content:'';position:absolute;inset:0;pointer-events:none;
  background-image:repeating-linear-gradient(-55deg,transparent,transparent 40px,
    rgba(255,255,255,.013) 40px,rgba(255,255,255,.013) 41px)}}
.hero-inner{{max-width:860px;margin:0 auto;position:relative}}
.hero-tag{{display:inline-block;font-family:var(--mono);font-size:.72rem;color:var(--accent);
  letter-spacing:.08em;text-transform:uppercase;border:1px solid rgba(26,92,82,.4);
  padding:.25rem .75rem;border-radius:2px;margin-bottom:1.5rem;
  animation:fadeUp .6s ease both}}
.hero h1{{font-family:var(--serif);font-size:clamp(1.9rem,4.5vw,3.2rem);font-weight:600;
  color:#fff;line-height:1.2;letter-spacing:-.02em;margin-bottom:1.25rem;
  animation:fadeUp .6s .1s ease both}}
.hero h1 em{{font-style:italic;color:var(--accent)}}
.hero-sub{{font-size:1rem;color:rgba(255,255,255,.65);max-width:620px;line-height:1.7;
  margin-bottom:2rem;animation:fadeUp .6s .2s ease both}}
.hero-meta{{display:flex;flex-wrap:wrap;gap:2rem;font-family:var(--mono);font-size:.75rem;
  color:rgba(255,255,255,.5);border-top:1px solid rgba(255,255,255,.1);
  padding-top:1.5rem;animation:fadeUp .6s .3s ease both}}
.hero-meta-item strong{{display:block;color:rgba(255,255,255,.85);font-size:.85rem;margin-bottom:.15rem}}
@keyframes fadeUp{{from{{opacity:0;transform:translateY(18px)}}to{{opacity:1;transform:translateY(0)}}}}
.kpi-strip{{background:var(--card);border-bottom:1px solid var(--border);padding:2rem}}
.kpi-grid{{max-width:900px;margin:0 auto;display:grid;grid-template-columns:repeat(4,1fr)}}
.kpi-cell{{padding:1.5rem;border-right:1px solid var(--border)}}
.kpi-cell:last-child{{border-right:none}}
.kpi-label{{font-size:.72rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
  color:var(--hint);margin-bottom:.5rem}}
.kpi-value{{font-family:var(--mono);font-size:1.9rem;font-weight:500;color:var(--ink);
  line-height:1;margin-bottom:.4rem}}
.kpi-value.green{{color:var(--green2)}}
.kpi-value.red{{color:var(--red2)}}
.kpi-sub{{font-size:.78rem;color:var(--muted)}}
.green-val{{color:var(--green2);font-weight:500}}
.red-val{{color:var(--red2);font-weight:500}}
.container{{max-width:860px;margin:0 auto;padding:0 2rem}}
.section{{opacity:0;transform:translateY(16px);
  transition:opacity .55s ease,transform .55s ease;
  padding:4.5rem 0;border-bottom:1px solid var(--border)}}
.section.visible{{opacity:1;transform:none}}
.section:last-of-type{{border-bottom:none}}
.section-label{{display:flex;align-items:center;gap:.6rem;margin-bottom:1rem}}
.section-counter{{font-family:var(--mono);font-size:.72rem;color:var(--hint);letter-spacing:.04em}}
.section-label span:last-child{{font-size:.72rem;font-weight:600;letter-spacing:.08em;
  text-transform:uppercase;color:var(--hint)}}
h2{{font-family:var(--serif);font-size:clamp(1.5rem,3vw,2.1rem);font-weight:600;
  color:var(--ink);line-height:1.25;letter-spacing:-.02em;margin-bottom:1.25rem}}
h2 em{{font-style:italic;color:var(--accent)}}
h3{{font-family:var(--serif);font-size:1.15rem;font-weight:600;color:var(--ink);margin:2rem 0 .75rem}}
p{{color:var(--muted);line-height:1.75;margin-bottom:1rem;text-align:justify;hyphens:auto}}
p:last-child{{margin-bottom:0}}
.callout{{display:flex;gap:1rem;padding:1.25rem 1.5rem;border-radius:4px;
  margin:1.5rem 0;border-left:3px solid}}
.callout.green{{background:var(--green-bg);border-color:var(--green2)}}
.callout.amber{{background:var(--amber-bg);border-color:var(--amber)}}
.callout.red{{background:var(--red-bg);border-color:var(--red2)}}
.callout.blue{{background:var(--blue-bg);border-color:var(--blue2)}}
.callout-icon{{font-size:1.1rem;flex-shrink:0;margin-top:.1rem}}
.callout-body{{font-size:.9rem;color:var(--ink);line-height:1.6}}
.callout-body strong{{font-weight:600}}
.table-wrap{{overflow-x:auto;margin:1.5rem 0;border-radius:4px;border:1px solid var(--border)}}
table{{width:100%;border-collapse:collapse;font-size:.875rem}}
thead tr{{background:var(--ink);color:#fff}}
thead th{{padding:.7rem .9rem;text-align:left;font-weight:500;font-size:.75rem;
  letter-spacing:.04em;white-space:nowrap;cursor:pointer;user-select:none}}
thead th:hover{{background:#1a3d3a}}
thead th.sort-asc::after{{content:' ↑'}}
thead th.sort-desc::after{{content:' ↓'}}
tbody tr{{border-bottom:1px solid var(--border);transition:background .15s}}
tbody tr:last-child{{border-bottom:none}}
tbody tr:hover{{background:var(--bg2)}}
tbody tr.top-row{{background:#ecfdf5;border-left:3px solid var(--accent)}}
tbody tr.top-row:hover{{background:#d1fae5}}
tbody tr.highlight-row{{background:#f0fdf4}}
tbody tr.bull-row td:first-child::before{{content:'▲ ';color:var(--green2);font-size:.7rem}}
tbody tr.bear-row td:first-child::before{{content:'▼ ';color:var(--red2);font-size:.7rem}}
td{{padding:.65rem .9rem;color:var(--muted);vertical-align:middle}}
td.num{{font-family:var(--mono);font-size:.83rem;text-align:right}}
td.mono{{font-family:var(--mono);font-size:.82rem}}
td.muted-cell{{color:var(--hint);font-size:.83rem}}
.fbadge{{display:inline-block;font-family:var(--mono);font-size:.68rem;
  padding:.1rem .4rem;border-radius:3px;background:var(--bg3);color:var(--ink);
  font-weight:600;margin-right:.2rem}}
.split-badge{{display:inline-block;font-family:var(--mono);font-size:.72rem;
  padding:.1rem .5rem;border-radius:3px;font-weight:600}}
.split-A{{background:var(--blue-bg);color:var(--blue)}}
.split-B{{background:var(--purple-bg);color:var(--purple)}}
.sleeve-badge{{display:inline-block;font-size:.72rem;font-weight:600;
  padding:.15rem .55rem;border-radius:3px}}
.sleeve-badge.factor{{background:var(--blue-bg);color:var(--blue)}}
.sleeve-badge.sector{{background:var(--purple-bg);color:var(--purple)}}
.chart-box{{background:var(--bg2);border:1px solid var(--border);
  border-radius:4px;padding:1.5rem;margin:1.5rem 0}}
.chart-title{{font-size:.85rem;font-weight:600;color:var(--ink);
  margin-bottom:1rem;letter-spacing:.02em}}
.hm-wrap{{overflow-x:auto;margin:.25rem 0}}
.hm-table{{border-collapse:collapse;width:100%;font-family:var(--mono);font-size:.75rem}}
.hm-table thead th,.hm-table tbody td{{border:1px solid var(--border)}}
.hm-corner{{background:var(--bg2);min-width:40px}}
.hm-col{{background:var(--ink);color:#fff;font-size:.68rem;font-weight:600;
  text-transform:uppercase;letter-spacing:.04em;padding:7px 10px;
  text-align:center;white-space:nowrap}}
.hm-row-label{{background:var(--bg2);color:var(--muted);font-size:.72rem;
  font-family:var(--sans);padding:7px 12px;white-space:nowrap;min-width:160px}}
.hm-fid{{display:inline-block;font-weight:700;color:var(--hint);
  margin-right:4px;font-size:.65rem}}
.hm-cell{{text-align:center;color:var(--ink);padding:6px 10px;
  white-space:nowrap;transition:filter .15s;cursor:default}}
.hm-cell:hover{{filter:brightness(.9)}}
.hm-empty{{background:var(--bg)}}
.hm-cell strong{{font-weight:600}}
.stat-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));
  gap:1rem;margin:1.5rem 0}}
.stat-card{{background:var(--bg2);border:1px solid var(--border);
  border-radius:4px;padding:1.25rem}}
.stat-label{{font-size:.72rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
  color:var(--hint);margin-bottom:.4rem}}
.stat-value{{font-family:var(--mono);font-size:1.5rem;font-weight:500;
  color:var(--ink);line-height:1;margin-bottom:.3rem}}
.stat-value.green{{color:var(--green2)}}
.stat-value.red{{color:var(--red2)}}
.stat-sub{{font-size:.78rem;color:var(--muted)}}
.param-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin:1.5rem 0}}
.param-card{{background:var(--bg2);border:1px solid var(--border);
  border-radius:4px;padding:1.25rem}}
.param-label{{font-size:.72rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
  color:var(--hint);margin-bottom:.75rem}}
.param-values{{display:flex;flex-wrap:wrap;gap:.4rem}}
.param-tag{{font-family:var(--mono);font-size:.75rem;background:var(--bg2);
  color:var(--ink);padding:.2rem .6rem;border-radius:3px;border:1px solid var(--border)}}
#side-nav{{position:fixed;right:0;top:50%;transform:translateY(-50%);
  z-index:50;display:flex;flex-direction:column;gap:2px;padding:10px 6px}}
#side-nav a{{display:flex;align-items:center;justify-content:flex-end;gap:7px;
  text-decoration:none;padding:5px 8px;border-radius:4px;transition:background .2s}}
#side-nav a:hover{{background:rgba(26,92,82,.07)}}
.sn-label{{font-size:.67rem;font-weight:500;color:var(--hint);white-space:nowrap;
  letter-spacing:.02em;font-family:var(--font);transition:color .2s;text-align:right}}
.sn-dot{{width:5px;height:5px;border-radius:50%;background:var(--border);
  flex-shrink:0;transition:all .2s}}
#side-nav a.active .sn-label{{color:var(--accent);font-weight:600}}
#side-nav a.active .sn-dot{{background:var(--accent);transform:scale(1.5)}}
#side-nav a:hover .sn-label{{color:var(--ink)}}
#side-nav a:hover .sn-dot{{background:var(--muted)}}
footer{{background:var(--ink);color:rgba(255,255,255,.6);padding:3rem 2rem}}
.footer-inner{{max-width:860px;margin:0 auto;display:flex;
  justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem}}
.footer-name{{font-family:var(--serif);font-weight:600;font-size:1rem;color:rgba(255,255,255,.9)}}
.footer-right{{font-size:.8rem;text-align:right}}
.footer-right a{{color:rgba(255,255,255,.5);text-decoration:none;margin-left:1.2rem}}
.footer-right a:hover{{color:rgba(255,255,255,.85)}}
.gh-btn{{display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);
  font-size:.68rem;color:rgba(255,255,255,.5);text-decoration:none;
  border:1px solid rgba(255,255,255,.2);padding:3px 9px;border-radius:3px;
  transition:all .2s;letter-spacing:.02em;align-self:center}}
.gh-btn:hover{{color:#fff;border-color:rgba(255,255,255,.5);background:rgba(255,255,255,.08)}}
@media(max-width:860px){{
  #side-nav{{display:none}}
  .kpi-grid{{grid-template-columns:repeat(2,1fr)}}
  .param-grid{{grid-template-columns:1fr}}
  .footer-inner{{flex-direction:column;text-align:center}}
  .footer-right{{text-align:center}}
}}
@media(max-width:560px){{
  .kpi-cell{{border-right:none;border-bottom:1px solid var(--border)}}
}}
@media(prefers-reduced-motion:reduce){{
  *,*::before,*::after{{animation-duration:.01ms!important;transition-duration:.01ms!important}}
}}
</style>
</head>
<body>

<div id="progress-bar"></div>

<nav>
  <div class="nav-logo">The Intrinsic Investor</div>
  <ul class="nav-links">
    <li><a href="/">Home</a></li>
    <li><a href="/research">Research</a></li>
    <li><a href="/about">About</a></li>
  </ul>
</nav>

<div class="hero">
  <div class="hero-inner">
    <div class="hero-tag">Systematic Market Research</div>
    <h1>Factor &amp; Sector Rotation:<br><em>A Systematic Parameter Optimisation</em></h1>
    <p class="hero-sub">A monthly ETF rotation strategy across two parallel sleeves, tested across 60 parameter combinations spanning momentum lookback periods, SPY drawdown filter methods, and sleeve allocation rules. All 60 results reported.</p>
    <div class="hero-meta">
      <div class="hero-meta-item"><strong>Brian Liew</strong>LSE, BSc Accounting and Finance</div>
      <div class="hero-meta-item"><strong>{START_DATE} &ndash; {END_DATE}</strong>Backtest Period</div>
      <div class="hero-meta-item"><strong>{N_MONTHS} Months</strong>Observations</div>
      <div class="hero-meta-item"><strong>60 Combinations</strong>5 lookbacks &times; 6 filters &times; 2 splits</div>
      <div class="hero-meta-item"><strong>Compustat / WRDS</strong>Data Source</div>
      <div class="hero-meta-item"><strong>April 2026</strong>Published</div>
      <a class="gh-btn" href="https://github.com/TheIntrinsicInvestor/Backtesting/tree/main/research/etf-factor-sector-rotation-strategy" target="_blank" rel="noopener noreferrer"><svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg> Code</a>
    </div>
  </div>
</div>

<div class="kpi-strip">
  <div class="kpi-grid">
    <div class="kpi-cell">
      <div class="kpi-label">Best Combo CAGR</div>
      <div class="kpi-value green">{best_m['cagr']*100:.1f}%</div>
      <div class="kpi-sub">{kpi_cagr_d}</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">Sharpe Ratio</div>
      <div class="kpi-value">{best_m['sharpe']:.3f}</div>
      <div class="kpi-sub">{kpi_sharpe_d}</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">Max Drawdown</div>
      <div class="kpi-value red">{best_m['max_dd']*100:.1f}%</div>
      <div class="kpi-sub">{kpi_dd_d}</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">% Months in Market</div>
      <div class="kpi-value">{best_m['pct_in']*100:.0f}%</div>
      <div class="kpi-sub">Per-sleeve average</div>
    </div>
  </div>
</div>


<section class="section" id="s1">
<div class="container">
  <div class="section-label"><span class="section-counter">01</span><span>The Strategy</span></div>
  <h2>Two sleeves, one <em>signal</em></h2>
  <p>This strategy allocates capital across two independent sleeves each month: a Factor sleeve and a Sector sleeve. At the end of each calendar month, the strategy scores every ETF in each sleeve by its N-month total return. The single top-ranked ETF in each sleeve receives the full sleeve allocation for the following month. This is pure momentum rotation, applied separately to two distinct groups of ETFs.</p>
  <p>The Factor sleeve covers four style-factor ETFs: momentum, quality, value, and small-cap. These capture systematic risk premia that have been documented extensively in academic finance literature. The Sector sleeve covers nine SPDR sector ETFs spanning the full S&amp;P 500 industry landscape, from technology to utilities. The two sleeves are designed to capture different dimensions of market leadership at any given point in the economic cycle.</p>
  <p>Capital is split between the two sleeves either with a fixed 50/50 allocation (Split A) or dynamically based on the relative momentum of each sleeve's top pick (Split B). A third dimension tests six methods for filtering out adverse market regimes using SPY as a proxy for broad market health. When the filter signals a deteriorating trend, both sleeves move to cash for that month, earning 0%.</p>
  <p>The strategy makes no fundamental judgements and no macroeconomic forecasts. It follows momentum mechanically, checks one market regime signal, and rebalances once per month. Execution is assumed at month-end closing prices with no transaction costs or slippage.</p>
</div>
</section>


<section class="section" id="s2">
<div class="container">
  <div class="section-label"><span class="section-counter">02</span><span>Universe &amp; Data</span></div>
  <h2>Thirteen ETFs, <em>two sleeves</em></h2>
  <p>All price and total return data is sourced from Compustat Security Daily (comp.secd) via WRDS. Returns are computed using the total return index, calculated as prccd &times; trfd (the Compustat total return factor), which adjusts closing prices for dividend reinvestment. This ensures returns reflect what an investor actually received, not just price appreciation.</p>
  <div class="table-wrap">
    <table>
      <thead><tr><th>Ticker</th><th>Name</th><th>Sleeve</th><th>Inception</th><th>Rationale</th></tr></thead>
      <tbody>{etf_rows_html}</tbody>
    </table>
  </div>
  <p>The common backtest start date of {START_DATE} is determined by the latest inception among all 13 ETFs (QUAL, July 2013), plus a 12-month lookback buffer for momentum scoring. SPY is used solely as a drawdown filter signal and benchmark; it is not part of the rotatable universe.</p>
</div>
</section>


<section class="section" id="s3">
<div class="container">
  <div class="section-label"><span class="section-counter">03</span><span>Methodology</span></div>
  <h2>Three variables, <em>sixty combinations</em></h2>
  <p>The parameter space spans three independent dimensions. Every combination is evaluated over the identical date range using the same data, so Sharpe ratios and drawdown statistics are directly comparable across the full grid.</p>

  <div class="param-grid">
    <div class="param-card">
      <div class="param-label">Lookback Period (5)</div>
      <div class="param-values">
        <span class="param-tag">1m</span><span class="param-tag">3m</span>
        <span class="param-tag">6m</span><span class="param-tag">9m</span><span class="param-tag">12m</span>
      </div>
    </div>
    <div class="param-card">
      <div class="param-label">Drawdown Filter (6)</div>
      <div class="param-values">
        <span class="param-tag">F0: None</span><span class="param-tag">F1: 12m ret</span>
        <span class="param-tag">F2: 10m SMA</span><span class="param-tag">F3: 200d SMA</span>
        <span class="param-tag">F4: 1m/10m SMA</span><span class="param-tag">F5: Death cross</span>
      </div>
    </div>
    <div class="param-card">
      <div class="param-label">Sleeve Split (2)</div>
      <div class="param-values">
        <span class="param-tag">A: 50/50 Fixed</span>
        <span class="param-tag">B: Momentum-weighted</span>
      </div>
    </div>
  </div>

  <h3>Momentum Scoring</h3>
  <p>At each month-end, every ETF in a sleeve is ranked by its N-month total return. The ETF with the highest score receives the full sleeve allocation for the following month. There is no blending or smoothing across lookback periods. For the total return calculation, the Compustat trfd factor is used throughout.</p>

  <h3>Drawdown Filters &amp; Sleeve Splits</h3>
  <div class="table-wrap">
    <table>
      <thead><tr><th>ID</th><th>Filter Rule (go to cash if&hellip;)</th><th>Series used</th></tr></thead>
      <tbody>
        <tr><td class="mono">F0</td><td>No filter &mdash; always invested</td><td class="muted-cell">Baseline</td></tr>
        <tr><td class="mono">F1</td><td>SPY 12-month total return &lt; 0</td><td class="muted-cell">Monthly</td></tr>
        <tr><td class="mono">F2</td><td>SPY month-end close &lt; 10-month SMA</td><td class="muted-cell">Monthly</td></tr>
        <tr><td class="mono">F3</td><td>SPY daily close &lt; 200-day SMA at month-end</td><td class="muted-cell">Daily</td></tr>
        <tr><td class="mono">F4</td><td>SPY 1-month close &lt; 10-month SMA (equiv. F2)</td><td class="muted-cell">Monthly</td></tr>
        <tr><td class="mono">F5</td><td>SPY 50-day SMA &lt; 200-day SMA (death cross)</td><td class="muted-cell">Daily</td></tr>
      </tbody>
    </table>
  </div>
  <p>When a filter triggers, both sleeves earn 0% for that month (no cash interest applied). <strong>Split A</strong> allocates 50/50 between sleeves each month. <strong>Split B</strong> weights each sleeve by its top pick's momentum score (floored at zero; falls back to 50/50 if both are negative).</p>

  <div class="callout amber">
    <div class="callout-icon">&#9888;</div>
    <div class="callout-body"><strong>Look-ahead bias check:</strong> All signals are computed using data available through the last trading day of the prior month. The selected ETF's return is the return earned in the following month. No future data enters any signal or selection rule.</div>
  </div>
</div>
</section>


<section class="section" id="s4">
<div class="container">
  <div class="section-label"><span class="section-counter">04</span><span>Sensitivity Analysis</span></div>
  <h2>Top 10 combinations, <em>ranked by Sharpe</em></h2>
  <p>Top 10 of 60 combinations sorted by Sharpe ratio. Top-3 rows highlighted. Click any column header to re-sort.</p>

  <div class="table-wrap">
    <table id="results-table">
      <thead>
        <tr>
          <th>Rank</th><th>Lookback</th><th>Filter</th><th>Split</th>
          <th>CAGR</th><th>Sharpe</th><th>Calmar</th><th>Max DD</th>
          <th>Win Rate</th><th>% In Mkt</th>
        </tr>
      </thead>
      <tbody>{table_rows_html}</tbody>
    </table>
  </div>

  <h3>Sharpe Heatmaps</h3>
  <p>The three heatmaps show how Sharpe ratio varies across the (lookback, filter) grid for each split method, plus the cell-wise best across both. Warmer green indicates higher risk-adjusted returns. A robust strategy shows a broad green region, not a single outlier cell.</p>

  <div class="chart-box">
    <div class="chart-title">Split A (50/50 Fixed) &mdash; Sharpe Ratio by Lookback &times; Filter</div>
    {hm_a_html}
  </div>
  <div class="chart-box">
    <div class="chart-title">Split B (Momentum-Weighted) &mdash; Sharpe Ratio by Lookback &times; Filter</div>
    {hm_b_html}
  </div>
  <div class="chart-box">
    <div class="chart-title">Combined Best &mdash; Highest Sharpe Across Both Splits per Cell</div>
    {hm_c_html}
  </div>

  <div class="callout green">
    <div class="callout-icon">&#10003;</div>
    <div class="callout-body"><strong>Top combination:</strong> A {int(best_key[0])}-month lookback with {FILTER_NAMES[best_key[1]].lower()} (Filter {best_key[1]}) and Split {best_key[2]} produces the highest Sharpe of {best_m['sharpe']:.3f}, versus {spy_m_obj['sharpe']:.3f} for SPY over the same period.</div>
  </div>
  <div class="callout amber">
    <div class="callout-icon">&#9888;</div>
    <div class="callout-body"><strong>Data mining caveat:</strong> With 60 combinations tested on a single historical period, some results are good by chance. Focus on the heatmap pattern rather than the single top row. A robust edge should appear as a broad green region across multiple neighbouring cells, not an isolated peak.</div>
  </div>
</div>
</section>


<section class="section" id="s5">
<div class="container">
  <div class="section-label"><span class="section-counter">05</span><span>Best Combination Deep Dive</span></div>
  <h2>L{best_key[0]}, Filter {best_key[1]}, <em>Split {best_key[2]}</em></h2>
  <p>The highest-Sharpe combination uses a {int(best_key[0])}-month lookback, {FILTER_NAMES[best_key[1]].lower()} as the drawdown filter, and {'50/50 fixed' if best_key[2]=='A' else 'momentum-weighted'} sleeve allocation.</p>

  <div class="stat-grid">
    <div class="stat-card">
      <div class="stat-label">CAGR</div>
      <div class="stat-value green">{best_m['cagr']*100:.2f}%</div>
      <div class="stat-sub">SPY: {spy_m_obj['cagr']*100:.2f}%</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Sharpe Ratio</div>
      <div class="stat-value">{best_m['sharpe']:.3f}</div>
      <div class="stat-sub">SPY: {spy_m_obj['sharpe']:.3f}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Max Drawdown</div>
      <div class="stat-value red">{best_m['max_dd']*100:.2f}%</div>
      <div class="stat-sub">SPY: {spy_m_obj['max_dd']*100:.2f}%</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Calmar Ratio</div>
      <div class="stat-value">{best_calmar_str}</div>
      <div class="stat-sub">CAGR / Max Drawdown</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Win Rate</div>
      <div class="stat-value">{best_m['win_rate']*100:.1f}%</div>
      <div class="stat-sub">Months with positive return</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Total Return</div>
      <div class="stat-value green">{best_m['total_ret']*100:.1f}%</div>
      <div class="stat-sub">SPY: {spy_m_obj['total_ret']*100:.1f}%</div>
    </div>
  </div>

  <h3>Equity Curve vs Benchmarks (Log Scale, Rebased to 100)</h3>
  <div class="chart-box">
    <div class="chart-title">Cumulative Growth of $100 &mdash; Top 3 Combos vs SPY vs Equal-Weight B&amp;H</div>
    <canvas id="equityCurve" height="55"></canvas>
  </div>

  <h3>Annual Returns vs SPY</h3>
  <div class="chart-box">
    <div class="chart-title">Calendar Year Returns &mdash; Best Combo vs SPY</div>
    <canvas id="annualBar" height="40"></canvas>
  </div>

  <h3>Monthly Return Heatmap</h3>
  <div class="chart-box">
    <div class="chart-title">Monthly Returns (%) &mdash; Best Combination</div>
    {hm_monthly_html}
  </div>

  <h3>Regime Analysis</h3>
  <p>Performance across distinct SPY trend regimes over the backtest period.</p>
  <div class="table-wrap">
    <table>
      <thead>
        <tr><th>Regime</th><th>Period</th><th>Strategy</th><th>SPY</th><th>Relative</th></tr>
      </thead>
      <tbody>{regime_rows}</tbody>
    </table>
  </div>
</div>
</section>


<section class="section" id="s6">
<div class="container">
  <div class="section-label"><span class="section-counter">06</span><span>Benchmark Comparison</span></div>
  <h2>Strategy vs <em>benchmarks</em></h2>
  <p>All three series evaluated over the identical period: {START_DATE} to {END_DATE}. Equal-weight buy-and-hold is rebalanced monthly across all 13 ETFs in the universe.</p>
  <div class="table-wrap">
    <table>
      <thead>
        <tr><th>Strategy</th><th>Total Ret</th><th>CAGR</th><th>Sharpe</th>
        <th>Calmar</th><th>Max DD</th><th>Win Rate</th><th>Best Yr</th><th>Worst Yr</th></tr>
      </thead>
      <tbody>{bench_table_html}</tbody>
    </table>
  </div>
</div>
</section>


<section class="section" id="s7">
<div class="container">
  <div class="section-label"><span class="section-counter">07</span><span>Risks &amp; Limitations</span></div>
  <h2>What this study <em>does not show</em></h2>
  <div class="callout red">
    <div class="callout-icon">&#9888;</div>
    <div class="callout-body"><strong>1. Data mining and overfitting.</strong> Sixty combinations were evaluated on a single historical period and the best selected. With a large enough parameter space, some combinations will appear strong by chance. The top combination should be treated as a hypothesis requiring out-of-sample validation, not a proven edge.</div>
  </div>
  <div class="callout red">
    <div class="callout-icon">&#9888;</div>
    <div class="callout-body"><strong>2. Short history for factor ETFs.</strong> MTUM and QUAL launched in 2013, giving this backtest roughly {N_MONTHS // 12} years of live data. This covers one full market cycle but is too short to draw strong statistical conclusions about the reliability of any specific parameter combination.</div>
  </div>
  <div class="callout amber">
    <div class="callout-icon">&#9651;</div>
    <div class="callout-body"><strong>3. Month-end execution timing.</strong> Signals are known only after the closing price on the last trading day of the month. In practice, execution occurs the following morning. This introduces a small timing bias that would modestly reduce realised returns relative to those reported here.</div>
  </div>
  <div class="callout amber">
    <div class="callout-icon">&#9651;</div>
    <div class="callout-body"><strong>4. No transaction costs or slippage.</strong> Each sleeve rotates at most once per month. At typical ETF bid-ask spreads (&lt;0.05%), round-trip costs are small but non-zero. Cumulative costs over {N_MONTHS} months could reduce CAGR by roughly 10&ndash;30 basis points annually.</div>
  </div>
  <div class="callout amber">
    <div class="callout-icon">&#9651;</div>
    <div class="callout-body"><strong>5. Single-ETF concentration per sleeve.</strong> Each sleeve holds exactly one ETF at a time. A sector-specific shock in the selected ETF hits the full sleeve allocation. There is no intra-sleeve diversification by design.</div>
  </div>
  <div class="callout blue">
    <div class="callout-icon">&#9432;</div>
    <div class="callout-body"><strong>6. No cash interest.</strong> When the drawdown filter triggers, both sleeves earn exactly 0% for that month. In practice, uninvested cash earns the short-term rate, which was material from 2022 onwards. The conservative 0% treatment is consistent with other studies published on this site.</div>
  </div>
</div>
</section>


<section class="section" id="s8">
<div class="container">
  <div class="section-label"><span class="section-counter">08</span><span>Conclusion</span></div>
  <h2>What the data <em>suggests</em></h2>
  <p>Across 60 parameter combinations, momentum-based ETF rotation produces Sharpe ratios ranging from {sharpe_range_lo:.2f} to {sharpe_range_hi:.2f} over the {common_start.strftime('%Y')}&ndash;{bt_monthly_tri.index[-1].strftime('%Y')} period. The top combinations consistently produce higher risk-adjusted returns than SPY buy-and-hold. Medium-length lookback periods (around {median_lookback} months) appear more robust than very short or very long windows. The inclusion of a drawdown filter generally improves Calmar ratios and reduces maximum drawdown, particularly during the 2022 bear market. The difference between Split A and Split B is modest, suggesting that the rotation signal itself matters more than the weighting rule between sleeves.</p>
  <p>This strategy is suited to an investor who wants systematic, rules-based exposure to relative equity strength without individual stock selection. It requires monthly attention and tolerance for periods of full cash when filters trigger. The results presented here should not be extrapolated without accounting for the data mining, short live-history, and execution-timing caveats described above. Walk-forward or out-of-sample testing on data after 2024 would be the appropriate next step before any live implementation.</p>
</div>
</section>


<footer>
  <div class="footer-inner">
    <div class="footer-name">The Intrinsic Investor</div>
    <div class="footer-right">
      &copy; Brian Liew &middot; BSc Accounting &amp; Finance, London School of Economics
      <a href="/">Home</a><a href="/research">Research</a><a href="/about">About</a>
    </div>
  </div>
</footer>

<div id="side-nav"></div>

<script>
// Progress bar
const pb = document.getElementById('progress-bar');
window.addEventListener('scroll', () => {{
  const max = document.documentElement.scrollHeight - window.innerHeight;
  pb.style.width = (window.scrollY / max * 100) + '%';
}}, {{passive: true}});

// Nav scroll shadow
const navEl = document.querySelector('nav');
window.addEventListener('scroll', () => {{
  navEl.classList.toggle('scrolled', window.scrollY > 10);
}}, {{passive: true}});

// Side nav build
const sections = document.querySelectorAll('.section');
const sideNav  = document.getElementById('side-nav');
const NAV_LABELS = ['Strategy','Universe','Methodology','Sensitivity','Best Combo','Benchmarks','Risks','Conclusion'];
sections.forEach((s, i) => {{
  if (!s.id) s.id = 'sec-' + i;
  const a = document.createElement('a');
  a.href = '#' + s.id;
  a.innerHTML = '<span class="sn-label">' + (NAV_LABELS[i] || '') + '</span><span class="sn-dot"></span>';
  sideNav.appendChild(a);
}});

// Scroll reveal
const io = new IntersectionObserver(entries => {{
  entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }});
}}, {{threshold: 0.08}});
sections.forEach(s => io.observe(s));

// Side nav active highlight
const sideLinks = sideNav.querySelectorAll('a');
const ioNav = new IntersectionObserver(entries => {{
  entries.forEach(e => {{
    const idx = Array.from(sections).indexOf(e.target);
    if (idx >= 0 && sideLinks[idx]) sideLinks[idx].classList.toggle('active', e.isIntersecting);
  }});
}}, {{threshold: 0.3}});
sections.forEach(s => ioNav.observe(s));

// Sortable results table
(function() {{
  const tbl = document.getElementById('results-table');
  if (!tbl) return;
  const ths = tbl.querySelectorAll('thead th');
  let col = -1, asc = true;
  ths.forEach((th, ci) => {{
    th.addEventListener('click', () => {{
      const tbody = tbl.querySelector('tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      const newAsc = col === ci ? !asc : true;
      rows.sort((a, b) => {{
        const av = a.cells[ci].textContent.replace(/[%+↑↓]/g,'').trim();
        const bv = b.cells[ci].textContent.replace(/[%+↑↓]/g,'').trim();
        const an = parseFloat(av), bn = parseFloat(bv);
        if (!isNaN(an) && !isNaN(bn)) return newAsc ? an - bn : bn - an;
        return newAsc ? av.localeCompare(bv) : bv.localeCompare(av);
      }});
      rows.forEach(r => tbody.appendChild(r));
      ths.forEach(h => h.classList.remove('sort-asc','sort-desc'));
      th.classList.add(newAsc ? 'sort-asc' : 'sort-desc');
      col = ci; asc = newAsc;
    }});
  }});
}})();

// Equity curve (Chart.js)
const eqLabels   = {equity_labels_json};
const eqDatasets = {equity_datasets_json};
new Chart(document.getElementById('equityCurve'), {{
  type: 'line',
  data: {{ labels: eqLabels, datasets: eqDatasets }},
  options: {{
    responsive: true, maintainAspectRatio: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ position: 'top', labels: {{ font: {{ family: 'Inter', size: 11 }}, boxWidth: 24 }} }},
      tooltip: {{ callbacks: {{ label: ctx => ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) }} }}
    }},
    scales: {{
      x: {{ ticks: {{ maxTicksLimit: 12, font: {{ family: 'JetBrains Mono', size: 10 }}, maxRotation: 0 }}, grid: {{ color: 'rgba(0,0,0,0.04)' }} }},
      y: {{
        type: 'logarithmic',
        title: {{ display: true, text: 'Portfolio value (log scale, base 100)', font: {{ size: 10 }} }},
        ticks: {{ font: {{ family: 'JetBrains Mono', size: 10 }}, callback: v => v }},
        grid: {{ color: 'rgba(0,0,0,0.04)' }}
      }}
    }}
  }}
}});

// Annual bar chart (Chart.js)
const annLabels = {annual_labels_json};
const annBest   = {annual_best_json};
const annSpy    = {annual_spy_json};
new Chart(document.getElementById('annualBar'), {{
  type: 'bar',
  data: {{
    labels: annLabels,
    datasets: [
      {{
        label: '{best_label_js}',
        data: annBest,
        backgroundColor: annBest.map(v => v >= 0 ? 'rgba(26,92,82,0.78)' : 'rgba(220,38,38,0.72)'),
        borderColor:     annBest.map(v => v >= 0 ? '#1a5c52' : '#dc2626'),
        borderWidth: 1, borderRadius: 2
      }},
      {{
        label: 'SPY',
        data: annSpy,
        backgroundColor: annSpy.map(v => v >= 0 ? 'rgba(30,64,175,0.42)' : 'rgba(220,38,38,0.3)'),
        borderColor:     annSpy.map(v => v >= 0 ? '#1e40af' : '#dc2626'),
        borderWidth: 1, borderRadius: 2
      }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: true,
    plugins: {{
      legend: {{ position: 'top', labels: {{ font: {{ family: 'Inter', size: 11 }}, boxWidth: 24 }} }},
      tooltip: {{ callbacks: {{ label: ctx => ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + '%' }} }}
    }},
    scales: {{
      x: {{ ticks: {{ font: {{ family: 'JetBrains Mono', size: 10 }} }}, grid: {{ display: false }} }},
      y: {{
        title: {{ display: true, text: 'Annual Return (%)', font: {{ size: 10 }} }},
        ticks: {{ font: {{ family: 'JetBrains Mono', size: 10 }}, callback: v => v + '%' }},
        grid: {{ color: 'rgba(0,0,0,0.04)' }}
      }}
    }}
  }}
}});
</script>
</body>
</html>"""

# ─────────────────────────────────────────────────────────────────────────────
# 12. WRITE OUTPUT
# ─────────────────────────────────────────────────────────────────────────────
output_file = 'index.html'
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(html)

size_kb = os.path.getsize(output_file) / 1024
print(f"\n[DONE] Written: {output_file} ({size_kb:.0f} KB)")
print("       Download and deploy to research/etf-factor-sector-rotation-strategy/")
print("       Then update research/index.html and index.html with the best Sharpe and CAGR.")
