"""
ProPublica Nonprofit Explorer API - free, public, no API key required.

Family offices are frequently paired with a family foundation, which
files a public Form 990. This is a genuinely different discovery
angle than SEC filings: it surfaces the philanthropic side of a
family, which often points to a private investment vehicle behind it
that never appears in any securities filing.

Docs: https://www.propublica.org/datastore/api/nonprofit-explorer-api
"""
import requests
from config import PROPUBLICA_BASE


def search_foundations(family_name: str, limit: int = 10) -> list[dict]:
    """
    Search 990 filers by name keyword. Good query: a family surname +
    'foundation' or 'family fund'.
    """
    url = f"{PROPUBLICA_BASE}/search.json"
    params = {"q": family_name}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for org in data.get("organizations", [])[:limit]:
        results.append({
            "name": org.get("name"),
            "ein": org.get("ein"),
            "city": org.get("city"),
            "state": org.get("state"),
            "ntee_code": org.get("ntee_code"),  # nonprofit category code
            "source": "propublica_990",
            "source_url": f"https://projects.propublica.org/nonprofits/organizations/{org.get('ein')}",
        })
    return results


def get_organization_detail(ein: str) -> dict:
    """Full filing detail for a given EIN - useful for confirming the
    entity is family-linked (e.g. name matches, purpose statement)."""
    url = f"{PROPUBLICA_BASE}/organizations/{ein}.json"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    # Smoke test - run this yourself once you're past this sandbox.
    # Try a real, known family name to confirm the API responds.
    results = search_foundations("Walton")
    for r in results:
        print(r)
