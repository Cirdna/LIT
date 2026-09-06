"""Process one document end to end: run the pipeline, write the webapp tables.

Two document kinds share the front of the pipeline (render + read the text) and
then branch:

  * contracts → the CUAD VLM extraction pass → extracted_fields + calendar.
  * invoices  → text-LLM header/line-item extraction → reconciliation against
    the contract portfolio (see worker/invoices.py).

Invoices are detected from the page text BEFORE the expensive VLM pass, so an
invoice never pays for a contract extraction it doesn't need.
"""

from __future__ import annotations

import logging
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Optional

import psycopg
from psycopg.types.json import Json

from pdf_analyzer.cuad_classes import CUAD_CLASSES
from pdf_analyzer.pipeline import _build_extraction, _finding_for
from pdf_analyzer.schema import ContractAnalysis, DocumentMetadata
from pdf_analyzer.stage1_ingest import ingest
from pdf_analyzer.stage2_ocr import extract_document_words
from pdf_analyzer.stage2_vlm import VlmBackend
from pdf_analyzer.stage3_reconcile import VERIFICATION_THRESHOLD, reconcile_phrase

from . import db, storage
from .geometry import PageGeometry, anchor_lines_for_bbox, build_document_geometry
from .invoices import looks_like_invoice, process_invoice
from .mapping import (
    build_calendar,
    classify_doc_type,
    counterparty_from,
    map_fields,
    provenance_and_status,
)

logger = logging.getLogger("worker.process")

PIPELINE_VERSION = "pdf-analyzer@0.1.0"


def _render_and_read(input_path: Path, work_dir: Path, dpi: int):
    """Stage 1 render + Stage 2a word boxes — the part both kinds need."""
    ingest_result = ingest(input_path, work_dir, dpi=dpi)
    page_dims = {p.page_number: (p.width_px, p.height_px) for p in ingest_result.pages}
    ocr_results = extract_document_words(ingest_result.standardized_pdf, ingest_result.pages)
    return ingest_result, ocr_results, page_dims


def _extract_cuad(input_path: Path, ingest_result, ocr_results, vlm_backend: VlmBackend, threshold: float) -> ContractAnalysis:
    """The contract-only VLM pass: extract → reconcile → 41 CUAD findings."""
    page_image_paths = {p.page_number: p.image_path for p in ingest_result.pages}
    vlm_results = vlm_backend.extract_document(page_image_paths)

    cuad_extractions: dict[str, list] = {key: [] for key in CUAD_CLASSES}
    for page_number, vlm_page in vlm_results.items():
        page_ocr = ocr_results.get(page_number)
        for item in vlm_page.extractions:
            match = reconcile_phrase(item.vlm_text, page_ocr, threshold=threshold) if page_ocr else None
            extraction = _build_extraction(item.vlm_text, item.clause_label, page_number, match)
            cuad_extractions[item.cuad_class].append(extraction)

    findings = {key: _finding_for(cuad_extractions[key]) for key in CUAD_CLASSES}
    return ContractAnalysis(
        contract_id=input_path.stem,
        document_metadata=DocumentMetadata(
            source_file=input_path.name,
            processed_pdf=ingest_result.standardized_pdf.name,
            total_pages=ingest_result.total_pages,
        ),
        cuad_findings=findings,
    )


