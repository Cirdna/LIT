"""Misrepresentation Act module and the shared reasonableness gate (Role B).

The point under test is the shape of the import: s.3 brings in s.11(1) of UCTA
and nothing else, so the same gate must produce a NARROWER factor list here than
it does for UCTA ss.6/7.
"""

from __future__ import annotations

import pytest

from pdf_analyzer.schema import Source
from pdf_analyzer.statutes import misrepresentation, ucta
from pdf_analyzer.statutes.reasonableness import (
    S11_BURDEN,
    S11_TEST,
    SCHEDULE_2_GUIDELINES,
    ReasonablenessContext,
    reasonableness_gate,
)
from pdf_analyzer.statutes.types import ClauseField, ContractContext, CounterpartyStatus


def clause(text: str, *, field_name: str = "entire_agreement", **context_kwargs) -> ClauseField:
    return ClauseField(
        field_name=field_name,
        text=text,
        source=Source(page=2, clause="Clause 21", exact_supporting_text=text),
        context=ContractContext(**context_kwargs),
    )


# --- s.3 triggers ----------------------------------------------------------


def test_exclusion_of_liability_for_misrepresentation_is_flagged():
    flag = misrepresentation.validate(
        clause("The Seller excludes all liability for any misrepresentation made before signing.")
    )
    assert flag is not None
    assert flag.citation == "s.3"
    assert flag.statute.startswith("Misrepresentation Act 1967")
    assert flag.reasonableness_test_applies is True


def test_non_reliance_boilerplate_is_flagged_without_an_exclusion_verb():
    # These clauses rarely contain the word "exclude" — that is the point of them.
    flag = misrepresentation.validate(
        clause("The Buyer acknowledges that it has not relied on any statement of the Seller.")
    )
    assert flag is not None
    assert "non-reliance" in flag.trigger


def test_entire_agreement_clause_only_flagged_where_it_reaches_representations():
    reaches = misrepresentation.validate(
        clause(
            "This Agreement constitutes the entire agreement between the parties and "
            "supersedes all prior representations."
        )
    )
    assert reaches is not None

    terms_only = misrepresentation.validate(
        clause("This Agreement constitutes the entire agreement between the parties.")
    )
    # A clause confined to contractual terms does not by itself engage s.3, so
    # raising it would be a false alarm on the most common clause in commerce.
    assert terms_only is None


def test_flags_the_substance_over_the_label():
    flag = misrepresentation.validate(
        clause("The Buyer acknowledges that no representations have been made to it.")
    )
    assert any("basis-of-contract" in f for f in flag.factors)


@pytest.mark.parametrize(
    "text",
    [
        "The Seller shall deliver the Goods by 1 March.",
        "Each party shall keep the other's information confidential.",
        "The Supplier's liability for breach shall not exceed the Fees paid.",
    ],
)
def test_does_not_fire_on_clauses_about_something_else(text):
    assert misrepresentation.validate(clause(text)) is None


# --- the shared gate -------------------------------------------------------


def test_s3_imports_s11_1_only_not_the_schedule_2_guidelines():
    flag = misrepresentation.validate(
        clause("All liability for misrepresentation is excluded.")
    )
    assert S11_TEST in flag.factors
    assert S11_BURDEN in flag.factors
    for guideline in SCHEDULE_2_GUIDELINES:
        assert guideline not in flag.factors
    assert any("not directed to this provision" in f for f in flag.factors)


def test_ucta_s6_and_misrep_s3_share_the_gate_but_not_the_factor_list():
    misrep = misrepresentation.validate(
        clause("All liability for misrepresentation is excluded.")
    )
    implied = ucta.validate(
        clause("All implied terms as to satisfactory quality are excluded.")
    )
    # Same test, same burden — one implementation.
    assert S11_TEST in misrep.factors and S11_TEST in implied.factors
    assert S11_BURDEN in misrep.factors and S11_BURDEN in implied.factors
    # Different reach: s.11(2) directs ss.6/7 to the Second Schedule, s.3 does not.
    assert len(implied.factors) > len(misrep.factors)


def test_the_gate_refuses_to_answer_the_question_it_raises():
    flag = reasonableness_gate(
        "Liability for misrepresentation is excluded.",
        ReasonablenessContext(
            field_name="entire_agreement",
            statute="Misrepresentation Act 1967 (2020 Rev Ed)",
            citation="s.3",
            trigger="An exclusion was detected.",
            raised_by="tests",
            counterparty_status=CounterpartyStatus.BUSINESS,
        ),
    )
    assert flag.requires_human_review is True
    assert "does not assess reasonableness" in flag.review_required
    prose = f"{flag.review_required} {' '.join(flag.factors)}".lower()
    for conclusion in ("is reasonable", "is unreasonable", "is void", "of no effect"):
        assert conclusion not in prose


def test_the_gate_adds_the_specified_sum_factors_only_when_asked():
    def build(limits: bool):
        return reasonableness_gate(
            "Liability is limited to S$1,000.",
            ReasonablenessContext(
                field_name="cap_on_liability",
                statute="Unfair Contract Terms Act 1977 (2020 Rev Ed)",
                citation="s.3",
                trigger="A cap was detected.",
                raised_by="tests",
                limits_to_specified_sum=limits,
                counterparty_status=CounterpartyStatus.BUSINESS,
            ),
        )

    assert any("s.11(4)" in f for f in build(True).factors)
    assert not any("s.11(4)" in f for f in build(False).factors)
