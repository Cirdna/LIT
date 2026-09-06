from pdf_analyzer.cuad_classes import CUAD_CLASSES


def test_exactly_41_classes():
    assert len(CUAD_CLASSES) == 41


def test_keys_are_snake_case_and_unique():
    assert len(set(CUAD_CLASSES.keys())) == len(CUAD_CLASSES)
    for key in CUAD_CLASSES:
        assert key == key.lower()
        assert " " not in key


def test_known_categories_present():
    for expected in ["governing_law", "cap_on_liability", "parties", "document_name", "non_compete"]:
        assert expected in CUAD_CLASSES


def test_classifiers_cover_all_classes():
    from pdf_analyzer.cuad_classes import CUAD_CLASSIFIERS

    assert set(CUAD_CLASSIFIERS) == set(CUAD_CLASSES)


def test_classifiers_are_element_based_strict_rules():
    """The definitions were replaced with strict, element-based classifiers.
    Each states what QUALIFIES and what does NOT, so the model classifies on
    operative legal effect rather than keywords."""
    from pdf_analyzer.cuad_classes import CUAD_CLASSIFIERS

    for key, text in CUAD_CLASSIFIERS.items():
        assert "DOES NOT QUALIFY" in text, f"{key} classifier missing a DOES NOT QUALIFY section"


def test_universal_and_group_rules_present():
    from pdf_analyzer.cuad_classes import GROUP_DISAMBIGUATION_RULES, STRICT_CLASSIFICATION_RULES

    # The load-bearing universal rule: operative effect, not keywords.
    assert "operative legal effect" in STRICT_CLASSIFICATION_RULES
    assert "Do NOT classify based merely on" in STRICT_CLASSIFICATION_RULES
    # Group disambiguation keeps the most-confused categories apart.
    assert "NON-COMPETE" in GROUP_DISAMBIGUATION_RULES
    assert "EXCLUSIVITY" in GROUP_DISAMBIGUATION_RULES


def test_non_compete_classifier_requires_operative_restraint():
    """Regression against the classic false positive: a definition of
    'Competitor' or a competitor list is NOT a non-compete."""
    from pdf_analyzer.cuad_classes import CUAD_CLASSIFIERS

    text = CUAD_CLASSIFIERS["non_compete"]
    assert "operative" in text.lower()
    assert 'A definition of "Competitor"' in text


def test_covenant_not_to_sue_targets_validity_challenge():
    """The category is chiefly an IP non-challenge covenant, not an ordinary
    forum/limitation clause."""
    from pdf_analyzer.cuad_classes import CUAD_CLASSIFIERS

    text = CUAD_CLASSIFIERS["covenant_not_to_sue"]
    assert "validity" in text
    assert "Arbitration or forum-selection clauses" in text  # explicitly excluded


def test_category_definition_returns_the_strict_classifier():
    from pdf_analyzer.cuad_classes import CUAD_CLASSIFIERS, category_definition

    assert category_definition("non_disparagement") == CUAD_CLASSIFIERS["non_disparagement"]
