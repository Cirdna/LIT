"""Frustrated Contracts Act 1959 (2020 Rev Ed) — Singapore. ROLE B: reviews clauses.

Frustration is not a drafting defect, so this module is not looking for one. It
is looking for the clause that CHANGES what happens if the contract is
frustrated — force majeure, act of God, material adverse change — because of how
s.3 works: where the contract makes its own provision for the frustrating
circumstances, the court gives effect to that provision, and the Act's
adjustment regime in s.2 (recovery of sums paid, allowance for a valuable
benefit conferred) applies only so far as the provision does not cover the case.

The practical consequence for a reader is counter-intuitive and worth flagging:
having a force majeure clause does not mean the statutory adjustment applies. It
may mean the opposite, for whatever the clause reaches.

No reasonableness test is involved here — `reasonableness_test_applies` is left
None rather than False, since the question is one of scope, not of a test that
happens to be unavailable.
"""

from __future__ import annotations

from typing import Optional

from ..schema import StatuteFlag
from ._triggers import Trigger, first_match, flag_id, phrase
from .types import ClauseField

STATUTE = "Frustrated Contracts Act 1959 (2020 Rev Ed)"
MODULE = "statutes.frustration"

_SUPERVENING_EVENT = phrase(
    r"force majeure",
    r"act of god",
    r"acts of god",
    r"beyond (?:its |their |the )?reasonable control",
    r"beyond (?:its |their |the )?control",
    r"material adverse (?:change|effect)",
    r"frustrat\w*",
    r"impossib\w*",
    r"impractica\w*",
    r"supervening event\w*",
)
_CONSEQUENCE = phrase(
    r"suspend\w*",
    r"terminat\w*",
    r"excused?",
    r"relieved",
    r"discharged?",
    r"no(?:t)? (?:be )?liable",
    r"extension of time",
)
_MONEY_ALREADY_PAID = phrase(
    r"refund\w*",
    r"repay\w*",
    r"reimburs\w*",
    r"non-?refundable",
    r"sums? (?:already )?paid",
    r"prepay\w*",
    r"pre-?paid",
    r"deposit",
    r"advance payment\w*",
)
_EXCLUDED_SUBJECT_MATTER = phrase(
    r"charterparty",
    r"charter-?party",
    r"carriage of goods by sea",
    r"bill of lading",
    r"contract of insurance",
    r"polic(?:y|ies) of insurance",
)

_SCOPE_FACTORS = (
    "Whether the clause actually covers the event that occurred. s.3 gives effect to the "
    "parties' own provision only so far as it does; the Act's adjustment applies to the "
    "remainder.",
    "What the clause says about sums already paid or benefits already conferred — this is "
    "the ground s.2 would otherwise occupy (recovery of sums paid, less allowance for "
    "expenses; and a just sum for any valuable benefit obtained).",
    "Whether the event merely makes performance harder or more expensive, which is not "
    "ordinarily frustration, as distinct from making it impossible or radically different.",
    "Whether this contract is of a kind the Act does not apply to — s.3 excludes, among "
    "others, charterparties (other than a time charter or a charter by way of demise), "
    "contracts for the carriage of goods by sea, contracts of insurance, and contracts for "
    "the sale of specific goods which perish.",
)

TRIGGERS = (
    Trigger(
        key="s3_provision_covering_prepayments",
        citation="s.3",
        required=(_SUPERVENING_EVENT, _MONEY_ALREADY_PAID),
        trigger=(
            "This clause provides for supervening events AND addresses money already paid or "
            "payable."
        ),
        review_required=(
            "This is the situation s.3 is about. Because the contract makes its own provision "
            "for the frustrating circumstances, the court gives effect to that provision, and "
            "the statutory adjustment in s.2 — recovery of sums paid, and a just sum for any "
            "valuable benefit conferred — applies only so far as the clause does not cover the "
            "case. Confirm the clause's scope against the event before assuming either regime "
            "governs."
        ),
        factors=_SCOPE_FACTORS,
    ),
    Trigger(
        key="s3_provision_for_frustrating_circumstances",
        citation="s.3",
        required=(_SUPERVENING_EVENT, _CONSEQUENCE),
        trigger=(
            "This clause provides for what happens on a supervening event outside the parties' "
            "control."
        ),
        review_required=(
            "Under s.3 the court gives effect to a contractual provision intended to apply in "
            "frustrating circumstances, and the Act's adjustment regime in s.2 applies only so "
            "far as that provision does not cover the case. Having such a clause therefore "
            "narrows, rather than confirms, the statutory position. Confirm what the clause "
            "covers."
        ),
        factors=_SCOPE_FACTORS,
    ),
    Trigger(
        key="s3_excluded_contract_type",
        citation="s.3",
        required=(_EXCLUDED_SUBJECT_MATTER, _SUPERVENING_EVENT),
        trigger=(
            "This clause refers to subject matter the Act may not extend to at all "
            "(charterparty, carriage of goods by sea, or insurance)."
        ),
        review_required=(
            "s.3 excludes certain contracts from the Act entirely, so the statutory "
            "adjustment on frustration may be unavailable regardless of what the clause says. "
            "Confirm the nature of the contract."
        ),
        factors=_SCOPE_FACTORS,
    ),
)


def validate(clause_field: ClauseField) -> Optional[StatuteFlag]:
    """Raise the frustration question this clause engages, or None."""
    match = first_match(clause_field.text, TRIGGERS)
    if match is None:
        return None
    trigger, hits = match

    return StatuteFlag(
        flag_id=flag_id(MODULE, clause_field.field_name, trigger.key, clause_field.text),
        statute=STATUTE,
        citation=trigger.citation,
        field_name=clause_field.field_name,
        trigger=f"{trigger.trigger} Detected on the wording: “{'”, “'.join(hits)}”.",
        review_required=trigger.review_required,
        factors=list(trigger.factors),
        excerpt=clause_field.text,
        source=clause_field.source,
        location=clause_field.location,
        # A question of scope, not of a reasonableness test.
        reasonableness_test_applies=None,
        requires_human_review=True,
        raised_by=MODULE,
    )
