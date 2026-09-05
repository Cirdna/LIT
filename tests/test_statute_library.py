"""The statute chunk library, and the gate that stops unverified quotation.

The gate is the point of the whole design, so it is tested from both directions:
that it refuses unverified wording, and that nothing in the store is currently
verified (because no human has done Phase 2 yet — a test that quietly passed once
someone marked a chunk verified without checking it would be worthless).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from pdf_analyzer.statutes.library import (
    AuthorityBasis,
    Provenance,
    RoleType,
    StatuteChunk,
    UnverifiedQuotationError,
    VerificationStatus,
    eligible_for_contract_type,
    keyword_hits,
    load_file,
    load_store,
    select,
    verification_worklist,
)
from pdf_analyzer.statutes.library.loader import CHUNKS_DIR


def _provenance() -> Provenance:
    return Provenance(
        retrieved_from="https://sso.agc.gov.sg/Act/UCTA1977",
        retrieved_at="2026-09-06",
        revised_edition="2020 Rev Ed",
    )


def _chunk(**overrides) -> StatuteChunk:
    base = dict(
        id="test_chunk",
        source="Unfair Contract Terms Act 1977 (2020 Rev Ed)",
        provision="Section 2(2)",
        draft_wording="In the case of other loss or damage, a person cannot so exclude...",
        summary="Negligence liability for other loss can only be excluded if reasonable.",
        role_type=RoleType.ROLE_B_VALIDATOR,
        target_fields=("liability_cap",),
        trigger_keywords=("negligence", "exclude"),
        verification_status=VerificationStatus.UNVERIFIED_DRAFT,
        provenance=_provenance(),
        applicable_contract_types=("services",),
        applicability_conditions=("the clause excludes liability for negligence",),
    )
    base.update(overrides)
    return StatuteChunk(**base)  # type: ignore[arg-type]


# ---- the gate ---------------------------------------------------------------


def test_unverified_wording_cannot_be_quoted():
    chunk = _chunk()
    with pytest.raises(UnverifiedQuotationError) as err:
        chunk.quotable_wording()
    # The error has to tell a developer what to do, not just say no.
    assert "unverified_draft" in str(err.value)
    assert "sso.agc.gov.sg" in str(err.value)


def test_verified_wording_can_be_quoted():
    chunk = _chunk(
        verification_status=VerificationStatus.VERIFIED,
        verified_as_at="2026-09-06",
        verified_by="manual_legal_review",
    )
    assert chunk.quotable_wording().startswith("In the case of other loss")


def test_gate_does_not_fall_back_to_the_summary():
    """A fallback would let unverified text reach a user under another label."""
    chunk = _chunk()
    with pytest.raises(UnverifiedQuotationError):
        chunk.quotable_wording()
    # The paraphrase remains freely available — it just is not a quotation.
    assert chunk.summary


def test_verified_chunk_must_carry_a_stamp():
    with pytest.raises(ValueError, match="verified_as_at"):
        _chunk(verification_status=VerificationStatus.VERIFIED).validate()


def test_unverified_chunk_must_not_carry_a_stamp():
    with pytest.raises(ValueError, match="must not carry a verification stamp"):
        _chunk(verified_by="manual_legal_review").validate()


# ---- provenance: wording must come from the source, never from recall -------


def test_model_recall_provenance_is_rejected():
    """The failure this whole scheme exists to prevent."""
    bad = replace(_provenance(), transcription="model_recall")
    with pytest.raises(ValueError, match="recalled"):
        _chunk(provenance=bad).validate()


def test_provenance_must_point_at_sso():
    bad = replace(_provenance(), retrieved_from="https://en.wikipedia.org/wiki/UCTA")
    with pytest.raises(ValueError, match="Statutes Online"):
        _chunk(provenance=bad).validate()


# ---- v2.1 gating requirements ----------------------------------------------


def test_chunk_without_declared_contract_types_is_rejected():
    with pytest.raises(ValueError, match="applicable_contract_types"):
        _chunk(applicable_contract_types=()).validate()


def test_role_b_validator_must_state_applicability_conditions():
    """Firing on field presence alone is the defect v2.1 3 names."""
    with pytest.raises(ValueError, match="applicability_conditions"):
        _chunk(applicability_conditions=()).validate()


def test_case_law_gloss_must_name_its_authority():
    with pytest.raises(ValueError, match="supporting_authority"):
        _chunk(authority_basis=AuthorityBasis.CASE_LAW_GLOSS).validate()


def test_unclassified_document_gets_no_statutory_overlay():
    """The SOGA-on-an-NDA fix: None is not a permissive default."""
    chunk = _chunk(applicable_contract_types=("sale_of_goods",))
    assert eligible_for_contract_type(chunk, None) is False
    assert eligible_for_contract_type(chunk, "nda") is False
    assert eligible_for_contract_type(chunk, "sale_of_goods") is True


def test_all_commercial_matches_any_named_type():
    chunk = _chunk(applicable_contract_types=("all_commercial",))
    assert eligible_for_contract_type(chunk, "distribution") is True
    assert eligible_for_contract_type(chunk, None) is False


def test_select_filters_by_type_role_and_field():
    a = _chunk(id="a", applicable_contract_types=("services",))
    b = _chunk(
        id="b",
        role_type=RoleType.ROLE_A_DEFAULT,
        applicable_contract_types=("sale_of_goods",),
        target_fields=("satisfactory_quality",),
        applicability_conditions=(),
    )
    assert [c.id for c in select([a, b], contract_type="services")] == ["a"]
    assert [c.id for c in select([a, b], contract_type="sale_of_goods")] == ["b"]
    assert (
        select([a, b], contract_type="sale_of_goods", field_name="liability_cap") == []
    )
    assert select([a, b], contract_type="services", verified_only=True) == []


def test_keyword_hits_is_case_insensitive_and_partial():
    chunk = _chunk(trigger_keywords=("negligence", "gross negligence"))
    assert keyword_hits(chunk, "Excludes liability for NEGLIGENCE.") == [
        "negligence"
    ]
    assert keyword_hits(chunk, "no relevant words here") == []


# ---- the shipped store ------------------------------------------------------


def test_store_loads_and_every_chunk_validates():
    store = load_store()
    assert len(store) >= 15, "the brief targets 15-40 provision-level chunks"
    assert len(store) <= 40


def test_every_shipped_chunk_is_still_an_unverified_draft():
    """Phase 2 has not happened. If this fails, someone flipped a status.

    That is allowed — but only with a character-for-character check against SSO,
    which means this test should be updated in the same commit as the evidence.
    """
    store = load_store()
    assert store.verified == [], (
        "chunks marked verified: "
        f"{[c.id for c in store.verified]} — confirm the wording was actually checked"
    )
    assert len(store.unverified) == len(store)


def test_no_shipped_chunk_can_be_quoted_yet():
    for chunk in load_store():
        with pytest.raises(UnverifiedQuotationError):
            chunk.quotable_wording()


def test_all_six_scoped_acts_are_represented():
    sources = set(load_store().by_source())
    for expected in (
        "Sale of Goods Act 1979 (2020 Rev Ed)",
        "Supply of Goods Act 1982 (2020 Rev Ed)",
        "Unfair Contract Terms Act 1977 (2020 Rev Ed)",
        "Contracts (Rights of Third Parties) Act 2001 (2020 Rev Ed)",
        "Misrepresentation Act 1967 (2020 Rev Ed)",
        "Frustrated Contracts Act 1959 (2020 Rev Ed)",
    ):
        assert expected in sources, f"missing chunks for {expected}"


def test_no_chunk_cites_a_cap_number_as_its_current_source():
    """Cap numbers are the superseded 1994/1999/2002 editions.

    They are kept in `legacy_citation` for cross-reference, but the `source` a
    citation is built from must be the current Revised Edition title.
    """
    for chunk in load_store():
        assert "Cap " not in chunk.source, f"{chunk.id} cites a Cap number as current"
        assert "Rev Ed" in chunk.source, f"{chunk.id} does not name a Revised Edition"


def test_supply_of_goods_chunks_never_fire_on_services_or_hire_purchase():
    """The Act covers transfer and hire of goods only.

    Singapore did not adopt the UK services provisions, and s.1(2)(b) makes
    hire-purchase an excepted contract. Letting these fire on a services contract
    would be the SOGA-on-an-NDA failure one layer deeper.
    """
    store = load_store()
    supply = store.by_source()["Supply of Goods Act 1982 (2020 Rev Ed)"]
    assert supply, "expected Supply of Goods chunks"
    for chunk in supply:
        assert "services" not in chunk.applicable_contract_types, chunk.id
        assert "hire_purchase" not in chunk.applicable_contract_types, chunk.id
        assert eligible_for_contract_type(chunk, "services") is False


def test_supply_of_goods_transfer_citations_match_the_act():
    """Guards the off-by-one this library was built to catch.

    statutes/supply_of_goods.py cites the transfer set as s.3/s.4/s.5/s.6. The Act
    puts title at s.2, description at s.3, quality and fitness at s.4, sample at
    s.5. These assertions pin the correct mapping so a future edit cannot quietly
    reintroduce the drift.
    """
    store = load_store()
    expected = {
        "sg_sga1982_s2_1": ("Section 2(1)", "title_to_goods"),
        "sg_sga1982_s3_2": ("Section 3(2)", "conformity_with_description"),
        "sg_sga1982_s4_2": ("Section 4(2)", "satisfactory_quality"),
        "sg_sga1982_s4_5": ("Section 4(5)", "fitness_for_purpose"),
        "sg_sga1982_s5_2": ("Section 5(2)", "sale_by_sample"),
    }
    for chunk_id, (provision, field_name) in expected.items():
        chunk = store.get(chunk_id)
        assert chunk.provision == provision
        assert field_name in chunk.target_fields


def test_misrepresentation_non_reliance_chunk_is_flagged_as_case_law_gloss():
    """The bare section does not say non-reliance clauses are caught by s.3."""
    chunk = load_store().get("sg_misrep_s3_nonreliance")
    assert chunk.authority_basis is AuthorityBasis.CASE_LAW_GLOSS
    assert chunk.supporting_authority
    # The authority is a known gap; it must be visibly unresolved rather than a
    # plausible-looking invented case name.
    assert "UNRESOLVED" in chunk.supporting_authority


def test_stitched_chunks_say_so_in_their_note():
    """Reassembled sub-paragraphs are the likeliest place wording drifted."""
    store = load_store()
    for chunk_id in (
        "sg_ucta_s11_4",
        "sg_soga_s14_3",
        "sg_soga_s15_2",
        "sg_sga1982_s5_2",
        "sg_misrep_s3",
        "sg_crtpa_s2_1",
        "sg_fca_s3_5",
    ):
        note = store.get(chunk_id).note or ""
        assert "STITCHED" in note, f"{chunk_id} was reassembled but does not say so"


def test_worklist_covers_every_unverified_chunk():
    store = load_store()
    rows = verification_worklist(store)
    assert len(rows) == len(store.unverified)
    assert all(r["url"].startswith("https://sso.agc.gov.sg/") for r in rows)


def test_coverage_reports_zero_verified():
    coverage = load_store().coverage()
    assert coverage
    assert all(v["verified"] == 0 for v in coverage.values())
    assert all(v["total"] > 0 for v in coverage.values())


# ---- loader robustness ------------------------------------------------------


def test_duplicate_ids_are_rejected(tmp_path: Path):
    entry = StatuteChunk.to_dict(_chunk())
    path = tmp_path / "dupes.json"
    path.write_text(json.dumps({"chunks": [entry, entry]}), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate chunk id"):
        load_store(tmp_path)


def test_round_trip_through_dict_preserves_the_chunk(tmp_path: Path):
    original = _chunk(id="rt", note="STITCHED test", legacy_citation="Cap 396")
    path = tmp_path / "rt.json"
    path.write_text(json.dumps({"chunks": [original.to_dict()]}), encoding="utf-8")
    (loaded,) = load_file(path)
    assert loaded == original


def test_readme_keys_in_shipped_files_do_not_become_chunks():
    """The `_readme` prose in each file is documentation, not data."""
    for path in sorted(CHUNKS_DIR.rglob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert "_readme" in raw, f"{path.name} should explain itself"
        assert isinstance(raw["chunks"], list)
        assert all("_readme" not in c for c in raw["chunks"])
