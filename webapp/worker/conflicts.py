"""Wire the cross-contract engine into the webapp.

Reads the portfolio's extracted fields out of Postgres, adapts them into the
`ContractAnalysis`/`cuad_findings` shape `pdf_analyzer.cross_contract` expects,
runs the deterministic conflict engine, and writes the results into the webapp's
`conflicts` + `handoff_briefs` tables (source='cross_contract') so they render on
the Conflicts page. No LLM — pure analysis over data already extracted.

Only engine-produced rows are cleared/rewritten each run; stub/manual conflicts
are left alone.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg
from psycopg.types.json import Json

from pdf_analyzer.cross_contract import ContractDoc, analyze

logger = logging.getLogger("worker.conflicts")

_SEVERITY = {"Critical": "high", "Significant": "medium", "Administrative": "low"}
_TIER = {"High": "verbatim", "Medium": "assembled", "Low": "inferred"}
_CONTRACT_EXCLUDED = ("not_a_contract", "invoice")


def _evidence_status(tier: str) -> str:
    if tier in ("verbatim", "normalised"):
        return "direct"
    if tier == "unverified":
        return "unresolved"
    return "inferred"


def _load_contract_docs(conn: psycopg.Connection, workspace_id: str):
    """Return (ContractDoc list, per-doc metadata) built from the DB."""
    docs = conn.execute(
        """
        SELECT id, filename, counterparty, doc_type FROM documents
        WHERE workspace_id=%s AND status IN ('ready','degraded')
          AND (doc_type IS NULL OR doc_type NOT IN ('not_a_contract','invoice'))
        """,
        (workspace_id,),
    ).fetchall()

    contract_docs: list[ContractDoc] = []
    meta: dict[str, dict[str, Any]] = {}

    for d in docs:
        doc_id = str(d["id"])
        fields = conn.execute(
            """
            SELECT id, field_key, value_verbatim, confidence_tier, clause_label, anchor_line_ids
            FROM extracted_fields WHERE document_id=%s
            """,
            (d["id"],),
        ).fetchall()
        lines = conn.execute(
            "SELECT line_id, page_number FROM text_lines WHERE document_id=%s",
            (d["id"],),
        ).fetchall()
        page_by_line = {r["line_id"]: r["page_number"] for r in lines}

        findings: dict[str, Any] = {}
        value_to_field: dict[str, str] = {}
        for f in fields:
            present = f["value_verbatim"] is not None
            tier = f["confidence_tier"]
            page = 0
            for lid in f["anchor_line_ids"] or []:
                if lid in page_by_line:
                    page = page_by_line[lid]
                    break
            extractions = []
            if present:
                grounded = tier != "unverified"
                extractions.append({
                    "vlm_text": f["value_verbatim"],
                    "location": {"page": page, "bbox_1000": [0, 0, 0, 0]},
                    "source": {"page": page, "clause": f["clause_label"] or "—", "exact_supporting_text": f["value_verbatim"]},
                    "ocr_verification": {"score": 95.0 if grounded else 0.0, "recall": 100.0, "evidence_mass": 5.0, "is_grounded": grounded},
                })
                # Key by the same truncation the engine's evidence uses, so a
                # long clause still resolves back to its field id for the paired view.
                value_to_field[f["value_verbatim"].strip()[:400]] = str(f["id"])
            findings[f["field_key"]] = {
                "answer": "present" if present else "absent",
                "summary": (f["value_verbatim"] or "")[:80],
                "evidence_status": _evidence_status(tier),
                "review_flag": {"flagged": tier == "unverified", "reason": ""},
                "extractions": extractions,
            }

        contract_docs.append(
            ContractDoc.from_dict(
                {
                    "contract_id": doc_id,
                    "document_metadata": {"source_file": d["filename"], "total_pages": 0},
                    "counterparties": [d["counterparty"]] if d["counterparty"] else [],
                    "assets": [],
                    "contract_family": None,
                    "amends": None,
                    "cuad_findings": findings,
                },
                doc_id,
            )
        )
        meta[doc_id] = {"filename": d["filename"], "value_to_field": value_to_field}

    return contract_docs, meta


def run_conflict_detection(conn: psycopg.Connection, workspace_id: str) -> int:
    """Run the engine over the portfolio and (re)write cross_contract conflicts."""
    docs, meta = _load_contract_docs(conn, workspace_id)
    report = analyze(docs) if len(docs) >= 2 else {"conflicts": []}
    conflicts = report["conflicts"]

    with conn.transaction(), conn.cursor() as cur:
        # Only manage engine-produced rows; leave stub/manual ones intact.
        cur.execute("DELETE FROM handoff_briefs WHERE workspace_id=%s AND source='cross_contract'", (workspace_id,))
        cur.execute("DELETE FROM conflicts WHERE workspace_id=%s AND source='cross_contract'", (workspace_id,))

        for c in conflicts:
            doc_ids = c["contracts_involved"]
            tier = _TIER.get(c["confidence"], "inferred")
            severity = _SEVERITY.get(c["severity"], "medium")

            field_ids: list[str] = []
            for ev in c["evidence"]:
                fid = meta.get(ev["contract_id"], {}).get("value_to_field", {}).get(ev["quote"])
                if fid and fid not in field_ids:
                    field_ids.append(fid)

            cur.execute(
                """
                INSERT INTO conflicts
                  (workspace_id, conflict_type, severity, summary, document_ids, field_ids, confidence_tier, source)
                VALUES (%s,%s,%s,%s,%s::uuid[],%s::uuid[],%s,'cross_contract')
                """,
                (
                    workspace_id, c["type"], severity,
                    f"{c['description']} {c['recommended_action']}".strip(),
                    doc_ids, field_ids, tier,
                ),
            )

            if c["severity"] in ("Critical", "Significant"):
                established = [
                    {
                        "label": f"{meta.get(ev['contract_id'], {}).get('filename', ev['contract_id'])} — {ev['clause']}",
                        "detail": ev["quote"],
                        "citation": ev["clause"],
                        "confidenceTier": tier,
                    }
                    for ev in c["evidence"]
                ]
                cur.execute(
                    """
                    INSERT INTO handoff_briefs
                      (workspace_id, trigger, issue, established, question, document_ids, source)
                    VALUES (%s,%s,%s,%s,%s,%s::uuid[],'cross_contract')
                    """,
                    (
                        workspace_id, f"conflict:{c['type']}", c["description"],
                        Json(established), _question(c, meta), doc_ids,
                    ),
                )

    logger.info("conflict detection: %d contracts, %d conflicts written", len(docs), len(conflicts))
    return len(conflicts)


def _question(c: dict, meta: dict) -> str:
    ev = c["evidence"]
    if len(ev) >= 2:
        a, b = ev[0], ev[1]
        fa = meta.get(a["contract_id"], {}).get("filename", "the first agreement")
        fb = meta.get(b["contract_id"], {}).get("filename", "the second agreement")
        return (
            f'{a["clause"]} of {fa} states "{a["quote"][:140]}" while {b["clause"]} of {fb} '
            f'states "{b["quote"][:140]}". Which agreement governs, and does this create a breach?'
        )
    return f"{c['description']} Which of the cited clauses governs?"
