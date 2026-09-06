import "./env.js"; // must run before anything reads process.env
import Fastify from "fastify";
import cors from "@fastify/cors";
import multipart from "@fastify/multipart";
import { config } from "./config.js";
import { ensureStorageDirs } from "./lib/storage.js";
import { ApiError, sendError } from "./lib/errors.js";
import { getWorkspaceId } from "./lib/workspace.js";
import { registerDocumentRoutes } from "./routes/documents.js";
import { registerCalendarRoutes } from "./routes/calendar.js";
import { registerConflictRoutes } from "./routes/conflicts.js";
import { registerHandoffRoutes } from "./routes/handoffs.js";
import { registerPortfolioRoutes } from "./routes/portfolio.js";
import { registerBenchmarkRoutes } from "./routes/benchmark.js";
import { registerChatRoutes } from "./routes/chat.js";
import { registerHealthRoutes } from "./routes/health.js";

async function build() {
  const app = Fastify({ logger: { level: "info" }, bodyLimit: config.upload.maxFileBytes });

  await app.register(cors, { origin: config.frontendOrigin });
  await app.register(multipart, {
    // Don't throw on an oversized file — truncate it so a single bad file in a
    // batch doesn't abort the other uploads. The route records it as rejected.
    throwFileSizeLimit: false,
    limits: {
      fileSize: config.upload.maxFileBytes,
      files: config.upload.maxFilesPerRequest,
    },
  });

  // One error shape everywhere: { error: { code, message, detail? } }.
  app.setErrorHandler((err: Error & { code?: string; statusCode?: number }, _req, reply) => {
    if (err instanceof ApiError) return sendError(reply, err);
    if ((err as { code?: string }).code === "FST_REQ_FILE_TOO_LARGE") {
      return sendError(
        reply,
        new ApiError(413, "file_too_large", `Each file must be ${config.upload.maxFileBytes / (1024 * 1024)} MB or smaller.`),
      );
    }
    if ((err as { code?: string }).code === "FST_FILES_LIMIT") {
      return sendError(
        reply,
        new ApiError(413, "too_many_files", `Upload at most ${config.upload.maxFilesPerRequest} files per request.`),
      );
    }
    if ((err as { statusCode?: number }).statusCode === 400) {
      return sendError(reply, new ApiError(400, "bad_request", err.message));
    }
    app.log.error(err);
    return sendError(reply, new ApiError(500, "internal_error", "Something went wrong on our side."));
  });

  await registerHealthRoutes(app);
  await registerDocumentRoutes(app);
  await registerCalendarRoutes(app);
  await registerConflictRoutes(app);
  await registerHandoffRoutes(app);
  await registerPortfolioRoutes(app);
  await registerBenchmarkRoutes(app);
  await registerChatRoutes(app);

  return app;
}

async function main() {
  await ensureStorageDirs();
  const app = await build();
  await getWorkspaceId(); // fail fast if the DB is unreachable or unseeded
  await app.listen({ port: config.port, host: config.host });
  app.log.info(`AITHENA API listening on http://${config.host}:${config.port}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
