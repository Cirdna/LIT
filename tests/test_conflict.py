"""Cross-contract conflict detection, tested against the judging scenario:
one planted asset-based conflict, one planted party-based conflict, and a
near-miss entity pair that must NOT be merged.
"""

from datetime import date

import pytest

from pdf_analyzer.conflict import (
    RULE_ASSET_EXCLUSIVE_OVERLAP,
    RULE_PARTY_CUMULATIVE_COMMITMENT,
    RULE_PARTY_MFN_TRIGGER,
    asset_based_pass,
    build_review_queue,
    party_based_pass,
)
from pdf_analyzer.schema import (
    ClauseQuantity,
    ClauseRef,
    ConfidenceTier,
    ConflictPass,
    ContractAnalysis,
    DateRange,
    DetectionProvenance,
    DocumentMetadata,
    EntityLink,
    Location,
    ResolutionMethod,
    RestrictiveClauseType,
    ScopeKind,
    ScopeTag,
    Source,
    StructuredClause,
)


def _clause(
    clause_id,
    clause_type,
    *,
    exclusive=False,
    asset=None,
    start=None,
    end=None,
    perpetual=False,
    quantity=None,
    page=1,
    text="...",
    amends=None,
):
    return StructuredClause(
        clause_id=clause_id,
        clause_type=clause_type,
        is_exclusive=exclusive,
        scope=(
            [ScopeTag(kind=ScopeKind.ASSET, canonical_id=asset, raw_value=asset or "")]
            if asset
            else []
        ),
        date_range=DateRange(start=start, end=end, is_perpetual=perpetual, raw_text=f"{start}..{end}"),
        quantity=quantity,
        source=Source(page=page, clause=clause_id, exact_supporting_text=text),
        location=Location(page=page, bbox_1000=[10, 20, 300, 40]),
        amends=amends,
    )


def _contract(cid, *, counterparties=(), assets=(), clauses=(), family=None, amends=None):
    return ContractAnalysis(
        contract_id=cid,
        document_metadata=DocumentMetadata(
            source_file=f"{cid}.pdf", processed_pdf=f"{cid}.pdf", total_pages=1
        ),
        counterparties=list(counterparties),
        assets=list(assets),
        contract_family=family,
        amends=amends,
        structured_clauses=list(clauses),
    )


def _link(cid, raw, method=ResolutionMethod.REGISTRATION_NUMBER):
    return EntityLink.build(cid, raw, method)


# --------------------------------------------------------------------------
# Planted asset-based conflict: the rental case
# --------------------------------------------------------------------------


def test_asset_pass_flags_two_exclusive_grants_on_one_asset():
    """Two leases for the same room to different tenants over overlapping
    periods. Each contract is individually valid; the conflict exists only in
    the relationship between them."""
    room = _link("asset:room-3b", "Room 3B", ResolutionMethod.EXACT_NAME)
    a = _contract(
        "lease-A",
        counterparties=[_link("party:tenant-a", "Tenant A Pte Ltd")],
        assets=[room],
        clauses=[
            _clause("2.1", RestrictiveClauseType.EXCLUSIVITY, exclusive=True,
                    asset="asset:room-3b", start=date(2026, 1, 1), end=date(2026, 12, 31),
                    text="exclusive use of Room 3B")
        ],
    )
    b = _contract(
        "lease-B",
        counterparties=[_link("party:tenant-b", "Tenant B Pte Ltd")],
        assets=[room],
        clauses=[
            _clause("3.4", RestrictiveClauseType.EXCLUSIVITY, exclusive=True,
                    asset="asset:room-3b", start=date(2026, 6, 1), end=date(2027, 5, 31),
                    text="sole and exclusive occupancy of Room 3B")
        ],
    )

    conflicts = asset_based_pass([a, b])

    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.conflict_class == "overlapping_exclusive_grant"
    assert c.detected_by is ConflictPass.ASSET_BASED
    # Must-have: a deterministic rule fires with no LLM call.
    assert c.provenance is DetectionProvenance.DETERMINISTIC
    assert c.rule_id == RULE_ASSET_EXCLUSIVE_OVERLAP
    # Must-have: both source excerpts, anchored.
    assert c.left.excerpt and c.right.excerpt
    assert c.left.page == 1 and c.right.page == 1
    assert len(c.left.bbox_1000) == 4


def test_asset_pass_ignores_non_overlapping_periods():
    room = _link("asset:room-3b", "Room 3B", ResolutionMethod.EXACT_NAME)
    a = _contract("lease-A", assets=[room], clauses=[
        _clause("2.1", RestrictiveClauseType.EXCLUSIVITY, exclusive=True, asset="asset:room-3b",
                start=date(2026, 1, 1), end=date(2026, 5, 31))])
    b = _contract("lease-B", assets=[room], clauses=[
        _clause("3.4", RestrictiveClauseType.EXCLUSIVITY, exclusive=True, asset="asset:room-3b",
                start=date(2026, 6, 1), end=date(2026, 12, 31))])

    assert asset_based_pass([a, b]) == []


