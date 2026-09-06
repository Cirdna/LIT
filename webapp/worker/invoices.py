"""Invoice ingestion + reconciliation (Feature 3).

An invoice is a Document with doc_type='invoice'. Instead of the CUAD contract
pass, we extract its header + line items with the text LLM, then reconcile it
against the contract portfolio in two phases:

  Phase A — entity & scope: fuzzy-match the billing party to a contract.
            0 matches → MISSING_CONTRACT_ROGUE; >1 → MULTIPLE_CONTRACTS_REVIEW.
  Phase B — temporal: if a single contract matched, check the invoice date falls
            within its [effective, expiration] window. In → HIGH_CONFIDENCE_MATCH;
            out/unknown → DATE_MISMATCH_REVIEW.

Party matching is deliberately conservative (exact-normalised or clear token
overlap); a weak guess is surfaced for review, never asserted as a match.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import psycopg
from psycopg.types.json import Json

from .llm import chat_json

logger = logging.getLogger("worker.invoices")

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SUFFIXES = {
    "llc", "inc", "incorporated", "ltd", "limited", "corp", "corporation", "co",
    "company", "pte", "plc", "gmbh", "llp", "lp", "sa", "ag", "bv",
}


# ---- detection -----------------------------------------------------------


def looks_like_invoice(full_text: str, filename: str) -> bool:
    """Conservative invoice detector — a contract that merely mentions invoicing
    must not trip this."""
    head = full_text[:400].lower()
    body = full_text.lower()
    if "invoice" in filename.lower():
        return True
    if "invoice" in head or "tax invoice" in head:
        return True
    signals = sum(
        1 for kw in ("bill to", "amount due", "remittance", "invoice number", "invoice no", "purchase order")
        if kw in body
    )
    return signals >= 2


# ---- extraction ----------------------------------------------------------


@dataclass
class LineItem:
    description: str
    quantity: Optional[float]
    amount: Optional[float]


@dataclass
class InvoiceExtraction:
    billing_from: Optional[str]
    billing_to: Optional[str]
    invoice_date: Optional[str]  # ISO or None
    invoice_number: Optional[str]
    currency: Optional[str]
    total: Optional[float]
    line_items: list[LineItem] = field(default_factory=list)


_EXTRACT_SYSTEM = """You extract structured data from an invoice. Return ONLY a JSON object:
{"billing_from": string|null, "billing_to": string|null, "invoice_date": "YYYY-MM-DD"|null,
 "invoice_number": string|null, "currency": string|null, "total": number|null,
 "line_items": [{"description": string, "quantity": number|null, "amount": number|null}]}
