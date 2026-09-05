// DB row -> API DTO. The return types here deliberately make confidenceTier and
// claimType NON-optional: dropping them in a serializer is the single commonest
// way the confidence signal fails to reach the UI (§14), so we make it a compile
// error rather than a code review note.
import type {
  CalendarEvent,
  Conflict,
  Document,
  DocumentPage,
  DocumentSegment,
  ExtractedField,
  HandoffBrief,
  Job,
} from "@prisma/client";
import type { AbsenceReason, ClaimType, ConfidenceTier } from "./domain.js";

/** A date column (@db.Date) as YYYY-MM-DD, no timezone games. */
function dateOnly(d: Date | null): string | null {
  return d ? d.toISOString().slice(0, 10) : null;
}

export type FieldDTO = {
  id: string;
  documentId: string;
  fieldKey: string;
  valueVerbatim: string | null;
  valueNormalized: unknown;
  confidenceTier: ConfidenceTier; // required — see file header
  claimType: ClaimType; // required — see file header
  absenceReason: AbsenceReason | null;
  anchorLineIds: string[];
  segmentKey: string | null;
  clauseLabel: string | null;
  consistencyScore: number | null;
  vlmAgreement: number | null;
  modelVersion: string | null;
};

export function serializeField(f: ExtractedField): FieldDTO {
  return {
    id: f.id,
    documentId: f.documentId,
    fieldKey: f.fieldKey,
    valueVerbatim: f.valueVerbatim,
    valueNormalized: f.valueNormalized ?? null,
    confidenceTier: f.confidenceTier as ConfidenceTier,
    claimType: f.claimType as ClaimType,
    absenceReason: (f.absenceReason as AbsenceReason | null) ?? null,
    anchorLineIds: f.anchorLineIds,
    segmentKey: f.segmentKey,
    clauseLabel: f.clauseLabel,
    consistencyScore: f.consistencyScore,
    vlmAgreement: f.vlmAgreement,
    modelVersion: f.modelVersion,
  };
}

export function serializePage(p: DocumentPage) {
  return {
    id: p.id,
    pageNumber: p.pageNumber,
    width: p.width,
    height: p.height,
    extractionMethod: p.extractionMethod,
    ocrConfMean: p.ocrConfMean,
    pageRole: p.pageRole,
    imageDpi: p.imageDpi,
    hasImage: p.imageKey != null,
  };
}

export function serializeSegment(s: DocumentSegment) {
  return {
    segmentKey: s.segmentKey,
    level: s.level,
    numberLabel: s.numberLabel,
    headingText: s.headingText,
    pageStart: s.pageStart,
    pageEnd: s.pageEnd,
    confidence: s.confidence,
  };
}

export function serializeDocumentSummary(d: Document) {
  return {
    id: d.id,
    filename: d.filename,
    status: d.status,
    provenanceQuality: d.provenanceQuality,
    pageCount: d.pageCount,
    ocrApplied: d.ocrApplied,
    docType: d.docType,
    docTypeConf: d.docTypeConf,
    counterparty: d.counterparty,
    warnings: d.warnings,
    error: d.error,
    uploadedAt: d.uploadedAt.toISOString(),
    processedAt: d.processedAt ? d.processedAt.toISOString() : null,
  };
}

export function serializeCalendarEvent(e: CalendarEvent) {
  return {
    id: e.id,
    documentId: e.documentId,
    eventType: e.eventType,
    eventDate: dateOnly(e.eventDate)!,
    actionByDate: dateOnly(e.actionByDate),
    title: e.title,
    detail: e.detail,
    confidenceTier: e.confidenceTier as ConfidenceTier, // required
    sourceFieldIds: e.sourceFieldIds,
    status: e.status,
  };
}

export function serializeConflict(c: Conflict) {
  return {
    id: c.id,
    conflictType: c.conflictType,
    severity: c.severity,
    summary: c.summary,
    documentIds: c.documentIds,
    fieldIds: c.fieldIds,
    confidenceTier: c.confidenceTier as ConfidenceTier, // required
    createdAt: c.createdAt.toISOString(),
  };
}

export function serializeHandoff(h: HandoffBrief) {
  return {
    id: h.id,
    trigger: h.trigger,
    issue: h.issue,
    established: h.established,
    question: h.question,
    documentIds: h.documentIds,
    createdAt: h.createdAt.toISOString(),
  };
}

export function serializeJobStatus(job: Job | null) {
  if (!job) return null;
  return {
    id: job.id,
    status: job.status,
    stage: job.stage,
    progress: job.progress,
    attempts: job.attempts,
    error: job.error,
  };
}
