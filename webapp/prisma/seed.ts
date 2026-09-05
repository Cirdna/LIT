// Seeds the single workspace and the demo corpus as `queued` documents + ingest
// jobs. Run the stub worker afterwards to fill in the fake extraction data:
//
//   npm run seed
//   npm run stub
//
// Idempotent: documents are keyed by content hash (here, the hash of the
// filename), so re-running does not duplicate rows.
import "../src/env.js"; // must run before anything reads process.env
import { createHash } from "node:crypto";
import { writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { prisma } from "../src/db.js";
import { storage } from "../src/config.js";
import { DEFAULT_WORKSPACE_NAME } from "../src/lib/workspace.js";
import { CORPUS } from "../scripts/corpus.js";

async function main() {
  const workspace =
    (await prisma.workspace.findFirst({ orderBy: { createdAt: "asc" } })) ??
    (await prisma.workspace.create({ data: { name: DEFAULT_WORKSPACE_NAME } }));
  console.log(`workspace: ${workspace.id} (${workspace.name})`);

  await mkdir(storage.originalsDir, { recursive: true });

  for (const doc of CORPUS) {
    const sha256 = createHash("sha256").update(doc.filename).digest("hex");
    const storageKey = storage.originalKey(sha256, doc.ext);

    const existing = await prisma.document.findUnique({
      where: { workspaceId_sha256: { workspaceId: workspace.id, sha256 } },
    });
    if (existing) {
      console.log(`  = ${doc.filename} (already seeded)`);
      continue;
    }

    // A placeholder original so DELETE and the storage layout are realistic. The
    // stub worker never reads it; the real worker will read genuine uploads.
    const placeholder = Buffer.from(`%PDF-1.7\n% AITHENA demo placeholder for ${doc.filename}\n`);
    await writeFile(storage.resolveKey(storageKey), placeholder);

    const created = await prisma.document.create({
      data: {
        workspaceId: workspace.id,
        filename: doc.filename,
        sha256,
        byteSize: BigInt(placeholder.byteLength),
        mimeType: doc.mime,
        storageKey,
        status: "queued",
      },
    });

    await prisma.job.create({
      data: { workspaceId: workspace.id, documentId: created.id, jobType: "ingest", status: "queued" },
    });
    console.log(`  + ${doc.filename}`);
  }

  console.log("\nSeed complete. Now run:  npm run stub");
}

main()
  .catch((err) => {
    console.error(err);
    process.exitCode = 1;
  })
  .finally(() => prisma.$disconnect());
