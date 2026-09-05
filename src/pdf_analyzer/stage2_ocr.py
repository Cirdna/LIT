"""Stage 2, Pipeline 2: OCR path — verbatim word-level scanning with exact
page bounding boxes, via Tesseract (pytesseract).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytesseract
from PIL import Image


@dataclass
class OcrWord:
    text: str
    x_min: int
    y_min: int
    x_max: int
    y_max: int
    confidence: float  # Tesseract's 0-100 per-word confidence


@dataclass
class OcrPageResult:
    page_number: int
    width_px: int
    height_px: int
    words: list[OcrWord]


def ocr_page(image_path: Path, page_number: int) -> OcrPageResult:
    """Run Tesseract on a single rendered page image, returning word-level
    tokens with exact pixel bounding boxes (x_min, y_min, x_max, y_max)."""
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

    return OcrPageResult(page_number=page_number, width_px=width, height_px=height, words=words)


def ocr_document(page_image_paths: dict[int, Path]) -> dict[int, OcrPageResult]:
    """OCR every page image, keyed by 1-indexed page number."""
    return {
        page_number: ocr_page(path, page_number)
        for page_number, path in page_image_paths.items()
    }
