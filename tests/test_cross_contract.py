"""Cross-contract conflict engine — synthetic fixtures (no network, no LLM)."""

from pdf_analyzer.cross_contract import ContractDoc, analyze


def _finding(present=True, quote="", clause="X", page=1, grounded=True, status="direct"):
    exts = []
    if quote:
        exts.append({
            "vlm_text": quote,
            "location": {"page": page, "bbox_1000": [0, 0, 0, 0]},
            "source": {"page": page, "clause": clause, "exact_supporting_text": quote},
            "ocr_verification": {"score": 95.0, "recall": 100.0, "evidence_mass": 5.0, "is_grounded": grounded},
        })
    return {
        "answer": "present" if present else "absent",
        "summary": quote[:60],
        "evidence_status": status,
        "review_flag": {"flagged": False, "reason": ""},
        "extractions": exts,
    }


def _contract(cid, findings, **kw):
    d = {"contract_id": cid, "document_metadata": {"source_file": cid, "total_pages": 5}, "cuad_findings": findings, **kw}
    return ContractDoc.from_dict(d, cid)


def _types(report):
    return " | ".join(c["type"] for c in report["conflicts"])


def test_exclusivity_double_grant_flagged_critical():
    a = _contract("A", {
        "parties": _finding(quote="Acme Corp and Buyer One", clause="Preamble"),
        "exclusivity": _finding(quote="exclusive rights to distribute the Widget Trademarks in Singapore", clause="4.1"),
    })
    b = _contract("B", {
        "parties": _finding(quote="Acme Corp and Buyer Two", clause="Preamble"),
        "exclusivity": _finding(quote="exclusive license to the Widget Trademarks worldwide", clause="2.3"),
    })
    report = analyze([a, b])
    hit = [c for c in report["conflicts"] if "Double-Grant" in c["type"]]
    assert hit, _types(report)
    assert hit[0]["severity"] == "Critical"
    assert hit[0]["confidence"] == "High"  # both direct + grounded, asset-based (not inferred)
    assert len(hit[0]["evidence"]) == 2  # two traceable citations


def test_ip_ownership_vs_license_conflict():
    a = _contract("A", {
        "parties": _finding(quote="Acme Corp and Delta LLC"),
        "ip_ownership_assignment": _finding(quote="all IP in the Foo Platform shall be the property of Acme", clause="7.1"),
    })
    b = _contract("B", {
        "parties": _finding(quote="Acme Corp and Echo Ltd"),
        "license_grant": _finding(quote="hereby grants a license to the Foo Platform", clause="3.2"),
    })
    report = analyze([a, b])
    assert any("IP Ownership" in c["type"] for c in report["conflicts"]), _types(report)


def test_no_conflict_without_shared_entity_or_asset():
    a = _contract("A", {
        "parties": _finding(quote="Acme Corp and Delta LLC"),
        "exclusivity": _finding(quote="exclusive rights to the Alpha Marks"),
    })
    b = _contract("B", {
        "parties": _finding(quote="Zeta Inc and Omega LLC"),
        "exclusivity": _finding(quote="exclusive rights to the Beta Marks"),
    })
    report = analyze([a, b])
    assert report["conflicts"] == [], _types(report)


def test_governing_law_conflict_is_administrative():
    a = _contract("A", {
        "parties": _finding(quote="Acme Corp and Delta LLC"),
        "governing_law": _finding(quote="governed by the laws of the State of Delaware", clause="15.1"),
    })
    b = _contract("B", {
        "parties": _finding(quote="Acme Corp and Echo Ltd"),
        "governing_law": _finding(quote="governed by the laws of Singapore", clause="20"),
    })
    report = analyze([a, b])
    hit = [c for c in report["conflicts"] if "Governing Law" in c["type"]]
    assert hit, _types(report)
    assert hit[0]["severity"] == "Administrative"


def test_requires_two_citations():
    # B's exclusivity is 'present' but carries NO extraction → cannot cite → not reported.
    a = _contract("A", {
        "parties": _finding(quote="Acme Corp and Delta LLC"),
        "exclusivity": _finding(quote="exclusive rights to the Widget Trademarks", clause="4.1"),
    })
    b = _contract("B", {
        "parties": _finding(quote="Acme Corp and Echo Ltd"),
        "exclusivity": _finding(present=True, quote=""),  # present but unquoted
    })
    report = analyze([a, b])
    assert not any("Double-Grant" in c["type"] for c in report["conflicts"]), _types(report)


def test_unresolved_downgrades_confidence():
    a = _contract("A", {
        "parties": _finding(quote="Acme Corp and Delta LLC"),
        "exclusivity": _finding(quote="exclusive rights to the Widget Trademarks", clause="4.1", status="unresolved", grounded=False),
    })
    b = _contract("B", {
        "parties": _finding(quote="Acme Corp and Echo Ltd"),
        "exclusivity": _finding(quote="exclusive license to the Widget Trademarks", clause="2.3"),
    })
    report = analyze([a, b])
    hit = [c for c in report["conflicts"] if "Double-Grant" in c["type"]]
    assert hit and hit[0]["confidence"] == "Low", _types(report)
