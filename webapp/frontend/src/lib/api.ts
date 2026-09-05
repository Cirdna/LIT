// Thin typed client over the Node API. TanStack Query owns caching/polling on
// top of these; there is no client-side global store — the server is the state.

export type ConfidenceTier = "verbatim" | "normalised" | "assembled" | "inferred" | "unverified";
export type ClaimType = "contract_text" | "computed" | "benchmark";
export type AbsenceReason = "not_present" | "not_found" | "illegible";

export type FieldDTO = {
  id: string;
  documentId: string;
  fieldKey: string;
  valueVerbatim: string | null;
  valueNormalized: Record<string, unknown> | null;
  confidenceTier: ConfidenceTier;
  claimType: ClaimType;
  absenceReason: AbsenceReason | null;
  anchorLineIds: string[];
  segmentKey: string | null;
  clauseLabel: string | null;
  consistencyScore: number | null;
  vlmAgreement: number | null;
  modelVersion: string | null;
  citationPage?: number | null; // resolved on the detail endpoint
};

export type PageDTO = {
  id: string;
  pageNumber: number;
  width: number;
  height: number;
  extractionMethod: string;
  ocrConfMean: number | null;
  pageRole: string | null;
  imageDpi: number | null;
  hasImage: boolean;
};

export type SegmentDTO = {
  segmentKey: string;
  level: number;
  numberLabel: string | null;
  headingText: string | null;
  pageStart: number;
  pageEnd: number;
  confidence: string;
};

export type DocumentSummary = {
  id: string;
  filename: string;
  status: string;
  provenanceQuality: string | null;
  pageCount: number | null;
  ocrApplied: boolean;
  docType: string | null;
  docTypeConf: number | null;
  counterparty: string | null;
  warnings: string[];
  error: string | null;
  uploadedAt: string;
  processedAt: string | null;
  // present on the portfolio list rows (enriched from other tables)
  termEnd?: string | null;
  nextActionDate?: string | null;
  needsReview?: boolean;
};

export type JobStatus = {
  id: string;
  status: string;
  stage: string | null;
  progress: number;
  attempts: number;
  error: string | null;
} | null;

// The statute layer. Note the absence of `confidenceTier` on both: neither is an
// extraction, so neither carries a read-quality signal. See lib/confidence.tsx.
export type StatutoryDefaultDTO = {
  id: string;
  fieldName: string;
  statute: string;
  citation: string;
  jurisdiction: string;
  effect: string;
  appliesWhen: string;
  autoDisplacementSupported: boolean;
  isDisplaced: boolean;
  displacedByClause: string | null;
  displacedByPage: number | null;
};

export type StatuteFlagDTO = {
  id: string;
  statute: string;
  citation: string;
  jurisdiction: string;
  cuadCategory: string;
  fieldKey: string | null;
  trigger: string;
  reviewRequired: string;
  factors: string[];
  excerpt: string;
  sourceClause: string | null;
  sourcePage: number | null;
  reasonablenessTestApplies: boolean | null;
  requiresHumanReview: boolean;
};

export type DocumentDetail = DocumentSummary & {
  pages: PageDTO[];
  fields: FieldDTO[];
  segments: SegmentDTO[];
  statutoryDefaults: StatutoryDefaultDTO[];
  statuteFlags: StatuteFlagDTO[];
  job: JobStatus;
};

export type CalendarEventDTO = {
  id: string;
  documentId: string;
  eventType: string;
  eventDate: string;
  actionByDate: string | null;
  title: string;
  detail: string | null;
  confidenceTier: ConfidenceTier;
  sourceFieldIds: string[];
  status: string;
};

export type ConflictDTO = {
  id: string;
  conflictType: string;
  severity: string;
  summary: string;
  documentIds: string[];
  fieldIds: string[];
  confidenceTier: ConfidenceTier;
  createdAt: string;
  documents: DocumentSummary[];
  fields: FieldDTO[];
};

