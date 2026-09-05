"""Supply of Goods Act module, in isolation (Role A)."""

from __future__ import annotations

from pdf_analyzer.statutes import sale_of_goods, supply_of_goods


def test_covers_transfer_and_hire_separately():
    # The two sets are not interchangeable: which applies turns on whether goods
    # are transferred or hired, and the tool does not decide that.
    transfer = supply_of_goods.default_value("transfer_quality_and_fitness")
    hire = supply_of_goods.default_value("hire_quality_and_fitness")
    assert transfer is not None and hire is not None
    assert transfer.citation == "s.5"
    assert hire.citation == "s.9"
    assert "otherwise than by a sale" in transfer.applies_when
    assert "hire" in hire.applies_when


def test_does_not_answer_for_sale_topics():
    # Sale of goods is the other Act's territory; overlapping field names would
    # make it ambiguous which statute answered.
    assert supply_of_goods.default_value("satisfactory_quality") is None
    assert set(supply_of_goods.field_names()).isdisjoint(sale_of_goods.field_names())


def test_quiet_possession_is_part_of_the_hire_title_term():
    hire_title = supply_of_goods.default_value("hire_right_to_transfer_possession")
    assert "quiet possession" in hire_title.effect


def test_all_defaults_are_paraphrased_and_conditioned():
    for name in supply_of_goods.field_names():
        default = supply_of_goods.default_value(name)
        assert default.verbatim_text is None
        assert default.applies_when.strip()
        assert default.is_displaced is False
        assert default.raised_by == "statutes.supply_of_goods"
