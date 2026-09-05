import type { FastifyInstance } from "fastify";
import { prisma } from "../db.js";

export async function registerHealthRoutes(app: FastifyInstance) {
  app.get("/api/health", async () => {
    let db = "down";
    try {
      await prisma.$queryRaw`SELECT 1`;
      db = "up";
    } catch {
      db = "down";
    }
    return { ok: db === "up", db, time: new Date().toISOString() };
  });
}
