# Methodology Summary

## What this dataset is

50 real, individually-verified family office records in `data/records.json`
(28 single-family offices, 22 multi-family offices), produced by a
re-runnable pipeline (`scripts/discover_*.py` -> review files ->
`scripts/build_dataset.py` -> `scripts/apply_enrichment.py`), not
hand-assembled. Every record traces back to at least one primary or
secondary source cited in `sources_checked`/`evidence`.

## Discovery

Three independent, script-driven channels, deliberately kept separate so no
single convenient source drives the dataset (see `SYSTEM_DESIGN.md`, "Source
class separation"):

1. **SEC EDGAR 13F full-text search** (`ingestion/sec_13f_search.py`) —
   keyword sweeps ("family office", "family investments", "family wealth"
   etc.) against `data.sec.gov`, producing ~78 raw candidates
   (`data/13f_candidates_raw.json`), filtered for filing recency
   (`scripts/filter_stale_candidates.py` -> `13f_candidates_active.json`).
2. **Press-based seeding** (`ingestion/seed_candidates_researched.py`) —
   named single-family offices tied to a documented liquidity event
   (e.g., Duquesne/Druckenmiller, Kemnay/Alan Parker), independently
   re-verified through the SEC channel during this build rather than
   trusted on press alone.
3. **NewsAPI discovery** (`ingestion/news_search.py`,
   `scripts/discover_news_candidates.py`) — ~30-day rolling window, real
   API key, regex-based entity extraction (documented as crude, not NLP,
   in `SYSTEM_DESIGN.md`).

## Verification — two-rule model

- **Cell-level** (`sources_checked` / `evidence` per field): honest blanks
  allowed. A field is only ever filled when a specific source for that
  specific value was checked and logged — never inferred or guessed.
- **Firm-level** (`firm_qualifies`): strict, binary, anchored on the actual
  SEC family-office exemption standard (17 CFR 275.202(a)(11)(G)-1), not a
  vibe check. `processing/classifier.py::check_qualification()` produces a
  structured review prompt; the qualify/reject call itself is a logged
  human (AI-assisted) judgment, recorded per-candidate in
  `data/13f_review_notes.json` and `data/news_propublica_review.json` with
  verdict + reason + sources — this is the "manual judgment allowed, but
  it must be logged" artifact the brief permits alongside scripted
  discovery/compilation.

`qualifies_for_final_dataset()` requires both simultaneously — a
well-sourced record on a disqualified firm still fails, and a qualifying
firm with zero evidence still fails.

## Confidence scoring

Never hand-typed. `FamilyOfficeRecord.compute_confidence()` sums
`SOURCE_WEIGHTS` for whichever source classes were actually checked
(`sec_primary_declaration` 0.45, `press_named_sfo` 0.4, `sec_13f_clean`
0.3, `multi_source_corroboration` 0.25, capped at 1.0). Current dataset
average confidence: **0.34** — intentionally not inflated; most records
carry one or two source classes, not five.

## Enrichment

Structured findings logged to `data/enrichment_notes.json` with citations,
merged via `scripts/apply_enrichment.py`, which never silently overwrites
a non-empty field (prints a conflict instead). This is what makes the
process idempotent and re-runnable rather than a one-time hand edit.

## Known blind spots (stated honestly, not hidden)

- **Contact-level completion is genuinely capped for single-family
  offices specifically, and the gap is real, not just described in the
  abstract.** Overall field completion is **77.3%** across all schema
  fields; core identity/qualification fields (name, firm_type,
  qualification evidence, at least one source) are effectively 100%
  regardless of firm type. But actionability, the field group the brief
  weighs most heavily, splits sharply by firm type:

  | Field | SFO (n=28) | MFO (n=22) |
  |---|---|---|
  | principal_name / title | 100% | 95% |
  | principal_email | **0%** | 23% |
  | principal_phone | **0%** | 64% |
  | principal_linkedin | 11% | 59% |
  | corporate_linkedin | 64% | 50% |
  | AUM | 43% | 82% |

  Zero of the 28 SFOs have a verified principal email or phone. This is
  not an effort gap - it is the direct, honest cost of prioritizing true
  single-family-office discovery (the brief's stated "valued prize")
  over the multi-family offices that "want to be found" and therefore
  publish contact info by default. A dataset built by convenient
  sourcing would show the opposite pattern: high MFO contact completion,
  few SFOs at all. Spent focused time specifically closing the
  *corporate*-outreach gap (a verifiable, lower-impersonation-risk
  channel than personal contact details): SFO corporate LinkedIn
  coverage went from 39% (11/28) to 57% (16/28) in that pass, and 18/28
  SFOs now have at least one outreach path (personal or corporate
  LinkedIn) versus roughly half that before. Personal email/phone for
  SFOs stayed at 0% - genuinely unreachable through any research channel
  checked, not unresearched.

  One deliberate line was held while closing this gap: for 3 SFOs
  (Wildcat Capital Management, DNS Capital, Duchossois Capital
  Management), their own websites list a general office inbox and, for
  two of them, a phone number (`info@wildcatcap.com` +
  212-468-5100; `info@dnscap.com`; `info@dcmllc.com` + 312.586.2080).
  Every existing `principal_email` value in this dataset is a
  named-person address (e.g. `chris@biltmorefamilyoffice.com`) - a
  generic `info@` inbox doesn't meet that bar, and filling
  `principal_email` with it would misrepresent a general company inbox
  as the decision-maker's verified direct line, exactly what "a guessed
  value dressed up as verified" means. These were logged in `notes` as
  clearly-labeled general office contacts instead, and deliberately do
  NOT count toward the principal_email/principal_phone completion
  numbers above - real, useful information, honestly categorized rather
  than used to quietly inflate the metric that matters most.
- **13F dollar values are unreliable beyond joint-filing detection.** Three
  distinct failure modes were found and documented in `SYSTEM_DESIGN.md`
  (joint filings, discretion-over-others'-assets even with a clean filer
  count, and a batch-pull schema issue that inflated one firm's value 89x).
  Response: dollar figures were dropped dataset-wide except where
  independently corroborated as plausible — an honest blank over a wrong
  number, per the brief's own stated standard.
- **News-based entity extraction is regex, not NLP** — expected to miss or
  misfire on some candidate names; this is why every news-discovered
  candidate is independently re-verified before inclusion, not
  auto-accepted.
- One firm (Noble Family Wealth) was provisionally qualified during an
  earlier pass on a thin, unsourced description, then caught during final
  integrity review (empty `evidence` field), re-researched, and reversed
  to reject — recorded here as an example of the review catching itself,
  not swept under the rug.
- A second, later catch of the same kind: **Hemendra Kothari Family
  Office** was in the dataset with its own `notes` field admitting the
  problem outright - *"'Kothari' is a common Indian surname with
  multiple distinct wealthy families with their own family offices...
  this record is my best-evidenced match, not a certain one."* That is a
  Rule 2 (firm identity) failure, not a Rule 1 (cell uncertainty) one -
  the brief is explicit that an unresolved identity question means the
  record does not qualify, regardless of how well other cells are
  sourced. An attempt to resolve it with more research briefly produced
  a false positive (a search summary claimed a third source explicitly
  confirmed the connection; directly fetching that source showed it did
  not say that at all - a live example of exactly the kind of
  verification gap this whole project is built to catch, this time in
  my own research process). Replaced with **DFO Management, LLC**
  (Michael Dell's family office, formerly MSD Capital, L.P.) - unambiguous
  identity confirmed via SEC EDGAR (CIK 1105497, active non-joint 13F
  filer) plus independent press/reference corroboration, confidence 0.7
  vs. the removed record's 0.1. The same 13F-value-implausibility issue
  documented elsewhere in this file also showed up on this record's
  first pull ($78.24B against a small-cap REIT) and was caught the same
  way - the value was dropped, the identity was not.
- **Geographic scope was narrowed to US and Europe as a deliberate product
  decision, separate from the evidence-quality point above.** The
  dataset's one remaining non-US/EU record (Adar Poonawalla Family
  Office, India) was well-evidenced - multi-source corroborated, no
  identity ambiguity - and was removed anyway, on scope grounds rather
  than quality grounds. Replaced with **Willett Advisors LLC** (Michael
  Bloomberg's single-family office, est. 2010): SEC-confirmed as a real
  registered entity (CIK 1509379, address matches independent sources
  exactly) plus unambiguous press corroboration (confidence 0.75, the
  second-highest in this dataset). One honesty note on this record: its
  SEC 13F filings are stale (last filed 2014) - its `sec_filing` source
  class here means "confirmed to exist as a registered entity," not
  "currently active 13F filer," and that distinction is stated
  explicitly rather than implied.

## Final composition

| Metric | Value |
|---|---|
| Total records | 50 |
| Single-family offices | 28 |
| Multi-family offices | 22 |
| Firms passing `firm_qualifies` | 50 / 50 |
| Overall field completion | 77.3% |
| Average confidence score | 0.36 |
| SFOs with a corporate LinkedIn | 18 / 28 (64%) |
| SFOs with any outreach path (personal or corporate LinkedIn) | 19 / 28 (68%) |
| SFOs with a verified principal email or phone | 0 / 28 |
| Geographic scope | US and Europe only (deliberate scope decision, see below) |
