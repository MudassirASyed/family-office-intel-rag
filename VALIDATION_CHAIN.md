# 3-Record Full Validation Chain

Per the brief's deliverable requirement: *"Select 3 records and provide a full
validation chain: discovery source, extraction method, enrichment steps,
validation logic, confidence assessment, and exact sources or links used."*

These 3 were deliberately chosen to show three different things: the
strongest evidence tier we found (West Family Investments), a real error
caught and prevented from entering the dataset (Kemnay Advisory Services),
and the hardest-won record in the file — a genuinely ambiguous
single-family office where the classification itself needed a judgment
call, two different people are legitimately "the principal" for different
reasons, and the personal-contact gap the brief calls out as the core
difficulty of this market shows up directly, unresolved, rather than
smoothed over (Wildcat Capital Management).

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

## 3. Wildcat Capital Management

**Discovery source:** Press coverage of a 2025 exit
(`ingestion/seed_candidates_researched.py` seed set) — a single source
class, weaker than West's SEC primary declaration or Kemnay's dual
press+SEC path, and honestly scored that way (confidence 0.4, not 0.7+).
Chosen for this validation chain specifically because it is *not* the
easy case.

**Extraction method:** Yahoo Finance/Motley Fool coverage of a $16.6M
TIC Solutions exit named Wildcat as "founded 2011 as the single-family
office of David Bonderman" (TPG co-founder). Corporate LinkedIn
(`linkedin.com/company/wildcat-capital-management`) and the firm's own
site (`wildcatcap.com`) were checked directly, not assumed from the
press mention alone.

**Validation logic — where this one actually got hard:** One source
describes Wildcat as also "managing assets for an institutional client
base" beyond the Bonderman family - a real complication for a
single-family-office classification, not a footnote. Rather than either
ignore it or reflexively downgrade the record, the original press
evidence ("founded as the single-family office of David Bonderman") was
weighed against this caveat and judged to still hold - the institutional
detail was logged as an explicit, visible caveat in the record's `notes`
field instead of silently resolved either direction. Separately, the
"principal" itself turned out not to be a single clean answer: David
Bonderman died December 2024, and Len Potter (ex-Soros Fund Management
private equity co-head) has run Wildcat as CEO & CIO since 2011 - the
*operating* principal, distinct from Bonderman as the *family* principal
whose wealth the office exists to manage. Both were recorded, labeled by
role, rather than arbitrarily picking one and dropping the other.

**Enrichment steps, including today's live attempt at the hardest gap in
the dataset:** AUM ($4.08-4.1B) added from 13F-adjacent holdings data.
For principal contact specifically - the field this entire dataset is
weakest on for single-family offices - `wildcatcap.com` was fetched
directly and returned a real general office contact:
`info@wildcatcap.com`, 212-468-5100, 888 7th Avenue 37th Fl, New York,
NY. This was deliberately **not** written into `principal_email` or
`principal_phone`: every other populated `principal_email` in this
dataset is a named-person address (e.g. `chris@biltmorefamilyoffice.com`),
and a generic `info@` inbox does not meet that bar - filling it in would
have meant presenting a general company inbox as a verified
decision-maker contact, which is precisely the kind of guessed-value-
dressed-as-verified the brief disqualifies. It was logged in `notes`
as a clearly-labeled general office contact instead. The field stays
honestly blank.

**Confidence assessment:** 0.4 — `press_named_sfo` alone. No SEC 13F
corroboration was found for this specific entity, so it carries a real,
visible confidence gap relative to West and Kemnay, not an inflated
score to match them.

**Exact sources:**
- https://finance.yahoo.com/news/billionaire-family-offices-16-6-183153119.html (press, discovery + exit detail)
- https://www.linkedin.com/company/wildcat-capital-management (corporate LinkedIn)
- https://www.wildcatcap.com (direct fetch, general office contact)
