"""
SEC 13F-based discovery. Free, public, no API key - just a compliant
User-Agent header (SEC_USER_AGENT in config.py).

Why 13F and not just ADV (which edgar_search.py already covers):
Form ADV exempts true single-family offices entirely - they're
invisible to it by design (17 CFR 275.202(a)(11)(G)-1). Form 13F is
different: it's triggered by AUM in listed securities (>$100M),
*regardless* of adviser-registration status. A single-family office
that invests its money in public equities after a liquidity event
still has to file a 13F even though it never had to register as an
adviser. That makes 13F filers a genuinely different, and genuinely
useful, discovery pool - not just a re-scrape of the same famous names
press coverage already surfaces.

Confirmed live against the real SEC API while building this (not
assumed from docs): a single full-text search for "family office"
restricted to 13F-HR filings turned up 33 distinct filer entities in
one query, most of which do not appear in any "top family offices"
press list - e.g. "Kopp Family Office, LLC" (Bloomington, MN),
"Stenger Family Office, LLC" (Naperville, IL), "Timonier Family
Office, LTD." (Winston-Salem, NC). That is what real discovery looks
like versus convenient discovery.

CRITICAL - what this source can and cannot prove (do not skip this):
A name containing "Family Office" and a real SEC filing are NOT, by
themselves, affirmative evidence of single-family status under the
brief's rule 2. Multi-family offices and RIAs that use "family office"
as a marketing term file 13F too (several of the 33 above - e.g.
Pathstone, Veritable, Geller Family Office Services - read as
multi-family/RIA-style service providers on their face, not
single-family). This module's job is DISCOVERY ONLY. Every hit still
needs a second, independent source (the firm's own site, ADV Part 2
brochure via IAPD, or press) before firm_qualifies can be set True.
Treat every result here as "candidate, unconfirmed type" - that is
also why build_record_from_candidate() in run_pipeline.py defaults
firm_qualifies=False and does not auto-approve anything from this
source.
"""
import time
from xml.etree import ElementTree as ET

import requests
from config import SEC_USER_AGENT

FTS_URL = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data/{cik_nolead}/{accession_nodash}"

HEADERS = {"User-Agent": SEC_USER_AGENT}


def _pad_cik(cik: str) -> str:
    return str(int(cik)).zfill(10)


def search_by_keyword(keyword: str, max_pages: int = 5, page_size: int = 10) -> list[dict]:
    """
    Discovery step. Searches 13F-HR filing text for `keyword` (e.g.
    "family office", "family capital"), paginates, and dedupes to one
    row per filer (CIK) - a filer shows up in every quarterly filing
    that mentions the phrase, so raw hits wildly overcount entities.

    Returns candidates in the same shape run_pipeline.py already
    expects: {"name", "source", "notes", "source_url", "cik"}.
    """
    seen: dict[str, dict] = {}
    for page in range(max_pages):
        params = {"q": f'"{keyword}"', "forms": "13F-HR", "from": page * page_size}
        resp = requests.get(FTS_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        hits = resp.json().get("hits", {}).get("hits", [])
        if not hits:
            break
        for h in hits:
            src = h["_source"]
            cik = src["ciks"][0]
            if cik in seen:
                continue
            raw_name = src["display_names"][0]
            name = raw_name.split("  (CIK")[0].strip()
            seen[cik] = {
                "name": name,
                "cik": cik,
                "source": "sec_13f",
                "notes": f"13F-HR filer, matched keyword '{keyword}'. Location: {src.get('biz_locations', [''])[0]}.",
                "source_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=13F-HR",
            }
        time.sleep(0.3)  # be polite to a free public API with no key/quota
    return list(seen.values())


def get_entity_profile(cik: str) -> dict:
    """
    Verification/enrichment step. data.sec.gov's submissions API - a
    clean JSON endpoint (not the old Atom feed) with the filer's
    registered address, phone, EIN, and full filing history. Useful
    for corroborating a business address (a real signal a true SFO
    exists at a specific place) and for finding the most recent 13F
    filing to cite as a dated activity signal.
    """
    resp = requests.get(SUBMISSIONS_URL.format(cik10=_pad_cik(cik)), headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])

    latest_13f = None
    for form, date, accession in zip(forms, dates, accessions):
        if form == "13F-HR":
            latest_13f = {"filing_date": date, "accession_number": accession}
            break  # `recent` is already newest-first

    return {
        "name": data.get("name", ""),
        "cik": cik,
        "ein": data.get("ein", ""),
        "phone": data.get("phone", ""),
        "state_of_incorporation": data.get("stateOfIncorporation", ""),
        "business_address": data.get("addresses", {}).get("business", {}),
        "latest_13f_filing": latest_13f,
    }


