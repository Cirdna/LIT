import type { FastifyReply } from "fastify";

// Every error response shares one shape: { error: { code, message, detail? } }.
export class ApiError extends Error {
  constructor(
    public statusCode: number,
    public code: string,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const notFound = (message = "Not found", detail?: unknown) =>
  new ApiError(404, "not_found", message, detail);

export const badRequest = (message: string, detail?: unknown) =>
  new ApiError(400, "bad_request", message, detail);

export const unsupportedMedia = (message: string, detail?: unknown) =>
  new ApiError(415, "unsupported_media_type", message, detail);

export function sendError(reply: FastifyReply, err: ApiError) {
  return reply.code(err.statusCode).send({
    error: { code: err.code, message: err.message, ...(err.detail !== undefined ? { detail: err.detail } : {}) },
  });
}
