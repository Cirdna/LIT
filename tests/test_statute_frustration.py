"""Frustrated Contracts Act module, in isolation (Role B)."""

from __future__ import annotations

import pytest

from pdf_analyzer.schema import Source
from pdf_analyzer.statutes import frustration
from pdf_analyzer.statutes.types import ClauseField


def clause(text: str, *, field_name: str = "force_majeure") -> ClauseField:
    return ClauseField(
        field_name=field_name,
        text=text,
        source=Source(page=11, clause="Clause 14", exact_supporting_text=text),
    )


def test_force_majeure_clause_is_flagged_for_scope_review():
    flag = frustration.validate(
        clause(
            "Neither party shall be liable for any failure to perform caused by events beyond "
            "its reasonable control, and performance shall be suspended for the duration."
        )
    )
    assert flag is not None
    assert flag.citation == "s.3"
    assert flag.statute.startswith("Frustrated Contracts Act 1959")


def test_it_is_not_a_reasonableness_question():
    # None rather than False: no reasonableness test is involved at all here, as
    # distinct from one that exists but is unavailable (UCTA s.2(1)).
    flag = frustration.validate(
        clause("Performance is excused where an act of God prevents it.")
    )
    assert flag.reasonableness_test_applies is None


def test_the_counter_intuitive_effect_is_stated():
    # A reader who sees a force majeure clause tends to assume the statute helps
    # them. Under s.3 the clause may be what displaces it.
    flag = frustration.validate(
        clause("Performance is excused where an act of God prevents it.")
    )
    assert "only so far as that provision does not cover the case" in flag.review_required


def test_prepayment_handling_gets_the_more_specific_trigger():
    flag = frustration.validate(
        clause(
            "If a force majeure event continues for 60 days, either party may terminate and "
            "any deposit paid shall be non-refundable."
        )
    )
    assert "money already paid" in flag.trigger
    assert "recovery of sums paid" in flag.review_required


def test_excluded_contract_types_are_raised():
    flag = frustration.validate(
        clause(
            "This contract of insurance is not affected by any event of force majeure."
        )
    )
    assert "may not extend to at all" in flag.trigger


def test_factors_include_the_statutory_exclusions_and_the_hardship_distinction():
    flag = frustration.validate(
        clause("Performance is suspended on any event beyond the reasonable control of a party.")
    )
    assert any("charterparties" in f for f in flag.factors)
    assert any("harder or more expensive" in f for f in flag.factors)


@pytest.mark.parametrize(
    "text",
    [
        "The Supplier shall deliver the Goods to the Buyer's warehouse.",
        "This Agreement may be terminated on 30 days' written notice.",
        "The parties shall review pricing annually.",
    ],
)
def test_does_not_fire_on_ordinary_clauses(text):
    assert frustration.validate(clause(text)) is None


def test_never_asserts_that_the_contract_is_frustrated():
    flag = frustration.validate(
        clause("Performance is excused where an act of God renders it impossible.")
    )
    assert flag.requires_human_review is True
    prose = f"{flag.trigger} {flag.review_required} {' '.join(flag.factors)}".lower()
    for conclusion in ("is frustrated", "has been discharged", "is void", "is terminated"):
        assert conclusion not in prose
