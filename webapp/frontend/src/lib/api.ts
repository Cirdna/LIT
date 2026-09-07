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
  humanEdited: boolean;
  editedBy: string | null;
  editedAt: string | null;
  citationPage?: number | null; // resolved on the detail endpoint
};

export type FieldState = "quoted" | "inferred" | "evaluation_required" | "na";

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

export type DocumentDetail = DocumentSummary & {
  pages: PageDTO[];
  fields: FieldDTO[];
  segments: SegmentDTO[];
  job: JobStatus;
  invoice: InvoiceDTO | null;
};

export type InvoiceMatchStatus =
  | "HIGH_CONFIDENCE_MATCH"
  | "MISSING_CONTRACT_ROGUE"
  | "MULTIPLE_CONTRACTS_REVIEW"
  | "DATE_MISMATCH_REVIEW";

export type InvoiceDTO = {
  header: {
    billingFrom: string | null;
    billingTo: string | null;
    invoiceDate: string | null;
    invoiceNumber: string | null;
    currency: string | null;
    total: number | null;
    confidenceTier: ConfidenceTier;
  };
  lineItems: { id: string; description: string; quantity: number | null; amount: number | null }[];
  match: {
    status: InvoiceMatchStatus;
    confidenceTier: ConfidenceTier;
    reasons: string[];
    matchedOn: unknown;
    contract: { id: string; filename: string; counterparty: string | null } | null;
  } | null;
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
  updateField: (docId: string, fieldId: string, patch: { state: FieldState; value?: string | null; clauseLabel?: string | null }) =>
    req<FieldDTO>(`/documents/${docId}/fields/${fieldId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    }),
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
  recheckConflicts: () => req<{ enqueued: boolean; jobId: string }>("/conflicts/recheck", { method: "POST" }),
  handoffs: () => req<{ handoffs: HandoffDTO[] }>("/handoffs"),
  handoff: (id: string) => req<HandoffDTO>(`/handoffs/${id}`),
  createHandoff: (conflictId: string) =>
    req<HandoffDTO>("/handoffs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ conflictId }),
    }),

  benchmarks: (documentId: string) =>
    req<{ documentId: string; benchmarks: BenchmarkDTO[] }>(`/benchmark?documentId=${documentId}`),

  chat: (message: string, history: { role: "user" | "assistant"; content: string }[]) =>
    req<ChatResponse>("/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message, history }),
    }),

  statutes: () => req<{ clauses: StatuteClauseSummary[] }>("/statutes"),
  statute: (id: string) => req<StatuteClauseDetail>(`/statutes/${id}`),
  addStatuteNote: (id: string, body: string) =>
    req<ClauseAnnotation>(`/statutes/${id}/notes`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ body }),
    }),
  verifyStatute: (id: string, action: "agree" | "disagree" | "manual_review", note?: string) =>
    req<{ id: string; reviewStatus: ReviewStatus; annotations: ClauseAnnotation[] }>(`/statutes/${id}/verify`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action, note }),
    }),

  documentStatutes: (docId: string) =>
    req<{ documentId: string; jurisdiction: string; docType: string | null; statutes: ContractStatute[] }>(
      `/documents/${docId}/statutes`,
    ),
  addDocStatuteNote: (docId: string, clauseId: string, body: string) =>
    req<ClauseAnnotation>(`/documents/${docId}/statutes/${clauseId}/notes`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ body }),
    }),
  verifyDocStatute: (docId: string, clauseId: string, action: "agree" | "disagree" | "manual_review", note?: string) =>
    req<{ clauseId: string; reviewStatus: ReviewStatus; annotations: ClauseAnnotation[] }>(
      `/documents/${docId}/statutes/${clauseId}/verify`,
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ action, note }) },
    ),
};

export type ContractStatute = {
  id: string;
  clauseKey: string;
  source: string;
  provision: string;
  exactWording: string;
  summary: string | null;
  status: AiStatus; // per-contract status
  reason: string | null;
  authorityBasis: string | null;
  caseCitation: string | null;
  targetFields: string[];
  reviewStatus: ReviewStatus;
  annotations: ClauseAnnotation[];
};

export type AiStatus = "Quoted" | "Inferred" | "Evaluation Required" | "NA";
export type ReviewStatus = "open" | "human_verified" | "overridden" | "manual_review";

export type StatuteClauseSummary = {
  id: string;
  clauseKey: string;
  source: string;
  provision: string;
  aiStatus: AiStatus;
  reviewStatus: ReviewStatus;
  annotationCount: number;
};

export type ClauseAnnotation = {
  id: string;
  kind: "note" | "agree" | "disagree" | "manual_review";
  author: string;
  body: string | null;
  createdAt: string;
};

export type StatuteClauseDetail = {
  id: string;
  clauseKey: string;
  source: string;
  provision: string;
  exactWording: string;
  summary: string | null;
  aiStatus: AiStatus;
  reviewStatus: ReviewStatus;
  authorityBasis: string | null;
  caseCitation: string | null;
  naReason: string | null;
  targetFields: string[];
  applicableContractTypes: string[];
  annotations: ClauseAnnotation[];
};

export type ChatResultField = {
  fieldKey: string;
  value: string | null;
  normalized: unknown;
  confidenceTier: ConfidenceTier;
  clauseLabel: string | null;
  absenceReason: string | null;
};
export type ChatResult = {
  documentId: string;
  filename: string;
  counterparty: string | null;
  docType: string | null;
  fields: ChatResultField[];
};
export type ChatResponse =
  | { status: "need_clarification"; question: string }
  | { status: "answered"; answer: string; results: ChatResult[]; params?: unknown };

export type BenchmarkDTO = {
  category: string;
  label: string;
  unit: string;
  direction: "higher_better" | "lower_better" | "neutral";
  value: number;
  average: number;
  deviation: number;
  percentWorse: number;
  sampleSize: number;
  risk: "green" | "yellow" | "red";
};

export const pageImageUrl = (documentId: string, pageNumber: number) =>
  `/api/documents/${documentId}/pages/${pageNumber}/image`;
