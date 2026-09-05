"""Misrepresentation Act 1967 (2020 Rev Ed) — Singapore. ROLE B: reviews clauses.

s.3 is the provision that bites on drafting: a term excluding or restricting
liability for a pre-contractual misrepresentation, or a remedy for one, "shall
be of no effect except in so far as it satisfies the requirement of
reasonableness as stated in section 11(1) of the Unfair Contract Terms Act".

That is why this module shares UCTA's gate rather than owning a test of its own.
Note the narrower import: s.3 brings in s.11(1) only, so the Second Schedule
guidelines (directed by s.11(2) to ss.6 and 7 of UCTA) are NOT appended here.
Getting that wrong would hand a reviewer five factors the court is not directed
to for this clause.

The clauses that trigger it are the ones nobody reads: entire agreement,
non-reliance, and "no representations have been made" boilerplate. Whether such
a clause engages s.3 at all depends on substance rather than its label, which is
precisely why this module raises the question instead of settling it.
"""

from __future__ import annotations

from typing import Optional

from ..schema import StatuteFlag
from ._triggers import EXCLUSION_VERBS, Trigger, first_match, phrase
from .reasonableness import ReasonablenessContext, reasonableness_gate
from .types import ClauseField

STATUTE = "Misrepresentation Act 1967 (2020 Rev Ed)"
MODULE = "statutes.misrepresentation"

_MISREPRESENTATION = phrase(
    r"misrepresentation\w*",
    r"misstatement\w*",
    r"representation\w*",
    r"pre-?contractual statement\w*",
)
_NON_RELIANCE = phrase(
    r"has not relied",
    r"have not relied",
    r"does not rely",
    r"do not rely",
    r"no reliance",
    r"acknowledges? that no representation",
    r"no representations? (?:have|has) been made",
)
_ENTIRE_AGREEMENT = phrase(
    r"entire agreement",
    r"whole agreement",
    r"supersedes? all (?:prior|previous)",
    r"constitutes? the entire understanding",
)
_REMEDY = phrase(
    r"rescission",
    r"rescind",
    r"terminate the (?:agreement|contract) for misrepresentation",
    r"remed(?:y|ies)",
    r"damages",
)

TRIGGERS = (
    Trigger(
        key="s3_excludes_liability_for_misrepresentation",
        citation="s.3",
        required=(EXCLUSION_VERBS, _MISREPRESENTATION),
        trigger=(
            "This clause appears to exclude or restrict liability for a pre-contractual "
            "misrepresentation."
        ),
        review_required="",  # supplied by the gate
        reasonableness_test_applies=True,
    ),
    Trigger(
        key="s3_excludes_remedy_for_misrepresentation",
        citation="s.3",
        required=(EXCLUSION_VERBS, _REMEDY, _MISREPRESENTATION),
        trigger=(
            "This clause appears to exclude or restrict a remedy for a pre-contractual "
            "misrepresentation."
        ),
        review_required="",
        reasonableness_test_applies=True,
    ),
    Trigger(
        key="s3_non_reliance",
        citation="s.3",
        required=(_NON_RELIANCE,),
        trigger=(
            "This clause contains a non-reliance or 'no representations' acknowledgement."
        ),
        review_required="",
        reasonableness_test_applies=True,
        factors=(
            "Whether the clause operates as a basis-of-contract clause (defining what was "
            "represented) or as an exclusion of liability for what was in fact represented — "
            "s.3 reaches the second, and the label given to the clause does not decide which "
            "it is.",
        ),
    ),
    Trigger(
        key="s3_entire_agreement",
        citation="s.3",
        required=(_ENTIRE_AGREEMENT, _MISREPRESENTATION),
        trigger=(
            "This entire agreement clause extends to representations, not only to terms."
        ),
        review_required="",
        reasonableness_test_applies=True,
        factors=(
            "An entire agreement clause that is confined to contractual terms does not by "
            "itself exclude liability for misrepresentation; one that extends to "
            "representations may engage s.3.",
        ),
    ),
)


def validate(clause_field: ClauseField) -> Optional[StatuteFlag]:
    """Raise s.3 for this clause, or None."""
    match = first_match(clause_field.text, TRIGGERS)
    if match is None:
        return None
    trigger, hits = match

    context = ReasonablenessContext(
        field_name=clause_field.field_name,
        statute=STATUTE,
        citation=trigger.citation,
        trigger=f"{trigger.trigger} Detected on the wording: “{'”, “'.join(hits)}”.",
        raised_by=MODULE,
        # s.3 imports s.11(1) alone — the Second Schedule guidelines belong to
        # ss.6 and 7 of UCTA and are deliberately not added here.
        include_schedule_2=False,
        counterparty_status=clause_field.context.counterparty_status,
        source=clause_field.source,
        location=clause_field.location,
        extra_factors=trigger.factors
        + (
            "s.3 applies the s.11(1) UCTA test only; the Second Schedule guidelines are not "
            "directed to this provision.",
        ),
    )
    return reasonableness_gate(clause_field.text, context)
