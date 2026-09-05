// Feature 3 — invoice-to-contract matching ("detect the contract that is missing").
//
// WHAT IS GROUNDED AND WHAT IS NOT, because this feature reads two documents with
// very different standing:
//   * The INVOICE is read by the model. Its parties, line items and date are
//     labelled `model_read` and are never presented as quoted. They are used only
//     as lookup keys.
//   * The CONTRACT side is never read by the model. Every check runs against rows
//     already in `extracted_fields`, and every status returned names the exact
//     field id, clause and page it was decided from.
// So the feature can be wrong about an invoice; it cannot invent a contract term.
//
// IT DOES NOT WRITE TO THE `conflicts` TABLE. An invoice finding is returned on
// its own channel with `resultChannel: "invoice_match"`. The conflicts table
// already mixes a seeded demo row with real detections and needs no third
// unlabelled source (GAP_REPORT §4).
import path from "node:path";
import { readFile } from "node:fs/promises";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { storage } from "../config.js";
import { prisma } from "../db.js";
import { ApiError, notFound } from "../lib/errors.js";
import { labelForField } from "../lib/labels.js";
import { askForJson } from "../lib/llm.js";
import { partyKeysFrom } from "../lib/parties.js";
import { fieldDateIso, parseIsoDate } from "../lib/quantities.js";
import { getWorkspaceId } from "../lib/workspace.js";

const PARTY_FIELD_KEYS = ["party_a", "party_b"]; // CURRENT vocabulary — see STATUS_UPDATE.md

// ---- step 0: find something to read ----------------------------------------
// The real pipeline path writes no `document_text` row and its analysis JSON
// carries no full text, so the only text available for a real upload is the set of
// grounded extraction spans. That is a much thinner input than a page of invoice
// text, and when it is what we used, the response says so.

type TextSource = { text: string; source: "document_text" | "analysis_spans"; note: string | null };

async function invoiceText(documentId: string): Promise<TextSource> {
  const stored = await prisma.documentText.findUnique({ where: { documentId } });
  if (stored?.text?.trim())
    return { text: stored.text, source: "document_text", note: null };

  const analysisPath = path.join(storage.root, "analysis", `${documentId}.json`);
  const raw = await readFile(analysisPath, "utf8").catch(() => null);
  if (raw) {
    type Finding = { extractions?: { ocr_verification?: { ocr_text?: string; is_grounded?: boolean } }[] };
    const analysis = JSON.parse(raw) as { cuad_findings?: Record<string, Finding> };
    const spans: string[] = [];
    for (const [category, finding] of Object.entries(analysis.cuad_findings ?? {}))
      for (const e of finding.extractions ?? [])
        if (e.ocr_verification?.is_grounded && e.ocr_verification.ocr_text)
          spans.push(`${category}: ${e.ocr_verification.ocr_text}`);
    if (spans.length)
      return {
        text: spans.join("\n"),
        source: "analysis_spans",
        note:
          "No stored page text exists for this document, so only the clauses the pipeline managed to extract were read. An invoice's billing lines are usually not among them, so a MISSING CONTRACT result here may reflect thin input rather than a missing contract.",
      };
  }

  throw new ApiError(
    422,
    "no_readable_text",
    "There is no stored text for this document, so its billing parties cannot be read.",
    {
      why: "The extraction pipeline that processed this document does not write a document_text row, and its analysis JSON holds no full text.",
      remedy: "Re-process the document with a worker that stores page text, then retry.",
    },
  );
}

// ---- step 1: read the invoice (the only model call in this feature) ---------

const invoiceReadSchema = z.object({
  is_invoice: z.boolean(),
  billing_parties: z
    .array(
      z.object({
        name: z.string().min(1).max(200),
        role: z.enum(["biller", "payer", "unknown"]).default("unknown"),
      }),
    )
    .max(10)
    .default([]),
  line_items: z
    .array(
      z.object({
        description: z.string().min(1).max(300),
        amount: z.number().nullable().default(null),
        currency: z.string().max(8).nullable().default(null),
      }),
    )
    .max(40)
    .default([]),
  invoice_date: z.string().max(40).nullable().default(null),
  invoice_number: z.string().max(60).nullable().default(null),
});

const READER_SYSTEM = [
  "You read one invoice and return what it says. You do not interpret, judge, or",
  "compare it to anything — a separate system checks it against a contract",
  "database and shows a lawyer the result.",
  "",
  "Return the party names EXACTLY as written on the invoice, including any legal",
  "suffix (Pte Ltd, Inc, LLC). Do not expand abbreviations, correct spelling, or",
  "guess a fuller name: the names are used as exact lookup keys, so an improved",
  "name is a wrong name.",
  "",
  "If a value is not on the document, return null. Never fill a gap.",
  "Set is_invoice false if this is not an invoice, bill or statement of charges.",
  "",
  "Return JSON with: is_invoice, billing_parties [{name, role}], line_items",
  "[{description, amount, currency}], invoice_date (ISO if you can), invoice_number.",
].join("\n");

// ---- step 2 (Phase A): exact-name match against contract fields -------------

