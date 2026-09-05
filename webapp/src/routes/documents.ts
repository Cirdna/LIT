import { readFile } from "node:fs/promises";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { Prisma } from "@prisma/client";
import { prisma } from "../db.js";
import { storage } from "../config.js";
import { getWorkspaceId } from "../lib/workspace.js";
import { badRequest, notFound } from "../lib/errors.js";
import { ACCEPTED_FORMATS, sniff } from "../lib/magic.js";
import {
  deleteDocumentFiles,
  discardTmp,
  persistToTmp,
  promoteToOriginal,
} from "../lib/storage.js";
import {
  serializeDocumentSummary,
  serializeField,
  serializePage,
  serializeSegment,
  serializeJobStatus,
} from "../lib/serialize.js";

// Opaque offset cursor. Keeps clients from depending on the encoding.
function encodeCursor(offset: number): string {
  return Buffer.from(String(offset)).toString("base64url");
}
function decodeCursor(cursor: string | undefined): number {
  if (!cursor) return 0;
  const n = Number(Buffer.from(cursor, "base64url").toString("utf8"));
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

type UploadEntry = {
  id?: string;
  filename: string;
  status: string;
  jobId?: string;
  duplicate?: boolean;
  error?: string;
};

export async function registerDocumentRoutes(app: FastifyInstance) {
  // ---- Upload (multipart, 1..n files) -----------------------------------
  app.post("/api/documents", async (req, reply) => {
    if (!req.isMultipart()) throw badRequest("Send the files as multipart/form-data.");
    const workspaceId = await getWorkspaceId();
    const entries: UploadEntry[] = [];

    for await (const part of req.parts()) {
      if (part.type !== "file") continue;
      const filename = part.filename || "upload";

      const persisted = await persistToTmp(part.file);

      // Record a rejected upload as an `unsupported` row, deduped by content so a
      // repeated bad file returns duplicate instead of colliding — and never
      // aborts the rest of the batch.
      const reject = async (sha256: string, error: string) => {
        await discardTmp(persisted.tmpPath);
        const existing = await prisma.document.findUnique({
          where: { workspaceId_sha256: { workspaceId, sha256 } },
        });
        if (existing) {
          entries.push({ id: existing.id, filename, status: existing.status, duplicate: true, error: existing.error ?? undefined });
          return;
        }
        const doc = await prisma.document.create({
          data: {
            workspaceId,
            filename,
            sha256,
            byteSize: BigInt(persisted.byteSize),
            mimeType: "application/octet-stream",
            storageKey: "",
            status: "unsupported",
            error,
          },
        });
        entries.push({ id: doc.id, filename, status: "unsupported", error: doc.error! });
      };

      // @fastify/multipart flags truncation when a file exceeds the size limit.
      if (part.file.truncated) {
        await reject(`rejected-${persisted.sha256}`, "File is larger than 50 MB and was not stored.");
        continue;
      }

      const kind = sniff(persisted.head);
      if (!kind) {
        await reject(`unsupported-${persisted.sha256}`, `Unsupported file type. Accepted formats: ${ACCEPTED_FORMATS}.`);
        continue;
      }

      // Dedup by content hash within the workspace.
      const existing = await prisma.document.findUnique({
        where: { workspaceId_sha256: { workspaceId, sha256: persisted.sha256 } },
      });
      if (existing) {
        await discardTmp(persisted.tmpPath);
        entries.push({ id: existing.id, filename, status: existing.status, duplicate: true });
        continue;
      }

      const storageKey = storage.originalKey(persisted.sha256, kind.ext);
      await promoteToOriginal(persisted.tmpPath, storageKey);

      const doc = await prisma.document.create({
        data: {
          workspaceId,
          filename,
          sha256: persisted.sha256,
          byteSize: BigInt(persisted.byteSize),
          mimeType: kind.mime,
          storageKey,
          status: "queued",
        },
      });
      const job = await prisma.job.create({
        data: { workspaceId, documentId: doc.id, jobType: "ingest", status: "queued" },
      });
      entries.push({ id: doc.id, filename, status: "queued", jobId: job.id });
    }

    if (entries.length === 0) throw badRequest("No files were included in the upload.");

    const allDuplicates = entries.every((e) => e.duplicate);
    return reply.code(allDuplicates ? 200 : 201).send(entries);
  });

  // ---- List --------------------------------------------------------------
  const listQuery = z.object({
    status: z.string().optional(),
    docType: z.string().optional(),
    q: z.string().optional(),
    sort: z.enum(["recent", "oldest", "name"]).optional().default("recent"),
    cursor: z.string().optional(),
    limit: z.coerce.number().int().min(1).max(100).optional().default(50),
  });

  app.get("/api/documents", async (req) => {
    const workspaceId = await getWorkspaceId();
    const q = listQuery.parse(req.query);
    const offset = decodeCursor(q.cursor);

    const where: Prisma.DocumentWhereInput = { workspaceId };
    if (q.status) where.status = { in: q.status.split(",").map((s) => s.trim()) };
    if (q.docType) where.docType = q.docType;
    if (q.q)
      where.OR = [
        { filename: { contains: q.q, mode: "insensitive" } },
        { counterparty: { contains: q.q, mode: "insensitive" } },
      ];

    const orderBy =
      q.sort === "name"
        ? { filename: "asc" as const }
        : q.sort === "oldest"
          ? { uploadedAt: "asc" as const }
          : { uploadedAt: "desc" as const };

    const [rows, total, statusGroups] = await Promise.all([
      prisma.document.findMany({ where, orderBy, skip: offset, take: q.limit + 1 }),
      prisma.document.count({ where }),
      prisma.document.groupBy({ by: ["status"], where: { workspaceId }, _count: true }),
    ]);

    const hasMore = rows.length > q.limit;
    const page = hasMore ? rows.slice(0, q.limit) : rows;
    const counts: Record<string, number> = {};
    for (const g of statusGroups) counts[g.status] = g._count;

    // Enrich each row with the few cross-table facts the portfolio table shows:
    // term end, the next action date, and whether it needs review.
    const ids = page.map((d) => d.id);
    const [events, termEnds, reviewFields] = await Promise.all([
      prisma.calendarEvent.findMany({
        where: { documentId: { in: ids }, status: { in: ["open", "acknowledged"] } },
        select: { documentId: true, eventDate: true, actionByDate: true },
      }),
      prisma.extractedField.findMany({
        where: { documentId: { in: ids }, fieldKey: "expiration_date" },
        select: { documentId: true, valueNormalized: true, valueVerbatim: true },
      }),
      prisma.extractedField.findMany({
        where: {
          documentId: { in: ids },
          OR: [{ confidenceTier: { in: ["unverified", "inferred"] } }, { absenceReason: "illegible" }],
        },
        select: { documentId: true },
        distinct: ["documentId"],
      }),
    ]);

    const nextAction = new Map<string, string>();
    for (const e of events) {
      const eff = (e.actionByDate ?? e.eventDate).toISOString().slice(0, 10);
      const cur = nextAction.get(e.documentId);
      if (!cur || eff < cur) nextAction.set(e.documentId, eff);
    }
    const termEnd = new Map<string, string>();
    for (const f of termEnds) {
      const norm = f.valueNormalized as { date?: string } | null;
      const val = norm?.date ?? f.valueVerbatim ?? undefined;
      if (val) termEnd.set(f.documentId, val);
    }
    const reviewSet = new Set(reviewFields.map((r) => r.documentId));

    return {
      documents: page.map((d) => ({
        ...serializeDocumentSummary(d),
        termEnd: termEnd.get(d.id) ?? null,
        nextActionDate: nextAction.get(d.id) ?? null,
        needsReview: reviewSet.has(d.id) || d.status === "degraded",
      })),
      counts,
      total,
      nextCursor: hasMore ? encodeCursor(offset + q.limit) : null,
    };
  });

  // ---- Detail ------------------------------------------------------------
  app.get<{ Params: { id: string } }>("/api/documents/:id", async (req) => {
    const doc = await prisma.document.findUnique({
      where: { id: req.params.id },
      include: {
        pages: { orderBy: { pageNumber: "asc" } },
        fields: { orderBy: { fieldKey: "asc" } },
        segments: { orderBy: { charStart: "asc" } },
        jobs: { orderBy: { createdAt: "desc" }, take: 1 },
      },
    });
    if (!doc) throw notFound("Document not found.");

    // Resolve each field's citation page from its first anchor line so the UI can
    // render "Clause 12.3 · page 7" without a second round-trip.
    const allLineIds = [...new Set(doc.fields.flatMap((f) => f.anchorLineIds))];
    const lines = allLineIds.length
      ? await prisma.textLine.findMany({
          where: { documentId: doc.id, lineId: { in: allLineIds } },
          select: { lineId: true, pageNumber: true },
        })
      : [];
    const pageByLine = new Map(lines.map((l) => [l.lineId, l.pageNumber]));

    return {
      ...serializeDocumentSummary(doc),
      pages: doc.pages.map(serializePage),
      fields: doc.fields.map((f) => ({
        ...serializeField(f),
        citationPage: f.anchorLineIds.map((id) => pageByLine.get(id)).find((p) => p != null) ?? null,
      })),
      segments: doc.segments.map(serializeSegment),
      job: serializeJobStatus(doc.jobs[0] ?? null),
    };
  });

  // ---- Lightweight status poll target ------------------------------------
  app.get<{ Params: { id: string } }>("/api/documents/:id/status", async (req) => {
    const doc = await prisma.document.findUnique({
      where: { id: req.params.id },
      select: { id: true, status: true, jobs: { orderBy: { createdAt: "desc" }, take: 1 } },
    });
    if (!doc) throw notFound("Document not found.");
    const job = doc.jobs[0] ?? null;
    return {
      id: doc.id,
      status: doc.status,
      stage: job?.stage ?? null,
      progress: job?.progress ?? 0,
    };
  });

  // ---- Delete ------------------------------------------------------------
  app.delete<{ Params: { id: string } }>("/api/documents/:id", async (req, reply) => {
    const doc = await prisma.document.findUnique({ where: { id: req.params.id } });
    if (!doc) throw notFound("Document not found.");
    if (doc.storageKey)
      await deleteDocumentFiles({ documentId: doc.id, storageKey: doc.storageKey, sha256: doc.sha256 });
    await prisma.document.delete({ where: { id: doc.id } }); // cascades in the DB
    return reply.code(204).send();
  });

  // ---- Full text (reader pane) -------------------------------------------
  app.get<{ Params: { id: string } }>("/api/documents/:id/text", async (req) => {
    const row = await prisma.documentText.findUnique({ where: { documentId: req.params.id } });
    return { documentId: req.params.id, text: row?.text ?? "" };
  });

  // ---- Anchors (line id -> box) ------------------------------------------
  const anchorQuery = z.object({ lineIds: z.string() });
  app.get<{ Params: { id: string } }>("/api/documents/:id/anchors", async (req) => {
    const { lineIds } = anchorQuery.parse(req.query);
    const ids = lineIds.split(",").map((s) => s.trim()).filter(Boolean);
    if (ids.length === 0) return [];
    const lines = await prisma.textLine.findMany({
      where: { documentId: req.params.id, lineId: { in: ids } },
    });
    return lines.map((l) => ({ lineId: l.lineId, page: l.pageNumber, bbox: l.bbox, text: l.text }));
  });

  // ---- Page image --------------------------------------------------------
  app.get<{ Params: { id: string; n: string } }>(
    "/api/documents/:id/pages/:n/image",
    async (req, reply) => {
      const pageNumber = Number(req.params.n);
      const page = await prisma.documentPage.findUnique({
        where: { documentId_pageNumber: { documentId: req.params.id, pageNumber } },
      });
      if (!page || !page.imageKey) throw notFound("Page image not found.");
      const bytes = await readFile(storage.resolveKey(page.imageKey)).catch(() => null);
      if (!bytes) throw notFound("Page image file is missing from storage.");
      return reply
        .header("content-type", "image/png")
        .header("cache-control", "public, max-age=31536000, immutable")
        .send(bytes);
    },
  );

  // ---- Integrity check (§10) --------------------------------------------
  // Validates the invariants Node relies on the pipeline to hold. Should report
  // zero dangling anchors on stub data.
  app.get("/api/integrity", async () => {
    const workspaceId = await getWorkspaceId();
    const docs = await prisma.document.findMany({ where: { workspaceId }, select: { id: true } });

    const danglingAnchors: { documentId: string; fieldId: string; lineId: string }[] = [];
    const badTiers: { fieldId: string; tier: string }[] = [];
    const missingAbsence: { fieldId: string }[] = [];
    const validTiers = new Set(["verbatim", "normalised", "assembled", "inferred", "unverified"]);

    for (const d of docs) {
      const [fields, lines] = await Promise.all([
        prisma.extractedField.findMany({ where: { documentId: d.id } }),
        prisma.textLine.findMany({ where: { documentId: d.id }, select: { lineId: true } }),
      ]);
      const known = new Set(lines.map((l) => l.lineId));
      for (const f of fields) {
        if (!validTiers.has(f.confidenceTier)) badTiers.push({ fieldId: f.id, tier: f.confidenceTier });
        if (f.valueVerbatim == null && !f.absenceReason) missingAbsence.push({ fieldId: f.id });
        for (const lid of f.anchorLineIds)
          if (!known.has(lid)) danglingAnchors.push({ documentId: d.id, fieldId: f.id, lineId: lid });
      }
    }

    const badCalendar = await prisma.$queryRaw<{ id: string }[]>`
      SELECT id FROM calendar_events
      WHERE action_by_date IS NOT NULL AND action_by_date > event_date`;

    const ok =
      danglingAnchors.length === 0 &&
      badTiers.length === 0 &&
      missingAbsence.length === 0 &&
      badCalendar.length === 0;

    return { ok, danglingAnchors, badTiers, missingAbsence, badCalendar };
  });
}
