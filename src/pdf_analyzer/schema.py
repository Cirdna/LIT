"""JSON schema for contract analysis output.

Two things this schema has to do that a flat per-contract record cannot:

1. Answer every CUAD category, including the ones that are absent. A review
   that says nothing about Non-Compete is ambiguous between "there is no
   non-compete", "we didn't look", and "the model failed". Expert review
   output asserts absence explicitly and gives its reasoning, so
   `CategoryFinding.answer` is always populated for all 41 categories.

2. Represent relationships *between* contracts. A conflict never lives inside
   one record -- two leases for the same room are each individually valid --
   so join keys (counterparty, asset, contract family) are first-class
   fields. Free text hides exactly what needs comparing: "Acme Inc." and
   "Acme Corp" don't match as strings, and a prose paragraph about an
   exclusivity grant can't be checked for date-range overlap. Restrictive
   clauses therefore carry structured scope and dates alongside their quote.

Every inferred join key carries its own confidence tier and resolution
method, because these IDs fail in both directions: merging two different
companies invents a conflict, and failing to merge two spellings of one
company hides a real one.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Anchoring: where a piece of text physically sits in the source document
# --------------------------------------------------------------------------


class Location(BaseModel):
    page: int
    bbox_1000: List[float] = Field(min_length=4, max_length=4)


class Source(BaseModel):
    page: int
    clause: str
    exact_supporting_text: str


class OcrVerification(BaseModel):
    """Mechanical check that the model's text really appears in the document.

    Deliberately named for what it measures. This is an anti-hallucination
    grounding signal from Stage 3 reconciliation -- it says the text was
    found on the page, and nothing about whether the legal reading is right.
    It is not the same judgement as `EvidenceStatus` or `ReviewFlag` below,
    which are about the analysis rather than the pixels.
    """

    ocr_text: str
    score: float = Field(ge=0.0, le=100.0)
    recall: float = Field(ge=0.0, le=100.0)
    evidence_mass: float
    is_grounded: bool


# --------------------------------------------------------------------------
# Analytical judgement (legal semantics, not OCR semantics)
# --------------------------------------------------------------------------


class EvidenceStatus(str, Enum):
    """How the answer for a category was arrived at."""

    DIRECT = "direct"  # quoted verbatim from the contract
    DERIVED = "derived"  # concluded from the absence of any such clause
    INFERRED = "inferred"  # legal judgement on top of the text
    UNRESOLVED = "unresolved"  # cannot determine from this document alone


class AnswerStatus(str, Enum):
    PRESENT = "present"  # the category is addressed by this contract
    ABSENT = "absent"  # searched for, genuinely not present
    UNRESOLVED = "unresolved"  # e.g. depends on an incorporated document


class ReviewFlag(BaseModel):
    """Analyst-facing judgement that a human needs to look at this.

    Raised for substantive reasons -- mixed asset-specific terms where a
    single value would mislead, or a restriction that lives in an
    incorporated agreement not reproduced here -- not merely because an OCR
    score was low.
    """

    flagged: bool
    reason: str = ""


class CategoryFinding(BaseModel):
    """The answer for one CUAD category. Always present for all 41."""

    answer: AnswerStatus
    summary: str  # e.g. "Delaware", "No", "No single contract-wide expiration date"
    evidence_status: EvidenceStatus
    review_flag: ReviewFlag
    extractions: List["CuadExtraction"] = Field(default_factory=list)


class CuadExtraction(BaseModel):
    """One quoted span supporting a category answer."""

    vlm_text: str
    location: Location
    source: Source
    ocr_verification: OcrVerification
    clause_id: Optional[str] = None  # links to a StructuredClause, when one exists


# --------------------------------------------------------------------------
# Relationship keys -- the join keys that make cross-contract checks possible
# --------------------------------------------------------------------------


class ConfidenceTier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ResolutionMethod(str, Enum):
    """How an entity/asset/family ID was assigned, which sets its tier."""

    REGISTRATION_NUMBER = "registration_number"  # -> high
    EXACT_NAME = "exact_name"  # -> high
    NORMALIZED_NAME = "normalized_name"  # -> medium (suffix/punctuation only)
    FUZZY_NAME = "fuzzy_name"  # -> medium, flagged
    LLM_SUGGESTED = "llm_suggested"  # -> low, always human review
    HUMAN_CONFIRMED = "human_confirmed"  # -> high
    UNRESOLVED = "unresolved"  # deliberate abstention


_TIER_BY_METHOD = {
    ResolutionMethod.REGISTRATION_NUMBER: ConfidenceTier.HIGH,
    ResolutionMethod.EXACT_NAME: ConfidenceTier.HIGH,
    ResolutionMethod.HUMAN_CONFIRMED: ConfidenceTier.HIGH,
    ResolutionMethod.NORMALIZED_NAME: ConfidenceTier.MEDIUM,
    ResolutionMethod.FUZZY_NAME: ConfidenceTier.MEDIUM,
    ResolutionMethod.LLM_SUGGESTED: ConfidenceTier.LOW,
    ResolutionMethod.UNRESOLVED: ConfidenceTier.LOW,
}


class EntityLink(BaseModel):
    """A resolved (or deliberately unresolved) canonical ID.

    `canonical_id is None` is a first-class outcome, not a failure: two
    similarly-named but genuinely different companies must stay unmerged, and
    abstaining is the correct answer there. A low-tier link may be recorded
    but must not on its own justify a flagged conflict.
    """

    canonical_id: Optional[str]
    raw_value: str
    resolution_method: ResolutionMethod
    confidence_tier: ConfidenceTier
    requires_human_review: bool
    evidence: str = ""  # e.g. "UEN 200812345K on both records"

    @classmethod
    def build(
        cls,
        canonical_id: Optional[str],
        raw_value: str,
        method: ResolutionMethod,
        evidence: str = "",
    ) -> "EntityLink":
        tier = _TIER_BY_METHOD[method]
        return cls(
            canonical_id=canonical_id,
            raw_value=raw_value,
            resolution_method=method,
            confidence_tier=tier,
            # Anything below high tier is a candidate for a phantom conflict,
            # so it is surfaced rather than trusted silently.
            requires_human_review=tier is not ConfidenceTier.HIGH,
            evidence=evidence,
        )


# --------------------------------------------------------------------------
# Structured restrictive clauses -- comparable, not prose
# --------------------------------------------------------------------------


class RestrictiveClauseType(str, Enum):
    """The nine clause types that can create a cross-contract conflict."""

    MFN = "most_favored_nation"
    NON_COMPETE = "non_compete"
    EXCLUSIVITY = "exclusivity"
    NO_SOLICIT = "no_solicit"
    ROFR_ROFO_ROFN = "rofr_rofo_rofn"
    MINIMUM_COMMITMENT = "minimum_commitment"
    VOLUME_RESTRICTION = "volume_restriction"
    PRICE_RESTRICTIONS = "price_restrictions"
    REVENUE_SHARING = "revenue_profit_sharing"


class ScopeKind(str, Enum):
    ASSET = "asset"
    PRODUCT = "product"
    TERRITORY = "territory"
    FIELD_OF_USE = "field_of_use"
    CUSTOMER_SEGMENT = "customer_segment"
    OTHER = "other"


class ScopeTag(BaseModel):
    """A canonical tag for what a clause covers.

    `canonical_id` is what deterministic comparison runs on; `raw_value`
    preserves the contract's own wording for the reviewer. Keeping both is
    what lets "US and Canada" and "North America" be compared structurally
    where the containment table knows the answer, and escalated to a narrow
    LLM scope judgement only where it doesn't.
    """

    kind: ScopeKind
    canonical_id: Optional[str]
    raw_value: str
    resolution_method: ResolutionMethod = ResolutionMethod.UNRESOLVED


class DateRange(BaseModel):
    """A clause's active period. Comparison here is plain logic, no model."""

    start: Optional[date] = None
    end: Optional[date] = None
    is_perpetual: bool = False
    raw_text: str = ""

    def overlaps(self, other: "DateRange") -> bool:
        """Deterministic date-range overlap. Open/perpetual ends are treated
        as extending indefinitely, so an unbounded grant overlaps anything
        starting after it -- the conservative reading for conflict review."""
        start_a = self.start
        start_b = other.start
        end_a = None if self.is_perpetual else self.end
        end_b = None if other.is_perpetual else other.end

        if end_a is not None and start_b is not None and end_a < start_b:
            return False
        if end_b is not None and start_a is not None and end_b < start_a:
            return False
        return True


