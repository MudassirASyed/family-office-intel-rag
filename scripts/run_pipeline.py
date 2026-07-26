"""
Orchestrator - the actual "pipeline" the brief requires (as opposed
to manual compilation). Run this to go from discovery -> verification
-> data/records.json.

This is a SKELETON of the control flow. You still need to:
  1. Get a free NewsAPI key and add it to .env
  2. Fill in your own INCLUSION_CRITERIA in processing/classifier.py
  3. Review each candidate this surfaces - the brief explicitly wants
     your judgment in the loop, not a fully unattended black box
  4. Do the manual enrichment lookups (principal name/email/phone)
     that require human judgment (e.g. LinkedIn lookups) and feed
     the results back into the record

Usage:
    python scripts/run_pipeline.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from ingestion import news_search, propublica_990, edgar_search, web_scraper
from ingestion.seed_candidates_researched import RESEARCHED_SEEDS
from processing.record import FamilyOfficeRecord
from config import NEWSAPI_KEY, MIN_CONFIDENCE_FOR_INCLUSION


def discover_candidates() -> list[dict]:
    """Combine multiple source classes into one candidate list."""
    candidates = list(RESEARCHED_SEEDS)  # real, hand-verified bootstrap set

    if NEWSAPI_KEY:
        for query in [
            '"family office" "sold his company"',
            '"family office" acquisition 2025',
        ]:
            try:
                articles = news_search.search_news(query, NEWSAPI_KEY)
                names = news_search.extract_candidate_names(articles)
                for n in names:
                    candidates.append({"name": n, "source": "news_search", "notes": f"query: {query}"})
            except Exception as e:
                print(f"News search failed for '{query}': {e}")
    else:
        print("NEWSAPI_KEY not set - skipping automated news discovery. "
              "Get a free key at https://newsapi.org/register")

    return candidates


def build_record_from_candidate(candidate: dict) -> FamilyOfficeRecord:
    """
    Turns a raw candidate into a FamilyOfficeRecord shell. This is
    where YOU add real enrichment logic - website checks, EDGAR
    cross-reference, manual LinkedIn lookups, etc. Currently a
    minimal starting shell so the pipeline runs end to end.
    """
    r = FamilyOfficeRecord(
        name=candidate["name"],
        firm_type="unclear",           # set this deliberately per your criteria
        firm_qualifies=False,          # default to False until evidence says otherwise
        qualification_evidence="",
        sources_checked={},
        evidence={},
        notes=candidate.get("notes", ""),
    )

    if candidate.get("source") == "press":
        r.sources_checked["press_named_sfo"] = True
        r.evidence["press_named_sfo"] = candidate.get("source_url", "")
        r.firm_qualifies = True   # these were pre-verified by hand during research
        r.firm_type = "single_family_office"
        r.qualification_evidence = candidate.get("notes", "")

    r.compute_confidence()
    return r


def main():
    candidates = discover_candidates()
    print(f"Discovered {len(candidates)} raw candidates")

    records = [build_record_from_candidate(c) for c in candidates]

    qualifying = [r for r in records if r.qualifies_for_final_dataset(MIN_CONFIDENCE_FOR_INCLUSION)]
    print(f"{len(qualifying)} records currently qualify at confidence >= {MIN_CONFIDENCE_FOR_INCLUSION}")

    with open("data/records.json", "w") as f:
        json.dump([r.to_dict() for r in records], f, indent=2)

    print("Wrote all records (qualifying and non-qualifying) to data/records.json")
    print("Review non-qualifying records, do the manual enrichment pass, "
          "and re-run classification before treating this as final.")


if __name__ == "__main__":
    main()