type Citation = {
  documentId: string;
  filename: string;
  fieldId: string;
  fieldKey: string;
  valueVerbatim: string;
  clauseLabel: string | null;
  page: number | null;
  confidenceTier: string;
  label: ReturnType<typeof labelForField>;
};

export type PartyIndex = Map<string, { raw: string; citations: Citation[] }>;

/** Every party key the portfolio's extracted party fields yield, with citations. */
export async function buildPartyIndex(workspaceId: string, excludeDocumentId: string): Promise<PartyIndex> {
  const rows = await prisma.extractedField.findMany({
    where: {
      fieldKey: { in: PARTY_FIELD_KEYS },
      valueVerbatim: { not: null },
      document: { workspaceId, id: { not: excludeDocumentId } },
    },
    include: { document: { select: { id: true, filename: true } } },
  });

  const index: PartyIndex = new Map();
  for (const row of rows) {
    const citation: Citation = {
      documentId: row.document.id,
      filename: row.document.filename,
      fieldId: row.id,
      fieldKey: row.fieldKey,
      valueVerbatim: row.valueVerbatim!,
      clauseLabel: row.clauseLabel,
      page: null,
      confidenceTier: row.confidenceTier,
      label: labelForField(row),
    };
    for (const { key, raw } of partyKeysFrom(row.valueVerbatim!)) {
      const entry = index.get(key) ?? { raw, citations: [] };
      entry.citations.push(citation);
      index.set(key, entry);
    }
  }
  return index;
}

type Match = {
  documentId: string;
  filename: string;
  matchedOn: { invoiceParty: string; contractParty: string; partyKey: string }[];
  citations: Citation[];
};

export function matchParties(
  invoiceParties: { name: string }[],
  index: PartyIndex,
): { matches: Match[]; unmatchedInvoiceParties: string[] } {
  const byDoc = new Map<string, Match>();
  const unmatched: string[] = [];

  for (const party of invoiceParties) {
    const keys = partyKeysFrom(party.name);
    let hit = false;
    for (const { key } of keys) {
      const entry = index.get(key);
      if (!entry) continue;
      hit = true;
      for (const citation of entry.citations) {
        const match =
          byDoc.get(citation.documentId) ??
          { documentId: citation.documentId, filename: citation.filename, matchedOn: [], citations: [] };
        if (!match.matchedOn.some((m) => m.partyKey === key && m.invoiceParty === party.name))
          match.matchedOn.push({ invoiceParty: party.name, contractParty: entry.raw, partyKey: key });
        if (!match.citations.some((c) => c.fieldId === citation.fieldId)) match.citations.push(citation);
        byDoc.set(citation.documentId, match);
      }
    }
    if (!hit) unmatched.push(party.name);
  }

  return { matches: [...byDoc.values()], unmatchedInvoiceParties: unmatched };
}

// ---- step 3 (Phase B): temporal validation ----------------------------------

const STATUS = {
  ROGUE: "MISSING CONTRACT - ROGUE INVOICE",
  MULTIPLE: "MULTIPLE CONTRACTS FOUND - MANUAL REVIEW REQUIRED",
  HIGH: "HIGH CONFIDENCE MATCH",
  DATE_MISMATCH: "DATE MISMATCH - MANUAL REVIEW REQUIRED",
  // Not in the original three. It exists because a contract whose dates were never
  // extracted cannot be called a date mismatch (that asserts a conflict we did not
  // find) and must not be called a high-confidence match either.
  DATE_UNVERIFIABLE: "DATE UNVERIFIABLE - MANUAL REVIEW REQUIRED",
  NOT_AN_INVOICE: "NOT AN INVOICE - NOTHING CHECKED",
} as const;

export async function temporalCheck(documentId: string, invoiceDateIso: string | null) {
  const rows = await prisma.extractedField.findMany({
    where: { documentId, fieldKey: { in: ["effective_date", "term_end"] } },
  });

  const read = (key: string) => {
    const row = rows.find((r) => r.fieldKey === key && r.valueVerbatim != null);
    if (!row) return null;
    const parsed = fieldDateIso(row);
    return {
      date: parsed?.date ?? null,
      citation: {
        fieldId: row.id,
        fieldKey: row.fieldKey,
        valueVerbatim: row.valueVerbatim!,
        clauseLabel: row.clauseLabel,
        confidenceTier: row.confidenceTier,
        label: labelForField(row),
      },
    };
  };

  const start = read("effective_date");
  const end = read("term_end");
  const checkedAgainst = [start?.citation, end?.citation].filter(Boolean);

  if (!invoiceDateIso)
    return {
      status: STATUS.DATE_UNVERIFIABLE,
      reason: "No invoice date could be read from the invoice.",
      invoiceDate: null,
      window: { from: start?.date ?? null, to: end?.date ?? null },
      checkedAgainst,
    };

  if (!start?.date && !end?.date)
    return {
      status: STATUS.DATE_UNVERIFIABLE,
      reason:
        "Neither effective_date nor term_end is available as a readable date on the matched contract, so the invoice date cannot be placed inside or outside its term.",
      invoiceDate: invoiceDateIso,
      window: { from: null, to: null },
      checkedAgainst,
    };

  const afterStart = !start?.date || invoiceDateIso >= start.date;
  const beforeEnd = !end?.date || invoiceDateIso <= end.date;
  const inWindow = afterStart && beforeEnd;

  const bound = !start?.date
    ? `on or before term_end (${end!.date})`
    : !end?.date
      ? `on or after effective_date (${start.date})`
      : `between effective_date (${start.date}) and term_end (${end.date})`;

  return {
    status: inWindow ? STATUS.HIGH : STATUS.DATE_MISMATCH,
    reason: inWindow
      ? `Invoice date ${invoiceDateIso} falls ${bound}.`
      : `Invoice date ${invoiceDateIso} does not fall ${bound}.`,
    invoiceDate: invoiceDateIso,
    window: { from: start?.date ?? null, to: end?.date ?? null },
    /** Partial windows are checked, but the reader is told the check was one-sided. */
    partialWindow: !start?.date || !end?.date,
    checkedAgainst,
  };
}

