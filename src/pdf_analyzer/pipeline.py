"""Orchestrates Stages 1-4 of the gameplan: ingest -> dual-pipeline extraction
-> fuzzy spatial reconciliation -> enriched CUAD JSON output.

Stage 5 (frontend click-to-jump) consumes the JSON this module produces; see
frontend/ and api/main.py.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .cuad_classes import CUAD_CLASSES
from .schema import (
    AnswerStatus,
    CategoryFinding,
    ContractAnalysis,
    CuadExtraction,
    DocumentMetadata,
    EvidenceStatus,
    Location,
    OcrVerification,
    ReviewFlag,
    Source,
)
from .stage1_ingest import ingest
from .stage2_ocr import ocr_document
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


def analyze_document(
    input_path: Path,
    work_dir: Path,
    vlm_backend: VlmBackend,
    dpi: int = 300,
    verification_threshold: float = VERIFICATION_THRESHOLD,
) -> ContractAnalysis:
    """Run the full Stage 1-4 pipeline for a single input document."""
    logger.info("Stage 1: ingesting %s", input_path)
    ingest_result = ingest(input_path, work_dir, dpi=dpi)

    page_image_paths = {p.page_number: p.image_path for p in ingest_result.pages}

    logger.info("Stage 2a: OCR pass over %d pages", len(page_image_paths))
    ocr_results = ocr_document(page_image_paths)

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

    analysis = ContractAnalysis(
        contract_id=input_path.stem,
        document_metadata=DocumentMetadata(
            source_file=str(input_path.name),
            processed_pdf=str(ingest_result.standardized_pdf.name),
            total_pages=ingest_result.total_pages,
        ),
        cuad_findings=findings,
    )
    return analysis


def analyze_and_write(
    input_path: Path,
    work_dir: Path,
    output_json: Path,
    vlm_backend: VlmBackend,
    dpi: int = 300,
    verification_threshold: float = VERIFICATION_THRESHOLD,
) -> Path:
    analysis = analyze_document(
        input_path, work_dir, vlm_backend, dpi=dpi, verification_threshold=verification_threshold
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(analysis.to_json_dict(), indent=2))
    return output_json
