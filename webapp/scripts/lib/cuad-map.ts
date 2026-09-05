// Maps the Python pipeline's analysis JSON onto the webapp's existing field
// keys (src/lib/domain.ts FIELD_GROUPS). Pure functions, no DB, no I/O — so the
// mapping can be reasoned about and tested without Postgres or a model call.
//
// Two rules make this honest, and both matter more than coverage:
//
//  1. Nothing is invented. A webapp field with no CUAD equivalent
//     (payment_amount, initial_term, cure_period, ...) gets NO row at all.
//     DocumentDetail already renders "Not extracted." for a field key with no
//     rows, which is the truth. Writing a placeholder row with a cheerful tier
//     is what the stub worker did, and it is the thing this pass removes.
//  2. The confidence tier is derived from Stage 3, not chosen. `is_grounded`
//     means the quoted text was located on the page above the 85% threshold;
//     that is `verbatim`. Not grounded means the quote was NOT found where it
//     was cited, which is exactly what the `unverified` tier is defined as
//     (see src/lib/domain.ts) — a fabrication signal, not a value to rely on.
import { ALL_FIELD_KEYS } from "../../src/lib/domain.js";
import type { AbsenceReason, ClaimType, ConfidenceTier } from "../../src/lib/domain.js";

// ---- the subset of the analysis JSON we read ------------------------------
// Mirrors src/pdf_analyzer/schema.py. Only the fields used below are declared.

export type OcrVerificationJson = {
  ocr_text: string;
  score: number; // 0-100, Stage 3 recall scaled by evidence mass
  recall: number;
  evidence_mass: number;
  is_grounded: boolean; // score >= VERIFICATION_THRESHOLD (85)
};

export type CuadExtractionJson = {
  vlm_text: string;
  location: { page: number; bbox_1000: number[] };
  source: { page: number; clause: string; exact_supporting_text: string };
  ocr_verification: OcrVerificationJson;
};

export type CategoryFindingJson = {
  answer: string; // present | absent | unresolved
  summary: string;
  evidence_status: string;
  review_flag: { flagged: boolean; reason: string };
  extractions: CuadExtractionJson[];
};

export type EntityLinkJson = {
  canonical_id: string | null;
  raw_value: string;
  resolution_method: string;
  confidence_tier: string; // high | medium | low
  requires_human_review: boolean;
  evidence: string;
};

export type ContractAnalysisJson = {
  contract_id: string;
  document_metadata: { source_file: string; processed_pdf: string; total_pages: number };
  counterparties: EntityLinkJson[];
  assets: EntityLinkJson[];
  cuad_findings: Record<string, CategoryFindingJson>;
  structured_clauses: unknown[];
};

// ---- CUAD category -> webapp field key -----------------------------------
// Listed in preference order: the first category with a usable extraction wins,
// so `liability_cap` reports a cap when there is one and the uncapped-liability
// clause otherwise.

export const CUAD_FIELD_MAP: { fieldKey: string; cuadKeys: string[] }[] = [
  { fieldKey: "effective_date", cuadKeys: ["effective_date"] },
  { fieldKey: "term_end", cuadKeys: ["expiration_date"] },
  { fieldKey: "renewal_term", cuadKeys: ["renewal_term"] },
  { fieldKey: "notice_period", cuadKeys: ["notice_period_to_terminate_renewal"] },
  { fieldKey: "termination_for_convenience", cuadKeys: ["termination_for_convenience"] },
  { fieldKey: "liability_cap", cuadKeys: ["cap_on_liability", "uncapped_liability"] },
  { fieldKey: "exclusivity", cuadKeys: ["exclusivity"] },
  { fieldKey: "non_compete", cuadKeys: ["non_compete"] },
  { fieldKey: "non_solicit", cuadKeys: ["no_solicit_of_employees", "no_solicit_of_customers"] },
];

