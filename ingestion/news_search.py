"""
News-based discovery via NewsAPI.org (free tier: 100 requests/day,
no credit card). This is your best source class for the specific
thing the brief calls out as most valuable: single-family offices
that formed after a liquidity event (a business sale) and got local
or trade press coverage, but have no ADV filing and no marketing site.

Get a free key at https://newsapi.org/register
"""
import requests

NEWSAPI_URL = "https://newsapi.org/v2/everything"


def search_news(query: str, api_key: str, page_size: int = 20) -> list[dict]:
    """
    Run a news search. Good queries for this scenario:
      - '"family office" acquisition 2025'
      - '"sold his company" "family office"'
      - '[City name] business sold family office'
    """
    params = {
        "q": query,
        "language": "en",
        "sortBy": "relevancy",
        "pageSize": page_size,
        "apiKey": api_key,
    }
    resp = requests.get(NEWSAPI_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for article in data.get("articles", []):
        results.append({
            "title": article.get("title"),
            "description": article.get("description"),
            "url": article.get("url"),
            "published_at": article.get("publishedAt"),
            "source_name": article.get("source", {}).get("name"),
        })
    return results


def extract_candidate_names(articles: list[dict]) -> list[str]:
    """
    Naive first pass: pull capitalized phrase patterns from titles/
    descriptions that look like entity names. This is intentionally
    crude - it's meant to produce a rough candidate list for YOU to
    review, not a finished answer. Refine this regex/NLP step as you
    see what real results look like.
    """
    import re
    candidates = set()
    pattern = re.compile(r"\b([A-Z][a-zA-Z&]+(?:\s+[A-Z][a-zA-Z&]+){0,3}\s+(?:Family Office|Capital|Partners|Holdings|Ventures))\b")
    for a in articles:
        text = f"{a.get('title', '')} {a.get('description', '')}"
        for match in pattern.findall(text):
            candidates.add(match)
    return sorted(candidates)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python news_search.py YOUR_NEWSAPI_KEY")
        sys.exit(1)

    api_key = sys.argv[1]
    articles = search_news('"family office" "sold his company"', api_key)
    print(f"Found {len(articles)} articles")
    candidates = extract_candidate_names(articles)
    print("Candidate entity names extracted:")
    for c in candidates:
        print(" -", c)
