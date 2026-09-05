"""The statute layer: what the law supplies, and what the law wants looked at.

Two roles, kept apart on purpose (see schema.StatutoryDefault / StatuteFlag):

  ROLE A — sale_of_goods, supply_of_goods, crtpa
      `default_value(field_name) -> StatutoryDefault | None`
      Runs BEFORE extraction. Supplies the term the law provides when the
      contract is silent. Displaced once the contract is found to deal with the
      topic itself.

  ROLE B — ucta, misrepresentation, frustration
      `validate(clause_field) -> StatuteFlag | None`
      Runs AFTER extraction. Reads the clause as extracted, returns a flag, and
      never modifies the clause.

Everything here is deterministic: statutory tables and regex triggers, no model
calls. Two consequences, both deliberate. First, it is auditable — every flag
names the provision and the wording that set it off. Second, it is incomplete —
an unusually drafted exclusion will be missed, and a missed trigger is silent.
Nothing in this layer decides a legal question.

JURISDICTION: Singapore.

CITATION NOTE: section numbers are drawn from the Acts as commonly cited and
should be checked against the current Revised Edition before being relied on in
advice. Statutory wording is PARAPHRASED throughout — StatutoryDefault
.verbatim_text is deliberately left None rather than reconstructed, because a
tool built on the rule that quotations must be verifiable does not get to make
an exception for quoting Acts.
"""

from __future__ import annotations

from types import ModuleType
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ..schema import CategoryFinding, Source, StatuteFlag, StatuteRole, StatutoryDefault
from . import crtpa, frustration, misrepresentation, sale_of_goods, supply_of_goods, ucta
from .reasonableness import (
    SCHEDULE_2_GUIDELINES,
    ReasonablenessContext,
    reasonableness_gate,
)
from .types import ClauseField, ContractContext, CounterpartyStatus

__all__ = [
    "ROLE_A_MODULES",
    "ROLE_B_MODULES",
    "ClauseField",
    "ContractContext",
    "CounterpartyStatus",
    "ReasonablenessContext",
    "SCHEDULE_2_GUIDELINES",
    "StatuteRole",
    "clause_fields_from_findings",
    "default_value",
    "mark_displaced",
    "prefill_defaults",
    "reasonableness_gate",
    "review_clause",
    "review_clauses",
]

ROLE_A_MODULES: Tuple[ModuleType, ...] = (sale_of_goods, supply_of_goods, crtpa)
ROLE_B_MODULES: Tuple[ModuleType, ...] = (ucta, misrepresentation, frustration)


# --------------------------------------------------------------------------
# Role A
# --------------------------------------------------------------------------


def default_value(field_name: str) -> Optional[StatutoryDefault]:
    """The first statute that supplies a default for `field_name`.

    Field names are namespaced by statute topic rather than shared, so in
    practice at most one module answers for any given name.
    """
    for module in ROLE_A_MODULES:
        found = module.default_value(field_name)
        if found is not None:
            return found
    return None


def prefill_defaults(field_names: Optional[Iterable[str]] = None) -> Dict[str, StatutoryDefault]:
    """Every statutory default, keyed by field name.

    Called BEFORE extraction: the result describes the legal position the
    contract starts from, which is what makes "the contract is silent on
    quality" a statement about the law rather than a blank in a table.
    """
    if field_names is None:
        names: List[str] = []
        for module in ROLE_A_MODULES:
            names.extend(module.field_names())
    else:
        names = list(field_names)

    out: Dict[str, StatutoryDefault] = {}
    for name in names:
        found = default_value(name)
        if found is not None:
            out[name] = found
    return out


def mark_displaced(
    defaults: Dict[str, StatutoryDefault],
    present_categories: Dict[str, Optional[Source]],
) -> Dict[str, StatutoryDefault]:
    """Displace the defaults the contract turns out to deal with itself.

    `present_categories` maps an extracted category to the clause that carried
    it. A default is displaced only where it declared a category that is present:
    where no category corresponds (auto_displacement_supported False) the default
    stays standing and says it could not be checked, because the absence of an
    extraction is not evidence that the contract is silent.
    """
    out: Dict[str, StatutoryDefault] = {}
    for name, default in defaults.items():
        hit = next(
            (cat for cat in default.displaced_by_categories if cat in present_categories), None
        )
        if hit is None:
            out[name] = default
            continue
        out[name] = default.model_copy(
            update={"is_displaced": True, "displaced_by": present_categories[hit]}
        )
    return out


# --------------------------------------------------------------------------
# Role B
# --------------------------------------------------------------------------


def review_clause(clause_field: ClauseField) -> List[StatuteFlag]:
    """Every Role B flag this clause raises — at most one per statute."""
    flags: List[StatuteFlag] = []
    for module in ROLE_B_MODULES:
        flag = module.validate(clause_field)
        if flag is not None:
            flags.append(flag)
    return flags


def review_clauses(clause_fields: Sequence[ClauseField]) -> List[StatuteFlag]:
    """Role B over many clauses, de-duplicated on flag_id.

    The same boilerplate often lands in two extracted categories; flag_id is a
    digest of the clause text, so the reader sees the point once.
    """
    seen = set()
    flags: List[StatuteFlag] = []
    for clause_field in clause_fields:
        for flag in review_clause(clause_field):
            if flag.flag_id in seen:
                continue
            seen.add(flag.flag_id)
            flags.append(flag)
    return flags


def clause_fields_from_findings(
    findings: Dict[str, CategoryFinding],
    context: Optional[ContractContext] = None,
) -> List[ClauseField]:
    """Turn extracted findings into Role B inputs, grounded text only.

    Ungrounded text is skipped deliberately. A statutory warning about a sentence
    Stage 3 could not find on the page would be a legal alarm attached to
    something that may not be in the contract at all — worse than no warning.
    """
    context = context or ContractContext()
    out: List[ClauseField] = []
    for category, finding in findings.items():
        for extraction in finding.extractions:
            text = extraction.vlm_text.strip()
            if not text or not extraction.ocr_verification.is_grounded:
                continue
            out.append(
                ClauseField(
                    field_name=category,
                    text=text,
                    source=extraction.source,
                    location=extraction.location,
                    is_grounded=True,
                    context=context,
                )
            )
    return out
