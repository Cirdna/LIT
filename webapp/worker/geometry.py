"""Turn Stage 2a word boxes into the webapp's line-level anchor model.

The webapp anchors every extracted value to `text_lines` rows: one row per
visual line, with a bbox in **PDF points, top-left origin** (frontend scales by
`image_dpi / 72`). The pipeline's Stage 2a gives word-level boxes in *pixels* at
the render DPI, uniformly for native-text and OCR pages. So here we:

  1. group words into visual lines by vertical overlap,
  2. convert pixel envelopes to points (points = pixels * 72 / dpi),
  3. assign each line a stable id ("L0001") and character offsets into the
     document's full text.

Working from the unified OcrWord list means native and scanned pages produce
identical geometry downstream — nothing here needs to know which source a page
came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pdf_analyzer.stage2_ocr import OcrPageResult, OcrWord

# A word joins the current line if its vertical midpoint sits inside the line's
# current vertical span. Robust to the small baseline jitter native extraction
# and OCR both produce, without merging genuinely separate lines.
_SAME_LINE_OVERLAP = 0.5


@dataclass
class LineBox:
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    text: str


@dataclass
class TextLineRow:
    line_id: str
    page_number: int
    char_start: int
    char_end: int
    bbox_points: dict[str, float]  # {x0, y0, x1, y1} in PDF points
    bbox_px: tuple[float, float, float, float]  # kept for anchor overlap tests
    text: str


@dataclass
class PageGeometry:
    page_number: int
    width_points: float
    height_points: float
    width_px: int
    height_px: int
    char_start: int
    char_end: int
    source: str  # "native" or "ocr"
    ocr_conf_mean: float | None
    lines: list[TextLineRow] = field(default_factory=list)


def _vertical_overlap(a: LineBox, w: OcrWord) -> float:
    top = max(a.y_min, w.y_min)
    bottom = min(a.y_max, w.y_max)
    inter = max(0.0, bottom - top)
    height = min(a.y_max - a.y_min, w.y_max - w.y_min) or 1.0
    return inter / height


def group_lines(words: list[OcrWord]) -> list[LineBox]:
    """Cluster words into visual lines, each sorted left-to-right."""
    if not words:
        return []

    ordered = sorted(words, key=lambda w: ((w.y_min + w.y_max) / 2, w.x_min))
    lines: list[list[OcrWord]] = []
    current: list[OcrWord] = []
    current_box: LineBox | None = None

    for w in ordered:
        if current_box is not None and _vertical_overlap(current_box, w) >= _SAME_LINE_OVERLAP:
            current.append(w)
            current_box.x_min = min(current_box.x_min, w.x_min)
            current_box.y_min = min(current_box.y_min, w.y_min)
            current_box.x_max = max(current_box.x_max, w.x_max)
            current_box.y_max = max(current_box.y_max, w.y_max)
        else:
            if current:
                lines.append(current)
            current = [w]
            current_box = LineBox(w.x_min, w.y_min, w.x_max, w.y_max, "")
    if current:
        lines.append(current)

    result: list[LineBox] = []
    for group in lines:
        group.sort(key=lambda w: w.x_min)
        text = " ".join(w.text for w in group).strip()
        if not text:
            continue
        result.append(
            LineBox(
                x_min=min(w.x_min for w in group),
                y_min=min(w.y_min for w in group),
                x_max=max(w.x_max for w in group),
                y_max=max(w.y_max for w in group),
                text=text,
            )
        )
    return result


def build_document_geometry(
    ocr_results: dict[int, OcrPageResult],
    page_dims: dict[int, tuple[int, int]],
    dpi: int,
) -> tuple[list[PageGeometry], str]:
    """Build per-page geometry and the concatenated document text.

    `page_dims` maps page_number -> (width_px, height_px) from Stage 1's render,
    so points are derived from the *actual* rendered size rather than an assumed
    DPI. Returns (pages, full_text) where full_text is the newline-joined line
    text that char offsets index into.
    """
    scale_pt = 72.0 / dpi
    pages: list[PageGeometry] = []
    text_parts: list[str] = []
    char_pos = 0
    line_counter = 0

    for page_number in sorted(ocr_results):
        page_ocr = ocr_results[page_number]
        width_px, height_px = page_dims[page_number]
        line_boxes = group_lines(page_ocr.words)

        page_char_start = char_pos
        rows: list[TextLineRow] = []
        confidences = [w.confidence for w in page_ocr.words if w.confidence >= 0]
        for lb in line_boxes:
            line_counter += 1
            line_id = f"L{line_counter:04d}"
            cs = char_pos
            char_pos += len(lb.text) + 1  # +1 for the newline join
            text_parts.append(lb.text)
            rows.append(
                TextLineRow(
                    line_id=line_id,
                    page_number=page_number,
                    char_start=cs,
                    char_end=char_pos - 1,
                    bbox_points={
                        "x0": round(lb.x_min * scale_pt, 2),
                        "y0": round(lb.y_min * scale_pt, 2),
                        "x1": round(lb.x_max * scale_pt, 2),
                        "y1": round(lb.y_max * scale_pt, 2),
                    },
                    bbox_px=(lb.x_min, lb.y_min, lb.x_max, lb.y_max),
                    text=lb.text,
                )
            )

        # OCR confidence: only meaningful on scanned pages (native text reports
        # 100 uniformly, which would falsely imply a "confidence" signal).
        ocr_conf_mean = None
        if page_ocr.source == "ocr" and confidences:
            ocr_conf_mean = round(sum(confidences) / len(confidences) / 100.0, 3)

        pages.append(
            PageGeometry(
                page_number=page_number,
                width_points=round(width_px * scale_pt, 2),
                height_points=round(height_px * scale_pt, 2),
                width_px=width_px,
                height_px=height_px,
                char_start=page_char_start,
                char_end=char_pos,
                source=page_ocr.source,
                ocr_conf_mean=ocr_conf_mean,
                lines=rows,
            )
        )

    return pages, "\n".join(text_parts)


def anchor_lines_for_bbox(
    page: PageGeometry, bbox_1000: list[float]
) -> list[str]:
    """Line ids whose pixel box intersects an extraction's normalized envelope.

    Stage 3 returns `bbox_1000` (0..1000 over the page's pixel size); convert it
    back to pixels here and return every line it touches, in reading order. This
    is what makes click-to-cite land on the exact words the value came from.
    """
    if not bbox_1000 or len(bbox_1000) != 4 or page.width_px <= 0:
        return []
    x0 = bbox_1000[0] / 1000.0 * page.width_px
    y0 = bbox_1000[1] / 1000.0 * page.height_px
    x1 = bbox_1000[2] / 1000.0 * page.width_px
    y1 = bbox_1000[3] / 1000.0 * page.height_px
    if x1 <= x0 and y1 <= y0:
        return []

    hits: list[str] = []
    for row in page.lines:
        lx0, ly0, lx1, ly1 = row.bbox_px
        # Rectangle intersection with a small tolerance.
        if lx0 <= x1 and lx1 >= x0 and ly0 <= y1 and ly1 >= y0:
            hits.append(row.line_id)
    return hits