def get_filing_summary(cik: str, accession_number: str) -> dict:
    """
    Parses the filing's primary_doc.xml cover/summary page. Critical
    field: `other_included_managers` - confirmed live while building
    this that some 13F filings are JOINT filings, where one filer
    reports combined holdings on behalf of multiple managers sharing a
    custodian. Example hit from this search: "EMFO, LLC" (a small
    Weston, FL entity) reported a $111.7B portfolio total - implausible
    for its apparent size - because its filing includes holdings for
    "MARSHFIELD ASSOCIATES" bundled into the same information table
    (otherIncludedManagersCount=1). Compare: Duquesne Family Office's
    filing has otherIncludedManagersCount=0 and a $3.4B total, which is
    plausible and clean. Never treat holdings from a filing with
    other_included_managers as belonging solely to the entity you're
    researching - the info table doesn't separate them by manager.

    SECOND, DISTINCT gotcha - also confirmed live, not theoretical: even
    with other_included_managers empty, `tableValueTotal` is NOT
    necessarily one family's money. Kemnay Advisory Services Inc.
    (CIK 1555283, confirmed via Preqin/Altss/SWFI to genuinely be Alan
    Parker's real single-family office) reported a $622B / 1,190-position
    13F total with otherIncludedManagersCount=0 - but Parker's own known
    real estate book alone is ~$2B per public sourcing, nowhere near
    $622B. otherIncludedManagersCount only catches joint CO-FILINGS
    (multiple managers filing together). It does NOT catch a manager
    that simply has investment discretion over other clients' or related
    entities' assets and reports them all under its own name, which
    appears to be what's happening here. Conclusion: never present a
    13F tableValueTotal as "this family's AUM" without independent
    corroboration. Individual position CHANGES (e.g. "increased Coinbase
    position X% quarter over quarter") are safer to cite as activity
    signals than the absolute total is as an AUM cell.
    """
    accession_nodash = accession_number.replace("-", "")
    cik_nolead = str(int(cik))
    doc_url = f"{ARCHIVE_BASE.format(cik_nolead=cik_nolead, accession_nodash=accession_nodash)}/primary_doc.xml"

    empty = {
        "table_value_total_thousands_usd": None,
        "table_entry_total": None,
        "other_included_managers": [],
        "parse_error": None,
    }
    try:
        resp = requests.get(doc_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.exceptions.HTTPError:
        # Confirmed live: pre-~2013 13F filings predate the XML technical
        # spec entirely and have no primary_doc.xml (404). Degrade
        # honestly instead of crashing - a filing this old is a strong
        # signal the entity is stale anyway (see get_activity_status()).
        return {**empty, "parse_error": "legacy filing format (pre-XML), summary unavailable"}

    ns = {"n": "http://www.sec.gov/edgar/thirteenffiler"}
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return {**empty, "parse_error": "could not parse primary_doc.xml"}

    summary = root.find(".//n:summaryPage", ns)
    if summary is None:
        return {**empty, "parse_error": "no summaryPage found in primary_doc.xml"}

    other_managers = [
        m.findtext("n:otherManager/n:name", default="", namespaces=ns)
        for m in summary.findall("n:otherManagers2Info/n:otherManager2", ns)
    ]
    return {
        "table_value_total_thousands_usd": int(summary.findtext("n:tableValueTotal", default="0", namespaces=ns)),
        "table_entry_total": int(summary.findtext("n:tableEntryTotal", default="0", namespaces=ns)),
        "other_included_managers": [m for m in other_managers if m],
        "parse_error": None,
    }


def get_latest_holdings(cik: str, accession_number: str, top_n: int = 10) -> dict:
    """
    Pulls the information-table XML for one 13F filing and returns the
    top N holdings by reported value (thousands of USD, per SEC 13F
    convention), PLUS a `joint_filing` flag from get_filing_summary().
    Callers must check that flag - if True, the holdings below are a
    combined total across multiple managers and must not be presented
    as this entity's own investment activity. This is exactly the kind
    of thing that looks like a working enrichment feature but produces
    a misattributed cell if the check is skipped - the brief scores
    that as worse than an honest blank.
    """
    summary = get_filing_summary(cik, accession_number)
    joint_filing = len(summary["other_included_managers"]) > 0

    accession_nodash = accession_number.replace("-", "")
    cik_nolead = str(int(cik))
    index_url = f"{ARCHIVE_BASE.format(cik_nolead=cik_nolead, accession_nodash=accession_nodash)}/index.json"

    holdings = []
    parse_error = summary["parse_error"]
    try:
        resp = requests.get(index_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        items = resp.json().get("directory", {}).get("item", [])
        infotable_name = next(
            (i["name"] for i in items if i["name"].endswith(".xml") and i["name"] != "primary_doc.xml"),
            None,
        )
        if infotable_name:
            doc_url = f"{ARCHIVE_BASE.format(cik_nolead=cik_nolead, accession_nodash=accession_nodash)}/{infotable_name}"
            resp = requests.get(doc_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()

            ns = {"n": "http://www.sec.gov/edgar/document/thirteenf/informationtable"}
            root = ET.fromstring(resp.content)
            for entry in root.findall("n:infoTable", ns):
                issuer = entry.findtext("n:nameOfIssuer", default="", namespaces=ns)
                value = entry.findtext("n:value", default="0", namespaces=ns)
                holdings.append({"issuer": issuer, "value_thousands_usd": int(value)})
            holdings.sort(key=lambda h: h["value_thousands_usd"], reverse=True)
        elif not parse_error:
            parse_error = "no information table found in filing index"
    except (requests.exceptions.HTTPError, ET.ParseError) as e:
        parse_error = parse_error or f"could not fetch/parse information table: {e}"

    return {
        "holdings": holdings[:top_n],
        "joint_filing": joint_filing,
        "other_included_managers": summary["other_included_managers"],
        "parse_error": parse_error,
    }


def get_activity_status(cik: str, max_age_days: int = 730) -> dict:
    """
    Recency check - confirmed live this matters, not a hypothetical
    edge case. "World Asset Management LLC" matched a 13F-HR keyword
    search but its last filing of ANY kind was in 2001 (12 total
    filings, all 1999-2001) - it's not a going concern today, and its
    keyword match turned out to be noise unrelated to being a family
    office at all. A firm with no SEC activity in `max_age_days` isn't
    disqualified by this alone (a true family office could simply have
    stopped filing 13F after dropping below the $100M threshold, or
    gone fully private) but it IS a strong signal to deprioritize -
    "current, dated signals" (the brief's own phrase) can't be built on
    a filer that's been silent for years.
    """
    resp = requests.get(SUBMISSIONS_URL.format(cik10=_pad_cik(cik)), headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    recent = data.get("filings", {}).get("recent", {})
    dates = recent.get("filingDate", [])

    if not dates:
        return {"is_active": False, "most_recent_filing_date": None, "total_filings_on_record": 0}

    most_recent = max(dates)
    from datetime import date
    age_days = (date.today() - date.fromisoformat(most_recent)).days
    return {
        "is_active": age_days <= max_age_days,
        "most_recent_filing_date": most_recent,
        "total_filings_on_record": len(dates),
    }


if __name__ == "__main__":
    candidates = search_by_keyword("family office", max_pages=2)
    print(f"Found {len(candidates)} unique 13F filers matching 'family office':\n")
    for c in candidates[:10]:
        print(f"  {c['name']}  (CIK {c['cik']})")

    # Duquesne Family Office LLC (CIK 1536411) - known-clean single-manager
    # filing, used here to demonstrate the joint_filing check passes cleanly
    # (contrast with EMFO, LLC / CIK 1859434, a known joint filing).
    for name, cik in [("Duquesne Family Office LLC", "1536411")]:
        print(f"\nProfile for {name}:")
        profile = get_entity_profile(cik)
        print(profile)

        if profile.get("latest_13f_filing"):
            result = get_latest_holdings(cik, profile["latest_13f_filing"]["accession_number"])
            if result["joint_filing"]:
                print(f"\n  JOINT FILING - holdings include other managers "
                      f"{result['other_included_managers']}. Not attributable to {name} alone. Skipping.")
            else:
                print(f"\nTop holdings from most recent 13F ({profile['latest_13f_filing']['filing_date']}):")
                for h in result["holdings"]:
                    print(f"  {h['issuer']}: ${h['value_thousands_usd']:,}k")
