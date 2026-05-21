"""
Pull committee assignments from unitedstates/congress-legislators (public domain YAML).
Match against politician names in all_trades.parquet.

Output: data/politician_committees.parquet
  Columns: name, bioguide_id, party, chamber, committees (list), committee_categories (list)

Committee categories used for jurisdiction tests in 04_analysis.py:
  - Financials:     House Financial Services, Senate Banking
  - Energy:         House Energy and Commerce, Senate Energy and Natural Resources
  - Defense:        House Armed Services, Senate Armed Services
  - Health:         House Energy and Commerce health subcommittee, Senate HELP, Senate Finance health
  - IT:             House Judiciary antitrust subcommittee, Senate Commerce, Senate Judiciary
"""

import re
import unicodedata
import requests
import yaml
import pandas as pd
from pathlib import Path

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
DATA_DIR.mkdir(exist_ok=True)

TRADES_PATH = DATA_DIR / "all_trades.parquet"
OUT_PATH    = DATA_DIR / "politician_committees.parquet"

LEG_URL = "https://raw.githubusercontent.com/unitedstates/congress-legislators/main/legislators-current.yaml"
CMT_URL = "https://raw.githubusercontent.com/unitedstates/congress-legislators/main/committee-membership-current.yaml"
CMTLIST_URL = "https://raw.githubusercontent.com/unitedstates/congress-legislators/main/committees-current.yaml"

# Map committee names to jurisdiction categories
CATEGORY_KEYWORDS = {
    "Financials": [
        "Financial Services",
        "Banking, Housing",
        "Banking",
        "Finance",  # Senate Finance is broader but covers financial sector
    ],
    "Energy": [
        "Energy and Commerce",
        "Energy and Natural Resources",
        "Natural Resources",
    ],
    "Defense": [
        "Armed Services",
        "Foreign Affairs",
        "Foreign Relations",
        "Homeland Security",
        "Intelligence",
    ],
    "Health": [
        "Health, Education, Labor",
        "Energy and Commerce",  # has health subcommittee
        "Ways and Means",        # has health subcommittee
        "Finance",               # has health subcommittee
    ],
    "IT": [
        "Judiciary",
        "Commerce, Science",
        "Oversight",
        "Science, Space, and Technology",
    ],
}


def normalize_name(s):
    """Normalize a name for fuzzy matching: lowercase, strip accents, strip suffixes/prefixes/punctuation."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    # Strip common suffixes
    s = re.sub(r"\b(jr\.?|sr\.?|iii|iv|ii|md|phd)\b", "", s)
    # Strip punctuation
    s = re.sub(r"[.,'\"\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build_committee_lookup(committees_list):
    """thomas_id -> committee_name"""
    lookup = {}

    def walk(committees, prefix=""):
        for c in committees:
            tid = c.get("thomas_id")
            name = c.get("name", "")
            if tid:
                lookup[tid] = prefix + name
            for sub in c.get("subcommittees") or []:
                sub_tid = (tid or "") + (sub.get("thomas_id") or "")
                sub_name = sub.get("name", "")
                if sub_tid:
                    lookup[sub_tid] = prefix + name + " | " + sub_name

    walk(committees_list)
    return lookup


def classify_committees(committee_names):
    """Return list of jurisdiction categories matched by any of the politician's committees."""
    cats = set()
    for name in committee_names:
        for cat, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in name.lower():
                    cats.add(cat)
                    break
    return sorted(cats)