// ---- the route --------------------------------------------------------------

export async function registerInvoiceRoutes(app: FastifyInstance) {
  const params = z.object({ documentId: z.string().uuid() });

  app.post("/api/invoices/:documentId/match", async (req) => {
    const { documentId } = params.parse(req.params);
    const workspaceId = await getWorkspaceId();

    const doc = await prisma.document.findFirst({ where: { id: documentId, workspaceId } });
    if (!doc) throw notFound("Document not found");

    const source = await invoiceText(documentId);

    const read = await askForJson({
      system: READER_SYSTEM,
      user: source.text.slice(0, 12_000),
      schema: invoiceReadSchema,
      maxTokens: 1200,
    });

    const invoice = {
      // Labelled at the boundary: nothing here carries a contract confidence tier.
      evidence: "model_read" as const,
      textSource: source.source,
      textSourceNote: source.note,
      isInvoice: read.is_invoice,
      number: read.invoice_number,
      dateRaw: read.invoice_date,
      dateIso: read.invoice_date ? parseIsoDate(read.invoice_date) : null,
      billingParties: read.billing_parties,
      lineItems: read.line_items,
    };

    const base = {
      resultChannel: "invoice_match" as const, // never the conflicts table
      documentId,
      filename: doc.filename,
      invoice,
      limitations: [
        "Party matching is exact-name only, reusing the rule the conflict engine uses (src/pdf_analyzer/pipeline.py:_exact_party_key). No fuzzy matching, no suffix normalisation: \"Acme Industries Pte Ltd\" will not match \"Acme Industrial Ltd\".",
        "For invoices this is stricter than reality, because a biller often abbreviates its own name. Expect MISSING CONTRACT results that a human would match. Fuzzy matching was deliberately not added here so that \"the same party\" keeps one meaning across this feature and conflict detection.",
        "Only contracts whose party fields were extracted can be matched. A contract in the portfolio whose parties were never extracted is invisible to this check.",
        ...(source.note ? [source.note] : []),
      ],
    };

    if (!read.is_invoice)
      return {
        ...base,
        status: STATUS.NOT_AN_INVOICE,
        phase: "A" as const,
        reason: "The document was not read as an invoice, bill or statement of charges.",
        matches: [],
        checkedAgainst: [],
      };

    const index = await buildPartyIndex(workspaceId, documentId);
    const { matches, unmatchedInvoiceParties } = matchParties(invoice.billingParties, index);

    if (matches.length === 0)
      return {
        ...base,
        status: STATUS.ROGUE,
        phase: "A" as const,
        reason:
          invoice.billingParties.length === 0
            ? "No billing party could be read from the invoice, so there was nothing to match."
            : `None of the billing parties (${invoice.billingParties.map((p) => p.name).join(", ")}) matches a party name extracted from any contract in the portfolio.`,
        matches: [],
        unmatchedInvoiceParties,
        /** The population searched, so "no match" is a measured result, not a shrug. */
        searched: { contractPartyKeys: index.size },
        checkedAgainst: [],
      };

    if (matches.length > 1)
      return {
        ...base,
        status: STATUS.MULTIPLE,
        phase: "A" as const,
        reason: `${matches.length} contracts share a party name with this invoice. Which one it bills against cannot be decided from the party name alone.`,
        matches,
        unmatchedInvoiceParties,
        checkedAgainst: matches.flatMap((m) => m.citations),
      };

    const match = matches[0]!;
    const temporal = await temporalCheck(match.documentId, invoice.dateIso);

    return {
      ...base,
      status: temporal.status,
      phase: "B" as const,
      reason: temporal.reason,
      matches,
      unmatchedInvoiceParties,
      match: {
        documentId: match.documentId,
        filename: match.filename,
        matchedOn: match.matchedOn,
      },
      temporal,
      // Party citations plus the date fields the temporal check read.
      checkedAgainst: [
        ...match.citations,
        ...temporal.checkedAgainst.map((c) => ({ ...c, documentId: match.documentId, filename: match.filename })),
      ],
    };
  });
}
