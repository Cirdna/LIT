"""Proof that the statute layer is reachable from real pipeline output.

The per-statute tests call the modules directly, so they prove the legal content
is right but not that anything invokes it. This file runs the actual pipeline
over a document (real Stage 1 render, real Stage 2a text extraction, VLM stood
in as elsewhere) and checks that the resulting ContractAnalysis carries:

  * Role A — statutory defaults, supplied before extraction, with the ones the
    contract dealt with itself marked displaced and the rest left standing;
  * Role B — flags raised from the extracted clause text, with the clause left
    exactly as extracted.

It also pins the two properties that keep the layer honest: ungrounded text
raises no flags, and the whole thing survives a JSON round-trip so the webapp
can read it.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from pdf_analyzer import pipeline as pipeline_mod
from pdf_analyzer.schema import ContractAnalysis
from pdf_analyzer.stage2_vlm import VlmBackend, VlmClauseExtraction, VlmPageResult

# Two clauses that between them exercise both roles. The exclusion is what Role B
# reads; the third-party clause is what displaces a Role A default.
EXCLUSION_TEXT = (
    "The Supplier excludes all terms implied by statute as to satisfactory quality "
    "and fitness for purpose."
)
THIRD_PARTY_TEXT = "No person other than a party may enforce any term of this Agreement."
PARTIES_TEXT = "Meridian Retail Pte Ltd and Acme Distribution Corp"


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
    def __init__(self, items):
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


def _analyze(tmp_path: Path, name: str, lines, items):
    pdf = _make_pdf(tmp_path / f"{name}.pdf", *lines)
    return pipeline_mod.analyze_document(
        input_path=pdf,
        work_dir=tmp_path / f"{name}.work",
        vlm_backend=ScriptedVlm(items),
        contract_id=name,
    )


@pytest.fixture
def analysis(tmp_path):
    return _analyze(
        tmp_path,
        "supply-2026",
        [PARTIES_TEXT, EXCLUSION_TEXT, THIRD_PARTY_TEXT],
        [
            ("parties", PARTIES_TEXT, "Preamble"),
            ("warranty_duration", EXCLUSION_TEXT, "Clause 8.1"),
            ("third_party_beneficiary", THIRD_PARTY_TEXT, "Clause 18.2"),
        ],
    )


# --- Role A ----------------------------------------------------------------


def test_analysis_carries_statutory_defaults(analysis):
    assert analysis.statutory_defaults
    assert "satisfactory_quality" in analysis.statutory_defaults
    assert "third_party_enforcement" in analysis.statutory_defaults


def test_defaults_are_kept_out_of_the_extracted_findings(analysis):
    # The separation is the safeguard: statute wording must never be able to
    # render as a quotation from the document.
    for finding in analysis.cuad_findings.values():
        for extraction in finding.extractions:
            assert "taken to promise" not in extraction.vlm_text


def test_an_express_clause_displaces_the_default_and_cites_the_clause(analysis):
    third_party = analysis.statutory_defaults["third_party_enforcement"]
    assert third_party.is_displaced is True
    assert third_party.displaced_by is not None
    assert third_party.displaced_by.clause == "Clause 18.2"


def test_untouched_topics_keep_their_default_standing(analysis):
    # Nothing in this contract addresses title, and no extraction category could
    # show it either way, so the default stays and says so.
    title = analysis.statutory_defaults["title"]
    assert title.is_displaced is False
    assert title.auto_displacement_supported is False


# --- Role B ----------------------------------------------------------------


def test_analysis_carries_flags_raised_from_the_extracted_text(analysis):
    citations = {(f.raised_by, f.citation) for f in analysis.flags}
    assert ("statutes.ucta", "s.6") in citations


def test_the_flag_points_back_at_the_clause_it_came_from(analysis):
    flag = next(f for f in analysis.flags if f.raised_by == "statutes.ucta")
    assert flag.field_name == "warranty_duration"
    assert flag.excerpt == EXCLUSION_TEXT
    assert flag.source.clause == "Clause 8.1"
    assert flag.source.page == 1


def test_flags_never_modify_the_extracted_field(analysis):
    extraction = analysis.cuad_findings["warranty_duration"].extractions[0]
    assert extraction.vlm_text == EXCLUSION_TEXT


def test_every_flag_requires_human_review(analysis):
    assert analysis.flags
    assert all(f.requires_human_review for f in analysis.flags)


def test_ungrounded_text_raises_no_flags(tmp_path):
    # The VLM reports an exclusion that is not on the page. Stage 3 cannot ground
    # it, so no statutory warning may be attached to it — a legal alarm about a
    # sentence that may not exist in the contract is worse than none.
    analysis = _analyze(
        tmp_path,
        "hallucinated",
        [PARTIES_TEXT, "The Supplier shall deliver the Goods to the Buyer."],
        [
            ("parties", PARTIES_TEXT, "Preamble"),
            ("warranty_duration", EXCLUSION_TEXT, "Clause 8.1"),
        ],
    )
    ungrounded = analysis.cuad_findings["warranty_duration"].extractions[0]
    assert ungrounded.ocr_verification.is_grounded is False
    assert analysis.flags == []


def test_an_ungrounded_clause_does_not_displace_a_default(tmp_path):
    analysis = _analyze(
        tmp_path,
        "hallucinated-third-party",
        [PARTIES_TEXT, "The Supplier shall deliver the Goods to the Buyer."],
        [
            ("parties", PARTIES_TEXT, "Preamble"),
            ("third_party_beneficiary", THIRD_PARTY_TEXT, "Clause 18.2"),
        ],
    )
    assert analysis.statutory_defaults["third_party_enforcement"].is_displaced is False


# --- the record the webapp reads -------------------------------------------


def test_the_statute_layer_survives_a_json_round_trip(analysis):
    restored = ContractAnalysis.model_validate_json(analysis.model_dump_json())
    assert restored.statutory_defaults.keys() == analysis.statutory_defaults.keys()
    assert [f.flag_id for f in restored.flags] == [f.flag_id for f in analysis.flags]
    assert restored.statutory_defaults["third_party_enforcement"].is_displaced is True


def test_conflict_join_keys_are_unaffected(analysis):
    # Fix 2 must keep working: the statute layer is additive.
    assert [c.raw_value for c in analysis.counterparties]
    assert analysis.contract_id == "supply-2026"
