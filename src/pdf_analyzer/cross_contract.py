"""Cross-contract conflict resolution (cross_contract_conflict_resolution.md).

Given two or more contract-extraction JSON files (the ContractAnalysis /
`cuad_findings` shape this pipeline emits), find places where the contracts,
read together, contradict each other: a right granted twice, an obligation whose
trigger depends on a contract that may have ended, ownership assigned to two
parties, and so on.

This is deliberately deterministic — no model call in the search path (the same
discipline as conflict.py). It complements conflict.py: that engine consumes the
richer `structured_clauses`/`counterparties` the pipeline does not yet populate;
this one derives everything it needs from the `cuad_findings` that ARE populated,
so it runs on real output today.

Every reported conflict is traceable to two extracted quotes (contract + page +
clause) and carries a confidence and a severity. Candidate flags for human legal
review — not a legal determination.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations
from pathlib import Path
from typing import Any, Optional

# Categories most likely to generate cross-contract conflicts (spec §2.3).
PRIORITY_CATEGORIES = [
    "exclusivity", "most_favored_nation", "non_compete", "no_solicit_of_customers",
    "no_solicit_of_employees", "rofr_rofo_rofn", "change_of_control", "anti_assignment",
    "ip_ownership_assignment", "joint_ip_ownership", "license_grant", "non_transferable_license",
    "termination_for_convenience", "minimum_commitment", "volume_restriction", "price_restrictions",
    "revenue_profit_sharing", "cap_on_liability", "uncapped_liability", "covenant_not_to_sue",
]

_SUFFIXES = {
    "llc", "inc", "incorporated", "ltd", "limited", "corp", "corporation", "co", "company",
    "lp", "llp", "plc", "gmbh", "pte", "sa", "ag", "bv", "holdings", "group", "na",
}
_STOPWORDS = {"the", "of", "and", "a", "an", "for"}
# Role-shorthands that must NOT cluster two different entities by themselves.
_ROLE_WORDS = {
    "company", "buyer", "seller", "licensor", "licensee", "landlord", "tenant",
    "supplier", "distributor", "purchaser", "vendor", "customer", "client", "party",
    "contractor", "lessor", "lessee",
}

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MONTH_RE = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


@dataclass
class ContractDoc:
    contract_id: str
    findings: dict
    counterparties: list
    assets: list
    contract_family: Optional[str]
    amends: Optional[str]
    source_file: str

    @classmethod
    def from_dict(cls, d: dict, fallback_id: str) -> "ContractDoc":
        md = d.get("document_metadata") or {}
        cid = d.get("contract_id") or md.get("source_file") or fallback_id
        return cls(
            contract_id=cid,
            findings=d.get("cuad_findings") or {},
            counterparties=_non_na_list(d.get("counterparties")),
            assets=_non_na_list(d.get("assets")),
            contract_family=_non_na(d.get("contract_family")),
            amends=_non_na(d.get("amends")),
            source_file=md.get("source_file") or cid,
        )


def load_contracts(paths: list[str | Path]) -> list[ContractDoc]:
    out: list[ContractDoc] = []
    for p in paths:
        p = Path(p)
        data = json.loads(p.read_text())
        out.append(ContractDoc.from_dict(data, fallback_id=p.stem))
    return out


def _non_na(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return None if s.upper() == "NA" or not s else s


def _non_na_list(v: Any) -> list:
    if not isinstance(v, list):
        return []
    return [x for x in v if _non_na(x if isinstance(x, str) else json.dumps(x)) is not None]


# --------------------------------------------------------------------------
# Finding accessors + normalization
# --------------------------------------------------------------------------


def _finding(c: ContractDoc, category: str) -> dict:
    return c.findings.get(category) or {}


def is_present(c: ContractDoc, category: str) -> bool:
    return _finding(c, category).get("answer") == "present"


def is_unresolved(c: ContractDoc, category: str) -> bool:
    f = _finding(c, category)
    return f.get("answer") == "unresolved" or f.get("evidence_status") == "unresolved"


@dataclass
class Evidence:
    contract_id: str
    page: int
    clause: str
    quote: str
    is_grounded: bool
    evidence_status: str


def evidence_for(c: ContractDoc, category: str) -> Optional[Evidence]:
    """The best (prefer grounded) extraction for a category, as a citation."""
    f = _finding(c, category)
    exts = f.get("extractions") or []
    if not exts:
        return None
    exts = sorted(exts, key=lambda e: not (e.get("ocr_verification") or {}).get("is_grounded", False))
    e = exts[0]
    src = e.get("source") or {}
    loc = e.get("location") or {}
    ocr = e.get("ocr_verification") or {}
    quote = src.get("exact_supporting_text") or e.get("vlm_text") or ""
    return Evidence(
        contract_id=c.contract_id,
        page=int(src.get("page") or loc.get("page") or 0),
        clause=src.get("clause") or "—",
        quote=quote.strip()[:400],
        is_grounded=bool(ocr.get("is_grounded")),
        evidence_status=f.get("evidence_status") or "unresolved",
    )


def category_text(c: ContractDoc, category: str) -> str:
    """All quoted/summary text for a category, lowered — for keyword tests."""
    f = _finding(c, category)
    parts = [f.get("summary") or ""]
    for e in f.get("extractions") or []:
        parts.append(e.get("vlm_text") or "")
        parts.append((e.get("source") or {}).get("exact_supporting_text") or "")
    return " ".join(parts).lower()


def normalize_entity(name: str) -> str:
    name = re.sub(r"\(([^)]*)\)", " ", name)  # drop parentheticals like ("Buyer")
    name = re.sub(r"[\"“”'’]", "", name)
    toks = re.sub(r"[^\w\s]", " ", name.lower()).split()
    toks = [t for t in toks if t not in _SUFFIXES and t not in _STOPWORDS]
    return " ".join(toks)


def entities_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    ta, tb = set(a.split()), set(b.split())
    overlap = ta & tb
    if not overlap:
        return False
    # A shared token must be distinctive (not a role word) to merge two names.
    if overlap <= _ROLE_WORDS:
        return False
    # One name's tokens are contained in the other's (e.g. "Acme" ⊂ "Acme Flooring").
    return len(overlap) >= min(len(ta), len(tb))


def party_names(c: ContractDoc) -> list[str]:
    names: list[str] = []
    for e in _finding(c, "parties").get("extractions") or []:
        txt = (e.get("source") or {}).get("exact_supporting_text") or e.get("vlm_text") or ""
        # Split "X and Y" / "between X and Y".
        for part in re.split(r"\band\b|;|,\s+(?=[A-Z])", txt):
            part = part.strip()
            if 2 < len(part) < 120:
                names.append(part)
    names.extend(str(x) for x in c.counterparties)
    return names


# Candidate asset phrases: defined-term / capitalized multiword noun phrases.
_ASSET_RE = re.compile(r"\b([A-Z][A-Za-z0-9&/.-]+(?:\s+[A-Z][A-Za-z0-9&/.-]+){0,5})\b")
_ASSET_STOP = {"agreement", "section", "article", "exhibit", "schedule", "the", "this", "party", "parties"}


def asset_phrases(c: ContractDoc, category: str) -> set[str]:
    out: set[str] = set()
    f = _finding(c, category)
    for e in f.get("extractions") or []:
        txt = (e.get("source") or {}).get("exact_supporting_text") or e.get("vlm_text") or ""
        for m in _ASSET_RE.findall(txt):
            words = [w for w in m.split() if w.lower() not in _ASSET_STOP]
            if len(words) >= 2:  # multiword proper phrase
                out.add(normalize_entity(m))
    return {a for a in out if a}


def parse_date(text: str) -> Optional[date]:
    if not text:
        return None
    m = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", text)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(rf"\b{_MONTH_RE}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", text, re.I)
    if m:
        return _safe_date(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
    return None


def _safe_date(y: int, mo: int, d: int) -> Optional[date]:
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def date_window(c: ContractDoc) -> tuple[Optional[date], Optional[date]]:
    eff = parse_date(category_text(c, "effective_date")) or parse_date(category_text(c, "agreement_date"))
    exp = parse_date(category_text(c, "expiration_date"))
    return eff, exp


def windows_overlap(a: ContractDoc, b: ContractDoc) -> bool:
    """Conservative: unknown ends are treated as open, so they overlap."""
    ea, xa = date_window(a)
    eb, xb = date_window(b)
    if xa and eb and xa < eb:
        return False
    if xb and ea and xb < ea:
        return False
    return True


# --------------------------------------------------------------------------
# Registries (spec §2)
# --------------------------------------------------------------------------


@dataclass
class EntityCluster:
    entity_id: str
    aliases: set = field(default_factory=set)
    contracts: set = field(default_factory=set)


def build_entity_registry(contracts: list[ContractDoc]) -> list[EntityCluster]:
    clusters: list[EntityCluster] = []
    for c in contracts:
        for raw in party_names(c):
            norm = normalize_entity(raw)
            if not norm:
                continue
            placed = None
            for cl in clusters:
                if any(entities_match(norm, normalize_entity(a)) for a in cl.aliases):
                    placed = cl
                    break
            if placed is None:
                placed = EntityCluster(entity_id=norm)
                clusters.append(placed)
            placed.aliases.add(raw.strip())
            placed.contracts.add(c.contract_id)
    return clusters


def shared_entities(a: ContractDoc, b: ContractDoc) -> list[str]:
    na = {normalize_entity(x) for x in party_names(a)}
    nb = {normalize_entity(x) for x in party_names(b)}
    out: list[str] = []
    for x in na:
        for y in nb:
            if x and entities_match(x, y):
                out.append(x)
                break
    return out


def shared_assets(a: ContractDoc, b: ContractDoc, categories: list[str]) -> set[str]:
    sa: set[str] = set()
    sb: set[str] = set()
    for cat in categories:
        sa |= asset_phrases(a, cat)
        sb |= asset_phrases(b, cat)
    return sa & sb


def build_obligation_registry(contracts: list[ContractDoc]) -> list[dict]:
    rows: list[dict] = []
    for c in contracts:
        for cat in PRIORITY_CATEGORIES:
            if not is_present(c, cat):
                continue
            ev = evidence_for(c, cat)
            rows.append({
                "contract_id": c.contract_id, "category": cat,
                "summary": _finding(c, cat).get("summary", ""),
                "evidence": ev,
            })
    return rows


def build_dependency_graph(contracts: list[ContractDoc]) -> list[dict]:
    by_id = {c.contract_id: c for c in contracts}
    edges: list[dict] = []
    for c in contracts:
        if c.amends and c.amends in by_id:
            edges.append({"from": c.contract_id, "to": c.amends, "kind": "amends", "inferred": False})
        if c.contract_family:
            for other in contracts:
                if other is not c and other.contract_family == c.contract_family:
                    edges.append({"from": c.contract_id, "to": other.contract_id, "kind": "family", "inferred": False})
    # Inferred edges: shared entity + overlapping windows.
    for a, b in combinations(contracts, 2):
        if shared_entities(a, b) and windows_overlap(a, b):
            edges.append({"from": a.contract_id, "to": b.contract_id, "kind": "inferred", "inferred": True})
    return edges


# --------------------------------------------------------------------------
# Conflicts + scoring (spec §5)
# --------------------------------------------------------------------------


@dataclass
class Conflict:
    type: str
    severity: str
    confidence: str
    contracts_involved: list[str]
    entities_involved: list[str]
    asset_or_subject: str
    description: str
    evidence: list[Evidence]
    recommended_action: str
    conflict_id: str = ""

    def dedup_key(self) -> tuple:
        return (frozenset(self.contracts_involved), frozenset(e.quote for e in self.evidence))


def _confidence(evs: list[Evidence], *, relationship_inferred: bool, unresolved: bool) -> str:
    if unresolved or relationship_inferred:
        return "Low"
    if evs and all(e.evidence_status == "direct" and e.is_grounded for e in evs):
        return "High"
    return "Medium"


def _mk(
    type_: str, severity: str, a: ContractDoc, b: ContractDoc, ea: Optional[Evidence], eb: Optional[Evidence],
    asset: str, description: str, action: str, *, relationship_inferred: bool = False, unresolved: bool = False,
) -> Optional[Conflict]:
    if ea is None or eb is None or not ea.quote or not eb.quote:
        return None  # spec §0: need two traceable quotes
    ents = sorted(set(shared_entities(a, b)))
    return Conflict(
        type=type_, severity=severity,
        confidence=_confidence([ea, eb], relationship_inferred=relationship_inferred, unresolved=unresolved),
        contracts_involved=[a.contract_id, b.contract_id],
        entities_involved=ents or ["(shared subject matter)"],
        asset_or_subject=asset, description=description, evidence=[ea, eb], recommended_action=action,
    )


# --------------------------------------------------------------------------
# The 11 checks (spec §3)
# --------------------------------------------------------------------------

_NON_EXCLUSIVE = "non-exclusive"
_TERRITORY_TOKENS = ["worldwide", "singapore", "malaysia", "united states", "u.s.", "europe", "asia", "global"]


def check_pair(a: ContractDoc, b: ContractDoc, common_entities: frozenset[str] = frozenset()) -> list[Conflict]:
    out: list[Conflict] = []
    # Sharing the portfolio owner (a party in most contracts) is not a conflict
    # signal — exclude ubiquitous entities so only a genuinely shared counterparty
    # or asset links a pair.
    ents = [e for e in shared_entities(a, b) if not any(entities_match(e, c) for c in common_entities)]
    assets_excl = shared_assets(a, b, ["exclusivity", "license_grant", "ip_ownership_assignment", "non_transferable_license"])
    linked = bool(ents) or bool(assets_excl)
    if not linked:
        return out  # spec §4.2: only compare pairs sharing an entity or asset

    def present_both(cat_a: str, cat_b: str) -> bool:
        return is_present(a, cat_a) and is_present(b, cat_b)

    # 3.1 Exclusivity / double-grant + MFN
    a_excl = is_present(a, "exclusivity") and _NON_EXCLUSIVE not in category_text(a, "exclusivity")
    b_excl = is_present(b, "exclusivity")
    if a_excl and b_excl and windows_overlap(a, b):
        asset = ", ".join(sorted(assets_excl)) or "; ".join(ents) or "the exclusive subject matter"
        c = _mk("Exclusivity / Double-Grant Conflict", "Critical", a, b,
                evidence_for(a, "exclusivity"), evidence_for(b, "exclusivity"), asset,
                "Both contracts create exclusive dealing over overlapping subject matter with overlapping time windows — an exclusive grant in one is undercut by the other.",
                "Escalate to legal counsel before relying on either exclusivity grant.",
                relationship_inferred=not assets_excl,
                unresolved=is_unresolved(a, "exclusivity") or is_unresolved(b, "exclusivity"))
        if c:
            out.append(c)
    if is_present(a, "most_favored_nation") and (is_present(b, "price_restrictions") or is_present(b, "revenue_profit_sharing")):
        c = _mk("MFN Conflict", "Significant", a, b,
                evidence_for(a, "most_favored_nation"),
                evidence_for(b, "price_restrictions") or evidence_for(b, "revenue_profit_sharing"),
                "; ".join(ents) or "MFN subject matter",
                "An MFN promise in one contract may be breached by pricing/revenue terms granted to another party.",
                "Compare the MFN terms against the other contract's pricing before signing.")
        if c:
            out.append(c)

    # 3.2 Territorial / field-of-use overlap
    ta, tb = category_text(a, "exclusivity") + category_text(a, "license_grant"), category_text(b, "exclusivity") + category_text(b, "license_grant")
    shared_terr = [t for t in _TERRITORY_TOKENS if t in ta and t in tb]
    if shared_terr and assets_excl:
        c = _mk("Territorial / Field-of-Use Overlap", "Critical", a, b,
                evidence_for(a, "exclusivity") or evidence_for(a, "license_grant"),
                evidence_for(b, "exclusivity") or evidence_for(b, "license_grant"),
                ", ".join(sorted(assets_excl)),
                f"Both contracts grant rights over the same asset in an overlapping territory ({', '.join(shared_terr)}).",
                "Confirm the territorial carve-outs actually differ.")
        if c:
            out.append(c)

    # 3.3 Contingency / cross-reference dependency
    for cat in ("termination_for_convenience", "change_of_control", "anti_assignment"):
        txt = category_text(a, cat)
        if re.search(r"(so long as|upon termination of|subject to|conditioned on|contingent (?:up)?on).{0,60}\bagreement\b", txt):
            ea = evidence_for(a, cat)
            # cite B's expiry/termination as the dependency risk
            eb = evidence_for(b, "expiration_date") or evidence_for(b, "termination_for_convenience")
            c = _mk("Contingency / Dependency Conflict", "Significant", a, b, ea, eb,
                    "; ".join(ents) or "dependent obligation",
                    f"An obligation in {a.contract_id} is contingent on another agreement, which the related contract may terminate or let expire first.",
                    "Verify the referenced agreement's current status and end date.",
                    relationship_inferred=True)
            if c:
                out.append(c)

    # 3.4 IP ownership & license-stack
    if present_both("ip_ownership_assignment", "license_grant") or present_both("ip_ownership_assignment", "joint_ip_ownership"):
        asset = ", ".join(sorted(shared_assets(a, b, ["ip_ownership_assignment", "license_grant", "joint_ip_ownership"]))) or "; ".join(ents) or "the intellectual property"
        eb = evidence_for(b, "license_grant") or evidence_for(b, "joint_ip_ownership")
        c = _mk("IP Ownership / License-Stack Conflict", "Critical", a, b,
                evidence_for(a, "ip_ownership_assignment"), eb, asset,
                "One contract assigns ownership of IP while another treats the same IP as owned or licensable by a different party.",
                "Reconcile the chain of title before relying on either grant.",
                relationship_inferred=not shared_assets(a, b, ["ip_ownership_assignment", "license_grant", "joint_ip_ownership"]))
        if c:
            out.append(c)

    # 3.5 Party role contradiction (same entity licensee here, licensor there)
    if ents and present_both("license_grant", "license_grant") and assets_excl and not is_present(a, "non_transferable_license"):
        c = _mk("Party Role Contradiction", "Critical", a, b,
                evidence_for(a, "license_grant"), evidence_for(b, "license_grant"),
                ", ".join(sorted(assets_excl)),
                "A shared entity appears to both receive and grant rights over the same asset without a clear sublicense chain.",
                "Confirm sublicense rights exist to make both grants legitimate.",
                relationship_inferred=True)
        if c:
            out.append(c)

    # 3.6 Term / renewal / notice
    ea_eff, ea_exp = date_window(a)
    eb_eff, eb_exp = date_window(b)
    if ents and is_present(a, "renewal_term") and ea_exp and eb_exp and ea_exp > eb_exp:
        c = _mk("Term / Renewal Conflict", "Significant", a, b,
                evidence_for(a, "renewal_term"), evidence_for(b, "expiration_date"),
                "; ".join(ents),
                f"{a.contract_id} renews past {b.contract_id}'s expiration ({eb_exp.isoformat()}), which the latter may assume has ended.",
                "Align the renewal and expiration dates across the related contracts.",
                relationship_inferred=True)
        if c:
            out.append(c)

    # 3.7 Financial commitment — weak co-presence signal; require a shared asset.
    fin = ["minimum_commitment", "volume_restriction", "price_restrictions", "revenue_profit_sharing"]
    fa = [cat for cat in fin if is_present(a, cat)]
    fb = [cat for cat in fin if is_present(b, cat)]
    if assets_excl and fa and fb:
        c = _mk("Financial Commitment Conflict", "Significant", a, b,
                evidence_for(a, fa[0]), evidence_for(b, fb[0]),
                "; ".join(ents),
                "Both contracts place commitments (minimums/volumes/pricing/revenue-share) that may compete for the same resource.",
                "Check the commitments can be met simultaneously.")
        if c:
            out.append(c)

    # 3.8 Liability / indemnity / insurance — require a shared asset.
    if assets_excl and is_present(a, "cap_on_liability") and (is_present(b, "uncapped_liability") or is_present(b, "third_party_beneficiary")):
        c = _mk("Liability / Indemnity Conflict", "Significant", a, b,
                evidence_for(a, "cap_on_liability"),
                evidence_for(b, "uncapped_liability") or evidence_for(b, "third_party_beneficiary"),
                "; ".join(ents),
                "A liability cap in one contract may be inconsistent with an uncapped/flow-down indemnity assumption in a related contract.",
                "Confirm the cap and the flow-down indemnity are compatible.")
        if c:
            out.append(c)

    # 3.9 Assignment / change of control — require a shared asset.
    if assets_excl and is_present(a, "anti_assignment") and is_present(b, "change_of_control"):
        c = _mk("Assignment / Change-of-Control Conflict", "Significant", a, b,
                evidence_for(a, "anti_assignment"), evidence_for(b, "change_of_control"),
                "; ".join(ents),
                "An anti-assignment restriction in one contract may be triggered by a change-of-control/transfer contemplated in the other.",
                "Check whether the transaction needs consent under the restricting contract.")
        if c:
            out.append(c)

    # 3.10 Governing law / forum
    gla, glb = category_text(a, "governing_law"), category_text(b, "governing_law")
    if ents and gla and glb:
        law_a = _law_of(gla)
        law_b = _law_of(glb)
        if law_a and law_b and law_a != law_b:
            c = _mk("Governing Law / Forum Conflict", "Administrative", a, b,
                    evidence_for(a, "governing_law"), evidence_for(b, "governing_law"),
                    "; ".join(ents),
                    f"Related contracts specify different governing law ({law_a} vs {law_b}), which complicates joint interpretation/litigation.",
                    "Note the forum split; usually not a hard contradiction.")
            if c:
                out.append(c)

    # 3.11 Non-compete / non-solicit overlap — require a shared asset.
    for cat in ("non_compete", "no_solicit_of_customers", "no_solicit_of_employees"):
        if assets_excl and is_present(a, cat) and (is_present(b, "license_grant") or is_present(b, "exclusivity")):
            c = _mk("Non-Compete / Non-Solicit Overlap", "Significant", a, b,
                    evidence_for(a, cat), evidence_for(b, "license_grant") or evidence_for(b, "exclusivity"),
                    "; ".join(ents),
                    f"A {cat.replace('_', ' ')} restriction in one contract may forbid conduct the other contract permits or requires.",
                    "Check the restricted conduct against the other contract's grants.")
            if c:
                out.append(c)
            break

    return out


def _law_of(text: str) -> str:
    m = re.search(r"laws? of (?:the )?(?:state of )?([a-z ]+?)(?:\.|,|;| and| with|$)", text)
    return m.group(1).strip() if m else ""


# --------------------------------------------------------------------------
# Orchestration + report (spec §4, §6)
# --------------------------------------------------------------------------


def analyze(contracts: list[ContractDoc]) -> dict:
    # Registries (built once; also surfaced in the report for transparency).
    entities = build_entity_registry(contracts)
    dependency = build_dependency_graph(contracts)

    # Ubiquitous entities (e.g. the portfolio owner, a party to most contracts)
    # must not, by themselves, link two contracts into a conflict.
    n = len(contracts)
    threshold = max(3, round(0.4 * n))
    common_entities = frozenset(e.entity_id for e in entities if len(e.contracts) >= threshold)

    raw: list[Conflict] = []
    for a, b in combinations(contracts, 2):
        raw.extend(check_pair(a, b, common_entities))

    # Dedup: merge conflicts citing the same contracts + evidence, keep all types.
    merged: dict[tuple, Conflict] = {}
    for c in raw:
        key = c.dedup_key()
        if key in merged:
            existing = merged[key]
            if c.type not in existing.type:
                existing.type = f"{existing.type}; {c.type}"
            existing.severity = _max_severity(existing.severity, c.severity)
            existing.confidence = _max_confidence(existing.confidence, c.confidence)
        else:
            merged[key] = c

    conflicts = list(merged.values())
    conflicts.sort(key=lambda c: (_SEV_ORDER[c.severity], _CONF_ORDER[c.confidence]))
    for i, c in enumerate(conflicts, 1):
        c.conflict_id = f"C-{i:03d}"

    return {
        "contracts_examined": [c.contract_id for c in contracts],
        "entity_registry": [{"entity_id": e.entity_id, "aliases": sorted(e.aliases), "contracts": sorted(e.contracts)} for e in entities],
        "dependency_edges": dependency,
        "conflicts": [_conflict_json(c) for c in conflicts],
    }


_SEV_ORDER = {"Critical": 0, "Significant": 1, "Administrative": 2}
_CONF_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def _max_severity(a: str, b: str) -> str:
    return a if _SEV_ORDER[a] <= _SEV_ORDER[b] else b


def _max_confidence(a: str, b: str) -> str:
    return a if _CONF_ORDER[a] <= _CONF_ORDER[b] else b


def _conflict_json(c: Conflict) -> dict:
    return {
        "conflict_id": c.conflict_id, "type": c.type, "severity": c.severity, "confidence": c.confidence,
        "contracts_involved": c.contracts_involved, "entities_involved": c.entities_involved,
        "asset_or_subject": c.asset_or_subject, "description": c.description,
        "evidence": [{"contract_id": e.contract_id, "page": e.page, "clause": e.clause, "quote": e.quote} for e in c.evidence],
        "recommended_action": c.recommended_action,
    }


def to_markdown(report: dict) -> str:
    conflicts = report["conflicts"]
    lines = [f"# Cross-contract conflict report", "",
             f"Contracts examined: {', '.join(report['contracts_examined'])}",
             f"Conflicts found: **{len(conflicts)}**", ""]
    if conflicts:
        lines += ["| ID | Type | Severity | Confidence | Contracts |", "|---|---|---|---|---|"]
        for c in conflicts:
            lines.append(f"| {c['conflict_id']} | {c['type']} | {c['severity']} | {c['confidence']} | {', '.join(c['contracts_involved'])} |")
        lines.append("")
        for c in conflicts:
            if c["severity"] in ("Critical", "Significant"):
                lines += [f"### {c['conflict_id']} — {c['type']} ({c['severity']}/{c['confidence']})", c["description"], ""]
    else:
        lines.append("_No cross-contract conflicts detected._")
    return "\n".join(lines)
