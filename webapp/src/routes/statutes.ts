import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { prisma } from "../db.js";
import { getWorkspaceId } from "../lib/workspace.js";
import { badRequest, notFound } from "../lib/errors.js";
import { evaluateClause, jurisdictionFor } from "../lib/statute_match.js";

// No auth in this build — one operator. Client may pass an author; default here.
const DEFAULT_AUTHOR = "andric.ang@gmail.com";

// A verify action maps to a resolved review status. Agree/Disagree are meant for
// Inferred + Evaluation Required flags; Raise Manual Review works on any.
const REVIEW_STATUS: Record<string, string> = {
  agree: "human_verified",
  disagree: "overridden",
  manual_review: "manual_review",
};

function serializeAnnotation(a: { id: string; kind: string; author: string; body: string | null; createdAt: Date }) {
  return { id: a.id, kind: a.kind, author: a.author, body: a.body, createdAt: a.createdAt.toISOString() };
}

export async function registerStatuteRoutes(app: FastifyInstance) {
  // ---- List (grouped client-side by source) ------------------------------
  app.get("/api/statutes", async () => {
    const workspaceId = await getWorkspaceId();
    const rows = await prisma.statuteClause.findMany({
      where: { workspaceId },
      orderBy: [{ source: "asc" }, { provision: "asc" }],
      include: { _count: { select: { annotations: true } } },
    });
    return {
      clauses: rows.map((c) => ({
        id: c.id,
        clauseKey: c.clauseKey,
        source: c.source,
        provision: c.provision,
        aiStatus: c.aiStatus,
        reviewStatus: c.reviewStatus,
        annotationCount: c._count.annotations,
      })),
    };
  });

  // ---- Detail + audit trail ----------------------------------------------
  app.get<{ Params: { id: string } }>("/api/statutes/:id", async (req) => {
    const clause = await prisma.statuteClause.findUnique({
      where: { id: req.params.id },
      include: { annotations: { orderBy: { createdAt: "asc" } } },
    });
    if (!clause) throw notFound("Statute clause not found.");
    return {
      id: clause.id,
      clauseKey: clause.clauseKey,
      source: clause.source,
      provision: clause.provision,
      exactWording: clause.exactWording,
      summary: clause.summary,
      aiStatus: clause.aiStatus,
      reviewStatus: clause.reviewStatus,
      authorityBasis: clause.authorityBasis,
      caseCitation: clause.caseCitation,
      naReason: clause.naReason,
      targetFields: clause.targetFields,
      applicableContractTypes: clause.applicableContractTypes,
      annotations: clause.annotations.map(serializeAnnotation),
    };
  });

  // ---- Append a note / justification (audit trail) -----------------------
  const noteBody = z.object({ body: z.string().min(1).max(4000), author: z.string().max(200).optional() });
  app.post<{ Params: { id: string } }>("/api/statutes/:id/notes", async (req, reply) => {
    const { body, author } = noteBody.parse(req.body);
    const clause = await prisma.statuteClause.findUnique({ where: { id: req.params.id } });
    if (!clause) throw notFound("Statute clause not found.");
    const annotation = await prisma.clauseAnnotation.create({
      data: { clauseId: clause.id, kind: "note", author: author ?? DEFAULT_AUTHOR, body },
    });
    return reply.code(201).send(serializeAnnotation(annotation));
  });

  // ---- Verify: agree / disagree / raise manual review --------------------
  const verifyBody = z.object({
    action: z.enum(["agree", "disagree", "manual_review"]),
    note: z.string().max(4000).optional(),
    author: z.string().max(200).optional(),
  });
  app.post<{ Params: { id: string } }>("/api/statutes/:id/verify", async (req) => {
    const { action, note, author } = verifyBody.parse(req.body);
    const clause = await prisma.statuteClause.findUnique({ where: { id: req.params.id } });
    if (!clause) throw notFound("Statute clause not found.");
    const reviewStatus = REVIEW_STATUS[action];
    if (!reviewStatus) throw badRequest("Unknown verify action.");

    const [, updated, annotations] = await prisma.$transaction([
      prisma.clauseAnnotation.create({
        data: { clauseId: clause.id, kind: action, author: author ?? DEFAULT_AUTHOR, body: note ?? null },
      }),
      prisma.statuteClause.update({ where: { id: clause.id }, data: { reviewStatus } }),
      prisma.clauseAnnotation.findMany({ where: { clauseId: clause.id }, orderBy: { createdAt: "asc" } }),
    ]);

    return { id: updated.id, reviewStatus: updated.reviewStatus, annotations: annotations.map(serializeAnnotation) };
  });

  // ---- Per-contract: statutes applicable to a specific document ----------
  app.get<{ Params: { id: string } }>("/api/documents/:id/statutes", async (req) => {
    const documentId = req.params.id;
    const doc = await prisma.document.findUnique({ where: { id: documentId }, select: { id: true, docType: true, workspaceId: true } });
    if (!doc) throw notFound("Document not found.");

    const govField = await prisma.extractedField.findFirst({
      where: { documentId, fieldKey: "governing_law" },
      select: { valueVerbatim: true },
    });
    const jurisdiction = jurisdictionFor(govField?.valueVerbatim ?? null);

    const [clauses, reviews, annotations] = await Promise.all([
      prisma.statuteClause.findMany({ where: { workspaceId: doc.workspaceId }, orderBy: [{ source: "asc" }, { provision: "asc" }] }),
      prisma.contractClauseReview.findMany({ where: { documentId } }),
      prisma.clauseAnnotation.findMany({ where: { documentId }, orderBy: { createdAt: "asc" } }),
    ]);
    const reviewByClause = new Map(reviews.map((r) => [r.clauseId, r.reviewStatus]));
    const notesByClause = new Map<string, typeof annotations>();
    for (const a of annotations) {
      const arr = notesByClause.get(a.clauseId) ?? [];
      arr.push(a);
      notesByClause.set(a.clauseId, arr);
    }

    const items = clauses
      .map((c) => {
        const res = evaluateClause(c, doc.docType, jurisdiction);
        if (!res.applies) return null;
        return {
          id: c.id,
          clauseKey: c.clauseKey,
          source: c.source,
          provision: c.provision,
          exactWording: c.exactWording,
          summary: c.summary,
          status: res.status, // per-contract status
          reason: res.reason,
          authorityBasis: c.authorityBasis,
          caseCitation: c.caseCitation,
          targetFields: c.targetFields,
          reviewStatus: reviewByClause.get(c.id) ?? "open",
          annotations: (notesByClause.get(c.id) ?? []).map(serializeAnnotation),
        };
      })
      .filter((x): x is NonNullable<typeof x> => x != null);

    return { documentId, jurisdiction, docType: doc.docType, statutes: items };
  });

  app.post<{ Params: { id: string; clauseId: string } }>("/api/documents/:id/statutes/:clauseId/notes", async (req, reply) => {
    const { body, author } = noteBody.parse(req.body);
    const { id: documentId, clauseId } = req.params;
    const clause = await prisma.statuteClause.findUnique({ where: { id: clauseId } });
    if (!clause) throw notFound("Statute clause not found.");
    const annotation = await prisma.clauseAnnotation.create({
      data: { clauseId, documentId, kind: "note", author: author ?? DEFAULT_AUTHOR, body },
    });
    return reply.code(201).send(serializeAnnotation(annotation));
  });

  app.post<{ Params: { id: string; clauseId: string } }>("/api/documents/:id/statutes/:clauseId/verify", async (req) => {
    const { action, note, author } = verifyBody.parse(req.body);
    const { id: documentId, clauseId } = req.params;
    const reviewStatus = REVIEW_STATUS[action];
    if (!reviewStatus) throw badRequest("Unknown verify action.");
    const clause = await prisma.statuteClause.findUnique({ where: { id: clauseId } });
    if (!clause) throw notFound("Statute clause not found.");

    const [, review, annotations] = await prisma.$transaction([
      prisma.clauseAnnotation.create({
        data: { clauseId, documentId, kind: action, author: author ?? DEFAULT_AUTHOR, body: note ?? null },
      }),
      prisma.contractClauseReview.upsert({
        where: { documentId_clauseId: { documentId, clauseId } },
        create: { documentId, clauseId, reviewStatus },
        update: { reviewStatus },
      }),
      prisma.clauseAnnotation.findMany({ where: { documentId, clauseId }, orderBy: { createdAt: "asc" } }),
    ]);

    return { clauseId, reviewStatus: review.reviewStatus, annotations: annotations.map(serializeAnnotation) };
  });
}