# --------------------------------------------------------------------------
# Near-miss entity pair: must abstain, not merge
# --------------------------------------------------------------------------


def test_near_miss_entities_are_not_merged_and_produce_no_conflict():
    """Two genuinely different companies with similar names. Abstaining
    (canonical_id=None) must group with nothing -- merging them would invent
    a conflict, which the spec scores as worse than a flagged gap."""
    abstained_1 = EntityLink.build(None, "Acme Industries Pte Ltd", ResolutionMethod.UNRESOLVED,
                                   "name similar to Acme Industrial Ltd; no registration match")
    abstained_2 = EntityLink.build(None, "Acme Industrial Ltd", ResolutionMethod.UNRESOLVED,
                                   "name similar to Acme Industries Pte Ltd; no registration match")

    a = _contract("msa-1", counterparties=[abstained_1], clauses=[
        _clause("5.1", RestrictiveClauseType.MFN, start=date(2026, 1, 1), end=date(2027, 1, 1))])
    b = _contract("msa-2", counterparties=[abstained_2], clauses=[
        _clause("7.2", RestrictiveClauseType.PRICE_RESTRICTIONS,
                start=date(2026, 3, 1), end=date(2027, 1, 1))])

    assert party_based_pass([a, b]) == []
    queue = build_review_queue([a, b])
    assert queue.conflicts == []
    assert queue.party_pass_groups == 0  # nothing grouped at all


def test_low_confidence_id_still_routes_to_human_review():
    """An LLM-suggested match may surface a candidate, but it must never
    read as high-confidence justification on its own."""
    guess = EntityLink.build("party:maybe", "Acme Corp", ResolutionMethod.LLM_SUGGESTED)
    assert guess.confidence_tier is ConfidenceTier.LOW
    assert guess.requires_human_review

    a = _contract("msa-1", counterparties=[guess], clauses=[
        _clause("5.1", RestrictiveClauseType.MFN, start=date(2026, 1, 1), end=date(2027, 1, 1))])
    b = _contract("msa-2", counterparties=[guess], clauses=[
        _clause("7.2", RestrictiveClauseType.PRICE_RESTRICTIONS,
                start=date(2026, 3, 1), end=date(2027, 1, 1))])

    conflicts = party_based_pass([a, b])
    assert len(conflicts) == 1
    assert conflicts[0].lowest_confidence_tier is ConfidenceTier.LOW
    assert conflicts[0].requires_human_review


# --------------------------------------------------------------------------
# Planted party-based conflict: MFN trigger
# --------------------------------------------------------------------------


def test_party_pass_flags_mfn_trigger():
    acme = _link("party:acme", "Acme Inc.")
    old = _contract("msa-2024", counterparties=[acme], clauses=[
        _clause("5.1", RestrictiveClauseType.MFN, start=date(2024, 1, 1), perpetual=True,
                text="Supplier shall offer Buyer terms no less favourable than any other customer")])
    new = _contract("sow-2026", counterparties=[acme], clauses=[
        _clause("2.3", RestrictiveClauseType.PRICE_RESTRICTIONS,
                start=date(2026, 1, 1), end=date(2027, 1, 1),
                text="unit price of S$80, a 20% discount on list")])

    conflicts = party_based_pass([old, new])

    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.conflict_class == "mfn_trigger"
    assert c.detected_by is ConflictPass.PARTY_BASED
    assert c.provenance is DetectionProvenance.DETERMINISTIC
    assert c.rule_id == RULE_PARTY_MFN_TRIGGER
    assert "S$80" in c.right.excerpt or "S$80" in c.left.excerpt


def test_party_pass_flags_cumulative_commitment_breach():
    acme = _link("party:acme", "Acme Inc.")
    ceiling = _contract("frame-agreement", counterparties=[acme], clauses=[
        _clause("9.1", RestrictiveClauseType.VOLUME_RESTRICTION,
                start=date(2026, 1, 1), end=date(2026, 12, 31),
                quantity=ClauseQuantity(value=1000, unit="units", period="per_year"),
                text="Buyer shall not order more than 1,000 units per year")])
    c1 = _contract("po-1", counterparties=[acme], clauses=[
        _clause("1.1", RestrictiveClauseType.MINIMUM_COMMITMENT,
                start=date(2026, 1, 1), end=date(2026, 12, 31),
                quantity=ClauseQuantity(value=700, unit="units", period="per_year"),
                text="minimum 700 units")])
    c2 = _contract("po-2", counterparties=[acme], clauses=[
        _clause("1.1", RestrictiveClauseType.MINIMUM_COMMITMENT,
                start=date(2026, 1, 1), end=date(2026, 12, 31),
                quantity=ClauseQuantity(value=500, unit="units", period="per_year"),
                text="minimum 500 units")])

    conflicts = party_based_pass([ceiling, c1, c2])

    assert len(conflicts) == 1
    assert conflicts[0].rule_id == RULE_PARTY_CUMULATIVE_COMMITMENT
    assert "1200" in conflicts[0].explanation.replace(",", "")


