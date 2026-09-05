"""UCTA module, in isolation (Role B).

The tests that matter most here are the negative ones: that the module raises a
question rather than answering it, and that it does not fire on clauses which
merely mention liability.
"""

from __future__ import annotations

import pytest

from pdf_analyzer.schema import Location, Source
from pdf_analyzer.statutes import ucta
from pdf_analyzer.statutes.types import ClauseField, ContractContext, CounterpartyStatus


def clause(text: str, *, field_name: str = "cap_on_liability", **context_kwargs) -> ClauseField:
    return ClauseField(
        field_name=field_name,
        text=text,
        source=Source(page=9, clause="Clause 9.2", exact_supporting_text=text),
        location=Location(page=9, bbox_1000=[10.0, 20.0, 30.0, 40.0]),
        context=ContractContext(**context_kwargs),
    )


# --- the provisions with no reasonableness escape --------------------------


def test_death_or_personal_injury_exclusion_has_no_reasonableness_escape():
    flag = ucta.validate(
        clause(
            "The Supplier shall not be liable for death or personal injury howsoever arising, "
            "including from its own negligence."
        )
    )
    assert flag is not None
    assert flag.citation == "s.2(1)"
    # False, not None: a test exists in the Act and is unavailable here.
    assert flag.reasonableness_test_applies is False
    assert "does not permit" in flag.review_required


def test_title_exclusion_is_flagged_under_s6_1():
    flag = ucta.validate(
        clause("All warranties as to title and quiet possession are hereby excluded.")
    )
    assert flag.citation == "s.6(1)"
    assert flag.reasonableness_test_applies is False


def test_the_most_specific_provision_wins():
    # This clause engages s.2(1) and s.2(2) both. Reporting the general one would
    # understate it, and reporting both would be noise about one sentence.
    flag = ucta.validate(
        clause(
            "The Company excludes all liability arising from negligence, including liability "
            "for personal injury."
        )
    )
    assert flag.citation == "s.2(1)"


# --- the provisions where reasonableness decides it ------------------------


def test_implied_terms_exclusion_goes_through_the_reasonableness_gate():
    flag = ucta.validate(
        clause(
            "All terms implied by statute as to satisfactory quality and fitness for purpose "
            "are excluded to the fullest extent permitted by law."
        )
    )
    assert flag.citation == "s.6"
    assert flag.reasonableness_test_applies is True
    # s.11(2) directs the court to the Second Schedule for ss.6 and 7.
    assert any("Sch 2(a)" in f for f in flag.factors)
    assert any("s.11(5)" in f for f in flag.factors)
    # And it must say the answer differs for a consumer.
    assert "consumer" in flag.review_required


def test_negligence_exclusion_for_other_loss_is_a_reasonableness_question():
    flag = ucta.validate(
        clause("The Supplier shall not be liable for any loss caused by its negligence.")
    )
    assert flag.citation == "s.2(2)"
    assert flag.reasonableness_test_applies is True
    # s.2(2) is not one of ss.6/7, so the Schedule 2 guidelines are not directed.
    assert not any("Sch 2(a)" in f for f in flag.factors)


def test_a_capped_sum_brings_in_the_insurance_and_resources_factors():
    flag = ucta.validate(
        clause(
            "The Supplier's aggregate liability for breach shall not exceed S$100,000."
        )
    )
    assert flag.reasonableness_test_applies is True
    assert any("s.11(4)" in f for f in flag.factors)


def test_unknown_consumer_status_is_surfaced_not_assumed():
    flag = ucta.validate(
        clause("Liability for breach of this Agreement is excluded.")
    )
    assert any("has not been determined" in f for f in flag.factors)


def test_known_business_counterparty_does_not_add_the_unknown_caveat():
    flag = ucta.validate(
        clause(
            "Liability for breach of this Agreement is excluded.",
            counterparty_status=CounterpartyStatus.BUSINESS,
        )
    )
    assert not any("has not been determined" in f for f in flag.factors)


# --- restraint -------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "The Supplier shall maintain insurance of not less than S$5,000,000.",
        "This Agreement is governed by the laws of Singapore.",
        "The Buyer shall pay each invoice within 30 days.",
        # Mentions liability, but excludes nothing.
        "Each party's liability under this Agreement is joint and several.",
    ],
)
def test_does_not_fire_on_clauses_that_exclude_nothing(text):
    assert ucta.validate(clause(text)) is None


def test_never_asserts_a_conclusion():
    flags = [
        ucta.validate(clause("The Supplier excludes liability for death or personal injury.")),
        ucta.validate(clause("All implied warranties of satisfactory quality are excluded.")),
    ]
    for flag in flags:
        assert flag.requires_human_review is True
        prose = f"{flag.trigger} {flag.review_required} {' '.join(flag.factors)}".lower()
        for conclusion in ("is void", "likely void", "unenforceable", "is invalid", "will fail"):
            assert conclusion not in prose


def test_the_flag_quotes_the_wording_that_set_it_off_and_keeps_the_clause_intact():
    text = "The Supplier shall not be liable for personal injury of any kind."
    flag = ucta.validate(clause(text))
    assert flag.excerpt == text  # unmodified
    assert "shall not be liable" in flag.trigger
    assert flag.source.clause == "Clause 9.2"
    assert flag.location.page == 9


def test_flag_ids_are_stable_across_runs():
    text = "All implied terms as to satisfactory quality are excluded."
    assert ucta.validate(clause(text)).flag_id == ucta.validate(clause(text)).flag_id


def test_flag_ids_differ_between_clauses():
    a = ucta.validate(clause("All implied terms as to satisfactory quality are excluded."))
    b = ucta.validate(clause("All implied terms as to fitness for purpose are excluded."))
    assert a.flag_id != b.flag_id
