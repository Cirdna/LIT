"""Stage 3: Fuzzy spatial reconciliation & bounding box envelope.

Aligns each VLM-extracted phrase to the OCR word array for its page,
computes the spatial envelope of the matched span, normalizes it to the
0-1000 grid, and applies the >=85% verification guardrail.

Matching approach
------------------
VLM extractions routinely compress or paraphrase the verbatim clause, e.g.
"Governed by the laws of California." standing in for "This Agreement shall
be governed by and construed in accordance with the laws of the State of
California." The phrase's own words are still present, in the same relative
order, but with unrelated filler words inserted between them (the actual
"and construed in accordance with... State of" tissue of the real sentence).

That relationship — same tokens, same order, arbitrary insertions in
between — is exactly what a left-to-right greedy anchor alignment finds: walk
the phrase's tokens in order, and for each one search a bounded lookahead
window of OCR words (starting where the previous token was found) for the
best Levenshtein-similarity match. This is the n-gram sliding window the
gameplan describes, applied per-token rather than per-fixed-size-window,
which is what makes it robust to the filler-word insertions a naive
whole-phrase window match penalizes.

The match score is the fraction of phrase tokens successfully anchored
(recall) — a direct measure of "how much of what the VLM claimed is actually
grounded in the document," which is the guardrail's actual purpose. The
bounding envelope spans every OCR word between the first and last anchored
token (inclusive), so the highlighted/verbatim span reconstructs the full
verbatim sentence rather than just the sparse matched words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from .stage2_ocr import OcrPageResult, OcrWord

VERIFICATION_THRESHOLD = 85.0
_NORM_GRID = 1000.0

# How far ahead (in OCR words) to search for the next phrase token once the
# previous one has been anchored. Bounded so a single stray match early in a
# long page can't drag the search arbitrarily far from the real span.
_LOOKAHEAD_WORDS = 40

# Per-token similarity floor for treating an OCR word as a match for a
# phrase token (0-100, rapidfuzz ratio).
_TOKEN_MATCH_THRESHOLD = 80.0

_PUNCT_RE = re.compile(r"[^\w]+")


@dataclass
class SpatialMatch:
    matched_text: str  # verbatim OCR text spanning the first->last anchored token
    match_score: float  # 0-100, fraction of phrase tokens successfully anchored
    is_verified: bool
    bbox_1000: list[float]  # [x_min, y_min, x_max, y_max] on the 0-1000 grid
    bbox_pixels: list[float]  # same box in source pixel coordinates
    matched_words: list[OcrWord]


def normalize_point(x_px: float, y_px: float, width_px: int, height_px: int) -> tuple[float, float]:
    norm_x = (x_px / width_px) * _NORM_GRID
    norm_y = (y_px / height_px) * _NORM_GRID
    return norm_x, norm_y


def normalize_bbox(
    x_min: float, y_min: float, x_max: float, y_max: float, width_px: int, height_px: int
) -> list[float]:
    nx_min, ny_min = normalize_point(x_min, y_min, width_px, height_px)
    nx_max, ny_max = normalize_point(x_max, y_max, width_px, height_px)
    return [nx_min, ny_min, nx_max, ny_max]


def _envelope(words: list[OcrWord]) -> tuple[float, float, float, float]:
    x_min = min(w.x_min for w in words)
    y_min = min(w.y_min for w in words)
    x_max = max(w.x_max for w in words)
    y_max = max(w.y_max for w in words)
    return x_min, y_min, x_max, y_max


def _clean(token: str) -> str:
    return _PUNCT_RE.sub("", token).lower()


def _tokens_match(phrase_token: str, word_token: str) -> bool:
    if not phrase_token or not word_token:
        return False
    if phrase_token == word_token:
        return True
    if len(phrase_token) <= 2 or len(word_token) <= 2:
        return False  # too short for fuzzy matching to be meaningful; require exact
    return fuzz.ratio(phrase_token, word_token) >= _TOKEN_MATCH_THRESHOLD


def _align_tokens(phrase_tokens: list[str], words: list[OcrWord]) -> list[int]:
    """Greedily anchor each phrase token, in order, to an OCR word index.

    Returns the list of matched word indices (strictly increasing, one per
    successfully anchored phrase token; unmatched tokens are simply skipped).
    """
    word_tokens = [_clean(w.text) for w in words]
    matched_indices: list[int] = []
    cursor = 0

    for phrase_token in phrase_tokens:
        clean_phrase_token = _clean(phrase_token)
        if not clean_phrase_token:
            continue

        search_end = min(len(words), cursor + _LOOKAHEAD_WORDS)
        best_index = None
        best_score = -1.0
        for i in range(cursor, search_end):
            if not _tokens_match(clean_phrase_token, word_tokens[i]):
                continue
            score = 100.0 if clean_phrase_token == word_tokens[i] else fuzz.ratio(
                clean_phrase_token, word_tokens[i]
            )
            if score > best_score:
                best_score = score
                best_index = i

        if best_index is not None:
            matched_indices.append(best_index)
            cursor = best_index + 1

    return matched_indices


def reconcile_phrase(
    phrase: str, page_ocr: OcrPageResult, threshold: float = VERIFICATION_THRESHOLD
) -> SpatialMatch | None:
    """Locate `phrase` (a VLM-extracted clause/entity) within `page_ocr`'s
    word array and compute its verified bounding box.

    Returns None if the page has no OCR words at all.
    """
    if not page_ocr.words:
        return None

    phrase_tokens = phrase.split()
    if not phrase_tokens:
        return None

    matched_indices = _align_tokens(phrase_tokens, page_ocr.words)
    match_score = 100.0 * len(matched_indices) / len(phrase_tokens)

    if not matched_indices:
        return SpatialMatch(
            matched_text="",
            match_score=0.0,
            is_verified=False,
            bbox_1000=[0.0, 0.0, 0.0, 0.0],
            bbox_pixels=[0.0, 0.0, 0.0, 0.0],
            matched_words=[],
        )

    span_start, span_end = min(matched_indices), max(matched_indices) + 1
    matched_words = page_ocr.words[span_start:span_end]
    matched_text = " ".join(w.text for w in matched_words)

    x_min, y_min, x_max, y_max = _envelope(matched_words)
    bbox_1000 = normalize_bbox(x_min, y_min, x_max, y_max, page_ocr.width_px, page_ocr.height_px)

    return SpatialMatch(
        matched_text=matched_text,
        match_score=match_score,
        is_verified=match_score >= threshold,
        bbox_1000=bbox_1000,
        bbox_pixels=[x_min, y_min, x_max, y_max],
        matched_words=matched_words,
    )
