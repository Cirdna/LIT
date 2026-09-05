"""Cross-contract conflict detection.

Two grouping passes, run independently rather than as one merged
comparison. They catch different things and a single "compare everything to
everything" sweep either misses one class or does not scale:

  party-based -- same counterparty across contracts, terms that contradict
                 once combined (an MFN silently triggered by a later deal,
                 cumulative commitments breaching a ceiling elsewhere).
  asset-based -- different counterparties, same underlying thing (two
                 exclusive grants over one asset in overlapping periods).

Everything in this module is deterministic. Date-range overlap and "more
than one exclusive grant on one asset" are plain logic: no model call, so no
false positives from language ambiguity, and no silent misses from a
retrieval step that quietly returned nothing. An LLM has exactly one
sanctioned role here -- deciding whether two already-paired scopes overlap
when the containment table cannot (`needs_scope_judgement`) -- and it is
never the mechanism doing the searching.

Grouping is driven by resolved join keys only. A deliberately unresolved ID
(`canonical_id is None`) groups with nothing, so abstaining on a near-miss
entity pair produces no conflict rather than a phantom one.
"""

from __future__ import annotations

import itertools
import logging
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

from .schema import (
    ConfidenceTier,
    ConflictEvidence,
    ConflictPass,
    ConflictReviewQueue,
    ContractAnalysis,
    DetectionProvenance,
    EntityLink,
    FlaggedConflict,
    RestrictiveClauseType,
    ScopeTag,
    StructuredClause,
)

logger = logging.getLogger(__name__)

RULE_ASSET_EXCLUSIVE_OVERLAP = "asset.exclusive_grant_overlap"
RULE_PARTY_MFN_TRIGGER = "party.mfn_trigger"
RULE_PARTY_CUMULATIVE_COMMITMENT = "party.cumulative_commitment_exceeds_ceiling"

_TIER_ORDER = {ConfidenceTier.HIGH: 0, ConfidenceTier.MEDIUM: 1, ConfidenceTier.LOW: 2}


def _lowest_tier(links: Iterable[EntityLink]) -> ConfidenceTier:
    tiers = [link.confidence_tier for link in links]
    if not tiers:
        return ConfidenceTier.HIGH
    return max(tiers, key=lambda t: _TIER_ORDER[t])


def _evidence(contract: ContractAnalysis, clause: StructuredClause) -> ConflictEvidence:
    return ConflictEvidence(
        contract_id=contract.contract_id,
        clause_id=clause.clause_id,
        excerpt=clause.source.exact_supporting_text,
        page=clause.source.page,
        clause=clause.source.clause,
        bbox_1000=clause.location.bbox_1000,
    )


def _is_superseded(clause: StructuredClause, contract: ContractAnalysis) -> bool:
    """An amendment changing its base contract's terms is an intended update,
    not a conflict. Without this every legitimately amended term in a deal
    family reads as a false positive."""
    return clause.amends is not None or contract.amends is not None


def _amends_same_family(a: ContractAnalysis, b: ContractAnalysis) -> bool:
    if a.contract_family is None or b.contract_family is None:
        return False
    if a.contract_family.canonical_id is None:
        return False
    if a.contract_family.canonical_id != b.contract_family.canonical_id:
        return False
    return _is_superseded_pair(a, b)


def _is_superseded_pair(a: ContractAnalysis, b: ContractAnalysis) -> bool:
    for later, earlier in ((a, b), (b, a)):
        if later.amends is not None and later.amends.contract_id == earlier.contract_id:
            return True
    return False


def _group_by_key(
    contracts: List[ContractAnalysis], key_getter
) -> Dict[str, List[Tuple[ContractAnalysis, EntityLink]]]:
    """Group contracts by a resolved canonical ID.

    Records whose ID is None are skipped entirely: an abstention must never
    become a grouping, or the near-miss entity pair it was protecting against
    turns into exactly the phantom conflict it was meant to prevent.
    """
    groups: Dict[str, List[Tuple[ContractAnalysis, EntityLink]]] = defaultdict(list)
    for contract in contracts:
        for link in key_getter(contract):
            if link is None or link.canonical_id is None:
                continue
            groups[link.canonical_id].append((contract, link))
    return groups


def needs_scope_judgement(a: ScopeTag, b: ScopeTag) -> bool:
    """True when two scopes are paired but containment can't settle overlap.

    This is the single point where a narrow LLM call is sanctioned: one
    clause pair in, one classification out. Callers that have no scope
    resolver should treat this as "route to human review" rather than
    guessing.
    """
    if a.canonical_id is not None and b.canonical_id is not None:
        return False
    return a.kind == b.kind


