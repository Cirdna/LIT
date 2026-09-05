"""Pydantic models for the Stage 4 enriched 41-CUAD dataset JSON schema."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Location(BaseModel):
    page: int
    bbox_1000: list[float] = Field(min_length=4, max_length=4)


class Source(BaseModel):
    page: int
    clause: str
    exact_supporting_text: str


class ReviewFlag(BaseModel):
    flagged: bool
    reason: str


class CuadExtraction(BaseModel):
    vlm_text: str
    ocr_verified_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    is_verified: bool
    location: Location
    source: Source
    evidence_status: str  # "direct" | "derived"
    review_flag: ReviewFlag


class DocumentMetadata(BaseModel):
    source_file: str
    processed_pdf: str
    total_pages: int


class ContractAnalysis(BaseModel):
    document_metadata: DocumentMetadata
    cuad_extractions: dict[str, list[CuadExtraction]]

    def to_json_dict(self) -> dict:
        return self.model_dump(mode="json")
