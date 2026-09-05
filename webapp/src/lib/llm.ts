// OpenRouter client for the API process.
//
// SCOPE LIMIT — read this before adding a caller.
// The model is allowed to do exactly two things in this codebase:
//   1. decide whether a user's question is specific enough to search, and
//   2. translate a specific question into a STRUCTURED FILTER.
// It is never allowed to state a fact about a contract. Every value a user sees
// still comes out of `extracted_fields` with its own confidence tier and clause
// citation. That boundary is what keeps the grounding guarantee intact: if the
// model hallucinates, the worst outcome is a filter that matches nothing, not a
// sentence a contract never contained.
//
// The one exception is invoice reading (routes/invoices.ts), where the model
// reads an invoice — a document we make no grounded claims about — and its output
// is only ever used as a LOOKUP KEY against grounded contract fields. The
// invoice's own extracted values are labelled as model-read, never as quoted.
import { z } from "zod";
import { ApiError } from "./errors.js";

// MODEL STRING — UNRESOLVED, see STATUS_UPDATE.md.
// The team named "Gemini Pro 3.10 preview", which is not an OpenRouter model
// slug and could not be verified. Rather than invent a literal, this defaults to
// the slug ALREADY IN USE elsewhere in this repo
// (src/pdf_analyzer/stage2_vlm.py:48, DEFAULT_OPENROUTER_MODEL_ID) and is
// overridable by env. Set OPENROUTER_MODEL once the team supplies the exact slug.
const DEFAULT_MODEL = "google/gemini-3.8-flash";
const DEFAULT_BASE_URL = "https://openrouter.ai/api/v1";

export const llmConfig = {
  get apiKey(): string | undefined {
    // Environment only. Nothing shared in chat is ever committed here.
    return process.env.OPENROUTER_API_KEY;
  },
  get model(): string {
    return process.env.OPENROUTER_MODEL ?? DEFAULT_MODEL;
  },
  /**
   * Overridable so the routes can be exercised end-to-end against a local
   * stand-in — the request/response shape and every downstream step are then real
   * code, and only the model's judgement is substituted. Also covers an
   * OpenAI-compatible gateway if the team ever fronts OpenRouter with one.
   */
  get baseUrl(): string {
    return (process.env.OPENROUTER_BASE_URL ?? DEFAULT_BASE_URL).replace(/\/$/, "");
  },
  get available(): boolean {
    return !!process.env.OPENROUTER_API_KEY;
  },
};

/** 503 rather than 500: the feature is unconfigured, not broken. */
export function requireLlm() {
  if (!llmConfig.available)
    throw new ApiError(
      503,
      "llm_unconfigured",
      "This feature needs a language model. Set OPENROUTER_API_KEY in the environment and restart the API.",
    );
}

function stripFence(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed.startsWith("```")) return trimmed;
  return trimmed.replace(/^```(?:json)?\s*/i, "").replace(/```\s*$/, "").trim();
}

/**
 * One JSON-returning call, validated against a schema.
 *
 * A response that does not satisfy the schema is an error, not something to
 * salvage. Silently dropping an unparseable field would turn a model failure
 * into a wrong-but-plausible answer, which is the failure mode this whole
 * codebase is built to avoid.
 */
export async function askForJson<T extends z.ZodTypeAny>(args: {
  system: string;
  user: string;
  schema: T;
  maxTokens?: number;
}): Promise<z.infer<T>> {
  requireLlm();

  const res = await fetch(`${llmConfig.baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${llmConfig.apiKey}`,
      "Content-Type": "application/json",
      "X-Title": "AITHENA",
    },
    body: JSON.stringify({
      model: llmConfig.model,
      temperature: 0, // the same question must produce the same filter
      max_tokens: args.maxTokens ?? 800,
      response_format: { type: "json_object" },
      messages: [
        { role: "system", content: args.system },
        { role: "user", content: args.user },
      ],
    }),
  }).catch((err: Error) => {
    throw new ApiError(502, "llm_unreachable", `Could not reach OpenRouter: ${err.message}`);
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(
      502,
      "llm_error",
      `OpenRouter returned ${res.status} for model "${llmConfig.model}".`,
      body.slice(0, 400),
    );
  }

  const payload = (await res.json()) as { choices?: { message?: { content?: string } }[] };
  const content = payload.choices?.[0]?.message?.content;
  if (!content) throw new ApiError(502, "llm_empty", "OpenRouter returned no content.");

  let parsed: unknown;
  try {
    parsed = JSON.parse(stripFence(content));
  } catch {
    throw new ApiError(502, "llm_bad_json", "The model did not return JSON.", content.slice(0, 400));
  }

  const result = args.schema.safeParse(parsed);
  if (!result.success)
    throw new ApiError(
      502,
      "llm_bad_shape",
      "The model returned JSON that does not match the expected shape.",
      result.error.issues.slice(0, 5),
    );
  return result.data;
}
