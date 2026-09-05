import type { FastifyInstance } from "fastify";
import { prisma } from "../db.js";
import { getWorkspaceId } from "../lib/workspace.js";
import { serializeConflict, serializeField, serializeDocumentSummary } from "../lib/serialize.js";

export async function registerConflictRoutes(app: FastifyInstance) {
  app.get("/api/conflicts", async () => {
    const workspaceId = await getWorkspaceId();
    const conflicts = await prisma.conflict.findMany({
      where: { workspaceId },
      orderBy: [{ severity: "asc" }, { createdAt: "desc" }],
    });

    // Hydrate the two clauses of each conflict so the paired view can render
    // both sides with their own citation and confidence tier without N calls.
    const docIds = [...new Set(conflicts.flatMap((c) => c.documentIds))];
    const fieldIds = [...new Set(conflicts.flatMap((c) => c.fieldIds))];
    const [docs, fields] = await Promise.all([
      prisma.document.findMany({ where: { id: { in: docIds } } }),
      prisma.extractedField.findMany({ where: { id: { in: fieldIds } } }),
    ]);
    const docById = new Map(docs.map((d) => [d.id, serializeDocumentSummary(d)]));
    const fieldById = new Map(fields.map((f) => [f.id, serializeField(f)]));

    return {
      conflicts: conflicts.map((c) => ({
        ...serializeConflict(c),
        documents: c.documentIds.map((id) => docById.get(id)).filter(Boolean),
        fields: c.fieldIds.map((id) => fieldById.get(id)).filter(Boolean),
      })),
    };
  });
}
