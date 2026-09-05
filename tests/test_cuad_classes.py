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


def test_descriptions_and_triggers_cover_all_classes():
    from pdf_analyzer.cuad_classes import CUAD_DESCRIPTIONS, CUAD_TRIGGER_PHRASES

    assert set(CUAD_DESCRIPTIONS) == set(CUAD_CLASSES)
    assert set(CUAD_TRIGGER_PHRASES) == set(CUAD_CLASSES)


def test_covenant_not_to_sue_keeps_the_unrelated_matters_qualifier():
    """Regression: the hand-written definition this replaced said only "or on
    bringing claims against them", dropping CUAD's qualifier "for matters
    unrelated to the contract". That omission matched a routine
    service-interruption liability waiver in the Chase affiliate agreement --
    a claim arising squarely under the contract, which the real scope
    excludes. The qualifier is what makes the category narrow enough to be
    useful, so it must survive any future edit.
    """
    from pdf_analyzer.cuad_classes import CUAD_DESCRIPTIONS

    assert "for matters unrelated to the contract" in CUAD_DESCRIPTIONS["covenant_not_to_sue"]


def test_descriptions_are_cuads_own_wording_not_a_paraphrase():
    """Spot-check verbatim fidelity to category_descriptions.csv. These are
    the questions CUAD's expert annotators actually answered; a paraphrase
    silently changes what the pipeline is measuring."""
    from pdf_analyzer.cuad_classes import CUAD_DESCRIPTIONS

    assert CUAD_DESCRIPTIONS["document_name"] == "The name of the contract"
    assert CUAD_DESCRIPTIONS["parties"] == "The two or more parties who signed the contract"
    assert (
        CUAD_DESCRIPTIONS["governing_law"]
        == "Which state/country's law governs the interpretation of the contract?"
    )
    # Official scope includes "whether during the contract or after the
    # contract ends", which distinguishes a real no-solicit from a passing
    # mention -- and names employees/contractors specifically, which is what
    # separates it from No-Solicit of Customers.
    assert "employees and/or contractors" in CUAD_DESCRIPTIONS["no_solicit_of_employees"]


def test_category_definition_composes_scope_then_wording():
    from pdf_analyzer.cuad_classes import CUAD_DESCRIPTIONS, category_definition

    text = category_definition("non_disparagement")
    assert text.startswith(CUAD_DESCRIPTIONS["non_disparagement"])
    assert "Wording to look for:" in text
    # The empirically-earned half: real contracts say "tarnish", not "disparage".
    assert "tarnish" in text
