"""
Runs ingestion/news_search.py across multiple query variants and
writes a deduped candidate pool to data/news_candidates_raw.json.

DISCOVERY-ONLY, same as scripts/discover_13f_candidates.py - nothing
here is verified yet. extract_candidate_names() is intentionally crude
(regex, not NLP) per its own docstring, so expect noise: duplicate
near-matches from overlapping regex captures, and names that aren't
family offices at all. That review happens per-candidate afterward.

NewsAPI's free tier only indexes roughly the last 30 days of articles
- this will surface CURRENT activity, not a historical archive. Re-run
periodically to catch new candidates as news cycles.

Usage:
    python scripts/discover_news_candidates.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from ingestion.news_search import search_news, extract_candidate_names
from config import NEWSAPI_KEY

QUERIES = [
    "family office",
    '"family office" acquisition',
    '"family office" billionaire',
    '"family office" invests',
    '"family office" launches',
    '"family office" backed',
    '"single-family office"',
    '"family office" stake',
]

OUTPUT_PATH = "data/news_candidates_raw.json"


def main():
    if not NEWSAPI_KEY:
        print("NEWSAPI_KEY not set in .env - nothing to do.")
        return

    all_candidates: dict[str, dict] = {}
    for q in QUERIES:
        try:
            articles = search_news(q, NEWSAPI_KEY, page_size=100)
        except Exception as e:
            print(f"Query {q!r} failed: {e}")
            continue

        names = extract_candidate_names(articles)
        print(f"{q!r}: {len(articles)} articles -> {len(names)} candidate names")
        for name in names:
            if name not in all_candidates:
                # keep one representative source article per candidate
                matching_article = next(
                    (a for a in articles if name.split(" Family Office")[0].split(" Capital")[0] in
                     f"{a.get('title', '')} {a.get('description', '')}"),
                    articles[0] if articles else {},
                )
                all_candidates[name] = {
                    "name": name,
                    "source": "news_search",
                    "matched_queries": [q],
                    "notes": f"Extracted from NewsAPI query {q!r}",
                    "source_url": matching_article.get("url", ""),
                    "source_title": matching_article.get("title", ""),
                }
            else:
                all_candidates[name]["matched_queries"].append(q)

    candidates = sorted(all_candidates.values(), key=lambda c: c["name"])
    with open(OUTPUT_PATH, "w") as f:
        json.dump(candidates, f, indent=2)

    print(f"\n{len(candidates)} unique candidate names across {len(QUERIES)} queries.")
    print(f"Written to {OUTPUT_PATH} - review each before it counts toward the 50.")


if __name__ == "__main__":
    main()
