"""
The FamilyOfficeRecord schema + confidence scoring.

Two separate rules, per the brief - implemented as two separate
fields so they can never be conflated:
  1. cell_confidence: per-field, can be an honest "could not verify"
  2. firm_qualifies: per-entity, strict - True only with affirmative
     evidence the firm actually IS a family office (not just wealthy,
     not just "family" in the name).
"""
from dataclasses import dataclass, field
from datetime import date

# Weight by source authority. Tune based on what you actually find -
# these are starting judgments, not fixed truths. Extended after the
# 13F/news discovery pass turned up source classes the original set
# didn't distinguish - e.g. a firm's own SEC filing stating "family
# office exempt under the Family Office Exemption" (West Family
# Investments) is categorically stronger evidence than a generic ADV
# filing, and deserves to score that way.
SOURCE_WEIGHTS = {
    "sec_primary_declaration": 0.45,  # the ENTITY'S OWN SEC filing states its family-office
                                       # status directly (e.g. citing the Family Office Exemption)
                                       # - strongest evidence class found this session
    "press_named_sfo": 0.4,           # named as SFO in credible financial press
    "sec_filing": 0.35,                # ADV or other SEC filing confirms entity exists
    "sec_13f_clean": 0.3,              # active, non-joint 13F filing at a plausible scale -
                                        # confirms the entity is real and a going concern
    "multi_source_corroboration": 0.25,  # 3+ independent sources agree (business journalism +
                                          # own site + third-party database, none contradicting)
    "own_website": 0.25,
    "990_foundation_link": 0.2,        # linked family foundation, corroborating
    "third_party_directory": 0.1,      # single aggregator label only - weakest, easy to be
                                        # wrong (confirmed live: Altss mislabeled Family Manage
                                        # LLC as single-family when the firm's own site said multi)
}


@dataclass
class FamilyOfficeRecord:
    name: str
    firm_type: str                      # "single_family_office" | "multi_family_office" | "unclear"
    firm_qualifies: bool                 # strict gate - see docstring above
    qualification_evidence: str          # what specifically proves firm_type
    sources_checked: dict = field(default_factory=dict)   # {"press_named_sfo": True, ...}
    evidence: dict = field(default_factory=dict)           # {"press_named_sfo": "url or excerpt"}

    # Firm-level enrichment (all optional, honestly blank if unverified)
    description: str = ""
    investment_thesis: str = ""
    investing_sectors: str = ""
    aum: str = ""            # keep as free text ("$400M-$600M, estimated per 13F"), not a bare
                              # number - AUM for true SFOs is rarely precisely disclosed, and a
                              # fake-precise figure is worse than an honest range with its basis
    website: str = ""
    corporate_linkedin: str = ""
    city: str = ""
    state: str = ""
    country: str = ""

    # Contact/principal enrichment
    principal_name: str = ""
    principal_title: str = ""
    principal_linkedin: str = ""
    principal_email: str = ""
    principal_email_verified: bool = False
    principal_phone: str = ""

    # Recent activity signal
    recent_activity: str = ""
    recent_activity_date: str = ""

    confidence: float = 0.0
    date_verified: str = field(default_factory=lambda: date.today().isoformat())
    notes: str = ""   # honest caveats, blind spots, what you could not confirm

    def compute_confidence(self) -> float:
        score = sum(w for k, w in SOURCE_WEIGHTS.items() if self.sources_checked.get(k))
        self.confidence = round(min(score, 1.0), 2)
        return self.confidence

    def qualifies_for_final_dataset(self, min_confidence: float) -> bool:
        """
        The strict gate: firm_qualifies must be True (rule 2 - the
        firm itself), AND confidence must clear your stated bar.
        A high-confidence record on a disqualified firm still fails.
        """
        return self.firm_qualifies and self.confidence >= min_confidence

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


if __name__ == "__main__":
    r = FamilyOfficeRecord(
        name="Example SFO LLC",
        firm_type="single_family_office",
        firm_qualifies=True,
        qualification_evidence="Named explicitly as a single-family office in CNBC's 2026 Inside Wealth ranking.",
        sources_checked={"press_named_sfo": True},
        evidence={"press_named_sfo": "https://example.com/article"},
        notes="Could not find principal email; website has no contact page.",
    )
    r.compute_confidence()
    print(r.to_dict())
    print("Qualifies at 0.3 bar:", r.qualifies_for_final_dataset(0.3))
