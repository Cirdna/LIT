import { createHash } from "node:crypto";
import { randomUUID } from "node:crypto";
import { createWriteStream } from "node:fs";
import { mkdir, rename, rm } from "node:fs/promises";
import { once } from "node:events";
import path from "node:path";
import { storage } from "../config.js";

const HEAD_BYTES = 512; // enough to sniff signatures and sample text

export async function ensureStorageDirs(): Promise<void> {
  await Promise.all(
    [storage.originalsDir, storage.ocrDir, storage.pagesDir, storage.tmpDir].map((d) =>
      mkdir(d, { recursive: true }),
    ),
  );
}

export type PersistResult = {
  tmpPath: string;
  byteSize: number;
  sha256: string;
  head: Buffer; // first bytes, for magic-byte sniffing
};

/**
 * Stream an upload to a temp file while hashing it — never buffer the whole
 * file in memory (§8). The caller decides, from the sha and head, whether to
 * promote the temp file to originals/ or discard it.
 */
export async function persistToTmp(source: AsyncIterable<Buffer>): Promise<PersistResult> {
  await ensureStorageDirs();
  const tmpPath = path.join(storage.tmpDir, randomUUID());
  const hash = createHash("sha256");
  const out = createWriteStream(tmpPath);
  const headChunks: Buffer[] = [];
  let headLen = 0;
  let byteSize = 0;

  try {
    for await (const chunk of source) {
      const buf = chunk as Buffer;
      byteSize += buf.length;
      hash.update(buf);
      if (headLen < HEAD_BYTES) {
        const take = buf.subarray(0, HEAD_BYTES - headLen);
        headChunks.push(take);
        headLen += take.length;
      }
      if (!out.write(buf)) await once(out, "drain");
    }
    out.end();
    await once(out, "finish");
  } catch (err) {
    out.destroy();
    await rm(tmpPath, { force: true });
    throw err;
  }

  return { tmpPath, byteSize, sha256: hash.digest("hex"), head: Buffer.concat(headChunks) };
}

/** Promote a temp file to its content-addressed home under originals/. */
export async function promoteToOriginal(tmpPath: string, storageKey: string): Promise<void> {
  const dest = storage.resolveKey(storageKey);
  await mkdir(path.dirname(dest), { recursive: true });
  await rename(tmpPath, dest);
}

export async function discardTmp(tmpPath: string): Promise<void> {
  await rm(tmpPath, { force: true });
}

/** Remove every stored artifact for a document (DELETE cascades in the DB). */
export async function deleteDocumentFiles(opts: {
  documentId: string;
  storageKey: string;
  sha256: string;
}): Promise<void> {
  await Promise.all([
    rm(storage.resolveKey(opts.storageKey), { force: true }),
    rm(path.join(storage.ocrDir, `${opts.sha256}.pdf`), { force: true }),
    rm(path.join(storage.pagesDir, opts.documentId), { recursive: true, force: true }),
  ]);
}