def main():
    print("Loading trades parquet...")
    trades = pd.read_parquet(TRADES_PATH)
    trade_names = trades["name"].dropna().unique()
    print(f"  {len(trade_names)} unique trader names")

    print("Fetching legislators-current.yaml...")
    leg_text = requests.get(LEG_URL, timeout=60).text
    leg = yaml.safe_load(leg_text)
    print(f"  {len(leg)} current legislators")

    print("Fetching committees-current.yaml...")
    cmt_text = requests.get(CMTLIST_URL, timeout=60).text
    cmt_list = yaml.safe_load(cmt_text)
    cmt_lookup = build_committee_lookup(cmt_list)
    print(f"  {len(cmt_lookup)} committee+subcommittee entries")

    print("Fetching committee-membership-current.yaml...")
    mem_text = requests.get(CMT_URL, timeout=60).text
    membership = yaml.safe_load(mem_text)

    # bioguide_id -> list of committee names
    bioguide_to_committees = {}
    for tid, members in membership.items():
        cmt_name = cmt_lookup.get(tid, tid)
        for m in members:
            bid = m.get("bioguide")
            if not bid:
                continue
            bioguide_to_committees.setdefault(bid, []).append(cmt_name)

    # Build legislator lookup keyed by normalized full name
    leg_index = {}
    for L in leg:
        name = L.get("name", {})
        bid = L.get("id", {}).get("bioguide")
        if not bid:
            continue
        first = name.get("first", "")
        last  = name.get("last", "")
        full  = f"{first} {last}"
        official = name.get("official_full", full)
        nickname = name.get("nickname")

        terms = L.get("terms", []) or []
        latest = terms[-1] if terms else {}
        party = latest.get("party", "")
        chamber = "House" if latest.get("type") == "rep" else "Senate" if latest.get("type") == "sen" else ""

        keys = {normalize_name(full), normalize_name(official)}
        if nickname:
            keys.add(normalize_name(f"{nickname} {last}"))
        # Also add last-name only as a weak fallback
        last_only = normalize_name(last)
        for k in keys:
            if not k:
                continue
            leg_index.setdefault(k, []).append({
                "bioguide_id": bid,
                "first": first,
                "last": last,
                "official": official,
                "party": party,
                "chamber": chamber,
            })
        # Weak match by last name only -- only use as final fallback
        leg_index.setdefault("LAST:" + last_only, []).append({
            "bioguide_id": bid,
            "first": first,
            "last": last,
            "official": official,
            "party": party,
            "chamber": chamber,
        })

    # Match trade names
    matched = []
    unmatched = []
    for tn in trade_names:
        key = normalize_name(tn)
        hit = leg_index.get(key)
        match_type = "exact"
        if not hit:
            # Try last-name fallback
            parts = key.split()
            if parts:
                hit = leg_index.get("LAST:" + parts[-1])
                match_type = "lastname"
        if not hit:
            unmatched.append(tn)
            continue
        # If multiple hits via last name, prefer the one whose first name starts with the same letter
        if len(hit) > 1 and match_type == "lastname":
            parts = key.split()
            if parts:
                first_initial = parts[0][0]
                better = [h for h in hit if h["first"].lower().startswith(first_initial)]
                if better:
                    hit = better
        L = hit[0]
        cmts = bioguide_to_committees.get(L["bioguide_id"], [])
        cats = classify_committees(cmts)
        matched.append({
            "name": tn,
            "bioguide_id": L["bioguide_id"],
            "party": L["party"],
            "chamber": L["chamber"],
            "committees": cmts,
            "committee_categories": cats,
            "match_type": match_type,
        })

    df = pd.DataFrame(matched)
    df.to_parquet(OUT_PATH, index=False)

    print()
    print(f"Matched: {len(matched)} / {len(trade_names)} ({len(matched)/len(trade_names)*100:.1f}%)")
    print(f"Unmatched: {len(unmatched)}")
    if unmatched:
        print(f"  Sample unmatched: {unmatched[:15]}")
    print(f"  Match type breakdown: {df['match_type'].value_counts().to_dict()}")

    # Coverage by category
    print("\n--- Politicians per jurisdiction category ---")
    cat_counts = {}
    for _, row in df.iterrows():
        for c in row["committee_categories"]:
            cat_counts[c] = cat_counts.get(c, 0) + 1
    for c, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {c:<12} {n}")

    # Spot checks
    print("\n--- Spot checks ---")
    spot = ["Nancy Pelosi", "Dan Crenshaw", "Josh Gottheimer", "Tommy Tuberville"]
    for s in spot:
        match = df[df["name"] == s]
        if not match.empty:
            row = match.iloc[0]
            print(f"  {s}: {row['committees'][:3]} -> cats={row['committee_categories']}")
        else:
            print(f"  {s}: NOT MATCHED")


if __name__ == "__main__":
    main()
