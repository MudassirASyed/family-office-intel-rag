"""
SEC EDGAR full-text search. Free, public, no API key.

IMPORTANT CAVEAT (confirmed via research, not assumed):
Fully-exempt single-family offices are explicitly NOT required to
file Form ADV at all under the SEC's family office exclusion
(17 CFR 275.202(a)(11)(G)-1). So EDGAR will NOT surface most true
single-family offices - it mainly surfaces:
  - Multi-family offices operating as registered/exempt-reporting advisers
  - Family offices that exceed the $150M private-fund-only threshold
    and must partially register
  - Family offices that voluntarily registered

Use this as ONE source class among several, not your primary SFO
discovery tool. It's most useful for verifying/enriching entities you
found elsewhere (does this name show up in any filing at all?).
"""
import time
import requests
from config import SEC_USER_AGENT

EDGAR_FULLTEXT_URL = "https://efts.sec.gov/LATEST/search-index"


def search_fulltext(query: str, forms: str = "ADV") -> dict:
    params = {"q": f'"{query}"', "forms": forms}
    headers = {"User-Agent": SEC_USER_AGENT}
    resp = requests.get(EDGAR_FULLTEXT_URL, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    time.sleep(0.3)
    return resp.json()


def extract_hits(raw_json: dict) -> list[dict]:
    hits = raw_json.get("hits", {}).get("hits", [])
    results = []
    for h in hits:
        source = h.get("_source", {})
        results.append({
            "entity_name": source.get("display_names", [None])[0],
            "cik": source.get("cik"),
            "form_type": source.get("root_form"),
            "filing_date": source.get("file_date"),
            "accession_no": h.get("_id"),
            "source": "sec_edgar",
        })
    return results


if __name__ == "__main__":
    raw = search_fulltext("family office", forms="ADV")
    hits = extract_hits(raw)
    print(f"Found {len(hits)} hits")
    for h in hits[:10]:
        print(h)
