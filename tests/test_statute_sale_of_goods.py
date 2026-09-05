"""Sale of Goods Act module, in isolation (Role A)."""

from __future__ import annotations

from pdf_analyzer.statutes import sale_of_goods


def test_supplies_the_implied_terms_a_reader_would_not_find_in_the_contract():
    quality = sale_of_goods.default_value("satisfactory_quality")
    assert quality is not None
    assert quality.citation == "s.14(2)"
    assert quality.statute.startswith("Sale of Goods Act 1979")
    assert quality.jurisdiction == "Singapore"
    assert "satisfactory quality" in quality.effect


def test_unknown_topics_return_none_rather_than_an_empty_default():
    # A default that exists but says nothing would read as "the law is silent",
    # which is a different and wrong statement.
    assert sale_of_goods.default_value("liability_cap") is None
    assert sale_of_goods.default_value("") is None


def test_defaults_start_undisplaced():
    for name in sale_of_goods.field_names():
        default = sale_of_goods.default_value(name)
        assert default.is_displaced is False
        assert default.displaced_by is None


def test_statutory_wording_is_never_fabricated():
    # The paraphrase is the deliverable; verbatim text stays absent until it
    # comes from an authoritative source.
    for name in sale_of_goods.field_names():
        default = sale_of_goods.default_value(name)
        assert default.verbatim_text is None
        assert default.effect.strip()


def test_every_default_states_its_precondition():
    # Applying a sale-of-goods implied term to a services agreement would be
    # wrong, and the pipeline does not classify contract type, so the condition
    # has to travel with the default.
    for name in sale_of_goods.field_names():
        default = sale_of_goods.default_value(name)
        assert "sale of goods" in default.applies_when


def test_business_seller_conditions_are_marked_as_such():
    # ss.14(2) and 14(3) only bite on a seller selling in the course of a
    # business; ss.12/13 do not carry that limit.
    assert "course of a business" in sale_of_goods.default_value("satisfactory_quality").applies_when
    assert (
        "course of a business"
        in sale_of_goods.default_value("fitness_for_particular_purpose").applies_when
    )
    assert "course of a business" not in sale_of_goods.default_value("title").applies_when


def test_title_default_records_that_it_cannot_be_excluded():
    # The cross-reference matters: s.6(1) UCTA makes s.12 unexcludable, which is
    # what turns a title exclusion into a hard flag rather than a review item.
    title = sale_of_goods.default_value("title")
    assert "cannot be excluded" in title.effect
    assert "s.6(1)" in title.effect


def test_displacement_mappings_are_not_loose():
    # Every declared category must plausibly address the topic. A default that
    # is wrongly displaced silently removes a correct statement of the law, which
    # is worse than one that admits it could not be checked.
    payment = sale_of_goods.default_value("time_of_payment")
    assert payment.displaced_by_categories == []
    assert payment.auto_displacement_supported is False


def test_displacement_is_only_claimed_where_a_category_can_show_it():
    quality = sale_of_goods.default_value("satisfactory_quality")
    assert quality.auto_displacement_supported is True
    assert "warranty_duration" in quality.displaced_by_categories

    # No extracted category corresponds to a title warranty, so the module says
    # so rather than implying the contract is silent.
    title = sale_of_goods.default_value("title")
    assert title.auto_displacement_supported is False
    assert title.displaced_by_categories == []
