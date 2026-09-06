// Structured retrieval for the RAG chat (Feature 1, Phase 1). The LLM turns a
// natural-language question into these whitelisted params; this module turns
// them into Prisma queries. Raw LLM text is only ever used as a parameterised
// `contains` value — never interpolated into SQL — so the model cannot shape a
// query beyond the fields below.
import { z } from "zod";
import { prisma } from "../db.js";
import { ALL_FIELD_KEYS } from "./domain.js";

const DOC_TYPES = ["nda", "lease", "msa", "distribution", "employment", "other"] as const;

// Categories whose normalized value is a comparable number, and under which key.
const NUMERIC_FIELD_UNIT: Record<string, "days" | "months"> = {
  notice_period_to_terminate_renewal: "days",
  renewal_term: "months",
  warranty_duration: "months",
};
const DATE_FIELDS = ["agreement_date", "effective_date", "expiration_date"] as const;

export const RetrievalParams = z
  .object({
    docType: z.enum(DOC_TYPES).optional(),
    counterparty: z.string().min(1).max(120).optional(),
    freeText: z.string().min(1).max(200).optional(),
    fieldKey: z.enum(ALL_FIELD_KEYS as [string, ...string[]]).optional(),
    presence: z.enum(["present", "absent"]).optional(),
    comparator: z.enum(["lt", "lte", "gt", "gte", "eq"]).optional(),
    threshold: z.number().optional(),
    dateField: z.enum(DATE_FIELDS).optional(),
    dateFrom: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
    dateTo: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  })
  .strip();

export type RetrievalParams = z.infer<typeof RetrievalParams>;

export type RetrievedField = {
  fieldKey: string;
  value: string | null;
  normalized: unknown;
  confidenceTier: string;
  clauseLabel: string | null;
  absenceReason: string | null;
};

export type RetrievedDoc = {
  documentId: string;
  filename: string;
  counterparty: string | null;
  docType: string | null;
  fields: RetrievedField[];
};

function cmp(a: number, op: string, b: number): boolean {
  switch (op) {
    case "lt": return a < b;
    case "lte": return a <= b;
    case "gt": return a > b;
    case "gte": return a >= b;
    case "eq": return a === b;
    default: return true;
  }
}

export async function retrieve(workspaceId: string, params: RetrievalParams): Promise<RetrievedDoc[]> {
  const where: Record<string, unknown> = {
    workspaceId,
    status: { in: ["ready", "degraded"] },
    // Contracts only unless a specific docType was asked for.
    docType: params.docType ?? { notIn: ["not_a_contract", "invoice"] },
  };
  if (params.counterparty) where.counterparty = { contains: params.counterparty, mode: "insensitive" };
  if (params.freeText)
    where.OR = [
      { filename: { contains: params.freeText, mode: "insensitive" } },
      { counterparty: { contains: params.freeText, mode: "insensitive" } },
    ];

  let docs = await prisma.document.findMany({
    where: where as never,
    select: { id: true, filename: true, counterparty: true, docType: true },
    take: 200,
  });
  if (docs.length === 0) return [];

  const matchedByDoc = new Map<string, RetrievedField[]>();

  if (params.fieldKey) {
    const rows = await prisma.extractedField.findMany({
      where: { documentId: { in: docs.map((d) => d.id) }, fieldKey: params.fieldKey },
      select: {
        documentId: true, fieldKey: true, valueVerbatim: true, valueNormalized: true,
        confidenceTier: true, clauseLabel: true, absenceReason: true,
      },
    });
    const keep = new Set<string>();
    for (const f of rows) {
      if (!fieldMatches(f, params)) continue;
      keep.add(f.documentId);
      const list = matchedByDoc.get(f.documentId) ?? [];
      list.push({
        fieldKey: f.fieldKey, value: f.valueVerbatim, normalized: f.valueNormalized,
        confidenceTier: f.confidenceTier, clauseLabel: f.clauseLabel, absenceReason: f.absenceReason,
      });
      matchedByDoc.set(f.documentId, list);
    }
    docs = docs.filter((d) => keep.has(d.id));
  }

  return docs.slice(0, 50).map((d) => ({
    documentId: d.id,
    filename: d.filename,
    counterparty: d.counterparty,
    docType: d.docType,
    fields: matchedByDoc.get(d.id) ?? [],
  }));
}

function fieldMatches(
  f: { valueVerbatim: string | null; valueNormalized: unknown; confidenceTier: string },
  p: RetrievalParams,
): boolean {
  const key = p.fieldKey!;
  const norm = (f.valueNormalized ?? {}) as Record<string, unknown>;

  if (p.presence === "absent") return f.valueVerbatim == null;
  if (p.presence === "present" && f.valueVerbatim == null) return false;

  // Numeric comparison.
  const unit = NUMERIC_FIELD_UNIT[key];
  if (p.threshold != null && p.comparator && unit) {
    if (f.confidenceTier === "unverified") return false;
    const n = norm[unit];
    if (typeof n !== "number") return false;
    return cmp(n, p.comparator, p.threshold);
  }

  // Date range.
  if ((p.dateFrom || p.dateTo) && (DATE_FIELDS as readonly string[]).includes(key)) {
    if (f.confidenceTier === "unverified") return false;
    const d = norm.date;
    if (typeof d !== "string") return false;
    if (p.dateFrom && d < p.dateFrom) return false;
    if (p.dateTo && d > p.dateTo) return false;
    return true;
  }

  // Default: the field is present (a value exists), which the guard above allows.
  return true;
}
