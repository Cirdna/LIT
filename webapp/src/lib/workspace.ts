import { prisma } from "../db.js";

// v1 has no auth and a single workspace. Its id is resolved server-side and kept
// out of the URL so adding real tenancy later doesn't churn the routes (§8).
export const DEFAULT_WORKSPACE_NAME = "Default workspace";

let cached: string | null = null;

export async function getWorkspaceId(): Promise<string> {
  if (cached) return cached;
  const ws =
    (await prisma.workspace.findFirst({ orderBy: { createdAt: "asc" } })) ??
    (await prisma.workspace.create({ data: { name: DEFAULT_WORKSPACE_NAME } }));
  cached = ws.id;
  return cached;
}
