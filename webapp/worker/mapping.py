"""Map the pipeline's CUAD findings onto the webapp's fields — one to one.

The webapp now displays the pipeline's own vocabulary: all 41 CUAD categories,
organised into the eight document-detail groups (see webapp/src/lib/domain.ts).
So this module is a direct projection, not a crosswalk — every category becomes
one `extracted_fields` row whose `field_key` is the CUAD key.

The value-bearing categories (dates, durations) are parsed into a normalised
form so the calendar can compute with them; every other category carries its
grounded quote. Confidence tiers follow docs/INTEGRATION.md §5/§7:

  grounded quote                    -> verbatim  (or normalised if parsed)
  grounded quote parsed to a value  -> normalised
  present but quote NOT grounded    -> unverified  (the fabrication signal)
  no extraction on this page        -> value NULL + absence_reason='not_found'
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from pdf_analyzer.cuad_classes import CUAD_CLASSES
from pdf_analyzer.schema import AnswerStatus, ContractAnalysis, CuadExtraction

_MAX_VERBATIM = 600


@dataclass
class FieldRow:
    field_key: str
    value_verbatim: Optional[str]
    value_normalized: Optional[dict]
    confidence_tier: str
    claim_type: str = "contract_text"
    absence_reason: Optional[str] = None
    clause_label: Optional[str] = None
    consistency_score: Optional[float] = None
    vlm_agreement: Optional[float] = None
    # Resolved to anchor_line_ids by the caller (needs page geometry).
    anchor_page: Optional[int] = None
    anchor_bbox_1000: Optional[list[float]] = None


# Categories whose grounded quote is parsed into a machine value.
_DATE_CATEGORIES = {"agreement_date", "effective_date", "expiration_date"}
_MONTHS_CATEGORIES = {"renewal_term"}
_DAYS_CATEGORIES = {"notice_period_to_terminate_renewal"}
_DURATION_CATEGORIES = {"warranty_duration"}  # months-or-days, whichever parses


# ---- value parsers -------------------------------------------------------

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_MONTH_NAME = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)


def parse_date(text: str) -> Optional[str]:
    """Best-effort ISO date from contract prose. Returns 'YYYY-MM-DD' or None."""
    if not text:
        return None
    t = text.strip()

    m = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", t)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = re.search(rf"\b{_MONTH_NAME}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", t, re.I)
    if m:
        return _iso(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))

    m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?{_MONTH_NAME}\.?,?\s+(\d{{4}})\b", t, re.I)
    if m:
        return _iso(int(m.group(3)), _MONTHS[m.group(2)[:3].lower()], int(m.group(1)))

    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", t)
    if m:
        return _iso(int(m.group(3)), int(m.group(1)), int(m.group(2)))

    return None


def _iso(year: int, month: int, day: int) -> Optional[str]:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


_WORD_NUMS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirty": 30, "sixty": 60, "ninety": 90,
}


def _first_number(text: str) -> Optional[int]:
    # Prefer a parenthetical digit ("twenty-four (24) months") — the drafter's
    # own disambiguation — then any bare digit, then a spelled-out number.
    m = re.search(r"\((\d{1,4})\)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(\d{1,4})\b", text)
    if m:
        return int(m.group(1))
    for word, val in _WORD_NUMS.items():
        if re.search(rf"\b{word}\b", text, re.I):
            return val
    return None


def parse_duration_days(text: str) -> Optional[int]:
    if not text:
        return None
    n = _first_number(text)
    if n is None:
        return None
    lower = text.lower()
    if "day" in lower:
        return n
    if "week" in lower:
        return n * 7
    if "month" in lower:
        return n * 30
    if "year" in lower:
        return n * 365
    return None


def parse_duration_months(text: str) -> Optional[int]:
    if not text:
        return None
    n = _first_number(text)
    if n is None:
        return None
    lower = text.lower()
    if "year" in lower:
        return n * 12
    if "month" in lower:
        return n
    return None


def _normalize_value(category: str, text: str, vlm_text: str) -> Optional[dict]:
    if category in _DATE_CATEGORIES:
        iso = parse_date(text) or parse_date(vlm_text)
        return {"date": iso} if iso else None
    if category in _MONTHS_CATEGORIES:
        months = parse_duration_months(text) or parse_duration_months(vlm_text)
        return {"months": months} if months is not None else None
    if category in _DAYS_CATEGORIES:
        days = parse_duration_days(text) or parse_duration_days(vlm_text)
        return {"days": days} if days is not None else None
    if category in _DURATION_CATEGORIES:
        months = parse_duration_months(text) or parse_duration_months(vlm_text)
        if months is not None:
            return {"months": months}
        days = parse_duration_days(text) or parse_duration_days(vlm_text)
        return {"days": days} if days is not None else None
    return None


# ---- extraction selection ------------------------------------------------


def _best_extraction(extractions: list[CuadExtraction]) -> Optional[CuadExtraction]:
    if not extractions:
        return None
    grounded = [e for e in extractions if e.ocr_verification.is_grounded]
    pool = grounded or extractions
    return max(pool, key=lambda e: e.ocr_verification.score)


def _verbatim_text(ext: CuadExtraction) -> str:
    # The OCR-matched span is the real page text; fall back to the model's text
    # when nothing was grounded.
    text = (ext.source.exact_supporting_text or ext.vlm_text or "").strip()
    return text[:_MAX_VERBATIM]


# ---- field builders ------------------------------------------------------


def _field_for_category(category: str, analysis: ContractAnalysis) -> FieldRow:
    finding = analysis.cuad_findings.get(category)
    if finding is None or finding.answer == AnswerStatus.UNRESOLVED or not finding.extractions:
        return FieldRow(
            field_key=category, value_verbatim=None, value_normalized=None,
            confidence_tier="inferred", absence_reason="not_found",
        )

    ext = _best_extraction(finding.extractions)
    assert ext is not None
    grounded = ext.ocr_verification.is_grounded
    verbatim = _verbatim_text(ext)
    normalized = _normalize_value(category, verbatim, ext.vlm_text)

    if not grounded:
        tier = "unverified"  # quote could not be located — a fabrication signal
    elif normalized is not None:
        tier = "normalised"
    else:
        tier = "verbatim"

    return FieldRow(
        field_key=category,
        value_verbatim=verbatim or None,
        value_normalized=normalized,
        confidence_tier=tier,
        claim_type="contract_text",
        clause_label=ext.source.clause or None,
        consistency_score=round(ext.ocr_verification.score / 100.0, 3),
        anchor_page=ext.location.page,
        anchor_bbox_1000=list(ext.location.bbox_1000),
    )


def map_fields(analysis: ContractAnalysis) -> list[FieldRow]:
    """One FieldRow per CUAD category (all 41), present or explicitly absent."""
    return [_field_for_category(category, analysis) for category in CUAD_CLASSES]


# ---- document-level classification --------------------------------------


def _finding_summary(analysis: ContractAnalysis, category: str) -> str:
    finding = analysis.cuad_findings.get(category)
    return (finding.summary if finding else "") or ""


def classify_doc_type(analysis: ContractAnalysis, full_text: str) -> tuple[str, float]:
    """Heuristic doc_type. CUAD has no document-classification category, so this
    is a keyword pass over the document name + body — modest confidence."""
    name = _finding_summary(analysis, "document_name").lower()
    head = (name + "\n" + full_text[:4000]).lower()

    present = sum(1 for f in analysis.cuad_findings.values() if f.answer == AnswerStatus.PRESENT)
    parties = analysis.cuad_findings.get("parties")
    parties_present = parties is not None and parties.answer == AnswerStatus.PRESENT
    if present <= 1 and not parties_present:
        return "not_a_contract", 0.6

    rules: list[tuple[str, tuple[str, ...]]] = [
        ("nda", ("non-disclosure", "nondisclosure", "confidentiality agreement", "mutual nda")),
        ("lease", ("lease", "landlord", "tenant", "leased premises", "demised premises")),
        ("distribution", ("distribution agreement", "distributor", "reseller agreement")),
        ("employment", ("employment agreement", "employee", "the employee shall", "job title")),
        ("msa", ("master services agreement", "services agreement", "statement of work", "master service")),
    ]
    for doc_type, keywords in rules:
        if any(k in head for k in keywords):
            return doc_type, 0.75
    return "other", 0.6


def provenance_and_status(page_sources: list[str], original_ext: str) -> tuple[str, bool, str]:
    """(provenance_quality, ocr_applied, status)."""
    ocr_applied = any(s == "ocr" for s in page_sources)
    ext = original_ext.lower().lstrip(".")
    if ext in ("docx", "doc", "rtf", "odt", "html", "htm", "txt"):
        return "text_only", ocr_applied, "ready"
    if ocr_applied:
        return "degraded", True, "degraded"
    return "exact", False, "ready"


def counterparty_from(analysis: ContractAnalysis, user_hint: Optional[str]) -> Optional[str]:
    """Extract a counterparty name from the CUAD `parties` finding.

    Conventionally the counterparty is the second-named party; without a
    configured portfolio owner we cannot be certain which side is "us", so we
    take the second distinct party span (falling back to the first) and trim it
    to the name portion."""
    finding = analysis.cuad_findings.get("parties")
    if not finding or finding.answer == AnswerStatus.UNRESOLVED:
        return None

    names: list[str] = []
    seen: set[str] = set()
    for ext in sorted(finding.extractions, key=lambda e: not e.ocr_verification.is_grounded):
        name = _party_name(_verbatim_text(ext))
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            names.append(name)

    if user_hint:
        for name in names:
            if user_hint.lower() not in name.lower():
                return name
    if len(names) >= 2:
        return names[1]
    if names:
        return names[0]
    return None


def _party_name(text: str) -> str:
    """Trim a party span to just the entity name (up to the first comma / paren)."""
    trimmed = re.split(r"[,(]", text, maxsplit=1)[0].strip()
    return trimmed[:80]


# ---- calendar ------------------------------------------------------------


@dataclass
class EventRow:
    event_type: str
    event_date: str  # ISO
    action_by_date: Optional[str]
    title: str
    detail: str
    confidence_tier: str
    source_field_keys: list[str] = field(default_factory=list)


def build_calendar(fields: list[FieldRow], counterparty: Optional[str]) -> list[EventRow]:
    """Forward-looking deadlines derived from the extracted dates.

    Only grounded, normalised dates feed the calendar — an `unverified` value is
    a fabrication signal and must never generate an obligation. The notice
    period (if present) sets the action-by date ahead of expiry.
    """
    by_key = {f.field_key: f for f in fields}
    who = counterparty or "the counterparty"

    def usable(row: Optional[FieldRow]) -> Optional[dict]:
        if not row or row.confidence_tier == "unverified":
            return None
        return row.value_normalized

    expiration = by_key.get("expiration_date")
    renewal = by_key.get("renewal_term")
    notice = by_key.get("notice_period_to_terminate_renewal")

    end_iso = (usable(expiration) or {}).get("date")
    if not end_iso:
        return []

    renews = usable(renewal) is not None and (renewal.value_verbatim is not None)
    notice_days = (usable(notice) or {}).get("days")
    action_by: Optional[str] = None
    if notice_days is not None:
        try:
            action_by = (date.fromisoformat(end_iso) - timedelta(days=int(notice_days))).isoformat()
        except (ValueError, TypeError):
            action_by = None

    if renews:
        return [
            EventRow(
                event_type="auto_renewal",
                event_date=end_iso,
                action_by_date=action_by,
                title=f"Renewal decision for {who}",
                detail=(
                    f"Give notice by {action_by} to terminate renewal."
                    if action_by else f"Renewal term begins at expiry on {end_iso}."
                ),
                confidence_tier="assembled" if action_by else "normalised",
                source_field_keys=[
                    k for k in ("expiration_date", "renewal_term", "notice_period_to_terminate_renewal")
                    if k in by_key
                ],
            )
        ]
    return [
        EventRow(
            event_type="expiry",
            event_date=end_iso,
            action_by_date=action_by,
            title=f"Agreement with {who} expires",
            detail=f"The term ends on {end_iso}.",
            confidence_tier="normalised",
            source_field_keys=["expiration_date"],
        )
    ]