class ClauseQuantity(BaseModel):
    """A numeric term, kept separate from prose so commitments and ceilings
    can be summed and compared without re-reading the clause."""

    value: float
    unit: str  # e.g. "SGD", "units", "percent"
    period: str = ""  # e.g. "per_year", "total"


class StructuredClause(BaseModel):
    """A restrictive clause in comparable form, alongside its source quote."""

    clause_id: str
    clause_type: RestrictiveClauseType
    restricts_who: List[str] = Field(default_factory=list)  # party raw names/roles
    restricted_action: str = ""
    scope: List[ScopeTag] = Field(default_factory=list)
    is_exclusive: bool = False
    date_range: DateRange = Field(default_factory=DateRange)
    quantity: Optional[ClauseQuantity] = None

    # Anchored exactly like every other extracted field.
    source: Source
    location: Location
    ocr_verification: Optional[OcrVerification] = None

    # Supersession: set when this clause amends one in another contract.
    amends: Optional["ClauseRef"] = None


class ClauseRef(BaseModel):
    contract_id: str
    clause_id: Optional[str] = None
    effect: str = "modifies"  # modifies | supersedes | terminates


# --------------------------------------------------------------------------
# Statute layer
#
# Two roles, and the distinction is the whole point:
#
#   Role A supplies what the law provides when the contract is silent
#          (StatutoryDefault). It is kept OUT of cuad_findings so that statute
#          wording can never be mistaken for a quote from the document. A
#          default is "displaced" once the contract is found to address the
#          topic itself.
#
#   Role B reads what the contract DOES say and raises a trigger for a human
#          (StatuteFlag). It never mutates the extracted field: the clause text
#          stays exactly as extracted, and the flag sits alongside it.
#
# Neither role decides anything. This layer surfaces the provision and the
# factors a lawyer must weigh; it does not weigh them.
# --------------------------------------------------------------------------


