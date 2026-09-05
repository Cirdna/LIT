"""Tests for Stage 2a's native-PDF-text-first extraction (stage2_ocr.py).

Covers: coordinate rescaling from PDF points into the same pixel space the
rendered PNG uses, fallback to Tesseract when a page has no text layer, and
that native extraction fixes the failure mode that motivated it (reading
order on a multi-column layout that OCR serializes incorrectly).
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from pdf_analyzer.stage1_ingest import PageRender
from pdf_analyzer.stage2_ocr import extract_document_words, native_text_page


def _make_pdf(tmp_path, build_page) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    build_page(page)
    path = tmp_path / "doc.pdf"
    doc.save(path)
    doc.close()
    return path


def test_native_text_page_returns_none_for_blank_page(tmp_path):
    path = _make_pdf(tmp_path, lambda page: None)  # no content at all
    doc = fitz.open(path)
    try:
        assert native_text_page(doc, 1, width_px=2550, height_px=3300) is None
    finally:
        doc.close()


def test_native_text_page_extracts_real_words_with_scaled_coordinates(tmp_path):
    path = _make_pdf(tmp_path, lambda page: page.insert_text((72, 100), "Hello World", fontsize=12))
    doc = fitz.open(path)
    try:
        page = doc[0]
        page_width_pt, page_height_pt = page.rect.width, page.rect.height
        width_px, height_px = 2550, 3300  # a 300 DPI render of a Letter page

        result = native_text_page(doc, 1, width_px=width_px, height_px=height_px)

        assert result is not None
        assert result.source == "native"
        assert result.width_px == width_px and result.height_px == height_px
        texts = [w.text for w in result.words]
        assert texts == ["Hello", "World"]

        # Coordinates must land in the *rendered pixel* space, not PDF points:
        # scale = rendered_px / page_points, applied independently per axis.
        scale_x = width_px / page_width_pt
        scale_y = height_px / page_height_pt
        first_word_native = list(page.get_text("words", sort=True))[0]
        expected_x_min = round(first_word_native[0] * scale_x)
        expected_y_min = round(first_word_native[1] * scale_y)
        assert result.words[0].x_min == expected_x_min
        assert result.words[0].y_min == expected_y_min
        # Sanity: scaled coordinates should be in the thousands (300 DPI),
        # not the low hundreds (72 DPI points) -- catches a missed rescale.
        assert result.words[0].x_min > 200
    finally:
        doc.close()


def test_native_text_page_confidence_is_fully_trusted(tmp_path):
    """Native text has no recognition uncertainty -- it's exact, not
    inferred from pixels -- so it's reported at the top of Tesseract's
    0-100 confidence scale rather than a fabricated in-between number."""
    path = _make_pdf(tmp_path, lambda page: page.insert_text((72, 100), "Delaware", fontsize=12))
    doc = fitz.open(path)
    try:
        result = native_text_page(doc, 1, width_px=2550, height_px=3300)
        assert all(w.confidence == 100.0 for w in result.words)
    finally:
        doc.close()


def test_native_text_page_reads_multi_column_layout_in_row_order(tmp_path):
    """The bug this module exists to fix: on a real domain-name/expiration
    table, Tesseract serialized a two-column layout column-major (every
    entry in column 1, then every entry in column 2), which could never
    align with a VLM's naturally row-major reading of the same table. The
    native text layer must read it row by row instead.
    """

    def build(page):
        rows = [("alpha.com", "01-Jan-2026"), ("beta.com", "02-Feb-2026"), ("gamma.com", "03-Mar-2026")]
        y = 100
        for domain, date in rows:
            page.insert_text((72, y), domain, fontsize=10)
            page.insert_text((300, y), date, fontsize=10)
            y += 20

    path = _make_pdf(tmp_path, build)
    doc = fitz.open(path)
    try:
        result = native_text_page(doc, 1, width_px=2550, height_px=3300)
        texts = [w.text for w in result.words]
        # Row-major: each domain immediately followed by its own date, not
        # every domain first (which is what column-major OCR order produced).
        assert texts == [
            "alpha.com", "01-Jan-2026",
            "beta.com", "02-Feb-2026",
            "gamma.com", "03-Mar-2026",
        ]
    finally:
        doc.close()


def test_extract_document_words_falls_back_to_ocr_for_textless_page(tmp_path, monkeypatch):
    """A page with no native text (e.g. a scanned image) must fall back to
    Tesseract rather than silently returning zero words."""
    import pdf_analyzer.stage2_ocr as stage2_ocr

    path = _make_pdf(tmp_path, lambda page: None)  # blank, no text layer
    fake_image = tmp_path / "page_0001.png"
    fake_image.write_bytes(b"not a real png, never opened because ocr_page is stubbed")

    calls = []

    def fake_ocr_page(image_path, page_number):
        calls.append((image_path, page_number))
        return stage2_ocr.OcrPageResult(
            page_number=page_number, width_px=2550, height_px=3300, words=[], source="ocr"
        )

    monkeypatch.setattr(stage2_ocr, "ocr_page", fake_ocr_page)

    pages = [PageRender(page_number=1, image_path=fake_image, width_px=2550, height_px=3300)]
    results = extract_document_words(path, pages)

    assert calls == [(fake_image, 1)]
    assert results[1].source == "ocr"


def test_extract_document_words_prefers_native_when_available(tmp_path, monkeypatch):
    import pdf_analyzer.stage2_ocr as stage2_ocr

    path = _make_pdf(tmp_path, lambda page: page.insert_text((72, 100), "Real text", fontsize=12))
    fake_image = tmp_path / "page_0001.png"
    fake_image.write_bytes(b"unused")

    def fail_if_called(image_path, page_number):
        raise AssertionError("ocr_page should not be called when native text is available")

    monkeypatch.setattr(stage2_ocr, "ocr_page", fail_if_called)

    pages = [PageRender(page_number=1, image_path=fake_image, width_px=2550, height_px=3300)]
    results = extract_document_words(path, pages)

    assert results[1].source == "native"
    assert [w.text for w in results[1].words] == ["Real", "text"]