export type EstablishedItem = {
  label: string;
  detail: string | null;
  citation: string | null;
  confidenceTier: string;
};

export type HandoffDTO = {
  id: string;
  trigger: string;
  issue: string;
  established: EstablishedItem[];
  question: string;
  documentIds: string[];
  createdAt: string;
  documents?: DocumentSummary[];
};

export type PortfolioSummary = {
  today: string;
  totalDocuments: number;
  contractsTracked: number;
  actionsNext90: number;
  overdue: number;
  conflictsFound: number;
  documentsNeedingReview: number;
  statusCounts: Record<string, number>;
  processing: number;
};

export type AnchorDTO = {
  lineId: string;
  page: number;
  bbox: { x0: number; y0: number; x1: number; y1: number };
  text: string;
};

// ---- Ask (portfolio question answering) -------------------------------------
// The model returns a FILTER, never an answer. Every value in `matches` is a real
// `extracted_fields` row and renders through the same badge as everywhere else.

export type PortfolioFilter = {
  fieldKeys: string[];
  valueContains?: string;
  counterpartyContains?: string;
  labels?: ("quoted" | "inferred" | "na")[];
  duration?: { op: "lt" | "lte" | "gt" | "gte" | "eq"; days: number };
  date?: { op: "before" | "after" | "between"; from?: string; to?: string };
  limit: number;
};

export type AskMatch = {
  documentId: string;
  filename: string;
  counterparty: string | null;
  field: FieldDTO;
  label: "quoted" | "inferred" | "na";
  comparison:
    | { kind: "duration"; days: number; from: string }
    | { kind: "date"; date: string; from: string }
    | null;
  statuteFlags: StatuteFlagDTO[];
};

export type AskResponse =
  | { mode: "clarify"; question: string; why: string | null; originalQuery: string }
  | {
      mode: "results";
      restated: string | null;
      filter: PortfolioFilter;
      matches: AskMatch[];
      totalMatched: number;
      truncated: boolean;
      skippedUnparseable: number;
      unknownKeys: string[];
      noSuchField: boolean;
      note: string;
    };

export type AskCapabilities = {
  llmConfigured: boolean;
  model: string | null;
  searchableFieldKeys: string[];
  limits: string[];
};

// ---- Benchmarking -----------------------------------------------------------

export type BenchmarkSample = {
  documentId: string;
  filename: string;
  counterparty: string | null;
  fieldId: string;
  value: number;
  display: string;
  valueVerbatim: string;
  clauseLabel: string | null;
  confidenceTier: ConfidenceTier;
  label: "quoted" | "inferred" | "na";
  readFrom: "normalized" | "parsed";
};

export type BenchmarkResponse = {
  fieldKey: string;
  fieldLabel: string;
  kind: "duration" | "date";
  polarity: "higher_is_better" | "lower_is_better" | "undefined";
  polarityNote: string | null;
  sampleSize: number;
  mean: number | null;
  meanDisplay: string | null;
  median: number | null;
  medianDisplay: string | null;
  samples: BenchmarkSample[];
  excluded: { documentId: string; filename: string; valueVerbatim: string; reason: string }[];
  sampleNote: string;
  selected:
    | (BenchmarkSample & {
        peerMean: number | null;
        peerCount: number;
        deviation: number | null;
        deviationDisplay: string | null;
        worsePct: number | null;
        light: "green" | "yellow" | "red" | "unrated";
        glyph: string;
        summary: string;
        note: string | null;
      })
    | null;
};

export type BenchmarkFields = {
  fields: {
    fieldKey: string;
    label: string;
    kind: "duration" | "date";
    polarity: string;
    polarityNote: string | null;
  }[];
  thresholds: Record<string, string>;
};

// ---- Invoice matching -------------------------------------------------------

export type InvoiceCitation = {
  documentId: string;
  filename?: string;
  fieldId: string;
  fieldKey: string;
  valueVerbatim: string;
  clauseLabel: string | null;
  confidenceTier: ConfidenceTier;
  label: "quoted" | "inferred" | "na";
};

