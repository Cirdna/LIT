"""Unfair Contract Terms Act 1977 (2020 Rev Ed) — Singapore. ROLE B: reviews clauses.

Reads clauses the pipeline already extracted and raises the provision that wants
looking at. It never edits the clause and never concludes that a term is void.

The distinction the Act draws, and that this module therefore draws, is between:

  * provisions admitting NO reasonableness escape — s.2(1) (death or personal
    injury from negligence) and s.6(1) (the implied undertaking as to title).
    Here the flag says the exclusion cannot be given effect, which is the Act's
    own position, not this tool's judgement.
  * provisions where a reasonableness test decides it — ss.2(2), 3, 6(3), 7.
    Here the flag hands off to `reasonableness.reasonableness_gate`, which names
    the test and refuses to apply it.

Whether the other side dealt as a consumer changes several answers and is not
something the pipeline determines, so the flags say so rather than assuming.
"""

from __future__ import annotations

from typing import Optional

from ..schema import StatuteFlag
from ._triggers import EXCLUSION_VERBS, Trigger, first_match, flag_id, phrase
from .reasonableness import UCTA, ReasonablenessContext, reasonableness_gate
from .types import ClauseField, CounterpartyStatus

STATUTE = UCTA
MODULE = "statutes.ucta"

_DEATH_OR_INJURY = phrase(r"death", r"personal injur\w*", r"bodily injur\w*")
_NEGLIGENCE = phrase(r"negligen\w*", r"breach of duty", r"failure to take reasonable care")
_TITLE = phrase(
    r"title",
    r"right to sell",
    r"quiet possession",
    r"free from (?:any )?encumbrance\w*",
)
_IMPLIED_TERMS = phrase(
    r"implied (?:term|terms|warrant\w*|condition\w*|undertaking\w*)",
    r"satisfactory quality",
    r"merchantab\w*",
    r"fitness for (?:a )?(?:particular )?purpose",
    r"fit for (?:a )?(?:particular )?purpose",
    r"correspond\w* with (?:its |the )?description",
)
_STATUTORY_SOURCE = phrase(
    r"sale of goods act",
    r"supply of goods act",
    r"statut\w*",
    r"by law",
    r"whether express or implied",
)
_SPECIFIED_SUM = phrase(
    r"shall not exceed",
    r"limited to",
    r"capped at",
    r"aggregate liabilit\w*",
    r"maximum (?:aggregate )?liabilit\w*",
)
_HIRE_OR_SUPPLY = phrase(r"hire", r"bailment", r"lease of (?:the )?goods", r"supply of goods")
_BREACH = phrase(r"breach", r"non-?performance", r"failure to perform", r"default")

