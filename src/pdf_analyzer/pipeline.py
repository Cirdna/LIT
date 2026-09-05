"""Orchestrates Stages 1-4 of the gameplan: ingest -> dual-pipeline extraction
-> fuzzy spatial reconciliation -> enriched CUAD JSON output.

Stage 5 (frontend click-to-jump) consumes the JSON this module produces; see
frontend/ and api/main.py.

Cross-contract conflict detection (conflict.py) runs over a *set* of these
analyses, so it lives at the end of this module (`scan_for_conflicts`) rather
than inside `analyze_document`: a conflict never exists inside one contract.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from . import statutes
from .conflict import build_review_queue
from .cuad_classes import CUAD_CLASSES
from .schema import (
    AnswerStatus,
    CategoryFinding,
    ConflictReviewQueue,
    ContractAnalysis,
    CuadExtraction,
    DateRange,
    DocumentMetadata,
    EntityLink,
    EvidenceStatus,
    Location,
    OcrVerification,
    ResolutionMethod,
    RestrictiveClauseType,
    ReviewFlag,
    Source,
    StructuredClause,
)
from .stage1_ingest import ingest
from .stage2_ocr import extract_document_words
from .stage2_vlm import VlmBackend
from .stage3_reconcile import VERIFICATION_THRESHOLD, reconcile_phrase

logger = logging.getLogger(__name__)


def _build_extraction(
    vlm_text: str,
    clause_label: str,
    page_number: int,
    match,
) -> CuadExtraction:
    grounded = match.is_verified if match is not None else False
    ocr_text = match.matched_text if match is not None else ""
    bbox_1000 = match.bbox_1000 if match is not None else [0.0, 0.0, 0.0, 0.0]

    return CuadExtraction(
        vlm_text=vlm_text,
        location=Location(page=page_number, bbox_1000=bbox_1000),
        source=Source(
            page=page_number,
            clause=clause_label or "Unlabeled",
            exact_supporting_text=ocr_text,
        ),
        ocr_verification=OcrVerification(
            ocr_text=ocr_text,
            score=match.match_score if match is not None else 0.0,
            recall=match.recall if match is not None else 0.0,
            evidence_mass=match.evidence_mass if match is not None else 0.0,
            is_grounded=grounded,
        ),
    )


def _finding_for(extractions: list) -> CategoryFinding:
    """Build a category answer from whatever this stage managed to extract.

    A category with no extraction is reported as UNRESOLVED, never ABSENT.
    Asserting absence is a substantive legal claim -- expert review says "no
    clause located restricting solicitation" only after looking -- and the
    current extraction stage cannot distinguish "this contract has no such
    clause" from "the model failed to report one". Recording silence as
    ABSENT would turn every extraction miss into a confident wrong answer,
    which is worse than a flagged gap.
    """
    if not extractions:
        return CategoryFinding(
            answer=AnswerStatus.UNRESOLVED,
            summary="",
            evidence_status=EvidenceStatus.UNRESOLVED,
            review_flag=ReviewFlag(
                flagged=True,
                reason=(
                    "No extraction produced for this category; absence has not been "
                    "verified, so this is an open question rather than a 'no'."
                ),
            ),
            extractions=[],
        )

    grounded = [e for e in extractions if e.ocr_verification.is_grounded]
    if grounded:
        return CategoryFinding(
            answer=AnswerStatus.PRESENT,
            summary=grounded[0].vlm_text,
            evidence_status=EvidenceStatus.DIRECT,
            review_flag=ReviewFlag(flagged=False, reason=""),
            extractions=extractions,
        )

    return CategoryFinding(
        answer=AnswerStatus.PRESENT,
        summary=extractions[0].vlm_text,
        evidence_status=EvidenceStatus.UNRESOLVED,
        review_flag=ReviewFlag(
            flagged=True,
            reason=(
                "Extracted text could not be grounded in the page's OCR above the "
                f"{VERIFICATION_THRESHOLD:.0f}% threshold; verify the quote before relying on it."
            ),
        ),
        extractions=extractions,
    )


# --------------------------------------------------------------------------
# Relationship join keys and comparable clauses
#
# conflict.py groups contracts by resolved canonical IDs and compares
# StructuredClauses. Both were previously left empty by this stage, which made
# every conflict pass a no-op on real documents. The two functions below fill
# them from what Stage 2b/3 already produced -- nothing more. In particular
# there is deliberately no fuzzy matching, no LLM resolution, no date parsing
# and no asset/scope resolution here; each of those is its own stage, and
# guessing at them would manufacture phantom conflicts.
# --------------------------------------------------------------------------

# A party span is split on these only. "Acme, Inc." must not be torn in half,
# so commas are not separators.
_PARTY_SEPARATORS = re.compile(r"\s+and\s+|;", re.IGNORECASE)
# Quotes/brackets/trailing sentence punctuation that ride along with a quoted
# span. Stripping them is not name normalization: no suffix ("Pte Ltd", "Inc")
# is ever removed, so two spellings of one company still stay unmerged.
_PARTY_EDGE_CHARS = "\"“”'()[] \t\n.,:;"


def _exact_party_key(raw: str) -> Optional[str]:
    """Canonical ID for a party, by exact name only.

    Whitespace is collapsed and case folded so that the same name wrapped
    differently across two pages still matches itself. Nothing else is
    touched: "Acme Industries Pte Ltd" and "Acme Industrial Ltd" produce two
    different keys and therefore never group, which is the required behaviour
    for a near-miss pair (merging them would invent a conflict).

    Returns None for a span too short or too generic to be a name at all.
    """
    cleaned = " ".join(raw.strip(_PARTY_EDGE_CHARS).split())
    if len(cleaned) < 3:
        return None
    return f"party:{cleaned.casefold()}"


def _counterparties_from_findings(findings: Dict[str, CategoryFinding]) -> List[EntityLink]:
    """Build counterparty join keys from the extracted `parties` category.

    Only *grounded* extractions are used. An ungrounded quote failed Stage 3's
    check that the text is really on the page, and a join key built from text
    the document may not contain is exactly how a phantom conflict starts.

    The split is deliberately dumb (see `_PARTY_SEPARATORS`). A span the VLM
    returned as prose -- "This Agreement is between Acme Inc. and Beta Ltd." --
    yields one usable name and one junk key. Junk keys are harmless: they
    match nothing, so the pass abstains instead of pairing the wrong records.
    """
    finding = findings.get("parties")
    if finding is None:
        return []

    links: List[EntityLink] = []
    seen: set[str] = set()
    for extraction in finding.extractions:
        if not extraction.ocr_verification.is_grounded:
            continue
        for part in _PARTY_SEPARATORS.split(extraction.ocr_verification.ocr_text):
            canonical_id = _exact_party_key(part)
            if canonical_id is None or canonical_id in seen:
                continue
            seen.add(canonical_id)
            links.append(
                EntityLink.build(
                    canonical_id=canonical_id,
                    raw_value=part.strip(_PARTY_EDGE_CHARS),
                    method=ResolutionMethod.EXACT_NAME,
                    evidence=(
                        f"exact name quoted on page {extraction.source.page} "
                        f"({extraction.source.clause})"
                    ),
                )
            )
    return links


# CUAD categories that map onto the nine conflict-capable clause types. Both
# no-solicit categories collapse onto one type, which is why this is a mapping
# rather than a name match.
_RESTRICTIVE_CLAUSE_TYPES: Dict[str, RestrictiveClauseType] = {
    "most_favored_nation": RestrictiveClauseType.MFN,
    "non_compete": RestrictiveClauseType.NON_COMPETE,
    "exclusivity": RestrictiveClauseType.EXCLUSIVITY,
    "no_solicit_of_customers": RestrictiveClauseType.NO_SOLICIT,
    "no_solicit_of_employees": RestrictiveClauseType.NO_SOLICIT,
    "rofr_rofo_rofn": RestrictiveClauseType.ROFR_ROFO_ROFN,
    "minimum_commitment": RestrictiveClauseType.MINIMUM_COMMITMENT,
    "volume_restriction": RestrictiveClauseType.VOLUME_RESTRICTION,
    "price_restrictions": RestrictiveClauseType.PRICE_RESTRICTIONS,
    "revenue_profit_sharing": RestrictiveClauseType.REVENUE_SHARING,
}


def _structured_clauses_from_findings(
    findings: Dict[str, CategoryFinding]
) -> List[StructuredClause]:
    """Put the restrictive clauses into the comparable form conflict.py needs.

    Two fields stay empty, and both limit what can fire:

    - `date_range` is left open, because no stage parses a clause's active
      period out of its prose yet. `DateRange.overlaps` treats an open range as
      extending indefinitely, so any two clauses paired here overlap by
      default. That is the conservative reading (a real overlap is never
      missed) but it means a flagged pair proves a *relationship*, not a proven
      date collision -- every FlaggedConflict is `requires_human_review`.
    - `scope` is left empty, because canonical asset IDs need an
      entity-resolution stage that does not exist. `asset_based_pass` matches
      on `scope[].canonical_id`, so it stays inert until that lands.
    - `quantity` is left None, so the cumulative-commitment rule also stays
      inert.

    What this does enable is the party-based MFN rule: an MFN in one contract
    alongside pricing/revenue-sharing terms agreed with the same exactly-named
    counterparty elsewhere.
    """
    clauses: List[StructuredClause] = []
    for category_key, clause_type in _RESTRICTIVE_CLAUSE_TYPES.items():
        finding = findings.get(category_key)
        if finding is None:
            continue
        for index, extraction in enumerate(finding.extractions, start=1):
            if not extraction.ocr_verification.is_grounded:
                continue
            clauses.append(
                StructuredClause(
                    clause_id=f"{category_key}#p{extraction.location.page}.{index}",
                    clause_type=clause_type,
                    restricted_action=CUAD_CLASSES[category_key],
                    scope=[],
                    is_exclusive=category_key == "exclusivity",
                    date_range=DateRange(raw_text=extraction.ocr_verification.ocr_text[:120]),
                    quantity=None,
                    source=extraction.source,
                    location=extraction.location,
                    ocr_verification=extraction.ocr_verification,
                )
            )
    return clauses


def _present_categories(
    findings: Dict[str, CategoryFinding]
) -> Dict[str, Optional[Source]]:
    """Categories the contract was actually found to address, with the clause.

    Grounded extractions only. An ungrounded one is not evidence that the
    contract dealt with the topic, and letting it displace a statutory default
    would delete a true statement about the law on the strength of a phrase
    Stage 3 could not find on the page.
    """
    present: Dict[str, Optional[Source]] = {}
    for category, finding in findings.items():
        for extraction in finding.extractions:
            if extraction.ocr_verification.is_grounded:
                present[category] = extraction.source
                break
    return present


def analyze_document(
    input_path: Path,
    work_dir: Path,
    vlm_backend: VlmBackend,
    dpi: int = 300,
    verification_threshold: float = VERIFICATION_THRESHOLD,
    contract_id: Optional[str] = None,
) -> ContractAnalysis:
    """Run the full Stage 1-4 pipeline for a single input document.

    `contract_id` defaults to the input filename stem. Callers that own their
    own identifiers (the webapp worker passes a document UUID) should set it,
    because it is the ID a cross-contract conflict is reported against.
    """
    logger.info("Stage 1: ingesting %s", input_path)
    ingest_result = ingest(input_path, work_dir, dpi=dpi)

    page_image_paths = {p.page_number: p.image_path for p in ingest_result.pages}

    # Role A statutes, BEFORE anything is extracted. The order is the point: the
    # legal position is what the contract starts from, and extraction then shows
    # which parts of it the parties displaced. Computing these afterwards would
    # invert that -- the defaults would look like a fallback for fields the
    # extractor happened to miss, rather than the terms the law supplies.
    statutory_defaults = statutes.prefill_defaults()
    logger.info("Role A: %d statutory defaults supplied pre-extraction", len(statutory_defaults))

    logger.info("Stage 2a: text extraction pass over %d pages", len(page_image_paths))
    ocr_results = extract_document_words(ingest_result.standardized_pdf, ingest_result.pages)

    logger.info("Stage 2b: VLM pass over %d pages", len(page_image_paths))
    vlm_results = vlm_backend.extract_document(page_image_paths)

    logger.info("Stage 3: fuzzy spatial reconciliation")
    cuad_extractions: dict[str, list[CuadExtraction]] = {key: [] for key in CUAD_CLASSES}

    for page_number, vlm_page in vlm_results.items():
        page_ocr = ocr_results.get(page_number)
        for item in vlm_page.extractions:
            match = reconcile_phrase(item.vlm_text, page_ocr, threshold=verification_threshold) if page_ocr else None
            extraction = _build_extraction(
                vlm_text=item.vlm_text,
                clause_label=item.clause_label,
                page_number=page_number,
                match=match,
            )
            cuad_extractions[item.cuad_class].append(extraction)

    logger.info("Stage 4: assembling enriched CUAD JSON")
    # Every one of the 41 categories gets an answer, including the ones with
    # nothing extracted -- silence in the output is otherwise ambiguous
    # between "no such clause" and "the extractor missed it".
    findings = {key: _finding_for(cuad_extractions[key]) for key in CUAD_CLASSES}

    counterparties = _counterparties_from_findings(findings)
    structured_clauses = _structured_clauses_from_findings(findings)
    logger.info(
        "join keys: %d counterparties (exact-name), %d comparable clauses",
        len(counterparties),
        len(structured_clauses),
    )

    # Now that the contract has spoken: displace the defaults it dealt with
    # itself, then run Role B over what it actually says.
    statutory_defaults = statutes.mark_displaced(
        statutory_defaults, _present_categories(findings)
    )
    flags = statutes.review_clauses(statutes.clause_fields_from_findings(findings))
    logger.info(
        "Role A/B: %d defaults displaced by an express clause, %d flags raised",
        sum(1 for d in statutory_defaults.values() if d.is_displaced),
        len(flags),
    )

    analysis = ContractAnalysis(
        contract_id=contract_id or input_path.stem,
        document_metadata=DocumentMetadata(
            source_file=str(input_path.name),
            processed_pdf=str(ingest_result.standardized_pdf.name),
            total_pages=ingest_result.total_pages,
        ),
        counterparties=counterparties,
        structured_clauses=structured_clauses,
        cuad_findings=findings,
        statutory_defaults=statutory_defaults,
        flags=flags,
    )
    return analysis


def analyze_and_write(
    input_path: Path,
    work_dir: Path,
    output_json: Path,
    vlm_backend: VlmBackend,
    dpi: int = 300,
    verification_threshold: float = VERIFICATION_THRESHOLD,
    contract_id: Optional[str] = None,
) -> Path:
    analysis = analyze_document(
        input_path,
        work_dir,
        vlm_backend,
        dpi=dpi,
        verification_threshold=verification_threshold,
        contract_id=contract_id,
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(analysis.to_json_dict(), indent=2))
    return output_json


# --------------------------------------------------------------------------
# Cross-contract pass
# --------------------------------------------------------------------------


def load_analysis(path: Path) -> ContractAnalysis:
    """Read one analysis JSON back into a model, so a conflict scan can run
    over documents processed in separate jobs rather than one CLI invocation."""
    return ContractAnalysis.model_validate_json(Path(path).read_text())


def scan_for_conflicts(analyses: Iterable[ContractAnalysis]) -> ConflictReviewQueue:
    """Run both conflict passes over a set of analyses.

    Kept as the pipeline's entry point to conflict.py so callers do not have to
    know that the party and asset passes are separate: `build_review_queue`
    runs them independently and tags which one caught what.
    """
    batch = list(analyses)
    logger.info("conflict scan over %d analyses", len(batch))
    return build_review_queue(batch)