# --------------------------------------------------------------------------
# Pass 1: asset-based
# --------------------------------------------------------------------------


def asset_based_pass(contracts: List[ContractAnalysis]) -> List[FlaggedConflict]:
    """Flag more than one exclusive/restrictive grant active on one asset in
    the same period. Purely deterministic: shared canonical asset ID plus
    date-range overlap.
    """
    conflicts: List[FlaggedConflict] = []
    groups = _group_by_key(contracts, lambda c: c.assets)

    for asset_id, members in groups.items():
        for (contract_a, link_a), (contract_b, link_b) in itertools.combinations(members, 2):
            if contract_a.contract_id == contract_b.contract_id:
                continue
            if _amends_same_family(contract_a, contract_b):
                continue

            for clause_a in _exclusive_clauses(contract_a, asset_id):
                for clause_b in _exclusive_clauses(contract_b, asset_id):
                    if not clause_a.date_range.overlaps(clause_b.date_range):
                        continue

                    links = [link_a, link_b]
                    tier = _lowest_tier(links)
                    conflicts.append(
                        FlaggedConflict(
                            conflict_id=f"asset:{asset_id}:{contract_a.contract_id}:{clause_a.clause_id}"
                            f":{contract_b.contract_id}:{clause_b.clause_id}",
                            conflict_class="overlapping_exclusive_grant",
                            detected_by=ConflictPass.ASSET_BASED,
                            provenance=DetectionProvenance.DETERMINISTIC,
                            rule_id=RULE_ASSET_EXCLUSIVE_OVERLAP,
                            left=_evidence(contract_a, clause_a),
                            right=_evidence(contract_b, clause_b),
                            relationship_ids=links,
                            lowest_confidence_tier=tier,
                            requires_human_review=True,
                            explanation=(
                                f"Two exclusive grants cover asset '{asset_id}' with overlapping "
                                f"periods ({clause_a.date_range.raw_text or 'unspecified'} vs "
                                f"{clause_b.date_range.raw_text or 'unspecified'})."
                            ),
                        )
                    )
    return conflicts


def _exclusive_clauses(contract: ContractAnalysis, asset_id: str) -> List[StructuredClause]:
    out = []
    for clause in contract.structured_clauses:
        if not clause.is_exclusive:
            continue
        if _is_superseded(clause, contract):
            continue
        if any(tag.canonical_id == asset_id for tag in clause.scope):
            out.append(clause)
    return out


# --------------------------------------------------------------------------
# Pass 2: party-based
# --------------------------------------------------------------------------


def party_based_pass(contracts: List[ContractAnalysis]) -> List[FlaggedConflict]:
    """Flag obligations that contradict once combined for one counterparty.

    Two deterministic rules: an MFN in one contract sitting alongside pricing
    or revenue-sharing terms agreed with the same counterparty over an
    overlapping period, and cumulative minimum commitments exceeding a volume
    ceiling agreed elsewhere with that counterparty.
    """
    conflicts: List[FlaggedConflict] = []
    groups = _group_by_key(contracts, lambda c: c.counterparties)

    for party_id, members in groups.items():
        conflicts.extend(_mfn_trigger_rule(party_id, members))
        conflicts.extend(_cumulative_commitment_rule(party_id, members))
    return conflicts


_PRICING_TYPES = {
    RestrictiveClauseType.PRICE_RESTRICTIONS,
    RestrictiveClauseType.REVENUE_SHARING,
}