class StatuteRole(str, Enum):
    DEFAULT_SUPPLYING = "role_a_default"  # gap-filler: applies unless displaced
    REVIEWING = "role_b_review"  # validator: reads the clause, raises a trigger


class StatutoryDefault(BaseModel):
    """What the law supplies for a topic, absent contrary agreement."""

    field_name: str
    statute: str
    citation: str  # e.g. "s.14(2)"
    jurisdiction: str = "Singapore"

    # A PARAPHRASE, always. `verbatim_text` stays None until someone loads the
    # actual statute text from an authoritative source: this project refuses to
    # present unverified wording as a quotation, and that rule does not stop
    # applying just because the source is an Act rather than a contract.
    effect: str
    verbatim_text: Optional[str] = None

    # The precondition for the default applying at all (e.g. "the seller sells
    # in the course of a business"). Not evaluated here — stated for the reader.
    applies_when: str

    # Extracted categories whose presence means the contract addressed the topic.
    displaced_by_categories: List[str] = Field(default_factory=list)
    # False where no extracted category corresponds, i.e. this tool cannot tell
    # whether the contract displaced the default. Silence is not agreement.
    auto_displacement_supported: bool = True

    is_displaced: bool = False
    displaced_by: Optional[Source] = None  # the clause that displaced it

    raised_by: str  # module that supplied it, for traceability


