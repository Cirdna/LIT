// Node-side OpenRouter text client for the RAG chat + (later) invoice reasoning.
// The pipeline's Python side has its own vision client; this is the text/JSON
// equivalent, sharing the same key and one configurable model.
//
// Model: OPENROUTER_CHAT_MODEL, defaulting to the pipeline's current model so the
// whole system speaks one model unless a deployment overrides it.
const ENDPOINT = "https://openrouter.ai/api/v1/chat/completions";

export class OpenRouterError extends Error {}

export type ChatMessage = { role: "system" | "user" | "assistant"; content: string };

function model(): string {
  return process.env.OPENROUTER_CHAT_MODEL || "google/gemini-3.8-flash";
}

async function complete(messages: ChatMessage[], opts: { json?: boolean } = {}): Promise<string> {
  const key = process.env.OPENROUTER_API_KEY;
  if (!key) throw new OpenRouterError("OPENROUTER_API_KEY is not set (add it to webapp/.env).");

  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
      "X-Title": "AITHENA",
    },
    body: JSON.stringify({
      model: model(),
      messages,
      temperature: 0.2,
      ...(opts.json ? { response_format: { type: "json_object" } } : {}),
    }),
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new OpenRouterError(`OpenRouter ${res.status}: ${body.slice(0, 300)}`);
  }
  const data = (await res.json()) as { choices?: { message?: { content?: string } }[] };
  return data.choices?.[0]?.message?.content ?? "";
}

export async function chatText(system: string, user: string, history: ChatMessage[] = []): Promise<string> {
  return complete([{ role: "system", content: system }, ...history, { role: "user", content: user }]);
}

/** Ask for a JSON object and parse it defensively (models sometimes wrap it). */
export async function chatJson<T = unknown>(
  system: string,
  user: string,
  history: ChatMessage[] = [],
): Promise<T> {
  const raw = await complete(
    [{ role: "system", content: system }, ...history, { role: "user", content: user }],
    { json: true },
  );
  return parseJsonObject<T>(raw);
}

export function parseJsonObject<T = unknown>(raw: string): T {
  const trimmed = raw.trim().replace(/^```(?:json)?/i, "").replace(/```$/, "").trim();
  try {
    return JSON.parse(trimmed) as T;
  } catch {
    // Fall back to the first balanced-looking object in the string.
    const start = trimmed.indexOf("{");
    const end = trimmed.lastIndexOf("}");
    if (start >= 0 && end > start) {
      try {
        return JSON.parse(trimmed.slice(start, end + 1)) as T;
      } catch {
        /* fall through */
      }
    }
    throw new OpenRouterError("Model did not return valid JSON.");
  }
}
