"""Stage 1: Unified PDF ingestion & DPI-standardized rendering.

Converts DOCX/HTML/RTF inputs to a standardized intermediate PDF via a
headless conversion engine, validates native PDFs, then renders every page
to a high-resolution PNG (default 300 DPI) using PyMuPDF.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

RENDER_DPI = 300
_PDF_POINTS_PER_INCH = 72.0

_OFFICE_EXTENSIONS = {".docx", ".doc", ".rtf", ".odt"}
_HTML_EXTENSIONS = {".html", ".htm"}


class ConversionError(RuntimeError):
    """Raised when a headless conversion (LibreOffice/Playwright) fails."""


@dataclass
class PageRender:
    page_number: int  # 1-indexed
    image_path: Path
    width_px: int
    height_px: int


@dataclass
class IngestResult:
    source_file: Path
    standardized_pdf: Path
    total_pages: int
    pages: list[PageRender]


def convert_to_pdf(input_path: Path, out_dir: Path) -> Path:
    """Route `input_path` through the appropriate headless converter.

    Native PDFs are validated and passed through untouched (copied into
    `out_dir` so downstream stages always read from a consistent location).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = input_path.suffix.lower()

    if suffix == ".pdf":
        return _validate_and_copy_pdf(input_path, out_dir)
    if suffix in _OFFICE_EXTENSIONS:
        return _convert_office_to_pdf(input_path, out_dir)
    if suffix in _HTML_EXTENSIONS:
        return _convert_html_to_pdf(input_path, out_dir)

    raise ConversionError(f"Unsupported input format: {suffix!r} ({input_path})")


def _validate_and_copy_pdf(input_path: Path, out_dir: Path) -> Path:
    try:
        doc = fitz.open(input_path)
        if doc.page_count < 1:
            raise ConversionError(f"PDF has no pages: {input_path}")
        doc.close()
    except Exception as exc:  # PyMuPDF raises its own exception types
        raise ConversionError(f"Invalid PDF {input_path}: {exc}") from exc

    dest = out_dir / f"standardized_{input_path.stem}.pdf"
    shutil.copyfile(input_path, dest)
    return dest


def _convert_office_to_pdf(input_path: Path, out_dir: Path) -> Path:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        raise ConversionError(
            "LibreOffice (soffice) not found on PATH; required to convert "
            f"{input_path.suffix} files to PDF."
        )

    cmd = [
        soffice,
        "--headless",
        "--convert-to",
        "pdf",
        str(input_path),
        "--outdir",
        str(out_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise ConversionError(
            f"soffice conversion failed for {input_path}: {proc.stderr.strip()}"
        )

    produced = out_dir / f"{input_path.stem}.pdf"
    if not produced.exists():
        raise ConversionError(
            f"soffice reported success but no output PDF found at {produced}"
        )

    dest = out_dir / f"standardized_{input_path.stem}.pdf"
    produced.rename(dest)
    return dest


def _convert_html_to_pdf(input_path: Path, out_dir: Path) -> Path:
    """Render HTML to PDF via headless Chrome (Playwright), A4/Letter with
    0.5-inch margins, so the text layout renders predictably."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ConversionError(
            "playwright is not installed; run `pip install playwright && "
            "playwright install chromium` to enable HTML-to-PDF conversion."
        ) from exc

    dest = out_dir / f"standardized_{input_path.stem}.pdf"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(input_path.resolve().as_uri())
        page.pdf(
            path=str(dest),
            format="A4",
            margin={"top": "0.5in", "bottom": "0.5in", "left": "0.5in", "right": "0.5in"},
            print_background=True,
        )
        browser.close()
    return dest


def render_pages(pdf_path: Path, out_dir: Path, dpi: int = RENDER_DPI) -> list[PageRender]:
    """Render every page of `pdf_path` to a PNG at the given DPI.

    Page dimensions map onto the normalized [0, 0, 1000, 1000] scale
    downstream (see stage3_reconcile.normalize_bbox); this function records
    each page's actual pixel dimensions so that normalization is exact.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    zoom = dpi / _PDF_POINTS_PER_INCH
    matrix = fitz.Matrix(zoom, zoom)

    renders: list[PageRender] = []
    doc = fitz.open(pdf_path)
    try:
        for index, page in enumerate(doc):
            page_number = index + 1
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image_path = out_dir / f"page_{page_number:04d}.png"
            pix.save(image_path)
            renders.append(
                PageRender(
                    page_number=page_number,
                    image_path=image_path,
                    width_px=pix.width,
                    height_px=pix.height,
                )
            )
    finally:
        doc.close()

    return renders


def ingest(input_path: Path, work_dir: Path, dpi: int = RENDER_DPI) -> IngestResult:
    """Run the full Stage 1 pipeline: convert (if needed) then render."""
    pdf_dir = work_dir / "pdf"
    pages_dir = work_dir / "pages"

    standardized_pdf = convert_to_pdf(input_path, pdf_dir)
    pages = render_pages(standardized_pdf, pages_dir, dpi=dpi)

    return IngestResult(
        source_file=input_path,
        standardized_pdf=standardized_pdf,
        total_pages=len(pages),
        pages=pages,
    )