def _copy_page_images(document_id: str, ingest_result, dpi: int) -> None:
    dest_dir = storage.pages_dir() / str(document_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for page in ingest_result.pages:
        dest = storage.page_image_path(document_id, page.page_number, dpi)
        shutil.copyfile(page.image_path, dest)


def _resolve_anchors(field_row, pages_by_number: dict[int, PageGeometry]) -> list[str]:
    if field_row.confidence_tier == "inferred":
        return []
    if field_row.anchor_page is None or not field_row.anchor_bbox_1000:
        return []
    page = pages_by_number.get(field_row.anchor_page)
    if page is None:
        return []
    return anchor_lines_for_bbox(page, field_row.anchor_bbox_1000)


def process_document(
    conn: psycopg.Connection,
    job: dict[str, Any],
    vlm_backend: VlmBackend,
    dpi: int,
    threshold: float = VERIFICATION_THRESHOLD,
    user_hint: Optional[str] = None,
) -> None:
    document_id = job["document_id"]
    job_id = job["id"]
    workspace_id = job["workspace_id"]

    doc = conn.execute(
        "SELECT id, filename, sha256, storage_key, mime_type FROM documents WHERE id=%s",
        (document_id,),
    ).fetchone()
    if not doc:
        raise RuntimeError(f"document {document_id} not found")

    original_path = storage.resolve_key(doc["storage_key"])
    if not original_path.exists():
        raise RuntimeError(f"original file missing from storage: {doc['storage_key']}")
    original_ext = Path(doc["filename"]).suffix or original_path.suffix

    with conn.transaction():
        conn.execute("UPDATE documents SET status='processing', error=NULL WHERE id=%s", (document_id,))
    db.set_progress(conn, job_id, "reading document", 0.05)

    work_dir = storage.storage_root() / "tmp" / f"work-{document_id}"
    try:
        db.set_progress(conn, job_id, "rendering pages", 0.15)
        ingest_result, ocr_results, page_dims = _render_and_read(original_path, work_dir, dpi)
        pages, full_text = build_document_geometry(ocr_results, page_dims, dpi)
        pages_by_number = {p.page_number: p for p in pages}
        _copy_page_images(document_id, ingest_result, dpi)

        page_sources = [p.source for p in pages]
        provenance, ocr_applied, status = provenance_and_status(page_sources, original_ext)

        # Shared: page images + text + line anchors, for either kind.
        db.set_progress(conn, job_id, "writing pages", 0.45)
        _write_pages_text(conn, document_id, dpi, pages, full_text)

        if looks_like_invoice(full_text, doc["filename"]):
            db.set_progress(conn, job_id, "reading invoice", 0.6)
            match = process_invoice(
                conn,
                document_id=document_id,
                workspace_id=workspace_id,
                filename=doc["filename"],
                full_text=full_text,
                page_count=len(pages),
                provenance=provenance,
                ocr_applied=ocr_applied,
                pipeline_version=PIPELINE_VERSION,
            )
            db.set_progress(conn, job_id, "done", 1.0)
            logger.info("document %s: invoice, %d pages, match=%s", document_id, len(pages), match["status"])
            return

        # Contract branch — the CUAD VLM pass.
        db.set_progress(conn, job_id, "extracting fields", 0.6)
        analysis = _extract_cuad(original_path, ingest_result, ocr_results, vlm_backend, threshold)
        doc_type, doc_type_conf = classify_doc_type(analysis, full_text)
        is_contract = doc_type != "not_a_contract"
        field_rows = map_fields(analysis) if is_contract else []
        counterparty = counterparty_from(analysis, user_hint) if is_contract else None
        events = build_calendar(field_rows, counterparty) if is_contract else []

        warnings: list[str] = []
        if provenance == "degraded":
            warnings.append("Scanned document — values read by OCR, expect lower certainty.")
        if not is_contract:
            warnings.append("This does not look like a contract. No terms were extracted.")
        if any(f.confidence_tier == "unverified" for f in field_rows):
            warnings.append("One or more extracted values could not be verified against the page — shown as suspected errors.")

        db.set_progress(conn, job_id, "writing results", 0.9)
        _write_contract_results(
            conn,
            document_id=document_id,
            workspace_id=workspace_id,
            page_count=len(pages),
            pages_by_number=pages_by_number,
            field_rows=field_rows,
            events=events,
            doc_type=doc_type,
            doc_type_conf=doc_type_conf,
            provenance=provenance,
            ocr_applied=ocr_applied,
            status=status,
            counterparty=counterparty,
            warnings=warnings,
        )
        db.set_progress(conn, job_id, "done", 1.0)
        logger.info(
            "document %s: contract, %d pages, %d fields, %d events, doc_type=%s",
            document_id, len(pages), len(field_rows), len(events), doc_type,
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _write_pages_text(conn: psycopg.Connection, document_id: str, dpi: int, pages: list[PageGeometry], full_text: str) -> None:
    """Shared write: document_text, document_pages, text_lines (idempotent)."""
    with conn.transaction(), conn.cursor() as cur:
        for table in ("text_lines", "document_pages", "document_text"):
            cur.execute(f"DELETE FROM {table} WHERE document_id=%s", (document_id,))

        cur.execute("INSERT INTO document_text (document_id, text) VALUES (%s, %s)", (document_id, full_text))

        cur.executemany(
            """
            INSERT INTO document_pages
              (document_id, page_number, width, height, char_start, char_end,
               extraction_method, ocr_conf_mean, page_role, image_key, image_dpi)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    document_id, p.page_number, p.width_points, p.height_points,
                    p.char_start, p.char_end,
                    "pdf_text" if p.source == "native" else "ocr",
                    p.ocr_conf_mean,
                    _page_role(p.page_number, len(pages)),
                    storage.page_image_key(document_id, p.page_number, dpi),
                    dpi,
                )
                for p in pages
            ],
        )

        line_params = [
            (
                document_id, row.line_id, row.page_number, row.char_start, row.char_end,
                Json(row.bbox_points), row.text,
            )
            for p in pages for row in p.lines
        ]
        if line_params:
            cur.executemany(
                """
                INSERT INTO text_lines
                  (document_id, line_id, page_number, char_start, char_end, bbox, text)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                line_params,
            )


def _write_contract_results(
    conn: psycopg.Connection,
    *,
    document_id: str,
    workspace_id: str,
    page_count: int,
    pages_by_number: dict[int, PageGeometry],
    field_rows: list,
    events: list,
    doc_type: str,
    doc_type_conf: float,
    provenance: str,
    ocr_applied: bool,
    status: str,
    counterparty: Optional[str],
    warnings: list[str],
) -> None:
    """Contract branch: extracted_fields, calendar_events, document update."""
    with conn.transaction(), conn.cursor() as cur:
        for table in ("document_segments", "extracted_fields", "calendar_events"):
            cur.execute(f"DELETE FROM {table} WHERE document_id=%s", (document_id,))

        field_id_by_key: dict[str, str] = {}
        for fr in field_rows:
            anchors = _resolve_anchors(fr, pages_by_number)
            absence = fr.absence_reason if fr.value_verbatim is None else None
            cur.execute(
                """
                INSERT INTO extracted_fields
                  (document_id, field_key, value_verbatim, value_normalized,
                   confidence_tier, claim_type, absence_reason, anchor_line_ids,
                   segment_key, clause_label, consistency_score, vlm_agreement, model_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    document_id, fr.field_key, fr.value_verbatim,
                    Json(fr.value_normalized) if fr.value_normalized is not None else None,
                    fr.confidence_tier, fr.claim_type, absence, anchors,
                    None, fr.clause_label, fr.consistency_score, fr.vlm_agreement,
                    PIPELINE_VERSION,
                ),
            )
            field_id_by_key[fr.field_key] = cur.fetchone()["id"]

        for ev in events:
            source_ids = [field_id_by_key[k] for k in ev.source_field_keys if k in field_id_by_key]
            cur.execute(
                """
                INSERT INTO calendar_events
                  (workspace_id, document_id, event_type, event_date, action_by_date,
                   title, detail, confidence_tier, source_field_ids, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::uuid[],'open')
                """,
                (
                    workspace_id, document_id, ev.event_type,
                    date.fromisoformat(ev.event_date),
                    date.fromisoformat(ev.action_by_date) if ev.action_by_date else None,
                    ev.title, ev.detail, ev.confidence_tier, source_ids,
                ),
            )

        cur.execute(
            """
            UPDATE documents SET
              status=%s, provenance_quality=%s, page_count=%s, ocr_applied=%s,
              doc_type=%s, doc_type_conf=%s, counterparty=%s, warnings=%s,
              pipeline_version=%s, processed_at=now(), error=NULL
            WHERE id=%s
            """,
            (
                status, provenance, page_count, ocr_applied, doc_type, doc_type_conf,
                counterparty, Json(warnings), PIPELINE_VERSION, document_id,
            ),
        )


def _page_role(page_number: int, total: int) -> str:
    if page_number == 1:
        return "cover"
    if page_number == total:
        return "signature"
    return "operative"
