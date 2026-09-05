// Builds a handoff brief from a conflict. Shared between the POST /api/handoffs
// route (manual, from the conflicts screen) and the stub worker (automatic, when
// a boundary is tripped) so both produce an identically shaped, specific brief.
import type { Conflict, Document, ExtractedField } from "@prisma/client";

export type EstablishedItem = {
  label: string;
  detail: string | null;
  citation: string | null;
  confidenceTier: string;
};

export type BriefData = {
  trigger: string;
  issue: string;
  established: EstablishedItem[];
  question: string;
  documentIds: string[];
};

export function buildBriefFromConflict(
  conflict: Conflict,
  docs: Document[],
  fields: ExtractedField[],
): BriefData {
  const docById = new Map(docs.map((d) => [d.id, d]));
  const established: EstablishedItem[] = fields.map((f) => {
    const doc = docById.get(f.documentId);
    return {
      label: `${doc?.filename ?? "Document"} — ${f.clauseLabel ?? f.fieldKey}`,
      detail: f.valueVerbatim,
      citation: f.clauseLabel,
      confidenceTier: f.confidenceTier,
    };
  });

  // A specific question naming the clauses in tension — never "please review".
  let question: string;
  if (fields.length >= 2 && fields[0] && fields[1]) {
    const a = fields[0];
    const b = fields[1];
    const docA = docById.get(a.documentId)?.filename ?? "the first agreement";
    const docB = docById.get(b.documentId)?.filename ?? "the second agreement";
    question =
      conflict.conflictType === "exclusivity_breach"
        ? `${a.clauseLabel ?? "A clause"} of ${docA} grants exclusive rights in the same territory that ${b.clauseLabel ?? "a clause"} of ${docB} also grants. Does the later grant breach the earlier exclusivity, and which agreement governs that territory?`
        : `${a.clauseLabel ?? "A clause"} of ${docA} states "${a.valueVerbatim ?? "—"}" while ${b.clauseLabel ?? "a clause"} of ${docB} states "${b.valueVerbatim ?? "—"}". Which governs?`;
  } else {
    question = `${conflict.summary} Which of the cited clauses governs?`;
  }

  return {
    trigger: `conflict:${conflict.conflictType}`,
    issue: conflict.summary,
    established,
    question,
    documentIds: conflict.documentIds,
  };
}
