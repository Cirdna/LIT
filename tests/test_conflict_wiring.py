"""Proof that conflict.py is reachable from real pipeline output.

test_conflict.py builds `ContractAnalysis` objects by hand, so it proved the
rules were correct but not that anything ever calls them. This file runs the
actual pipeline over two documents (real Stage 1 render + real Stage 2a text
extraction; the VLM stands in, as it does in test_pipeline_integration.py),
then hands the resulting analyses to `pipeline.scan_for_conflicts`.

What it therefore covers: join keys are populated from extracted text, exact
names group across two documents, near-miss names do not, and the party-based
MFN rule fires deterministically on pipeline output.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from pdf_analyzer import pipeline as pipeline_mod
from pdf_analyzer.schema import (
    ConflictPass,
    DetectionProvenance,
    ResolutionMethod,
    RestrictiveClauseType,
)
from pdf_analyzer.stage2_vlm import VlmBackend, VlmClauseExtraction, VlmPageResult

# Quoted identically in both contracts, so the exact-name key matches.
SHARED_PARTIES = "Meridian Retail Pte Ltd and Acme Distribution Corp"
MFN_TEXT = "Supplier shall offer Buyer terms no less favourable than any other customer."
PRICING_TEXT = "The unit price shall be S$80, a twenty percent discount on list price."


def _make_pdf(path: Path, *lines: str) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    y = 100
    for line in lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 40
    doc.save(path)
    doc.close()
    return path


class ScriptedVlm(VlmBackend):
    """Returns the extractions a real VLM would report for these pages."""

    def __init__(self, items: list[tuple[str, str, str]]) -> None:
        self.items = items

    def extract_page(self, image_path: Path, page_number: int) -> VlmPageResult:
        if page_number != 1:
            return VlmPageResult(page_number=page_number, extractions=[])
        return VlmPageResult(
            page_number=page_number,
            extractions=[
                VlmClauseExtraction(cuad_class=cls, vlm_text=text, clause_label=label)
                for cls, text, label in self.items
            ],
        )


def _analyze(tmp_path: Path, name: str, lines: list[str], items: list[tuple[str, str, str]]):
    pdf = _make_pdf(tmp_path / f"{name}.pdf", *lines)
    return pipeline_mod.analyze_document(
        input_path=pdf,
        work_dir=tmp_path / f"{name}.work",
        vlm_backend=ScriptedVlm(items),
        contract_id=name,
    )


@pytest.fixture
def mfn_holder(tmp_path):
    return _analyze(
        tmp_path,
        "msa-2024",
        [SHARED_PARTIES, MFN_TEXT],
        [
            ("parties", SHARED_PARTIES, "Preamble"),
            ("most_favored_nation", MFN_TEXT, "Clause 5.1"),
        ],
    )


@pytest.fixture
def pricing_contract(tmp_path):
    return _analyze(
        tmp_path,
        "sow-2026",
        [SHARED_PARTIES, PRICING_TEXT],
        [
            ("parties", SHARED_PARTIES, "Preamble"),
            ("price_restrictions", PRICING_TEXT, "Clause 2.3"),
        ],
    )


def test_pipeline_populates_counterparties_by_exact_name(mfn_holder):
    """These were `[]` before, which made every conflict pass a no-op."""
    links = mfn_holder.counterparties
    assert [link.raw_value for link in links] == [
        "Meridian Retail Pte Ltd",
        "Acme Distribution Corp",
    ]
    for link in links:
        assert link.resolution_method is ResolutionMethod.EXACT_NAME
        assert link.canonical_id is not None
        assert "page 1" in link.evidence


def test_pipeline_populates_comparable_clauses(mfn_holder):
    clauses = mfn_holder.structured_clauses
    assert len(clauses) == 1
    clause = clauses[0]
    assert clause.clause_type is RestrictiveClauseType.MFN
    assert clause.source.clause == "Clause 5.1"
    assert clause.ocr_verification is not None and clause.ocr_verification.is_grounded


def test_ungrounded_extraction_does_not_become_a_join_key(tmp_path):
    """A party name Stage 3 could not find on the page must not group anything:
    a join key built from unverifiable text is how a phantom conflict starts."""
    analysis = _analyze(
        tmp_path,
        "ghost",
        ["A wholly unrelated page of text about insurance obligations."],
        [("parties", "Hallucinated Holdings Ltd and Phantom Corp", "Preamble")],
    )
    assert analysis.cuad_findings["parties"].extractions  # the VLM did report one
    assert not analysis.cuad_findings["parties"].extractions[0].ocr_verification.is_grounded
    assert analysis.counterparties == []


def test_scan_for_conflicts_flags_mfn_trigger_from_pipeline_output(mfn_holder, pricing_contract):
    """The end of the wire: real analyses in, deterministic conflict out."""
    queue = pipeline_mod.scan_for_conflicts([mfn_holder, pricing_contract])

    assert queue.contracts_examined == ["msa-2024", "sow-2026"]
    assert queue.party_pass_groups == 2  # both names shared across the pair
    assert queue.conflicts, "no conflict detected from real pipeline output"

    for conflict in queue.conflicts:
        assert conflict.conflict_class == "mfn_trigger"
        assert conflict.detected_by is ConflictPass.PARTY_BASED
        assert conflict.provenance is DetectionProvenance.DETERMINISTIC
        assert conflict.requires_human_review
        assert {conflict.left.contract_id, conflict.right.contract_id} == {"msa-2024", "sow-2026"}
        assert "S$80" in conflict.right.excerpt or "S$80" in conflict.left.excerpt


def test_near_miss_party_names_do_not_group(tmp_path):
    """Exact-name resolution only. Two similar names must stay unmerged, so the
    pair produces no conflict rather than an invented one."""
    a = _analyze(
        tmp_path,
        "msa-a",
        ["Acme Industries Pte Ltd", MFN_TEXT],
        [
            ("parties", "Acme Industries Pte Ltd", "Preamble"),
            ("most_favored_nation", MFN_TEXT, "Clause 5.1"),
        ],
    )
    b = _analyze(
        tmp_path,
        "msa-b",
        ["Acme Industrial Ltd", PRICING_TEXT],
        [
            ("parties", "Acme Industrial Ltd", "Preamble"),
            ("price_restrictions", PRICING_TEXT, "Clause 2.3"),
        ],
    )

    keys_a = {link.canonical_id for link in a.counterparties}
    keys_b = {link.canonical_id for link in b.counterparties}
    assert keys_a and keys_b and keys_a.isdisjoint(keys_b)
    assert pipeline_mod.scan_for_conflicts([a, b]).conflicts == []


def test_asset_pass_stays_inert_until_scope_resolution_exists(tmp_path):
    """Documents the known limit: exclusivity is extracted and comparable, but
    `asset_based_pass` matches on canonical asset IDs, which nothing assigns."""
    exclusivity = "Distributor is granted exclusive rights to distribute the Products in Singapore."
    a = _analyze(
        tmp_path, "dist-a", [SHARED_PARTIES, exclusivity],
        [("parties", SHARED_PARTIES, "Preamble"), ("exclusivity", exclusivity, "Clause 4.1")],
    )
    b = _analyze(
        tmp_path, "dist-b", [SHARED_PARTIES, exclusivity],
        [("parties", SHARED_PARTIES, "Preamble"), ("exclusivity", exclusivity, "Clause 2.3")],
    )

    assert a.structured_clauses[0].is_exclusive
    assert a.structured_clauses[0].scope == []
    assert a.assets == []
    queue = pipeline_mod.scan_for_conflicts([a, b])
    assert queue.asset_pass_groups == 0
    assert [c for c in queue.conflicts if c.detected_by is ConflictPass.ASSET_BASED] == []
