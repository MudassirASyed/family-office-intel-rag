# 3-Record Full Validation Chain

Per the brief's deliverable requirement: *"Select 3 records and provide a full
validation chain: discovery source, extraction method, enrichment steps,
validation logic, confidence assessment, and exact sources or links used."*

These 3 were deliberately chosen to show three different things: the
strongest evidence tier we found (West Family Investments), a real error
caught and prevented from entering the dataset (Kemnay Advisory Services),
and a clean multi-source cross-validation with a correctly-scoped financial
signal (Duquesne Family Office).

---

## 1. West Family Investments, Inc.

**Discovery source:** SEC EDGAR full-text search (`ingestion/sec_13f_search.py`,
keyword `"family investments"`) — script-driven, part of the 78-candidate
13F sweep in `data/13f_candidates_raw.json`.

**Extraction method:** `get_entity_profile()` pulled the registered name,
address, and filing history from `data.sec.gov/submissions/CIK0001568303.json`.
Separately, a web search for "family office" + Gary West surfaced a real SEC
Schedule 13D/13G filing.

**Validation logic:** Fetched the actual 13D/13G document text directly
(`curl` with a compliant User-Agent, not a summary) and confirmed it states,
verbatim: *"The Adviser is a family office exempt from registration under the
Family Office Exemption."* This is a primary legal self-declaration — the
strongest evidence tier used anywhere in this dataset. Cross-checked
`get_filing_summary()` on the most recent 13F: `otherIncludedManagersCount=0`
(clean, not a joint filing), continuously active 2013–2026 (97 filings).

**Enrichment steps:** Investment thesis, sectors, and AUM ($383M in
13F-reportable securities) added from West Health Investment Fund press
coverage and 13F holdings data. One real correction made during enrichment: a
Bloomberg aggregator listed the city as Evanston, IL, contradicting the SEC
filing and all other sources (Carlsbad, CA) — treated as an aggregator error
and documented in the record's `notes` field rather than silently overwritten.
A candidate "Gary West" LinkedIn profile was found but excluded — the entity
name on that profile didn't clearly match, so it was left blank rather than
risk a wrong-person attribution.

**Confidence assessment:** 0.75 — `sec_primary_declaration` (0.45, highest
weight in `SOURCE_WEIGHTS`) + `sec_13f_clean` (0.3). Computed by
`FamilyOfficeRecord.compute_confidence()`, not asserted by hand.

**Exact sources:**
- https://www.sec.gov/Archives/edgar/data/1568303/0001104659-21-108534.txt (primary declaration)
- https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=1568303&type=13F-HR (filing history)

---

## 2. Kemnay Advisory Services

**Discovery source:** Originally from `ingestion/seed_candidates_researched.py`
(press-based seed, pre-dating the 13F pipeline), then independently
re-discovered and re-verified through the SEC 13F channel during this
session.

**Extraction method:** CNBC's 13F coverage (`cnbc.com/2026/02/26/...`) named
Kemnay and cited a ~44% Q4 2025 increase in its Coinbase position.
Independently, `get_entity_profile()` and `get_latest_holdings()` were run
directly against CIK 1555283 to verify the underlying SEC data itself, not
just press characterization of it.

**Validation logic — the important part:** The first live pull of Kemnay's
13F table showed a `tableValueTotal` of **~$622.3 billion**, which is
wildly implausible for what public sourcing confirms is a family office tied
to one individual's 1997 liquidity event (Alan Parker, Duty Free Shoppers
sale to LVMH). Rather than accept the figure, `get_filing_summary()` was used
to inspect the filing's cover page directly. Result: `otherIncludedManagersCount
= 0` — meaning this wasn't a joint co-filing (the pattern that explained a
similar issue found earlier with a different firm, EMFO/Marshfield
Associates). This forced a harder conclusion: Kemnay's filer entity likely has
investment discretion over assets well beyond Alan Parker's personal wealth,
and the 13F total cannot be used as an AUM figure for this family
specifically — a *distinct* failure mode from joint filings, undiagnosed
until this record was checked. Independent identity verification (Preqin,
Altss, SWFI all separately confirm Kemnay as Parker's real single-family
office) meant the firm's *qualification* stayed intact — only the AUM number
was rejected. This finding is documented in `SYSTEM_DESIGN.md` under Known
Limitations as a project-wide caution, not just a one-off note on this record.

**Enrichment steps:** Corporate LinkedIn added
(linkedin.com/company/kemnay-advisory-services-inc). A candidate LinkedIn
profile for "Alan Parker" was found but confirmed to be a *different* person
(a marketing consultant, unrelated) and explicitly excluded. Address refined
to 45 Rockefeller Plaza, NY via the SEC profile.

**Confidence assessment:** 0.7 — `press_named_sfo` (0.4) + `sec_13f_clean`
(0.3). Note the AUM field is deliberately **blank**, not populated with the
misleading $622B figure — an honest blank scored higher by the brief's own
stated standard than a wrong number would be.

**Exact sources:**
- https://www.cnbc.com/2026/02/26/billionaire-family-office-investments.html (press)
- https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=1555283&type=13F-HR (13F filing history)
- Direct fetch of `primary_doc.xml` for the filing's `otherIncludedManagersCount` field (via `ingestion/sec_13f_search.py::get_filing_summary()`)

---

## 3. Duquesne Family Office

**Discovery source:** Press seed (`seed_candidates_researched.py`),
independently re-verified via the SEC 13F channel this session — the same
dual-path pattern as Kemnay, used deliberately as a contrast case.

**Extraction method:** CNBC named Duquesne and Stanley Druckenmiller
directly. `get_entity_profile()` (CIK 1536411) confirmed registered name,
NYC address (40 West 57th Street), and continuous 13F filing history
2013–2026.

**Validation logic:** Ran the *same* joint-filing check used on Kemnay:
`get_filing_summary()` on the most recent 13F returned
`otherIncludedManagersCount = 0` **and** a `tableValueTotal` of ~$3.4–4.2B —
a figure that is actually plausible for a known billionaire's single-family
office, unlike Kemnay's. This is the deliberate contrast: identical
verification method applied to two records, one passing the plausibility
check clean, one failing it. Top holding confirmed directly from the parsed
information table: Natera Inc, $612.7M as of the 2026-05-15 filing.

**Enrichment steps:** A second, non-obvious principal was found and added —
Sue Meng, Partner & Managing Director, who leads Duquesne's private
investment strategy in disruptive technology and life sciences — sourced
independently of Druckenmiller's own press coverage, via a dedicated
LinkedIn/Bloomberg search on the firm rather than the person. Recent activity
enriched with confirmed exits (Entegris, ON Semiconductor) and a new Q4 2025
Bloom Energy position, both from CNBC's 13F coverage.

**Confidence assessment:** 0.7 — `press_named_sfo` (0.4) + `sec_13f_clean`
(0.3), identical composition to Kemnay's score. The scores being equal is
itself informative: confidence here measures *evidence class*, not *AUM
size* — Kemnay and Duquesne are equally well-evidenced as real
single-family offices, even though only one of their AUM figures could be
trusted.

**Exact sources:**
- https://www.cnbc.com/2026/02/26/billionaire-family-office-investments.html (press)
- https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=1536411&type=13F-HR (filing history)
- Direct fetch of `form13f_20260331.xml` (holdings) and `primary_doc.xml` (summary/joint-filing check) via `ingestion/sec_13f_search.py`
