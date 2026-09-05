import pytest
from pydantic import ValidationError

from pdf_analyzer.schema import (
    ContractAnalysis,
    CuadExtraction,
    DocumentMetadata,
    Location,
    ReviewFlag,
    Source,
)


def _sample_extraction(**overrides):
    defaults = dict(
        vlm_text="Governed by the laws of California.",
        ocr_verified_text="This Agreement shall be governed by the laws of California.",
        confidence=0.96,
        is_verified=True,
        location=Location(page=11, bbox_1000=[105, 450, 850, 490]),
        source=Source(
            page=11,
            clause="Section 14.2 Governing Law",
            exact_supporting_text="This Agreement shall be governed by and construed in accordance with the laws of the State of California.",
        ),
        evidence_status="direct",
        review_flag=ReviewFlag(flagged=False, reason="High confidence match."),
    )
    defaults.update(overrides)
    return CuadExtraction(**defaults)


def test_full_document_round_trips_through_json():
    analysis = ContractAnalysis(
        document_metadata=DocumentMetadata(
            source_file="original_contract.docx",
            processed_pdf="standardized_contract.pdf",
            total_pages=12,
        ),
        cuad_extractions={"governing_law": [_sample_extraction()]},
    )
    payload = analysis.to_json_dict()
    assert payload["document_metadata"]["total_pages"] == 12
    assert payload["cuad_extractions"]["governing_law"][0]["is_verified"] is True

    # Round-trips back into the model without loss.
    reloaded = ContractAnalysis.model_validate(payload)
    assert reloaded == analysis


def test_confidence_must_be_within_unit_interval():
    with pytest.raises(ValidationError):
        _sample_extraction(confidence=1.5)


def test_bbox_must_have_exactly_four_values():
    with pytest.raises(ValidationError):
        Location(page=1, bbox_1000=[1, 2, 3])
