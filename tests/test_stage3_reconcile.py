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
    # Asserted on recall, which isolates alignment from the evidence-mass
    # weighting applied to the final score.
    assert match.recall == pytest.approx(100.0 / 3.0)


def _page_of_words(tokens, page_number=1, y=100, width_px=2550, height_px=3300):
    """Lay tokens out left-to-right on one synthetic line."""
    words = []
    x = 100
    for token in tokens:
        w = 12 * len(token) + 10
        words.append(_word(token, x, y, x + w, y + 30))
        x += w + 8
    return OcrPageResult(
        page_number=page_number, width_px=width_px, height_px=height_px, words=words
    )


def test_phrase_far_down_the_page_is_still_found():
    """Regression: a single greedy pass from index 0 could only find the
    leading token within one lookahead window of the top of the page, so
    clause headings and footers lower down scored zero despite being present
    in the OCR (seen on real contract pages with 'Counterparts.' at word 144
    and a '1/7/2019' footer at word 378)."""
    filler = ["filler"] * 300
    page = _page_of_words(filler + ["Counterparts.", "This", "Agreement", "may", "be", "executed"])

    match = reconcile_phrase("Counterparts.", page)

    assert match is not None
    # The bug under test is one of *location*, so assert the phrase was found
    # at all. The final score is separately discounted here because a lone
    # short token carries little distinguishing evidence (see the
    # evidence-mass tests below).
    assert match.recall == pytest.approx(100.0)
    assert match.matched_text == "Counterparts."


def test_best_occurrence_wins_over_first_superficial_match():
    """Regression: contract pages repeat boilerplate, so the earliest
    superficial match is often the wrong occurrence. The alignment recalling
    the most phrase tokens must win, otherwise the bounding box points at
    plausible-looking but wrong text."""
    decoy = "This Agreement may be amended only in writing signed by both parties".split()
    real = "This Agreement shall be governed by the laws of the State of Delaware".split()
    page = _page_of_words(decoy + ["filler"] * 50 + real)

    match = reconcile_phrase(
        "This Agreement shall be governed by the laws of the State of Delaware", page
    )

    assert match is not None
    assert match.match_score == pytest.approx(100.0)
    assert "Delaware" in match.matched_text
    # Must have anchored past the decoy, not on it.
    assert "amended" not in match.matched_text


def test_common_word_phrase_is_discounted_despite_full_recall():
    """Regression: recall alone can't tell a real match from a spurious one.

    A short phrase built from words that are ubiquitous on the page recalls
    100% of its own tokens off unrelated text, because recall normalizes by
    the phrase itself. Observed on a real contract page, where the phrase
    'Arizona and Company' scored a perfect 1.00 against a span reading
    'Arizona Copyright Grant. Subject to the terms and conditions...'.
    Scaling by evidence mass must pull such a match below verification.
    """
    # "arizona" / "company" / "and" recur constantly, as a defined party name
    # does throughout a real contract.
    boilerplate = []
    for _ in range(30):
        boilerplate += ["Arizona", "and", "the", "Company", "shall", "provide"]
    page = _page_of_words(boilerplate)

    match = reconcile_phrase("Arizona and Company", page)

    assert match is not None
    assert match.recall == pytest.approx(100.0)  # every token found...
    assert match.evidence_mass < 2.0  # ...but they carry almost no information
    assert not match.is_verified


def test_distinctive_phrase_keeps_full_score():
    """The counterpart to the test above: a phrase carrying genuinely rare
    tokens must still verify at full strength, so the discount targets
    uninformative phrases rather than penalizing length or filler words."""
    page = _page_of_words(
        "This Agreement shall be governed by the laws of the State of Delaware, "
        "its rules of conflict of laws notwithstanding.".split()
    )

    match = reconcile_phrase(
        "governed by the laws of the State of Delaware notwithstanding", page
    )

    assert match is not None
    assert match.evidence_mass >= 2.0
    assert match.match_score == pytest.approx(match.recall)  # undiscounted
    assert match.is_verified
