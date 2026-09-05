import pytest
from pydantic import ValidationError

from pdf_analyzer.schema import (
    AnswerStatus,
    CategoryFinding,
    ContractAnalysis,
    CuadExtraction,
    DocumentMetadata,
    EntityLink,
    EvidenceStatus,
    Location,
    OcrVerification,
    ResolutionMethod,
    ReviewFlag,
    Source,
)


def _sample_extraction(**overrides):
    defaults = dict(
        vlm_text="Governed by the laws of the State of Delaware.",
        location=Location(page=13, bbox_1000=[167, 110, 801, 119]),
        source=Source(
            page=13,
            clause="13.5 Governing Law",
            exact_supporting_text=(
                "This Agreement shall be governed by the laws of the State of Delaware, "
                "its rules of conflict of laws notwithstanding."
            ),
        ),
        ocr_verification=OcrVerification(
            ocr_text="This Agreement shall be governed by the laws of the State of Delaware",
            score=100.0,
            recall=100.0,
            evidence_mass=13.69,
            is_grounded=True,
        ),
    )
    defaults.update(overrides)
    return CuadExtraction(**defaults)


def _finding(**overrides):
    defaults = dict(
        answer=AnswerStatus.PRESENT,
        summary="Delaware",
        evidence_status=EvidenceStatus.DIRECT,
        review_flag=ReviewFlag(flagged=False, reason=""),
        extractions=[_sample_extraction()],
    )
    defaults.update(overrides)
    return CategoryFinding(**defaults)


def test_full_document_round_trips_through_json():
    analysis = ContractAnalysis(
        contract_id="armstrong-ip",
        document_metadata=DocumentMetadata(
            source_file="original_contract.pdf",
            processed_pdf="standardized_contract.pdf",
            total_pages=40,
        ),
        cuad_findings={"governing_law": _finding()},
    )
    payload = analysis.to_json_dict()
    assert payload["document_metadata"]["total_pages"] == 40
    assert payload["cuad_findings"]["governing_law"]["answer"] == "present"
    assert payload["cuad_findings"]["governing_law"]["evidence_status"] == "direct"

    reloaded = ContractAnalysis.model_validate(payload)
    assert reloaded == analysis


def test_absent_is_distinct_from_unresolved():
    """A reasoned 'no clause exists' and 'we could not determine' are
    different answers and must not collapse into one another."""
    absent = _finding(
        answer=AnswerStatus.ABSENT,
        summary="No",
        evidence_status=EvidenceStatus.DERIVED,
        extractions=[],
    )
    unresolved = _finding(
        answer=AnswerStatus.UNRESOLVED,
        summary="",
        evidence_status=EvidenceStatus.UNRESOLVED,
        extractions=[],
    )
    assert absent.answer != unresolved.answer
    assert absent.evidence_status != unresolved.evidence_status


def test_ocr_verification_is_separate_from_evidence_status():
    """OCR grounding is a pixel-level check; evidence_status is a legal
    judgement. A finding can be grounded yet still analytically inferred."""
    finding = _finding(evidence_status=EvidenceStatus.INFERRED)
    assert finding.extractions[0].ocr_verification.is_grounded
    assert finding.evidence_status is EvidenceStatus.INFERRED


def test_entity_link_tiers_follow_resolution_method():
    high = EntityLink.build("p1", "Acme Inc.", ResolutionMethod.REGISTRATION_NUMBER)
    medium = EntityLink.build("p1", "Acme Incorporated", ResolutionMethod.FUZZY_NAME)
    low = EntityLink.build("p1", "Acme Corp", ResolutionMethod.LLM_SUGGESTED)
    abstain = EntityLink.build(None, "Acme Industrial Ltd", ResolutionMethod.UNRESOLVED)

    assert not high.requires_human_review
    assert medium.requires_human_review
    assert low.requires_human_review
    assert abstain.canonical_id is None and abstain.requires_human_review


def test_bbox_must_have_exactly_four_values():
    with pytest.raises(ValidationError):
        Location(page=1, bbox_1000=[1, 2, 3])


def test_ocr_score_is_bounded():
    with pytest.raises(ValidationError):
        OcrVerification(ocr_text="x", score=150.0, recall=10.0, evidence_mass=1.0, is_grounded=True)
