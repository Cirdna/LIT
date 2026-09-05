// Single source of truth for env config AND the storage layout (§5). Both halves
// of the seam — Node here, the Python worker separately — must agree on these
// paths, so keeping them in one file makes swapping the storage root a one-file
// change.
import path from "node:path";

function required(name: string, fallback?: string): string {
  const v = process.env[name] ?? fallback;
  if (v === undefined) throw new Error(`Missing required env var: ${name}`);
  return v;
}

export const config = {
  port: Number(process.env.PORT ?? 3001),
  host: process.env.HOST ?? "0.0.0.0",
  databaseUrl: required("DATABASE_URL", "postgresql://aithena:aithena@localhost:5432/aithena?schema=public"),
  frontendOrigin: process.env.FRONTEND_ORIGIN ?? "http://localhost:5173",
  storageRoot: path.resolve(process.env.STORAGE_ROOT ?? "./storage"),

  upload: {
    maxFileBytes: 50 * 1024 * 1024, // 50 MB per file
    maxFilesPerRequest: 25,
  },
} as const;

// ---- Storage layout (§5) -------------------------------------------------
// storage/
//   originals/<sha256>.<ext>
//   ocr/<sha256>.pdf
//   pages/<document_id>/p<N>@<dpi>.png
//   tmp/
export const storage = {
  root: config.storageRoot,
  originalsDir: path.join(config.storageRoot, "originals"),
  ocrDir: path.join(config.storageRoot, "ocr"),
  pagesDir: path.join(config.storageRoot, "pages"),
  tmpDir: path.join(config.storageRoot, "tmp"),

  /** Path (and storage_key) of an uploaded original, keyed by content hash. */
  originalKey(sha256: string, ext: string): string {
    const clean = ext.replace(/^\./, "").toLowerCase();
    return path.join("originals", clean ? `${sha256}.${clean}` : sha256);
  },
  originalPath(sha256: string, ext: string): string {
    return path.join(config.storageRoot, this.originalKey(sha256, ext));
  },

  /** Rendered page PNG (worker writes these; Node only reads/serves them). */
  pageImageKey(documentId: string, pageNumber: number, dpi: number): string {
    return path.join("pages", documentId, `p${pageNumber}@${dpi}.png`);
  },
  pageImagePath(documentId: string, pageNumber: number, dpi: number): string {
    return path.join(config.storageRoot, this.pageImageKey(documentId, pageNumber, dpi));
  },

  /** Absolute path for any storage_key/image_key stored in the DB. */
  resolveKey(key: string): string {
    return path.join(config.storageRoot, key);
  },
} as const;
