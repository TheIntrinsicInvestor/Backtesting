"""
Scrape all congressional trades from capitoltrades.com.
Output: data/all_trades.parquet

Runtime: ~10 minutes (368 pages at 1.5s each).
Checkpoints every 50 pages so it can resume if interrupted.
"""

import time
import re
import os
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL = "https://www.capitoltrades.com/trades"
PAGE_SIZE = 96
DELAY = 1.5          # seconds between requests
CHECKPOINT_EVERY = 50
DATA_DIR = Path(__file__).parent / "data"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_page(session, page_num, retries=3):
    url = f"{BASE_URL}?pageSize={PAGE_SIZE}&page={page_num}"
    for attempt in range(retries):
        try:
            r = session.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.text
        except Exception as e:
            if attempt < retries - 1:
                print(f"    retry {attempt+1} for page {page_num}: {e}")
                time.sleep(3)
            else:
                raise


def get_total_pages(html):
    soup = BeautifulSoup(html, "html.parser")
    # Target the compact pagination label: class "hidden leading-7 sm:block"
    # which renders exactly "Page1of368" with no extra sibling text.
    for el in soup.find_all(class_="sm:block"):
        text = el.get_text(separator="", strip=True)
        m = re.fullmatch(r"Page\d+of(\d+)", text)
        if m:
            return int(m.group(1))
    # Fallback: scan all leaf text nodes for the pattern
    for el in soup.find_all(string=re.compile(r"Page\d+of\d+")):
        m = re.search(r"Page\d+of(\d+)$", el.strip())
        if m:
            return int(m.group(1))
    return None


def parse_trade_date(cell):
    """
    Trade date cell structure:
      <div class="text-size-3 font-medium">2 Apr</div>  <- day + month
      <div class="text-size-2 text-txt-dimmer">2026</div>  <- year
    Target the specific classes rather than all divs.
    """
    main = cell.find(class_="text-size-3")
    year_el = cell.find(class_=re.compile(r"text-txt-dimmer"))
    if main and year_el:
        main_text = main.get_text(strip=True)   # e.g. "2 Apr"
        year_text = year_el.get_text(strip=True)  # e.g. "2026"
        if year_text.isdigit():
            combined = f"{main_text} {year_text}"
            for fmt in ("%d %b %Y", "%b %Y"):
                try:
                    return datetime.strptime(combined, fmt)
                except ValueError:
                    continue
    return None


def parse_row(row):
    cells = row.find_all("td", recursive=False)
    if len(cells) < 7:
        return None

    # Politician
    name_el = row.find("a", href=re.compile(r"/politicians/"))
    name = name_el.get_text(strip=True) if name_el else ""
    if not name:
        return None

    party_el = row.find(class_=re.compile(r"party--"))
    party = party_el.get_text(strip=True) if party_el else ""

    chamber_el = row.find(class_=re.compile(r"chamber--"))
    chamber = chamber_el.get_text(strip=True) if chamber_el else ""

    state_el = row.find(class_=re.compile(r"us-state-compact--"))
    state = state_el.get_text(strip=True) if state_el else ""

    # Issuer
    issuer_el = row.find("a", href=re.compile(r"/issuers/"))
    issuer = issuer_el.get_text(strip=True) if issuer_el else ""

    ticker_el = row.find(class_="q-field issuer-ticker")
    ticker = ticker_el.get_text(strip=True) if ticker_el else ""
    # Strip exchange suffix e.g. "JPM:US" -> "JPM"
    if ":" in ticker:
        ticker = ticker.split(":")[0]

    # Disclosure / Filed date (3rd cell, index 2) and Trade date (4th cell, index 3)
    disclosure_date = parse_trade_date(cells[2]) if len(cells) > 2 else None
    trade_date = parse_trade_date(cells[3]) if len(cells) > 3 else None

    # Owner
    owner_el = row.find(class_=re.compile(r"owner-with-icon"))
    owner_label = owner_el.find(class_="q-label") if owner_el else None
    owner = owner_label.get_text(strip=True) if owner_label else ""

    # TX type
    tx_el = row.find(class_=re.compile(r"tx-type"))
    tx_type = tx_el.get_text(strip=True) if tx_el else ""

    # Trade size text (e.g. "50K-100K")
    size_el = row.find(class_="q-field trade-size")
    if size_el:
        size_dimmer = size_el.find(class_=re.compile(r"text-txt-dimmer"))
        size = size_dimmer.get_text(strip=True) if size_dimmer else size_el.get_text(strip=True)
    else:
        size = ""

    return {
        "name": name,
        "party": party,
        "chamber": chamber,
        "state": state,
        "issuer": issuer,
        "ticker": ticker,
        "trade_date": trade_date,
        "disclosure_date": disclosure_date,
        "owner": owner,
        "tx_type": tx_type,
        "size": size,
    }


