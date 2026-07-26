"""
Runs get_activity_status() from ingestion/sec_13f_search.py across
every candidate in data/13f_candidates_raw.json and splits them by
SEC filing recency.

This does NOT decide single-vs-multi-family or qualify anything for
the final 50 - it only removes/deprioritizes candidates that are not
a going concern today (confirmed live: "World Asset Management LLC"
matched a keyword search but hasn't filed anything with the SEC since
2001). Per the brief's own instruction, rejected candidates are kept
in a separate audit file, not silently deleted.

Usage:
    python scripts/filter_stale_candidates.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
from ingestion.sec_13f_search import get_activity_status

INPUT_PATH = "data/13f_candidates_raw.json"
ACTIVE_PATH = "data/13f_candidates_active.json"
STALE_PATH = "data/13f_candidates_stale_excluded.json"


def main():
    with open(INPUT_PATH) as f:
        candidates = json.load(f)

    active, stale = [], []
    for i, c in enumerate(candidates):
        try:
            status = get_activity_status(c["cik"])
        except Exception as e:
            print(f"  [{i+1}/{len(candidates)}] {c['name']}: ERROR checking activity ({e}) - keeping in active pool for manual check")
            c["activity_check_error"] = str(e)
            active.append(c)
            time.sleep(0.25)
            continue

        c.update(status)
        if status["is_active"]:
            active.append(c)
            print(f"  [{i+1}/{len(candidates)}] {c['name']}: active (last filing {status['most_recent_filing_date']})")
        else:
            stale.append(c)
            print(f"  [{i+1}/{len(candidates)}] {c['name']}: STALE (last filing {status['most_recent_filing_date']}, "
                  f"{status['total_filings_on_record']} filings total) - excluded")
        time.sleep(0.25)  # polite pacing against a free, key-less public API

    with open(ACTIVE_PATH, "w") as f:
        json.dump(active, f, indent=2)
    with open(STALE_PATH, "w") as f:
        json.dump(stale, f, indent=2)

    print(f"\n{len(active)} active candidates -> {ACTIVE_PATH}")
    print(f"{len(stale)} stale candidates excluded -> {STALE_PATH} (audit trail, not deleted)")


if __name__ == "__main__":
    main()
