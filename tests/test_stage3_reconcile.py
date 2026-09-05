import pytest

from pdf_analyzer.stage2_ocr import OcrPageResult, OcrWord
from pdf_analyzer.stage3_reconcile import (
    normalize_bbox,
    normalize_point,
    reconcile_phrase,
)


def _word(text, x_min, y_min, x_max, y_max):
    return OcrWord(text=text, x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max, confidence=95.0)


@pytest.fixture
def page_ocr():
    # Simulates a line of OCR-tokenized words at 300 DPI on a Letter page
    # (2550x3300 px), each word ~60px wide, 30px tall, at y=450.
    words = []
    sentence = "This Agreement shall be governed by and construed in accordance with the laws of the State of California."
    x = 100
    for token in sentence.split():
        width = 12 * len(token) + 10
        words.append(_word(token, x, 450, x + width, 480))
        x += width + 8
    return OcrPageResult(page_number=11, width_px=2550, height_px=3300, words=words)


def test_normalize_point_maps_corners_to_grid_bounds():
    assert normalize_point(0, 0, 2550, 3300) == (0.0, 0.0)
    x, y = normalize_point(2550, 3300, 2550, 3300)
    assert x == pytest.approx(1000.0)
    assert y == pytest.approx(1000.0)


def test_normalize_bbox_scales_independently_per_axis():
    bbox = normalize_bbox(0, 0, 1275, 1650, 2550, 3300)
    assert bbox == pytest.approx([0.0, 0.0, 500.0, 500.0])


def test_reconcile_phrase_finds_high_confidence_match(page_ocr):
    vlm_phrase = "Governed by the laws of California."
    match = reconcile_phrase(vlm_phrase, page_ocr)

    assert match is not None
    assert match.is_verified
    assert match.match_score >= 85.0
    assert "California" in match.matched_text
    # bbox should be within the normalized grid
    x_min, y_min, x_max, y_max = match.bbox_1000
    assert 0 <= x_min < x_max <= 1000
    assert 0 <= y_min < y_max <= 1000


def test_reconcile_phrase_flags_low_confidence_as_unverified(page_ocr):
    unrelated_phrase = "Force majeure excuses non-performance during pandemics."
    match = reconcile_phrase(unrelated_phrase, page_ocr)

    assert match is not None
    assert not match.is_verified
    assert match.match_score < 85.0


def test_reconcile_phrase_returns_none_for_empty_page():
    from pdf_analyzer.stage2_ocr import OcrPageResult

    empty_page = OcrPageResult(page_number=1, width_px=100, height_px=100, words=[])
    assert reconcile_phrase("anything", empty_page) is None


def test_reconcile_phrase_exact_verbatim_scores_100(page_ocr):
    exact_phrase = (
        "This Agreement shall be governed by and construed in accordance "
        "with the laws of the State of California."
    )
    match = reconcile_phrase(exact_phrase, page_ocr)

    assert match is not None
    assert match.match_score == pytest.approx(100.0)
    assert match.is_verified
    assert match.matched_text == exact_phrase


def test_reconcile_phrase_hallucinated_text_scores_near_zero(page_ocr):
    hallucinated = "Arbitration shall occur exclusively in Singapore under ICC rules."
    match = reconcile_phrase(hallucinated, page_ocr)

    assert match is not None
    assert not match.is_verified
    assert match.match_score < 30.0


def test_reconcile_phrase_out_of_order_tokens_do_not_falsely_anchor():
    # "of California the" reverses word order relative to the source; a
    # left-to-right anchor walk should still find some tokens but the
    # reversal costs recall (the cursor can't walk backward for "the").
    page = OcrPageResult(
        page_number=1,
        width_px=1000,
        height_px=1000,
        words=[
            _word("The", 0, 0, 40, 30),
            _word("laws", 45, 0, 90, 30),
            _word("of", 95, 0, 120, 30),
            _word("California", 125, 0, 220, 30),
        ],
    )
    match = reconcile_phrase("California of the", page)
    assert match is not None
    # "California" anchors first; cursor then can't walk back to find "of"/"the" before it.
    assert match.match_score == pytest.approx(100.0 / 3.0)
