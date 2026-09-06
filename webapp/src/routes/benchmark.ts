import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { getWorkspaceId } from "../lib/workspace.js";
import { badRequest } from "../lib/errors.js";
import {
  BENCHMARK_CATEGORIES,
  benchmarksForDocument,
  portfolioStats,
} from "../lib/benchmark.js";

export async function registerBenchmarkRoutes(app: FastifyInstance) {
  // The categories the UI can benchmark on.
  app.get("/api/benchmark/categories", async () => ({
    categories: Object.entries(BENCHMARK_CATEGORIES).map(([key, c]) => ({
      key,
      label: c.label,
      unit: c.unit,
      direction: c.direction,
    })),
  }));

  const query = z.object({ documentId: z.string().uuid().optional(), category: z.string().optional() });

  // `?documentId=` → every benchmark for that contract (drives the detail panel).
  // `?category=`   → portfolio-wide stats for one category.
  app.get("/api/benchmark", async (req) => {
    const workspaceId = await getWorkspaceId();
    const { documentId, category } = query.parse(req.query);

    if (documentId) {
      const benchmarks = await benchmarksForDocument(workspaceId, documentId);
      return { documentId, benchmarks };
    }
    if (category) {
      if (!(category in BENCHMARK_CATEGORIES)) throw badRequest(`Unknown benchmark category: ${category}.`);
      return await portfolioStats(workspaceId, category);
    }
    throw badRequest("Provide either documentId or category.");
  });
}