def parse_page(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table or not table.find("tbody"):
        return []
    rows = table.find("tbody").find_all("tr", recursive=False)
    records = []
    for row in rows:
        rec = parse_row(row)
        if rec:
            records.append(rec)
    return records


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / "all_trades.parquet"
    checkpoint_path = DATA_DIR / "_checkpoint.parquet"

    # Resume from checkpoint if it exists
    start_page = 1
    all_records = []
    if checkpoint_path.exists():
        df_cp = pd.read_parquet(checkpoint_path)
        all_records = df_cp.to_dict("records")
        # Estimate which page we left off on
        start_page = len(all_records) // PAGE_SIZE + 1
        print(f"Resuming from checkpoint: {len(all_records):,} records, starting at page {start_page}")

    session = requests.Session()

    # Get total pages from page 1
    print("Fetching page 1 to get total page count...")
    html1 = fetch_page(session, 1)
    total_pages = get_total_pages(html1)
    if total_pages is None:
        print("Could not determine total pages — defaulting to 400")
        total_pages = 400
    print(f"Total pages: {total_pages} ({total_pages * PAGE_SIZE:,} max trades)")
    print()

    # Parse page 1 if not resuming
    if start_page == 1:
        records = parse_page(html1)
        all_records.extend(records)
        print(f"Page 1/{total_pages}: {len(records)} rows  |  total: {len(all_records):,}")
        start_page = 2
        time.sleep(DELAY)

    # Paginate
    for page in range(start_page, total_pages + 1):
        try:
            html = fetch_page(session, page)
            records = parse_page(html)

            if not records:
                print(f"Page {page}/{total_pages}: no rows returned — stopping")
                break

            all_records.extend(records)

            if page % 10 == 0 or page == total_pages:
                print(f"Page {page}/{total_pages}: {len(records)} rows  |  total: {len(all_records):,}")

            # Checkpoint
            if page % CHECKPOINT_EVERY == 0:
                pd.DataFrame(all_records).to_parquet(checkpoint_path, index=False)
                print(f"  Checkpoint saved at page {page}")

            time.sleep(DELAY)

        except KeyboardInterrupt:
            print("\nInterrupted — saving checkpoint...")
            pd.DataFrame(all_records).to_parquet(checkpoint_path, index=False)
            print(f"Saved {len(all_records):,} records to {checkpoint_path}")
            return

        except Exception as e:
            print(f"Error on page {page}: {e} — saving checkpoint and stopping")
            pd.DataFrame(all_records).to_parquet(checkpoint_path, index=False)
            break

    # Final save
    df = pd.DataFrame(all_records)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["disclosure_date"] = pd.to_datetime(df["disclosure_date"])
    df.to_parquet(out_path, index=False)
    print(f"\nSaved {len(df):,} trades to {out_path}")

    # Cleanup checkpoint
    if checkpoint_path.exists():
        checkpoint_path.unlink()

    # Quick summary
    print()
    print("--- Summary ---")
    print(f"Total trades        : {len(df):,}")
    print(f"Date range          : {df['trade_date'].min().date()} to {df['trade_date'].max().date()}")
    # Disclosure lag validation
    lag = (df["disclosure_date"] - df["trade_date"]).dt.days
    valid_lag = lag[lag >= 0]
    pct_valid = len(valid_lag) / len(lag) * 100 if len(lag) else 0
    print(f"Disclosure lag (days): median={lag.median():.0f}, mean={lag.mean():.0f}, pct_nonneg={pct_valid:.1f}%")
    print(f"Unique politicians  : {df['name'].nunique()}")
    print(f"Unique tickers      : {df['ticker'].nunique()}")
    print(f"Chambers            :")
    print(df["chamber"].value_counts().to_string())
    print(f"TX types            :")
    print(df["tx_type"].value_counts().to_string())


if __name__ == "__main__":
    main()
