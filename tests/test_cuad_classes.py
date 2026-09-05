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