def _mfn_trigger_rule(party_id, members) -> List[FlaggedConflict]:
    out = []
    for (contract_a, link_a), (contract_b, link_b) in itertools.combinations(members, 2):
        if contract_a.contract_id == contract_b.contract_id:
            continue
        if _amends_same_family(contract_a, contract_b):
            continue

        for holder, other, link_h, link_o in (
            (contract_a, contract_b, link_a, link_b),
            (contract_b, contract_a, link_b, link_a),
        ):
            mfns = [
                c
                for c in holder.structured_clauses
                if c.clause_type is RestrictiveClauseType.MFN and not _is_superseded(c, holder)
            ]
            pricing = [
                c
                for c in other.structured_clauses
                if c.clause_type in _PRICING_TYPES and not _is_superseded(c, other)
            ]
            for mfn in mfns:
                for price in pricing:
                    if not mfn.date_range.overlaps(price.date_range):
                        continue
                    links = [link_h, link_o]
                    out.append(
                        FlaggedConflict(
                            conflict_id=f"party:{party_id}:mfn:{holder.contract_id}:{mfn.clause_id}"
                            f":{other.contract_id}:{price.clause_id}",
                            conflict_class="mfn_trigger",
                            detected_by=ConflictPass.PARTY_BASED,
                            provenance=DetectionProvenance.DETERMINISTIC,
                            rule_id=RULE_PARTY_MFN_TRIGGER,
                            left=_evidence(holder, mfn),
                            right=_evidence(other, price),
                            relationship_ids=links,
                            lowest_confidence_tier=_lowest_tier(links),
                            requires_human_review=True,
                            explanation=(
                                f"Counterparty '{party_id}' holds an MFN in "
                                f"{holder.contract_id} while pricing terms were agreed in "
                                f"{other.contract_id} over an overlapping period; the MFN may "
                                "be triggered."
                            ),
                        )
                    )
    return out


def _cumulative_commitment_rule(party_id, members) -> List[FlaggedConflict]:
    """Sum minimum commitments for one counterparty and compare against any
    volume ceiling agreed with them elsewhere. Comparison only runs on
    matching units, so unit mismatches abstain instead of guessing."""
    out = []
    commitments = [
        (contract, link, clause)
        for contract, link in members
        for clause in contract.structured_clauses
        if clause.clause_type is RestrictiveClauseType.MINIMUM_COMMITMENT
        and clause.quantity is not None
        and not _is_superseded(clause, contract)
    ]
    ceilings = [
        (contract, link, clause)
        for contract, link in members
        for clause in contract.structured_clauses
        if clause.clause_type is RestrictiveClauseType.VOLUME_RESTRICTION
        and clause.quantity is not None
        and not _is_superseded(clause, contract)
    ]

    for ceil_contract, ceil_link, ceiling in ceilings:
        unit = ceiling.quantity.unit
        relevant = [
            (c, l, cl)
            for c, l, cl in commitments
            if cl.quantity.unit == unit
            and c.contract_id != ceil_contract.contract_id
            and cl.date_range.overlaps(ceiling.date_range)
        ]
        total = sum(cl.quantity.value for _, _, cl in relevant)
        if not relevant or total <= ceiling.quantity.value:
            continue

        # Report against the largest contributor so the pair is concrete.
        contrib_contract, contrib_link, contrib_clause = max(
            relevant, key=lambda r: r[2].quantity.value
        )
        links = [ceil_link, contrib_link]
        out.append(
            FlaggedConflict(
                conflict_id=f"party:{party_id}:commitment:{ceil_contract.contract_id}"
                f":{ceiling.clause_id}",
                conflict_class="cumulative_commitment_exceeds_ceiling",
                detected_by=ConflictPass.PARTY_BASED,
                provenance=DetectionProvenance.DETERMINISTIC,
                rule_id=RULE_PARTY_CUMULATIVE_COMMITMENT,
                left=_evidence(ceil_contract, ceiling),
                right=_evidence(contrib_contract, contrib_clause),
                relationship_ids=links,
                lowest_confidence_tier=_lowest_tier(links),
                requires_human_review=True,
                explanation=(
                    f"Cumulative minimum commitments for '{party_id}' total {total:g} {unit} "
                    f"across {len(relevant)} contract(s), exceeding the {ceiling.quantity.value:g} "
                    f"{unit} ceiling in {ceil_contract.contract_id}."
                ),
            )
        )
    return out


# --------------------------------------------------------------------------
# Queue assembly
# --------------------------------------------------------------------------


def build_review_queue(contracts: List[ContractAnalysis]) -> ConflictReviewQueue:
    """Run both passes independently and return the merged review queue.

    The passes are run separately and their results tagged, rather than
    folded into one comparison, so it stays visible which pass caught what.
    """
    party = party_based_pass(contracts)
    asset = asset_based_pass(contracts)
    logger.info(
        "conflict scan: %d contracts, %d party-based, %d asset-based",
        len(contracts),
        len(party),
        len(asset),
    )
    return ConflictReviewQueue(
        conflicts=party + asset,
        contracts_examined=[c.contract_id for c in contracts],
        party_pass_groups=len(_group_by_key(contracts, lambda c: c.counterparties)),
        asset_pass_groups=len(_group_by_key(contracts, lambda c: c.assets)),
    )