billing_from is the vendor issuing the invoice; billing_to is the customer being billed.
Use null when a field is not present. Do not invent values."""


def extract_invoice(full_text: str) -> InvoiceExtraction:
    raw = chat_json(_EXTRACT_SYSTEM, full_text[:6000])
    inv_date = raw.get("invoice_date")
    if not (isinstance(inv_date, str) and _ISO.match(inv_date)):
        inv_date = None
    items: list[LineItem] = []
    for it in raw.get("line_items") or []:
        if not isinstance(it, dict):
            continue
        desc = str(it.get("description") or "").strip()
        if not desc:
            continue
        items.append(
            LineItem(
                description=desc[:300],
                quantity=_num(it.get("quantity")),
                amount=_num(it.get("amount")),
            )
        )
    return InvoiceExtraction(
        billing_from=_str(raw.get("billing_from")),
        billing_to=_str(raw.get("billing_to")),
        invoice_date=inv_date,
        invoice_number=_str(raw.get("invoice_number")),
        currency=_str(raw.get("currency")),
        total=_num(raw.get("total")),
        line_items=items,
    )


def _str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s[:200] or None


def _num(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"-?\d+(?:\.\d+)?", v.replace(",", ""))
        if m:
            return float(m.group(0))
    return None


# ---- party matching ------------------------------------------------------


def _normalize(name: str) -> str:
    tokens = re.sub(r"[^\w\s]", " ", name.lower()).split()
    kept = [t for t in tokens if t not in _SUFFIXES]
    return " ".join(kept or tokens)


def _match_method(a: str, b: str) -> Optional[str]:
    """'exact' | 'fuzzy' | None between two party names."""
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return None
    if na == nb:
        return "exact"
    if na in nb or nb in na:
        return "fuzzy"
    ta, tb = set(na.split()), set(nb.split())
    overlap = ta & tb
    # Fuzzy only when the shorter name's tokens are entirely contained in the
    # other's — so "Acme" matches "Acme Distribution", but a single generic
    # shared word like "Distribution" does not merge two different vendors.
    if overlap and len(overlap) >= min(len(ta), len(tb)):
        return "fuzzy"
    return None


# ---- persistence + reconciliation ---------------------------------------


def process_invoice(
    conn: psycopg.Connection,
    *,
    document_id: str,
    workspace_id: str,
    filename: str,
    full_text: str,
    page_count: int,
    provenance: str,
    ocr_applied: bool,
    pipeline_version: str,
) -> dict[str, Any]:
    """Extract the invoice, persist it, reconcile it, and update the document."""
    extraction = extract_invoice(full_text)
    header_tier = "normalised" if extraction.invoice_date and (extraction.billing_from or extraction.billing_to) else "inferred"

    with conn.transaction(), conn.cursor() as cur:
        cur.execute("DELETE FROM invoice_line_items WHERE document_id=%s", (document_id,))
        cur.execute("DELETE FROM invoice_matches WHERE invoice_id=%s", (document_id,))
        cur.execute("DELETE FROM invoice_headers WHERE document_id=%s", (document_id,))

        cur.execute(
            """
            INSERT INTO invoice_headers
              (document_id, billing_from, billing_to, invoice_date, invoice_number, currency, total, confidence_tier)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                document_id, extraction.billing_from, extraction.billing_to,
                date.fromisoformat(extraction.invoice_date) if extraction.invoice_date else None,
                extraction.invoice_number, extraction.currency, extraction.total, header_tier,
            ),
        )
        for li in extraction.line_items:
            cur.execute(
                "INSERT INTO invoice_line_items (document_id, description, quantity, amount, anchor_line_ids) VALUES (%s,%s,%s,%s,%s)",
                (document_id, li.description, li.quantity, li.amount, []),
            )

        match = _reconcile(cur, workspace_id, document_id, extraction)
        cur.execute(
            """
            INSERT INTO invoice_matches
              (invoice_id, contract_document_id, status, confidence_tier, reasons, matched_on)
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (
                document_id, match["contractDocumentId"], match["status"], match["confidenceTier"],
                Json(match["reasons"]), Json(match["matchedOn"]),
            ),
        )

        warnings = _warnings_for(match)
        cur.execute(
            """
            UPDATE documents SET
              status='ready', doc_type='invoice', doc_type_conf=0.9,
              provenance_quality=%s, page_count=%s, ocr_applied=%s,
              counterparty=%s, warnings=%s, pipeline_version=%s, processed_at=now(), error=NULL
            WHERE id=%s
            """,
            (
                provenance, page_count, ocr_applied, extraction.billing_from,
                Json(warnings), pipeline_version, document_id,
            ),
        )

    logger.info("invoice %s → %s (contract=%s)", document_id, match["status"], match["contractDocumentId"])
    return match


def _reconcile(cur, workspace_id: str, invoice_id: str, inv: InvoiceExtraction) -> dict[str, Any]:
    vendor = inv.billing_from or inv.billing_to
    reasons: list[str] = []
    if not vendor:
        return _result(None, "MISSING_CONTRACT_ROGUE", "inferred",
                       ["No billing party could be read from the invoice."],
                       {"party": None})

    # Candidate contracts + their party names.
    cur.execute(
        """
        SELECT id, counterparty FROM documents
        WHERE workspace_id=%s AND status IN ('ready','degraded')
          AND (doc_type IS NULL OR doc_type NOT IN ('not_a_contract','invoice'))
        """,
        (workspace_id,),
    )
    contracts = cur.fetchall()
    if not contracts:
        return _result(None, "MISSING_CONTRACT_ROGUE", "inferred",
                       [f"No contracts to match the vendor “{vendor}”."], {"party": {"invoice": vendor}})

    ids = [c["id"] for c in contracts]
    cur.execute(
        "SELECT document_id, value_verbatim FROM extracted_fields WHERE field_key='parties' AND document_id = ANY(%s)",
        (ids,),
    )
    parties = {r["document_id"]: r["value_verbatim"] for r in cur.fetchall()}

    # Phase A — party match.
    matches: list[dict[str, Any]] = []
    for c in contracts:
        candidates = [c["counterparty"], parties.get(c["id"])]
        best: Optional[str] = None
        for cand in candidates:
            if not cand:
                continue
            method = _match_method(vendor, cand)
            if method == "exact":
                best = "exact"
                break
            if method == "fuzzy" and best is None:
                best = "fuzzy"
        if best:
            matches.append({"id": c["id"], "counterparty": c["counterparty"], "method": best})

    if len(matches) == 0:
        return _result(None, "MISSING_CONTRACT_ROGUE", "inferred",
                       [f"No contract's party matches the vendor “{vendor}”. Possible rogue invoice."],
                       {"party": {"invoice": vendor}})
    if len(matches) > 1:
        return _result(None, "MULTIPLE_CONTRACTS_REVIEW", "inferred",
                       [f"{len(matches)} active contracts match “{vendor}”. Manual review required."],
                       {"party": {"invoice": vendor, "candidates": [m["counterparty"] for m in matches]}})

    # Exactly one — Phase B temporal validation.
    m = matches[0]
    tier = "normalised" if m["method"] == "exact" else "inferred"
    reasons.append(f"Vendor “{vendor}” matched contract party “{m['counterparty']}” ({m['method']}).")

    cur.execute(
        """
        SELECT field_key, value_normalized FROM extracted_fields
        WHERE document_id=%s AND field_key IN ('effective_date','expiration_date') AND confidence_tier <> 'unverified'
        """,
        (m["id"],),
    )
    dates = {r["field_key"]: (r["value_normalized"] or {}).get("date") for r in cur.fetchall()}
    eff, exp = dates.get("effective_date"), dates.get("expiration_date")
    matched_on = {
        "party": {"invoice": vendor, "contract": m["counterparty"], "method": m["method"]},
        "dateWindow": {"invoiceDate": inv.invoice_date, "effective": eff, "expiration": exp},
    }

    if not inv.invoice_date:
        reasons.append("The invoice date could not be read, so the contract window can't be confirmed.")
        return _result(m["id"], "DATE_MISMATCH_REVIEW", "inferred", reasons, matched_on)
    if not eff or not exp:
        reasons.append("The contract's effective/expiration dates are incomplete, so the window can't be confirmed.")
        return _result(m["id"], "DATE_MISMATCH_REVIEW", "inferred", reasons, matched_on)
    if eff <= inv.invoice_date <= exp:
        reasons.append(f"Invoice date {inv.invoice_date} falls within the contract window {eff} → {exp}.")
        return _result(m["id"], "HIGH_CONFIDENCE_MATCH", tier, reasons, matched_on)

    reasons.append(f"Invoice date {inv.invoice_date} is outside the contract window {eff} → {exp}.")
    return _result(m["id"], "DATE_MISMATCH_REVIEW", "inferred", reasons, matched_on)


def _result(contract_id, status, tier, reasons, matched_on) -> dict[str, Any]:
    return {
        "contractDocumentId": contract_id,
        "status": status,
        "confidenceTier": tier,
        "reasons": reasons,
        "matchedOn": matched_on,
    }


def _warnings_for(match: dict[str, Any]) -> list[str]:
    status = match["status"]
    if status == "MISSING_CONTRACT_ROGUE":
        return ["No matching contract found — this may be a rogue invoice."]
    if status == "MULTIPLE_CONTRACTS_REVIEW":
        return ["Multiple contracts could match this invoice — manual review required."]
    if status == "DATE_MISMATCH_REVIEW":
        return ["The invoice date could not be confirmed inside the contract window — manual review required."]
    return []
