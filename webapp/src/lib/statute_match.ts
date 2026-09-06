// The "which statutes apply to THIS contract" engine, driven by the metadata
// already on each statute chunk (see src/pdf_analyzer/files + the changelog):
//
//   1. contract-type gate — the chunk's applicable_contract_types vs the
//      document's doc_type (mapped into the statute taxonomy);
//   2. jurisdiction gate — the contract's extracted governing_law. Singapore or
//      silent → the statute fires; an express non-Singapore jurisdiction →
//      NA (governing_law_excluded);
//   3. the chunk's own AI status (Quoted/Inferred/Evaluation Required/NA) then
//      stands, unless jurisdiction/dependency forces NA.
//
// Deterministic — no model call. Produces affirmative "applies" / "does not
// apply, because …" results rather than silence.

export type AiStatus = "Quoted" | "Inferred" | "Evaluation Required" | "NA";

// webapp doc_type -> the statute store's contract-type taxonomy.
const DOC_TYPE_TO_STATUTE_TYPES: Record<string, string[]> = {
  nda: ["nda"],
  lease: ["lease", "goods_hire"],
  msa: ["services", "other_commercial"],
  distribution: ["distribution", "other_commercial"],
  employment: ["employment"],
  // The pipeline classifies IP/other agreements as "other"; the store models IP
  // agreements explicitly and folds the rest into other_commercial.
  other: ["other_commercial", "ip_agreement"],
};

export function statuteTypesFor(docType: string | null): string[] {
  if (!docType) return [];
  return DOC_TYPE_TO_STATUTE_TYPES[docType] ?? [];
}

export type Jurisdiction = "singapore" | "excluded" | "silent";

/** Apply the jurisdiction gate to a contract's extracted governing_law text. */
export function jurisdictionFor(governingLaw: string | null): Jurisdiction {
  if (!governingLaw || !governingLaw.trim()) return "silent"; // silent → fires
  const t = governingLaw.toLowerCase();
  if (t.includes("singapore")) return "singapore";
  return "excluded"; // an express non-Singapore governing law
}

type ClauseInput = {
  aiStatus: string;
  applicableContractTypes: string[];
};

export type PerContractResult = {
  applies: boolean; // in scope for this contract type at all
  status: AiStatus; // per-contract status
  reason: string | null; // why NA, when applicable
};

/**
 * Evaluate one statute clause against one contract. A clause is only shown when
 * it is in scope for the contract type; among those, jurisdiction/dependency can
 * still resolve it to NA with a citable reason.
 */
export function evaluateClause(
  clause: ClauseInput,
  docType: string | null,
  jurisdiction: Jurisdiction,
): PerContractResult {
  const scopeTypes = statuteTypesFor(docType);
  const applies = clause.applicableContractTypes.some((t) => scopeTypes.includes(t));
  if (!applies) return { applies: false, status: "NA", reason: "contract_type_excluded" };

  // The chunk was globally NA (e.g. engine_status=dependency_unavailable).
  if (clause.aiStatus === "NA") return { applies: true, status: "NA", reason: "dependency_unavailable" };

  if (jurisdiction === "excluded") return { applies: true, status: "NA", reason: "governing_law_excluded" };

  // In scope and jurisdiction is fine → the clause's own AI status stands.
  return { applies: true, status: clause.aiStatus as AiStatus, reason: null };
}
