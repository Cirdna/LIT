import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { prisma } from "../db.js";
import { getWorkspaceId } from "../lib/workspace.js";
import { badRequest, notFound } from "../lib/errors.js";
import { serializeHandoff, serializeDocumentSummary } from "../lib/serialize.js";
import { buildBriefFromConflict } from "../lib/handoff.js";

export async function registerHandoffRoutes(app: FastifyInstance) {
  app.get("/api/handoffs", async () => {
    const workspaceId = await getWorkspaceId();
    const briefs = await prisma.handoffBrief.findMany({
      where: { workspaceId },
      orderBy: { createdAt: "desc" },
    });
    return { handoffs: briefs.map(serializeHandoff) };
  });

  app.get<{ Params: { id: string } }>("/api/handoffs/:id", async (req) => {
    const brief = await prisma.handoffBrief.findUnique({ where: { id: req.params.id } });
    if (!brief) throw notFound("Handoff brief not found.");
    const docs = await prisma.document.findMany({ where: { id: { in: brief.documentIds } } });
    return { ...serializeHandoff(brief), documents: docs.map(serializeDocumentSummary) };
  });

  // Generate a brief. Either from an existing conflict (conflictId) or from
  // explicit fields supplied by the caller.
  const body = z.object({
    conflictId: z.string().optional(),
    trigger: z.string().optional(),
    issue: z.string().optional(),
    question: z.string().optional(),
    documentIds: z.array(z.string()).optional(),
    established: z.array(z.any()).optional(),
  });

  app.post("/api/handoffs", async (req, reply) => {
    const workspaceId = await getWorkspaceId();
    const input = body.parse(req.body);

    let data;
    if (input.conflictId) {
      const conflict = await prisma.conflict.findUnique({ where: { id: input.conflictId } });
      if (!conflict) throw notFound("Conflict not found.");
      const [docs, fields] = await Promise.all([
        prisma.document.findMany({ where: { id: { in: conflict.documentIds } } }),
        prisma.extractedField.findMany({ where: { id: { in: conflict.fieldIds } } }),
      ]);
      data = buildBriefFromConflict(conflict, docs, fields);
    } else {
      if (!input.trigger || !input.issue || !input.question || !input.documentIds?.length)
        throw badRequest("Provide either a conflictId, or trigger + issue + question + documentIds.");
      data = {
        trigger: input.trigger,
        issue: input.issue,
        question: input.question,
        documentIds: input.documentIds,
        established: input.established ?? [],
      };
    }

    const brief = await prisma.handoffBrief.create({
      data: {
        workspaceId,
        trigger: data.trigger,
        issue: data.issue,
        established: data.established as object,
        question: data.question,
        documentIds: data.documentIds,
      },
    });
    return reply.code(201).send(serializeHandoff(brief));
  });
}
