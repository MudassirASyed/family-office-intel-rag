"""
Merges data/enrichment_notes.json into data/records.json.

Same pattern as build_dataset.py, applied to the enrichment layer
instead of the discovery/qualification layer: research findings get
logged as structured, cited notes (the "validation notes" the brief
allows to be manual/AI-assisted), and this script does the actual
file compilation through code - never hand-edit records.json directly.

Only fields present in an enrichment entry are touched; anything not
yet researched is left as an honest blank, per the brief's own rule
("a cell you could not verify may be left honestly blank"). Existing
non-empty fields are never silently overwritten - a conflict is
printed so it can be resolved deliberately, not by whichever write
happened last.

Usage:
    python scripts/apply_enrichment.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

ENRICHMENT_PATH = "data/enrichment_notes.json"
RECORDS_PATH = "data/records.json"

ENRICHMENT_FIELDS = [
    "description", "investment_thesis", "investing_sectors", "aum",
    "website", "corporate_linkedin", "city", "state", "country",
    "principal_name", "principal_title", "principal_linkedin",
    "principal_email", "principal_email_verified", "principal_phone",
    "recent_activity", "recent_activity_date",
]


def main():
    with open(ENRICHMENT_PATH, encoding="utf-8") as f:
        enrichment = json.load(f)
    with open(RECORDS_PATH, encoding="utf-8") as f:
        records = json.load(f)

    by_name = {r["name"]: r for r in records}
    updated, conflicts, not_found = 0, [], []

    for entry in enrichment:
        name = entry["name"]
        record = by_name.get(name)
        if record is None:
            not_found.append(name)
            continue

        touched = False
        for field in ENRICHMENT_FIELDS:
            if field not in entry:
                continue
            new_val = entry[field]
            old_val = record.get(field)
            if old_val:  # non-empty existing value - don't silently clobber
                if old_val != new_val:
                    conflicts.append(f"{name}.{field}: existing={old_val!r} new={new_val!r} - kept existing")
                continue
            record[field] = new_val
            touched = True

        if entry.get("enrichment_notes"):
            existing_notes = record.get("notes", "")
            addition = entry["enrichment_notes"]
            if addition not in existing_notes:
                record["notes"] = (existing_notes + " | " + addition).strip(" |")
                touched = True

        if touched:
            updated += 1

    with open(RECORDS_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    print(f"Updated {updated} records with enrichment data.")
    if conflicts:
        print(f"\n{len(conflicts)} conflicts (existing values kept, review these):")
        for c in conflicts:
            print(" -", c)
    if not_found:
        print(f"\n{len(not_found)} enrichment entries didn't match any record name:")
        for n in not_found:
            print(" -", n)


if __name__ == "__main__":
    main()
