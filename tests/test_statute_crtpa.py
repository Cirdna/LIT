"""Contracts (Rights of Third Parties) Act module, in isolation (Role A)."""

from __future__ import annotations

from pdf_analyzer import statutes
from pdf_analyzer.schema import Source
from pdf_analyzer.statutes import crtpa


def test_supplies_the_third_party_enforcement_default():
    default = crtpa.default_value("third_party_enforcement")
    assert default is not None
    assert default.citation == "s.2(1)"
    # Both limbs matter: an express right, and a term that merely purports to
    # confer a benefit.
    assert "expressly provides" in default.effect
    assert "purports to confer a benefit" in default.effect
    # And the construction escape, or the default overstates the position.
    assert "s.2(2)" in default.effect


def test_identification_requirement_travels_with_the_default():
    default = crtpa.default_value("third_party_enforcement")
    assert "expressly identified" in default.applies_when


def test_variation_default_names_the_contracting_out_route():
    default = crtpa.default_value("variation_without_third_party_consent")
    assert "unless the contract provides otherwise" in default.effect
    assert default.citation == "s.3(1)"
    # Only a third-party clause can displace it: an anti-assignment clause is a
    # different subject, and matching it would be a false displacement.
    assert default.displaced_by_categories == ["third_party_beneficiary"]


def test_displacement_is_detectable_for_this_statute():
    # Unlike most Role A topics, CUAD extracts third-party beneficiary clauses,
    # so an express clause can actually be seen to displace the default.
    default = crtpa.default_value("third_party_enforcement")
    assert default.auto_displacement_supported is True
    assert "third_party_beneficiary" in default.displaced_by_categories


def test_an_express_clause_displaces_the_default_and_cites_it():
    defaults = statutes.prefill_defaults(["third_party_enforcement"])
    clause = Source(
        page=4,
        clause="Clause 18.2",
        exact_supporting_text="No third party may enforce this Agreement.",
    )

    after = statutes.mark_displaced(defaults, {"third_party_beneficiary": clause})

    displaced = after["third_party_enforcement"]
    assert displaced.is_displaced is True
    assert displaced.displaced_by.clause == "Clause 18.2"
    # The statutory position is still recorded, not deleted: a reader needs to
    # know what the clause displaced.
    assert "purports to confer a benefit" in displaced.effect


def test_silence_in_the_extraction_does_not_displace_anything():
    defaults = statutes.prefill_defaults(["third_party_enforcement"])
    after = statutes.mark_displaced(defaults, {})
    assert after["third_party_enforcement"].is_displaced is False