export type InvoiceMatchResponse = {
  resultChannel: "invoice_match";
  documentId: string;
  filename: string;
  status: string;
  phase: "A" | "B";
  reason: string;
  invoice: {
    evidence: "model_read";
    textSource: "document_text" | "analysis_spans";
    textSourceNote: string | null;
    isInvoice: boolean;
    number: string | null;
    dateRaw: string | null;
    dateIso: string | null;
    billingParties: { name: string; role: string }[];
    lineItems: { description: string; amount: number | null; currency: string | null }[];
  };
  matches: {
    documentId: string;
    filename: string;
    matchedOn: { invoiceParty: string; contractParty: string; partyKey: string }[];
    citations: InvoiceCitation[];
  }[];
  unmatchedInvoiceParties?: string[];
  searched?: { contractPartyKeys: number };
  match?: { documentId: string; filename: string; matchedOn: { invoiceParty: string; contractParty: string }[] };
  temporal?: {
    status: string;
    reason: string;
    invoiceDate: string | null;
    window: { from: string | null; to: string | null };
    partialWindow?: boolean;
  };
  checkedAgainst: InvoiceCitation[];
  limitations: string[];
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init);
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body?.error?.message ?? message;
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  portfolio: () => req<PortfolioSummary>("/portfolio/summary"),

  documents: (params: URLSearchParams) =>
    req<{ documents: DocumentSummary[]; counts: Record<string, number>; total: number; nextCursor: string | null }>(
      `/documents?${params.toString()}`,
    ),

  document: (id: string) => req<DocumentDetail>(`/documents/${id}`),
  documentStatus: (id: string) =>
    req<{ id: string; status: string; stage: string | null; progress: number }>(`/documents/${id}/status`),
  documentText: (id: string) => req<{ documentId: string; text: string }>(`/documents/${id}/text`),
  anchors: (id: string, lineIds: string[]) =>
    req<AnchorDTO[]>(`/documents/${id}/anchors?lineIds=${lineIds.join(",")}`),
  deleteDocument: (id: string) => req<void>(`/documents/${id}`, { method: "DELETE" }),

  upload: (files: File[]) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    return req<{ id?: string; filename: string; status: string; jobId?: string; duplicate?: boolean; error?: string }[]>(
      "/documents",
      { method: "POST", body: fd },
    );
  },

  calendar: (params: URLSearchParams) =>
    req<{ today: string; to: string; events: CalendarEventDTO[] }>(`/calendar?${params.toString()}`),
  patchEvent: (id: string, status: string) =>
    req<CalendarEventDTO>(`/calendar/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status }),
    }),

  conflicts: () => req<{ conflicts: ConflictDTO[] }>("/conflicts"),
  handoffs: () => req<{ handoffs: HandoffDTO[] }>("/handoffs"),
  handoff: (id: string) => req<HandoffDTO>(`/handoffs/${id}`),
  createHandoff: (conflictId: string) =>
    req<HandoffDTO>("/handoffs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ conflictId }),
    }),

  askCapabilities: () => req<AskCapabilities>("/chat/capabilities"),
  ask: (query: string, clarifying?: { originalQuery: string; question: string }) =>
    req<AskResponse>("/chat/query", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query, clarifying }),
    }),

  benchmarkFields: () => req<BenchmarkFields>("/benchmark/fields"),
  benchmark: (fieldKey: string, documentId?: string) =>
    req<BenchmarkResponse>(
      `/benchmark?fieldKey=${encodeURIComponent(fieldKey)}${documentId ? `&documentId=${documentId}` : ""}`,
    ),

  matchInvoice: (documentId: string) =>
    req<InvoiceMatchResponse>(`/invoices/${documentId}/match`, { method: "POST" }),
};

export const pageImageUrl = (documentId: string, pageNumber: number) =>
  `/api/documents/${documentId}/pages/${pageNumber}/image`;