/** Webapp fields the CUAD taxonomy has no equivalent for. Reported, never faked. */
export const FIELDS_WITHOUT_CUAD_SOURCE: string[] = ALL_FIELD_KEYS.filter(
  (key) =>
    key !== "party_a" &&
    key !== "party_b" &&
    !CUAD_FIELD_MAP.some((m) => m.fieldKey === key),
);

export type MappedField = {
  fieldKey: string;
  valueVerbatim: string;
  confidenceTier: ConfidenceTier;
  claimType: ClaimType;
  absenceReason: AbsenceReason | null;
  clauseLabel: string;
  /** Stage 3 match score, 0..1. Named for what the UI means by it: the text
   *  reading and the image reading agreeing. */
  vlmAgreement: number;
  sourceCuadKey: string;
  sourcePage: number;
};

/** Prefer a grounded extraction; fall back to the first one so an ungrounded
 *  quote is still surfaced — flagged as a suspected error, not hidden. */
function pickExtraction(finding: CategoryFindingJson | undefined): CuadExtractionJson | null {
  if (!finding || finding.extractions.length === 0) return null;
  return finding.extractions.find((e) => e.ocr_verification.is_grounded) ?? finding.extractions[0]!;
}

function toRow(fieldKey: string, cuadKey: string, extraction: CuadExtractionJson): MappedField {
  const v = extraction.ocr_verification;
  return {
    fieldKey,
    // Grounded: the page's own words, which is what "verbatim" has to mean.
    // Ungrounded: the model's text, kept only so a reviewer can see the claim
    // that failed verification.
    valueVerbatim: v.is_grounded ? v.ocr_text : extraction.vlm_text,
    confidenceTier: v.is_grounded ? "verbatim" : "unverified",
    claimType: "contract_text",
    absenceReason: null,
    // extracted_fields has no page column, and no text_lines are written on
    // this path, so the real page rides along in the clause label.
    clauseLabel: `${extraction.source.clause} (page ${extraction.source.page})`,
    vlmAgreement: Math.max(0, Math.min(1, v.score / 100)),
    sourceCuadKey: cuadKey,
    sourcePage: extraction.source.page,
  };
}

/**
 * The two parties come from one CUAD category, whose span is a single quote
 * ("X and Y"). We do not split it into party_a/party_b — that is name parsing,
 * and a wrong split is a wrong fact. Instead each separate `parties` extraction
 * fills the next slot, and an absent second one simply has no row.
 */
function mapParties(finding: CategoryFindingJson | undefined): MappedField[] {
  if (!finding) return [];
  const slots = ["party_a", "party_b"];
  const rows: MappedField[] = [];
  finding.extractions.slice(0, slots.length).forEach((extraction, i) => {
    rows.push(toRow(slots[i]!, "parties", extraction));
  });
  return rows;
}

export function mapAnalysisToFields(analysis: ContractAnalysisJson): MappedField[] {
  const rows: MappedField[] = [...mapParties(analysis.cuad_findings["parties"])];

  for (const { fieldKey, cuadKeys } of CUAD_FIELD_MAP) {
    for (const cuadKey of cuadKeys) {
      const extraction = pickExtraction(analysis.cuad_findings[cuadKey]);
      if (!extraction) continue;
      rows.push(toRow(fieldKey, cuadKey, extraction));
      break; // first category with an extraction wins
    }
  }

  // A typo here would silently create a field key no screen renders.
  const unknown = rows.map((r) => r.fieldKey).filter((k) => !ALL_FIELD_KEYS.includes(k));
  if (unknown.length > 0) throw new Error(`mapped unknown field keys: ${unknown.join(", ")}`);

  return rows;
}

/** The counterparty denormalised onto `documents.counterparty`, from the real
 *  exact-name join keys the pipeline resolved. Null when it abstained. */
export function counterpartyLabel(analysis: ContractAnalysisJson): string | null {
  const resolved = analysis.counterparties.filter((c) => c.canonical_id != null);
  if (resolved.length === 0) return null;
  // The first party of a preamble is usually the user's own entity; with two or
  // more names the second is the counterparty. With one, that one is all we know.
  return (resolved[1] ?? resolved[0]!).raw_value;
}
