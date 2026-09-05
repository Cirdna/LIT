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
    ContractAnalysis,
    CuadExtraction,
    DocumentMetadata,
    Location,
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
    is_verified = match.is_verified if match is not None else False
    confidence = round((match.match_score if match is not None else 0.0) / 100.0, 4)
    ocr_verified_text = match.matched_text if match is not None else ""
    bbox_1000 = match.bbox_1000 if match is not None else [0.0, 0.0, 0.0, 0.0]

    evidence_status = "direct" if is_verified else "derived"
    if is_verified:
        reason = "High-confidence alignment between VLM and OCR text (>= 85% match)."
    else:
        reason = (
            f"Alignment score below the {VERIFICATION_THRESHOLD:.0f}% verification "
            "threshold; requires human audit."
        )

    return CuadExtraction(
        vlm_text=vlm_text,
        ocr_verified_text=ocr_verified_text,
        confidence=confidence,
        is_verified=is_verified,
        location=Location(page=page_number, bbox_1000=bbox_1000),
        source=Source(
            page=page_number,
            clause=clause_label or "Unlabeled",
            exact_supporting_text=ocr_verified_text,
        ),
        evidence_status=evidence_status,
        review_flag=ReviewFlag(flagged=not is_verified, reason=reason),
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
    analysis = ContractAnalysis(
        document_metadata=DocumentMetadata(
            source_file=str(input_path.name),
            processed_pdf=str(ingest_result.standardized_pdf.name),
            total_pages=ingest_result.total_pages,
        ),
        cuad_extractions=cuad_extractions,
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