class StatuteFlag(BaseModel):
    """A trigger for human review — never a legal conclusion.

    "This clause excludes the s.14 implied terms; reasonableness review
    required" is a trigger. "This clause is void" is a conclusion, and nothing
    in this layer is entitled to reach one.
    """

    flag_id: str
    statute: str
    citation: str
    jurisdiction: str = "Singapore"

    field_name: str  # the extracted field that triggered it
    trigger: str  # what was detected, in plain language
    review_required: str  # what a human must now decide
    factors: List[str] = Field(default_factory=list)  # what that decision turns on

    excerpt: str  # the clause text as extracted, unmodified
    source: Optional[Source] = None
    location: Optional[Location] = None

    # None  = not a reasonableness question at all
    # False = the Act admits no reasonableness escape (e.g. UCTA s.2(1))
    # True  = a statutory reasonableness test applies
    reasonableness_test_applies: Optional[bool] = None

    # Never False. This layer raises questions; it does not close them.
    requires_human_review: bool = True

    raised_by: str


# --------------------------------------------------------------------------
# The per-contract record
# --------------------------------------------------------------------------


class DocumentMetadata(BaseModel):
    source_file: str
    processed_pdf: str
    total_pages: int


class ContractAnalysis(BaseModel):
    contract_id: str
    document_metadata: DocumentMetadata

    # Join keys. Present on every record so portfolio-level passes can group
    # without re-reading the documents.
    counterparties: List[EntityLink] = Field(default_factory=list)
    assets: List[EntityLink] = Field(default_factory=list)
    contract_family: Optional[EntityLink] = None
    amends: Optional[ClauseRef] = None  # this whole contract amends another

    # All 41 categories, always answered.
    cuad_findings: Dict[str, CategoryFinding] = Field(default_factory=dict)

    # Comparable form of the restrictive clauses found above.
    structured_clauses: List[StructuredClause] = Field(default_factory=list)

    # Statute layer, deliberately parallel to cuad_findings: what the law
    # supplies where the contract is silent (Role A), and what the law wants
    # looked at in what the contract does say (Role B). Neither is merged into
    # the extracted findings.
    statutory_defaults: Dict[str, StatutoryDefault] = Field(default_factory=dict)
    flags: List[StatuteFlag] = Field(default_factory=list)

    def to_json_dict(self) -> dict:
        return self.model_dump(mode="json")


# --------------------------------------------------------------------------
# Cross-contract conflict review queue
# --------------------------------------------------------------------------


class ConflictPass(str, Enum):
    PARTY_BASED = "party_based"
    ASSET_BASED = "asset_based"


class DetectionProvenance(str, Enum):
    DETERMINISTIC = "deterministic"
    LLM_ASSISTED = "llm_assisted"


class ConflictEvidence(BaseModel):
    """One side of a flagged pair, fully sourced back to the page."""

    contract_id: str
    clause_id: Optional[str]
    excerpt: str
    page: int
    clause: str
    bbox_1000: List[float] = Field(min_length=4, max_length=4)


class FlaggedConflict(BaseModel):
    """A pre-triaged pair handed to a lawyer.

    Deliberately carries no notion of which contract "wins" -- adjudication
    is the reviewer's, and the tool's job ends at presenting both sides with
    their provenance.
    """

    conflict_id: str
    conflict_class: str  # e.g. "overlapping_exclusive_grant", "mfn_trigger"
    detected_by: ConflictPass
    provenance: DetectionProvenance
    rule_id: Optional[str] = None  # which deterministic rule fired
    left: ConflictEvidence
    right: ConflictEvidence
    # Every join key the match leaned on, so a reviewer can see whether the
    # pairing rests on a registration-number match or a fuzzy name guess.
    relationship_ids: List[EntityLink] = Field(default_factory=list)
    lowest_confidence_tier: ConfidenceTier = ConfidenceTier.HIGH
    requires_human_review: bool = True
    explanation: str = ""


class ConflictReviewQueue(BaseModel):
    conflicts: List[FlaggedConflict] = Field(default_factory=list)
    contracts_examined: List[str] = Field(default_factory=list)
    party_pass_groups: int = 0
    asset_pass_groups: int = 0

    def to_json_dict(self) -> dict:
        return self.model_dump(mode="json")


CategoryFinding.model_rebuild()
StructuredClause.model_rebuild()
