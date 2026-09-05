import type { FastifyInstance } from "fastify";
import { prisma } from "../db.js";
import { getWorkspaceId } from "../lib/workspace.js";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}
function addDays(iso: string, days: number): string {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export async function registerPortfolioRoutes(app: FastifyInstance) {
  app.get("/api/portfolio/summary", async () => {
    const workspaceId = await getWorkspaceId();
    const today = todayIso();
    const in90 = addDays(today, 90);

    const [statusGroups, conflictCount, events, reviewFieldDocs, degradedDocs, totalDocs] =
      await Promise.all([
        prisma.document.groupBy({ by: ["status"], where: { workspaceId }, _count: true }),
        prisma.conflict.count({ where: { workspaceId } }),
        prisma.calendarEvent.findMany({
          where: { workspaceId, status: { in: ["open", "acknowledged"] } },
        }),
        prisma.extractedField.findMany({
          where: {
            document: { workspaceId },
            OR: [{ confidenceTier: { in: ["unverified", "inferred"] } }, { absenceReason: "illegible" }],
          },
          select: { documentId: true },
          distinct: ["documentId"],
        }),
        prisma.document.findMany({ where: { workspaceId, status: "degraded" }, select: { id: true } }),
        prisma.document.count({ where: { workspaceId } }),
      ]);

    const statusCounts: Record<string, number> = {};
    for (const g of statusGroups) statusCounts[g.status] = g._count;

    // Contracts tracked = analysed documents that are actually agreements.
    const analysed = (statusCounts.ready ?? 0) + (statusCounts.degraded ?? 0);
    const notContracts = await prisma.document.count({
      where: { workspaceId, docType: "not_a_contract" },
    });
    const contractsTracked = Math.max(0, analysed - notContracts);

    const effective = (e: (typeof events)[number]) =>
      (e.actionByDate ?? e.eventDate).toISOString().slice(0, 10);
    const actionsNext90 = events.filter((e) => effective(e) <= in90).length;
    const overdue = events.filter((e) => effective(e) < today).length;

    const reviewDocIds = new Set<string>([
      ...reviewFieldDocs.map((r) => r.documentId),
      ...degradedDocs.map((d) => d.id),
    ]);

    return {
      today,
      totalDocuments: totalDocs,
      contractsTracked,
      actionsNext90,
      overdue,
      conflictsFound: conflictCount,
      documentsNeedingReview: reviewDocIds.size,
      statusCounts,
      processing: (statusCounts.queued ?? 0) + (statusCounts.processing ?? 0),
    };
  });
}