def test_cumulative_rule_abstains_on_mismatched_units():
    """Summing across incompatible units would be a confident wrong answer."""
    acme = _link("party:acme", "Acme Inc.")
    ceiling = _contract("frame", counterparties=[acme], clauses=[
        _clause("9.1", RestrictiveClauseType.VOLUME_RESTRICTION,
                start=date(2026, 1, 1), end=date(2026, 12, 31),
                quantity=ClauseQuantity(value=1000, unit="units"))])
    spend = _contract("po-1", counterparties=[acme], clauses=[
        _clause("1.1", RestrictiveClauseType.MINIMUM_COMMITMENT,
                start=date(2026, 1, 1), end=date(2026, 12, 31),
                quantity=ClauseQuantity(value=99999, unit="SGD"))])

    assert party_based_pass([ceiling, spend]) == []


# --------------------------------------------------------------------------
# Supersession
# --------------------------------------------------------------------------


def test_amendment_does_not_read_as_a_conflict():
    """An amendment changing its base MSA's exclusive grant is an intended
    update. Without supersession handling every amended term in a family
    reads as a false positive."""
    family = EntityLink.build("family:acme-msa", "Acme MSA family", ResolutionMethod.EXACT_NAME)
    room = _link("asset:room-3b", "Room 3B", ResolutionMethod.EXACT_NAME)

    base = _contract("msa", assets=[room], family=family, clauses=[
        _clause("2.1", RestrictiveClauseType.EXCLUSIVITY, exclusive=True, asset="asset:room-3b",
                start=date(2026, 1, 1), end=date(2026, 12, 31))])
    amendment = _contract(
        "msa-amd-1", assets=[room], family=family,
        amends=ClauseRef(contract_id="msa", clause_id="2.1", effect="supersedes"),
        clauses=[
            _clause("2.1", RestrictiveClauseType.EXCLUSIVITY, exclusive=True, asset="asset:room-3b",
                    start=date(2026, 6, 1), end=date(2027, 6, 30),
                    amends=ClauseRef(contract_id="msa", clause_id="2.1", effect="supersedes"))],
    )

    assert asset_based_pass([base, amendment]) == []


# --------------------------------------------------------------------------
# Queue assembly: both passes run independently
# --------------------------------------------------------------------------


def test_both_passes_run_independently_and_are_distinguishable():
    room = _link("asset:room-3b", "Room 3B", ResolutionMethod.EXACT_NAME)
    acme = _link("party:acme", "Acme Inc.")

    lease_a = _contract("lease-A", counterparties=[_link("party:t-a", "Tenant A")], assets=[room],
        clauses=[_clause("2.1", RestrictiveClauseType.EXCLUSIVITY, exclusive=True,
                         asset="asset:room-3b", start=date(2026, 1, 1), end=date(2026, 12, 31))])
    lease_b = _contract("lease-B", counterparties=[_link("party:t-b", "Tenant B")], assets=[room],
        clauses=[_clause("3.4", RestrictiveClauseType.EXCLUSIVITY, exclusive=True,
                         asset="asset:room-3b", start=date(2026, 6, 1), end=date(2027, 5, 31))])
    msa = _contract("msa", counterparties=[acme], clauses=[
        _clause("5.1", RestrictiveClauseType.MFN, start=date(2024, 1, 1), perpetual=True)])
    sow = _contract("sow", counterparties=[acme], clauses=[
        _clause("2.3", RestrictiveClauseType.PRICE_RESTRICTIONS,
                start=date(2026, 1, 1), end=date(2027, 1, 1))])

    queue = build_review_queue([lease_a, lease_b, msa, sow])

    by_pass = {c.detected_by for c in queue.conflicts}
    assert by_pass == {ConflictPass.PARTY_BASED, ConflictPass.ASSET_BASED}
    assert len(queue.conflicts) == 2
    # Every flagged pair carries provenance and both excerpts.
    for c in queue.conflicts:
        assert c.provenance in (DetectionProvenance.DETERMINISTIC, DetectionProvenance.LLM_ASSISTED)
        assert c.left.contract_id and c.right.contract_id
        assert c.rule_id
    assert queue.asset_pass_groups == 1
    assert queue.party_pass_groups == 3  # t-a, t-b, acme
