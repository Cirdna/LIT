// Feature 1 — portfolio question answering.
//
// THE ARCHITECTURE IS THE POINT. A question goes to the model; a FILTER comes
// back; the filter runs against `extracted_fields`; the rows that come out are
// serialised through the same `serializeField` every other screen uses, so they
// arrive carrying their own confidence tier and clause citation. The model never
// sees a contract and never writes an answer.
//
// The consequence, stated plainly to the user in the response: this can only find
// what was extracted. It is not a search over contract text. If a term was never
// extracted, no phrasing of the question will surface it — and the reply says so
// rather than returning nothing and letting the reader infer absence.
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { prisma } from "../db.js";
import { ALL_FIELD_KEYS, FIELD_GROUPS } from "../lib/domain.js";
import { badRequest } from "../lib/errors.js";
import { DISPLAY_LABELS, labelForField, tiersForLabel, type DisplayLabel } from "../lib/labels.js";
import { askForJson, llmConfig } from "../lib/llm.js";
import { fieldDateIso, fieldDurationDays } from "../lib/quantities.js";
import { serializeField, serializeStatuteFlag } from "../lib/serialize.js";
import { getWorkspaceId } from "../lib/workspace.js";

// ---- the filter the model is allowed to emit --------------------------------
// Field keys are validated against the CURRENT vocabulary. If the team adopts
// main's 41 CUAD keys, this follows automatically because it reads ALL_FIELD_KEYS
// rather than restating the list — but the model's PROMPT also has to describe
// them, which is why the prompt is generated from FIELD_GROUPS below.

const filterSchema = z.object({
  fieldKeys: z.array(z.string()).max(24).default([]),
  valueContains: z.string().max(120).optional(),
  counterpartyContains: z.string().max(120).optional(),
  labels: z.array(z.enum(DISPLAY_LABELS)).optional(),
  duration: z
    .object({
      op: z.enum(["lt", "lte", "gt", "gte", "eq"]),
      days: z.number().int().positive().max(36_500),
    })
    .optional(),
  date: z
    .object({
      op: z.enum(["before", "after", "between"]),
      from: z.string().optional(),
      to: z.string().optional(),
    })
    .optional(),
  limit: z.number().int().positive().max(200).default(50),
});
export type PortfolioFilter = z.infer<typeof filterSchema>;

const triageSchema = z.discriminatedUnion("sufficient", [
  z.object({
    sufficient: z.literal(false),
    question: z.string().min(5).max(300),
    why: z.string().max(300).optional(),
  }),
  z.object({
    sufficient: z.literal(true),
    filter: filterSchema,
    restated: z.string().max(300).optional(),
  }),
]);

function fieldCatalogue(): string {
  return FIELD_GROUPS.map((g) => `  ${g.title}: ${g.fields.join(", ")}`).join("\n");
}

function systemPrompt(allowClarification: boolean): string {
  return [
    "You translate questions about a contract portfolio into a JSON filter.",
    "You do NOT answer questions and you never state anything about a contract:",
    "a separate system runs your filter against a database of extracted clauses",
    "and shows the user the real values with their citations.",
    "",
    "The only fields that exist are these. Never invent a field key:",
    fieldCatalogue(),
    "",
    "Duration fields (notice_period, cure_period, initial_term, renewal_term) are",
    "compared in DAYS. Date fields (effective_date, term_end, notice_deadline) are",
    "compared as ISO dates. `labels` filters by how well the value is evidenced:",
    '"quoted" = found verbatim in the contract, "inferred" = extracted but not',
    'located, "na" = never extracted.',
    "",
    allowClarification
      ? [
          "If the question is too vague to build a useful filter — no field, no",
          "threshold, no date, no counterparty — return",
          '{"sufficient": false, "question": "<ONE short question>"}.',
          "Ask for the single most useful missing detail. Never ask more than one",
          "thing and never ask for something the user already gave you.",
        ].join("\n")
      : [
          "The user has ALREADY answered one clarifying question. You must not ask",
          "another. Build the best filter you can from what you have, even if it is",
          "broad — a broad filter with visible citations is more useful than a",
          "second interrogation.",
        ].join("\n"),
    "",
    'When you can build a filter, return {"sufficient": true, "filter": {...},',
    '"restated": "<one line describing what will be searched>"}.',
    "Return JSON only.",
  ].join("\n");
}

// ---- executing the filter ---------------------------------------------------
// Everything below is deterministic. Given the same filter and the same database
// it returns the same rows, and no model is consulted.

export type FilterMatch = {
  documentId: string;
  filename: string;
  counterparty: string | null;
  field: ReturnType<typeof serializeField>;
  label: DisplayLabel;
  /** Present only when a numeric/date comparison actually decided this match. */
  comparison: { kind: "duration"; days: number; from: string } | { kind: "date"; date: string; from: string } | null;
  /** Statute flags on the same field, so a result can carry the Statute badge too. */
  statuteFlags: ReturnType<typeof serializeStatuteFlag>[];
};

