"""
Runs ingestion/sec_13f_search.py across multiple keyword variants and
writes a deduped candidate pool to data/13f_candidates_raw.json.

This is a DISCOVERY-ONLY staging file, not the final dataset. Every
row here is "name + CIK + which keyword matched" - nothing has been
verified as single-family vs multi-family vs not-actually-a-family-
office yet. That review happens per-candidate, against
processing/classifier.py's INCLUSION_CRITERIA, before anything moves
into data/records.json.

Usage:
    python scripts/discover_13f_candidates.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from ingestion.sec_13f_search import search_by_keyword

KEYWORDS = [
    "family office",
    "family capital",
    "family holdings",
    "family investments",
    "family management",
    "family partners",
    "family wealth",
]

OUTPUT_PATH = "data/13f_candidates_raw.json"


def main():
    all_candidates: dict[str, dict] = {}
    for kw in KEYWORDS:
        results = search_by_keyword(kw, max_pages=3)
        print(f"'{kw}': {len(results)} unique filers")
        for c in results:
            cik = c["cik"]
            if cik in all_candidates:
                all_candidates[cik]["matched_keywords"].append(kw)
            else:
                c["matched_keywords"] = [kw]
                all_candidates[cik] = c

    candidates = sorted(all_candidates.values(), key=lambda c: c["name"])
    with open(OUTPUT_PATH, "w") as f:
        json.dump(candidates, f, indent=2)

    print(f"\n{len(candidates)} unique candidate entities across {len(KEYWORDS)} keywords.")
    print(f"Written to {OUTPUT_PATH} - review each before it counts toward the 50.")


if __name__ == "__main__":
    main()
