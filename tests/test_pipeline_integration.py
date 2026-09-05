"""End-to-end wiring test for pipeline.analyze_document: real Stage 1
rendering (PyMuPDF) against a synthetic PDF, with fake OCR/VLM results
standing in for Tesseract and a local VLM (neither is installed in CI/dev
sandboxes without extra system deps). This exercises the page-number and
bbox plumbing between stages that pure unit tests can't catch.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from pdf_analyzer import pipeline as pipeline_mod
from pdf_analyzer.stage2_ocr import OcrPageResult, OcrWord
from pdf_analyzer.schema import AnswerStatus, EvidenceStatus
from pdf_analyzer.stage2_vlm import VlmBackend, VlmClauseExtraction, VlmPageResult


@pytest.fixture
def sample_pdf(tmp_path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # Letter, points
    page.insert_text((72, 100), "MASTER SERVICES AGREEMENT", fontsize=18)
    page.insert_text(
        (72, 700),
        "This Agreement shall be governed by the laws of California.",
        fontsize=11,
    )
    pdf_path = tmp_path / "sample.pdf"
    doc.save(pdf_path)
    doc.close()
    return pdf_path


class FakeVlmBackend(VlmBackend):
    """Stands in for Qwen2.5-VL/InternVL: returns fixed extractions instead
    of running real inference, so the pipeline's stage-wiring can be tested
    without GPU/model-weight dependencies."""

    def extract_page(self, image_path: Path, page_number: int) -> VlmPageResult:
        if page_number != 1:
            return VlmPageResult(page_number=page_number, extractions=[])
        return VlmPageResult(
            page_number=page_number,
            extractions=[
                VlmClauseExtraction(
                    cuad_class="document_name",
                    vlm_text="Master Services Agreement",
                    clause_label="Title Header",
                ),
                VlmClauseExtraction(
                    cuad_class="governing_law",
                    vlm_text="Governed by the laws of California.",
                    clause_label="Governing Law",
                ),
                VlmClauseExtraction(
                    cuad_class="insurance",
                    vlm_text="Party shall maintain cyber liability insurance of $5,000,000.",
                    clause_label="Insurance",
                ),
            ],
        )


def _fake_ocr_document(page_image_paths):
    """Stands in for stage2_ocr.ocr_document (real Tesseract binary isn't
    installed here); returns word-level boxes matching sample_pdf's text so
    Stage 3 reconciliation has something real to align against."""
    words_line_1 = [
        OcrWord(text=w, x_min=x, y_min=90, x_max=x + 10 * len(w), y_max=115, confidence=95.0)
        for x, w in _laid_out(["MASTER", "SERVICES", "AGREEMENT"], start_x=100)
    ]
    words_line_2 = [
        OcrWord(text=w, x_min=x, y_min=700, x_max=x + 10 * len(w), y_max=725, confidence=95.0)
        for x, w in _laid_out(
            ["This", "Agreement", "shall", "be", "governed", "by", "the", "laws", "of", "California."],
            start_x=100,
        )
    ]
    return {
        page_number: OcrPageResult(
            page_number=page_number,
            width_px=2550,
            height_px=3300,
            words=words_line_1 + words_line_2,
        )
        for page_number in page_image_paths
    }


def _laid_out(tokens, start_x):
    x = start_x
    out = []
    for token in tokens:
        out.append((x, token))
        x += 10 * len(token) + 15
    return out


def test_pipeline_wires_stages_together_correctly(sample_pdf, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_mod, "ocr_document", _fake_ocr_document)

    analysis = pipeline_mod.analyze_document(
        input_path=sample_pdf,
        work_dir=tmp_path / "work",
        vlm_backend=FakeVlmBackend(),
    )

    assert analysis.document_metadata.source_file == "sample.pdf"
    assert analysis.document_metadata.total_pages == 1

    # All 41 CUAD categories are answered, not just the ones with hits.
    assert len(analysis.cuad_findings) == 41

    doc_name = analysis.cuad_findings["document_name"]
    assert doc_name.answer is AnswerStatus.PRESENT
    assert doc_name.evidence_status is EvidenceStatus.DIRECT
    assert doc_name.extractions[0].source.page == 1
    assert doc_name.extractions[0].ocr_verification.is_grounded

    governing_law = analysis.cuad_findings["governing_law"]
    assert governing_law.answer is AnswerStatus.PRESENT
    assert "California" in governing_law.extractions[0].ocr_verification.ocr_text

    # Ungrounded extraction: text the OCR can't corroborate on the page.
    insurance = analysis.cuad_findings["insurance"]
    assert not insurance.extractions[0].ocr_verification.is_grounded
    assert insurance.review_flag.flagged
    assert insurance.evidence_status is EvidenceStatus.UNRESOLVED

    # A category with nothing extracted is UNRESOLVED, never ABSENT: this
    # stage cannot tell "no such clause" from "the model missed it", and
    # asserting absence would be a confident wrong answer.
    non_compete = analysis.cuad_findings["non_compete"]
    assert non_compete.answer is AnswerStatus.UNRESOLVED
    assert non_compete.answer is not AnswerStatus.ABSENT
    assert non_compete.review_flag.flagged
