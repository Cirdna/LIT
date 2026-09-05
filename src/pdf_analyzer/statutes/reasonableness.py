"""The s.11 UCTA reasonableness test, as a gate — built once, called twice.

s.3 of the Misrepresentation Act does not have its own test: it says a term
excluding liability or a remedy for misrepresentation is of no effect "except in
so far as it satisfies the requirement of reasonableness as stated in section
11(1) of the Unfair Contract Terms Act". So the same test governs both, and
implementing it twice would let the two drift apart.

WHAT THIS DOES NOT DO: it does not decide whether a clause is reasonable. That
question is fact-heavy, turns on the parties' relative bargaining strength and
what was known when the contract was made, and is exactly the judgement this
project reserves for a human. Full IRAC reasoning over the guidelines is
explicitly out of scope. The gate names the test, names the factors, and names
who carries the burden — then stops.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..schema import Location, Source, StatuteFlag
from ._triggers import flag_id
from .types import CounterpartyStatus

UCTA = "Unfair Contract Terms Act 1977 (2020 Rev Ed)"

# s.11(1): the term must have been a fair and reasonable one to include, judged
# on the circumstances known or contemplated when the contract was MADE — not
# with hindsight about the breach that later happened.
S11_TEST = (
    "Whether the term was a fair and reasonable one to include, having regard to the "
    "circumstances which were, or ought reasonably to have been, known to or in the "
    "contemplation of the parties when the contract was made (s.11(1) UCTA)."
)

# s.11(5): the burden sits on the party relying on the clause. Worth surfacing —
# it is the opposite of what a non-lawyer usually assumes.
S11_BURDEN = (
    "The party relying on the term must show that it satisfies the requirement of "
    "reasonableness; it is not for the other side to disprove it (s.11(5) UCTA)."
)

# s.11(4): specific to a cap at a stated sum.
S11_SUM_FACTORS = (
    "Where liability is limited to a specified sum: the resources available to meet the "
    "liability, and how far it was open to that party to cover itself by insurance "
    "(s.11(4) UCTA)."
)

# Second Schedule guidelines. s.11(2) directs the court to these for ss.6 and 7
# — not for s.3 or for s.3 of the Misrepresentation Act, which is why the gate
# takes a flag rather than always appending them.
SCHEDULE_2_GUIDELINES = (
    "The strength of the parties' bargaining positions relative to each other, including "
    "any alternative means of meeting the customer's requirements (Sch 2(a)).",
    "Whether the customer received an inducement to agree to the term, or could have "
    "contracted with someone else without accepting a similar term (Sch 2(b)).",
    "Whether the customer knew or ought reasonably to have known of the term's existence "
    "and extent, having regard to trade custom and any previous course of dealing "
    "(Sch 2(c)).",
    "Where the term applies only if a condition is not complied with, whether it was "
    "reasonable at the time to expect compliance to be practicable (Sch 2(d)).",
    "Whether the goods were manufactured, processed or adapted to the customer's special "
    "order (Sch 2(e)).",
)


@dataclass(frozen=True)
class ReasonablenessContext:
    """Everything the gate needs from the statute that imported the test."""

    field_name: str
    statute: str  # the Act whose provision brings the test in
    citation: str  # that provision, e.g. "s.6(3)" or "s.3"
    trigger: str  # what was detected in the clause
    raised_by: str
    # s.11(2) directs the court to the Second Schedule for ss.6 and 7 only.
    include_schedule_2: bool = False
    # Set when the clause caps liability at a stated sum, bringing s.11(4) in.
    limits_to_specified_sum: bool = False
    counterparty_status: CounterpartyStatus = CounterpartyStatus.UNKNOWN
    source: Optional[Source] = None
    location: Optional[Location] = None
    extra_factors: tuple = ()


def reasonableness_gate(clause_text: str, context: ReasonablenessContext) -> StatuteFlag:
    """Raise the reasonableness question for a clause, without answering it."""
    factors = [S11_TEST, S11_BURDEN]
    if context.include_schedule_2:
        factors.extend(SCHEDULE_2_GUIDELINES)
    if context.limits_to_specified_sum:
        factors.append(S11_SUM_FACTORS)
    factors.extend(context.extra_factors)

    if context.counterparty_status is CounterpartyStatus.UNKNOWN:
        # Not padding: under UCTA the same clause can be ineffective against a
        # consumer and merely reviewable against a business. Leaving that
        # unresolved is honest; guessing "business" would quietly downgrade the
        # warning on the one contract where it matters most.
        factors.append(
            "Whether the other party dealt as a consumer has not been determined. It "
            "changes the answer: against a consumer some exclusions are ineffective "
            "outright, while between businesses the reasonableness test applies."
        )

    return StatuteFlag(
        flag_id=flag_id(context.raised_by, context.field_name, context.citation, clause_text),
        statute=context.statute,
        citation=context.citation,
        field_name=context.field_name,
        trigger=context.trigger,
        review_required=(
            "A reasonableness review is required. This tool does not assess "
            "reasonableness — the factors below are what that assessment turns on."
        ),
        factors=factors,
        excerpt=clause_text,
        source=context.source,
        location=context.location,
        reasonableness_test_applies=True,
        requires_human_review=True,
        raised_by=context.raised_by,
    )
