"""
This is where you encode YOUR OWN inclusion standard (required
deliverable per the brief) as an actual checklist, so it's applied
consistently across all records rather than judged ad hoc.

Fill in INCLUSION_CRITERIA with your own written standard before you
classify a single real record - this should match the paragraph you
write for your methodology summary.
"""

INCLUSION_CRITERIA = """
DRAFT - reviewed and adjusted by [your name] on [date] before use.
Anchored to the SEC's actual family office exemption test (17 CFR
275.202(a)(11)(G)-1) rather than an invented standard, since that's
the closest thing to a legal definition of "single-family office"
that exists - a firm that (a) advises only "family clients" within one
lineage - family members, their spouses/spousal equivalents, certain
key employees, and entities wholly owned by the family - (b) is wholly
owned and controlled by family members/family entities, and (c) does
not hold itself out to the public as an investment adviser.

A firm qualifies as a SINGLE-family office if AT LEAST ONE of:
  1. A named, credible third-party source (established press, a
     family-office intelligence database such as Preqin/Altss/SWFI,
     or a court/regulatory filing) explicitly and specifically states
     it serves one named family exclusively - not "families" plural,
     not "high-net-worth clients" generally.
  2. The firm's own site/materials state exclusivity to one named
     family AND no evidence contradicts this (no public marketing to
     other clients, no ADV brochure describing multiple client types).
  3. SEC filings + independent corroboration together establish it:
     e.g. a 13F filer whose name and address match a specific known
     family AND at least one other source (press, database profile)
     names that same family as the sole client. Neither alone is
     enough - see rule 2 in the brief; a name match is not evidence.

A firm qualifies as a MULTI-family office if:
  1. Affirmative evidence shows it serves a small, DEFINED, named or
     nameable set of families (not "clients" generally), AND
  2. It is not a large, publicly-marketed wealth manager / RIA that
     happens to use "family office" as a marketing term for its
     general HNW client base.

A firm does NOT qualify merely because:
  - Its name contains "family," "capital," "holdings," or similar
  - It is described as serving "wealthy clients" or "HNW individuals"
    without naming a specific family or a specific small client set
  - It appears in a source list/search result associated with family
    offices with no further corroboration
  - It filed a 13F and its filing text happened to match a keyword
    search (confirmed noise in this project's own data: BancorpSouth
    and Barclays both matched "family holdings"/"family investments"
    as ordinary financial-filing language, not because they are
    family offices)
  - A financial figure appears in its 13F filing - a 13F reports
    everything the filer has investment discretion over, which can
    include other clients'/related entities' assets, not just one
    family's money (confirmed live: Kemnay Advisory Services Inc.'s
    13F shows $622B/1,190 positions; Alan Parker's actual known
    wealth is nowhere near that scale - the entity's SFO status is
    independently confirmed, but its 13F total is not usable as an
    AUM figure without a second source corroborating the actual scale)

If evidence is genuinely ambiguous (e.g. a plausible SFO with no
clear single-vs-multi signal), the record does NOT count toward the
50. It may be kept in the raw candidate pool with firm_type="unclear"
and firm_qualifies=False, and mentioned honestly as a blind spot in
the methodology summary - it does not get force-classified either way.
"""


def check_qualification(evidence_text: str, criteria: str = INCLUSION_CRITERIA) -> dict:
    """
    Deliberately NOT fully automated - this returns a structured
    prompt for YOU (or an LLM call you wire in here) to reason over,
    rather than a black-box yes/no. The brief explicitly wants your
    visible reasoning here, not a silent classifier.

    If you want to automate a first pass, wire in a Groq/LLM call
    that takes `evidence_text` + `criteria` and returns a structured
    judgment - but log its reasoning, and personally review every
    positive classification before it counts toward your 50.
    """
    return {
        "evidence_text": evidence_text,
        "criteria_applied": criteria,
        "requires_human_review": True,
    }
