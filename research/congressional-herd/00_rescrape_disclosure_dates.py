"""
Re-scrape Capitol Trades with disclosure_date column captured.
Deletes existing data files and runs a full fresh scrape.
Runtime: ~9 minutes (368 pages at 1.5s each).
"""
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

for fname in ["all_trades.parquet", "_checkpoint.parquet"]:
    p = DATA_DIR / fname
    if p.exists():
        p.unlink()
        print(f"Removed {p.name}")

import scrape_capitol_trades
scrape_capitol_trades.main()
