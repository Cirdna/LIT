"""Stage 2, Pipeline 2: word-level text extraction with exact page bounding
boxes — the independent source Stage 3 verifies the VLM's extractions
against.

For a born-digital PDF, the file already contains exact text in exact
reading order; asking Tesseract to re-derive that from a rendered PNG only
degrades it. Scored against a real contract (Armstrong Flooring IP
Agreement), Tesseract's word-level transcription differed from the PDF's own
text layer on 1-2% of words per page (e.g. "WHEREOF" -> "WHEREOPF"), and on
a multi-column domain-name/date table it serialized column-major (every
domain name, then every date) while a VLM reading the same table naturally
reports it row-major -- the two could never align in Stage 3 no matter how
correct each one was individually.

So: use the PDF's native text layer (PyMuPDF `page.get_text("words")`,
which returns exact words in correct reading order) whenever a page has one,
and fall back to Tesseract only for pages with no extractable text --
genuinely scanned pages, or images with no embedded text layer at all.
Native-layer coordinates arrive in PDF points and are rescaled into the same
pixel space the 300 DPI render uses, so this is a drop-in replacement:
OcrWord's contract (pixel coordinates matching the rendered PNG) is
unchanged, and nothing in Stage 3, the schema, or the frontend needs to
know or care which source produced a given page's words.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from .stage1_ingest import PageRender


@dataclass
class OcrWord:
    text: str
    x_min: int
    y_min: int
    x_max: int
    y_max: int
    confidence: float  # Tesseract: 0-100 recognition confidence. Native text
    # layer: no such thing as recognition uncertainty (the text is exact, not
    # inferred from pixels), reported as 100.0 to mean "fully trusted."


@dataclass
class OcrPageResult:
    page_number: int
    width_px: int
    height_px: int
    words: list[OcrWord]
    source: str = "ocr"  # "native" or "ocr", for logging/debugging only


def ocr_page(image_path: Path, page_number: int) -> OcrPageResult:
    """Run Tesseract on a single rendered page image, returning word-level
    tokens with exact pixel bounding boxes (x_min, y_min, x_max, y_max).

    This is the fallback path, used only when a page has no native PDF text
    layer to read instead (see extract_document_words).
    """
    image = Image.open(image_path)
    width, height = image.size

    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

    words: list[OcrWord] = []
    n = len(data["text"])
    for i in range(n):
        text = data["text"][i].strip()
        if not text:
            continue
        left, top = data["left"][i], data["top"][i]
        w, h = data["width"][i], data["height"][i]
        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1.0
        words.append(
            OcrWord(
                text=text,
                x_min=left,
                y_min=top,
                x_max=left + w,
                y_max=top + h,
                confidence=conf,
            )
        )

    return OcrPageResult(
        page_number=page_number, width_px=width, height_px=height, words=words, source="ocr"
    )


def native_text_page(
    pdf_document: fitz.Document, page_number: int, width_px: int, height_px: int
) -> OcrPageResult | None:
    """Read one page's words straight from the PDF's own text layer.

    Returns None if the page has no extractable text at all (a scanned page,
    or an image with no embedded text layer), signaling the caller to fall
    back to `ocr_page` instead.

    `width_px`/`height_px` must be the actual pixel dimensions of that page's
    300 DPI render (from stage1_ingest.PageRender) -- native coordinates
    arrive in PDF points, and are rescaled by width_px/page_width_pt (and the
    same for height) so the result lands in exactly the pixel space the
    rendered PNG uses. Deriving the scale from the real render dimensions,
    rather than assuming a fixed DPI, keeps this exact even if a caller
    rounds render dimensions or a page's MediaBox doesn't perfectly match a
    round DPI multiple.
    """
    page = pdf_document[page_number - 1]
    if not page.get_text().strip():
        return None

    scale_x = width_px / page.rect.width
    scale_y = height_px / page.rect.height

    words: list[OcrWord] = []
    for x0, y0, x1, y1, text, *_rest in page.get_text("words", sort=True):
        text = text.strip()
        if not text:
            continue
        words.append(
            OcrWord(
                text=text,
                x_min=round(x0 * scale_x),
                y_min=round(y0 * scale_y),
                x_max=round(x1 * scale_x),
                y_max=round(y1 * scale_y),
                confidence=100.0,
            )
        )

    return OcrPageResult(
        page_number=page_number, width_px=width_px, height_px=height_px, words=words, source="native"
    )


def extract_document_words(pdf_path: Path, pages: list[PageRender]) -> dict[int, OcrPageResult]:
    """Get word-level text + boxes for every page, native-text-first.

    `pages` is Stage 1's render list -- it supplies each page's exact
    rendered pixel dimensions, which native_text_page needs to produce boxes
    in the same coordinate space Stage 3 and the frontend already expect.
    """
    doc = fitz.open(pdf_path)
    try:
        results: dict[int, OcrPageResult] = {}
        for page in pages:
            native = native_text_page(doc, page.page_number, page.width_px, page.height_px)
            results[page.page_number] = native if native is not None else ocr_page(
                page.image_path, page.page_number
            )
        return results
    finally:
        doc.close()