export async function runFilter(workspaceId: string, filter: PortfolioFilter) {
  const unknownKeys = filter.fieldKeys.filter((k) => !ALL_FIELD_KEYS.includes(k));
  const fieldKeys = filter.fieldKeys.filter((k) => ALL_FIELD_KEYS.includes(k));

  // FAIL CLOSED. If the model asked for fields and none of them exist, dropping
  // the clause would widen the query to the whole portfolio and return 165 rows
  // that answer a different question than the one asked. An empty result plus the
  // invented key is the truthful outcome.
  if (filter.fieldKeys.length > 0 && fieldKeys.length === 0)
    return {
      matches: [] as FilterMatch[],
      totalMatched: 0,
      truncated: false,
      skippedUnparseable: 0,
      unknownKeys,
      noSuchField: true,
    };

  // A label filter of exactly ["na"] means "where is this MISSING", which is a
  // question about absent rows, so it cannot be expressed as a tier query.
  const wantsNa = (filter.labels ?? []).includes("na");
  const tierAllow = new Set((filter.labels ?? []).flatMap(tiersForLabel));

  const rows = await prisma.extractedField.findMany({
    where: {
      document: {
        workspaceId,
        ...(filter.counterpartyContains
          ? {
              OR: [
                { counterparty: { contains: filter.counterpartyContains, mode: "insensitive" } },
                { filename: { contains: filter.counterpartyContains, mode: "insensitive" } },
              ],
            }
          : {}),
      },
      ...(fieldKeys.length ? { fieldKey: { in: fieldKeys } } : {}),
      ...(filter.valueContains
        ? { valueVerbatim: { contains: filter.valueContains, mode: "insensitive" } }
        : {}),
    },
    include: { document: { select: { id: true, filename: true, counterparty: true } } },
    orderBy: [{ documentId: "asc" }, { fieldKey: "asc" }],
    take: 500, // hard ceiling before in-memory comparison; `limit` trims after
  });

  const matches: FilterMatch[] = [];
  let unparseable = 0;

  for (const row of rows) {
    const label = labelForField(row);
    if (filter.labels?.length) {
      const ok = label === "na" ? wantsNa : tierAllow.has(row.confidenceTier);
      if (!ok) continue;
    }

    let comparison: FilterMatch["comparison"] = null;

    if (filter.duration) {
      const d = fieldDurationDays(row);
      if (!d) {
        unparseable += 1;
        continue;
      }
      const { op, days } = filter.duration;
      const pass =
        op === "lt" ? d.days < days
        : op === "lte" ? d.days <= days
        : op === "gt" ? d.days > days
        : op === "gte" ? d.days >= days
        : d.days === days;
      if (!pass) continue;
      comparison = { kind: "duration", days: d.days, from: d.from };
    }

    if (filter.date) {
      const d = fieldDateIso(row);
      if (!d) {
        unparseable += 1;
        continue;
      }
      const { op, from, to } = filter.date;
      const pass =
        op === "before" ? !!to && d.date < to
        : op === "after" ? !!from && d.date > from
        : !!from && !!to && d.date >= from && d.date <= to;
      if (!pass) continue;
      comparison = { kind: "date", date: d.date, from: d.from };
    }

    matches.push({
      documentId: row.document.id,
      filename: row.document.filename,
      counterparty: row.document.counterparty,
      field: serializeField(row),
      label,
      comparison,
      statuteFlags: [],
    });
  }

  const trimmed = matches.slice(0, filter.limit);

  // Attach statute flags for the matched fields, so a result can show the fourth
  // badge where the law has something to say about the same clause.
  if (trimmed.length) {
    const flags = await prisma.statuteFlag.findMany({
      where: {
        documentId: { in: [...new Set(trimmed.map((m) => m.documentId))] },
        fieldKey: { in: [...new Set(trimmed.map((m) => m.field.fieldKey))] },
      },
    });
    for (const m of trimmed)
      m.statuteFlags = flags
        .filter((f) => f.documentId === m.documentId && f.fieldKey === m.field.fieldKey)
        .map(serializeStatuteFlag);
  }

  return {
    matches: trimmed,
    totalMatched: matches.length,
    truncated: matches.length > trimmed.length,
    /** Rows skipped because their quoted text held no parseable number or date. */
    skippedUnparseable: unparseable,
    /** Field keys the model invented; dropped rather than silently guessed. */
    unknownKeys,
    noSuchField: false,
  };
}

export async function registerChatRoutes(app: FastifyInstance) {
  const body = z.object({
    query: z.string().min(2).max(500),
    // Set by the client when it is replying to a clarifying question. Its presence
    // is what caps the loop at ONE round-trip.
    clarifying: z
      .object({ originalQuery: z.string().max(500), question: z.string().max(300) })
      .optional(),
  });

  app.get("/api/chat/capabilities", async () => ({
    llmConfigured: llmConfig.available,
    model: llmConfig.available ? llmConfig.model : null,
    searchableFieldKeys: ALL_FIELD_KEYS,
    /** Stated up front so the reader knows the boundary before asking. */
    limits: [
      "Searches only values the extraction pipeline produced — not the full text of your contracts.",
      "A field no extractor covers cannot be found by any phrasing of the question.",
      "Durations and dates are read from the quoted text; a value that cannot be read as a number is left out and counted.",
    ],
  }));

  app.post("/api/chat/query", async (req) => {
    const { query, clarifying } = body.parse(req.body);
    const workspaceId = await getWorkspaceId();

    const userMessage = clarifying
      ? [
          `Original question: ${clarifying.originalQuery}`,
          `You asked: ${clarifying.question}`,
          `They answered: ${query}`,
        ].join("\n")
      : query;

    const triage = await askForJson({
      system: systemPrompt(!clarifying),
      user: userMessage,
      schema: triageSchema,
    });

    if (!triage.sufficient) {
      // Defence in depth: even if the model ignores the instruction, a second
      // clarification is refused here rather than passed to the user.
      if (clarifying) throw badRequest("The model asked a second clarifying question; refused.");
      return {
        mode: "clarify" as const,
        question: triage.question,
        why: triage.why ?? null,
        originalQuery: query,
      };
    }

    const result = await runFilter(workspaceId, triage.filter);
    return {
      mode: "results" as const,
      restated: triage.restated ?? null,
      filter: triage.filter,
      ...result,
      note:
        "Every value below was read from the contract by the extraction pipeline and carries its own label and citation. The model only chose what to search for.",
    };
  });
}