# Declared most specific first: see _triggers.first_match.
TRIGGERS = (
    Trigger(
        key="s2_1_death_or_personal_injury",
        citation="s.2(1)",
        required=(EXCLUSION_VERBS, _DEATH_OR_INJURY),
        trigger=(
            "This clause appears to exclude or restrict liability in relation to death or "
            "personal injury."
        ),
        review_required=(
            "s.2(1) does not permit liability for death or personal injury resulting from "
            "negligence to be excluded or restricted by any contract term. There is no "
            "reasonableness test to satisfy here. Confirm whether the liability this clause "
            "reaches is negligence-based, then have the drafting reviewed."
        ),
        reasonableness_test_applies=False,
        factors=(
            "Whether the liability caught by this clause arises from negligence, as s.2 "
            "defines it (s.1(1)).",
            "Whether the clause is severable, so that the remainder of the exclusion can "
            "still operate.",
        ),
    ),
    Trigger(
        key="s6_1_title",
        citation="s.6(1)",
        required=(EXCLUSION_VERBS, _TITLE),
        trigger=(
            "This clause appears to exclude or restrict the implied undertaking as to title "
            "or quiet possession."
        ),
        review_required=(
            "s.6(1) does not permit the s.12 Sale of Goods Act undertaking as to title to be "
            "excluded or restricted by any contract term, in a business or consumer contract "
            "alike. No reasonableness test applies. Confirm whether the clause reaches the "
            "title undertaking rather than some other warranty."
        ),
        reasonableness_test_applies=False,
        factors=(
            "Whether the clause is directed at title (s.12) or at the description, quality "
            "and fitness terms (ss.13–15), which are treated differently.",
        ),
    ),
    Trigger(
        key="s6_implied_terms_sale",
        citation="s.6",
        required=(EXCLUSION_VERBS, _IMPLIED_TERMS),
        trigger=(
            "This clause appears to exclude or restrict the implied terms as to description, "
            "quality or fitness for purpose."
        ),
        review_required=(
            "Under s.6 the answer depends on who the other party is: as against a person "
            "dealing as a consumer these terms cannot be excluded at all (s.6(2)); against "
            "anyone else the exclusion is effective only so far as it is reasonable "
            "(s.6(3)). s.11(2) directs the court to the Second Schedule guidelines."
        ),
        reasonableness_test_applies=True,
        consumer_sensitive=True,
    ),
    Trigger(
        key="s7_implied_terms_supply",
        citation="s.7",
        required=(EXCLUSION_VERBS, _HIRE_OR_SUPPLY, _IMPLIED_TERMS),
        trigger=(
            "This clause appears to exclude implied terms in a contract for the supply or "
            "hire of goods rather than a sale."
        ),
        review_required=(
            "s.7 applies the same structure as s.6 to contracts under which goods pass "
            "otherwise than by sale: no exclusion against a consumer, and only a reasonable "
            "exclusion against anyone else."
        ),
        reasonableness_test_applies=True,
        consumer_sensitive=True,
    ),
    Trigger(
        key="s2_2_negligence_other_loss",
        citation="s.2(2)",
        required=(EXCLUSION_VERBS, _NEGLIGENCE),
        trigger="This clause appears to exclude or restrict liability for negligence.",
        review_required=(
            "For loss other than death or personal injury, s.2(2) allows the exclusion only "
            "so far as it satisfies the reasonableness test."
        ),
        reasonableness_test_applies=True,
    ),
    Trigger(
        key="s3_breach_of_contract",
        citation="s.3",
        required=(EXCLUSION_VERBS, _BREACH),
        trigger="This clause appears to exclude or restrict liability for breach of contract.",
        review_required=(
            "s.3 applies where one party deals as a consumer or on the other's written "
            "standard terms of business. If it applies, the exclusion is effective only so "
            "far as it is reasonable. Whether these are standard terms has not been "
            "determined by this tool."
        ),
        reasonableness_test_applies=True,
        consumer_sensitive=True,
    ),
)


def validate(clause_field: ClauseField) -> Optional[StatuteFlag]:
    """Raise the UCTA provision this clause engages, or None."""
    match = first_match(clause_field.text, TRIGGERS)
    if match is None:
        return None
    trigger, hits = match

    detected = f"{trigger.trigger} Detected on the wording: “{'”, “'.join(hits)}”."

    if trigger.reasonableness_test_applies is True:
        context = ReasonablenessContext(
            field_name=clause_field.field_name,
            statute=STATUTE,
            citation=trigger.citation,
            trigger=detected,
            raised_by=MODULE,
            # s.11(2) points to the Second Schedule for ss.6 and 7 only.
            include_schedule_2=trigger.citation in ("s.6", "s.7"),
            limits_to_specified_sum=bool(_SPECIFIED_SUM.search(clause_field.text)),
            counterparty_status=clause_field.context.counterparty_status,
            source=clause_field.source,
            location=clause_field.location,
            extra_factors=trigger.factors,
        )
        flag = reasonableness_gate(clause_field.text, context)
        if trigger.consumer_sensitive:
            flag = flag.model_copy(update={"review_required": trigger.review_required})
        return flag

    return StatuteFlag(
        flag_id=flag_id(MODULE, clause_field.field_name, trigger.citation, clause_field.text),
        statute=STATUTE,
        citation=trigger.citation,
        field_name=clause_field.field_name,
        trigger=detected,
        review_required=trigger.review_required,
        factors=list(trigger.factors),
        excerpt=clause_field.text,
        source=clause_field.source,
        location=clause_field.location,
        reasonableness_test_applies=trigger.reasonableness_test_applies,
        requires_human_review=True,
        raised_by=MODULE,
    )


def statutory_source_mentioned(text: str) -> bool:
    """Whether the clause names a statutory source of the terms it excludes.

    Useful context for a reviewer: "excludes all warranties implied by the Sale
    of Goods Act" is a squarely s.6 clause, while a bare "excludes all
    warranties" may or may not reach the implied terms.
    """
    return bool(_STATUTORY_SOURCE.search(text))


def consumer_status_of(clause_field: ClauseField) -> CounterpartyStatus:
    return clause_field.context.counterparty_status
