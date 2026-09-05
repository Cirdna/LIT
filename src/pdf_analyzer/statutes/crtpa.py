"""Contracts (Rights of Third Parties) Act 2001 (2020 Rev Ed) — Singapore.
ROLE A: supplies defaults.

NOTE ON THE ABBREVIATION: "CRTPA" is read here as the Contracts (Rights of
Third Parties) Act. It sits with the Sale of Goods and Supply of Goods Acts as a
Role A statute because it works the same way — the Act confers a right unless
the contract provides otherwise — so the pattern holds either way. If the brief
meant a different Act, only this file changes.

Why this matters to a non-lawyer reading a contract portfolio: the common-law
privity rule says a stranger to a contract cannot enforce it. This Act reverses
that in defined circumstances, which means a term drafted for someone else's
benefit may be enforceable BY that someone else even though they never signed.
A reader who assumes only the two signatories have rights is reading the
contract incorrectly, and the contract itself will not say so.
"""

from __future__ import annotations

from typing import Dict, Optional

from ..schema import StatutoryDefault
from ._catalogue import DefaultSpec, build_default

STATUTE = "Contracts (Rights of Third Parties) Act 2001 (2020 Rev Ed)"
MODULE = "statutes.crtpa"

_IDENTIFIED = (
    "the third party is expressly identified in the contract by name, as a member of a "
    "class, or as answering a particular description (s.2(3)) — the third party need not "
    "be in existence when the contract is made"
)

SPECS: Dict[str, DefaultSpec] = {
    "third_party_enforcement": DefaultSpec(
        citation="s.2(1)",
        effect=(
            "A third party may enforce a term of the contract in its own right where the "
            "contract expressly provides that it may (s.2(1)(a)), or where the term purports "
            "to confer a benefit on it (s.2(1)(b)). The second limb does not apply if, on a "
            "proper construction of the contract, the parties did not intend the term to be "
            "enforceable by the third party (s.2(2))."
        ),
        applies_when=_IDENTIFIED,
        # CUAD has a category for exactly this topic, so displacement by an
        # express clause is detectable here — unlike most Role A defaults.
        displaced_by_categories=("third_party_beneficiary",),
    ),
    "third_party_remedies": DefaultSpec(
        citation="s.2(5)",
        effect=(
            "Where a third party may enforce a term, it has the same remedies as if it had "
            "been a party to the contract, and the ordinary rules on damages, injunctions and "
            "specific performance apply."
        ),
        applies_when="a third party has a right of enforcement under s.2(1)",
        displaced_by_categories=("third_party_beneficiary",),
    ),
    "variation_without_third_party_consent": DefaultSpec(
        citation="s.3(1)",
        effect=(
            "Once the third party has assented to the term, or has relied on it in a way the "
            "promisor knew of or could reasonably have foreseen, the contracting parties may "
            "not rescind or vary the contract so as to extinguish or alter the third party's "
            "right without its consent — unless the contract provides otherwise (s.3(5))."
        ),
        applies_when="a third party has a right of enforcement under s.2(1)",
        # Only a third-party clause displaces this. An anti-assignment clause is
        # about transferring the contract, not about contracting out of s.3(5),
        # and treating it as equivalent would delete a true statement of the law
        # on the strength of unrelated boilerplate.
        displaced_by_categories=("third_party_beneficiary",),
    ),
}


def field_names() -> tuple:
    return tuple(SPECS)


def default_value(field_name: str) -> Optional[StatutoryDefault]:
    spec = SPECS.get(field_name)
    if spec is None:
        return None
    return build_default(field_name=field_name, statute=STATUTE, spec=spec, raised_by=MODULE)
