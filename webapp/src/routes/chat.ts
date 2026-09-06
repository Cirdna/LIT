import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { getWorkspaceId } from "../lib/workspace.js";
import { ALL_FIELD_KEYS } from "../lib/domain.js";
import { OpenRouterError, chatJson, chatText, type ChatMessage } from "../lib/openrouter.js";
import { RetrievalParams, retrieve, type RetrievedDoc } from "../lib/retrieval.js";
import { sendError, ApiError } from "../lib/errors.js";

const bodySchema = z.object({
  message: z.string().min(1).max(2000),
  history: z
    .array(z.object({ role: z.enum(["user", "assistant"]), content: z.string().max(4000) }))
    .max(20)
    .optional(),
});

// The schema the router LLM is told it can filter on. Kept in sync with
// retrieval.ts's whitelist.
const ROUTER_SYSTEM = `You are the query router for a contract-portfolio assistant.
Decide whether the user's request is specific enough to search the contract database.

The database has contracts, each with these extracted field keys:
${ALL_FIELD_KEYS.join(", ")}.
Numeric fields: notice_period_to_terminate_renewal (days), renewal_term (months), warranty_duration (months).
Date fields: agreement_date, effective_date, expiration_date (ISO YYYY-MM-DD).
Doc types: nda, lease, msa, distribution, employment, other.

Return ONLY a JSON object, one of:
{"status":"need_clarification","question":"<one specific question>"}
{"status":"ready","params":{ ...only the keys you need... }}

params may include: docType, counterparty (vendor/party name substring),
freeText (keyword), fieldKey (one of the field keys), presence ("present"|"absent"),
comparator ("lt"|"lte"|"gt"|"gte"|"eq") with threshold (number) for a numeric field,
dateField with dateFrom/dateTo for a date range.

Ask for clarification only when the request is genuinely too vague to search
(e.g. "show me risky contracts" — ask which risk/term). If the user names a
vendor, term, threshold, or date range, proceed with "ready".`;

const SYNTH_SYSTEM = `You are a contract-portfolio assistant. Answer ONLY from the
JSON search results provided — never invent contracts, values, dates, or clauses.
Be concise and factual. When you state a contract's value, name the contract and
its clause. If the results are empty, say plainly that no matching contracts were
found. Do not add legal advice.`;

export async function registerChatRoutes(app: FastifyInstance) {
  app.post("/api/chat", async (req, reply) => {
    const { message, history } = bodySchema.parse(req.body);
    const workspaceId = await getWorkspaceId();
    const priorTurns: ChatMessage[] = (history ?? []).map((h) => ({ role: h.role, content: h.content }));

    let routed: unknown;
    try {
      routed = await chatJson(ROUTER_SYSTEM, message, priorTurns);
    } catch (err) {
      if (err instanceof OpenRouterError) {
        return sendError(reply, new ApiError(503, "llm_unavailable", err.message));
      }
      throw err;
    }

    const router = z
      .object({
        status: z.enum(["need_clarification", "ready"]),
        question: z.string().optional(),
        params: z.unknown().optional(),
      })
      .safeParse(routed);

    if (!router.success) {
      return { status: "answered", answer: "I couldn't interpret that — try naming a vendor, a term, or a date range.", results: [] };
    }

    if (router.data.status === "need_clarification") {
      return { status: "need_clarification", question: router.data.question ?? "Could you be more specific?" };
    }

    // Validate/whitelist the LLM's params before they touch the DB.
    const parsed = RetrievalParams.safeParse(router.data.params ?? {});
    if (!parsed.success) {
      return { status: "need_clarification", question: "Which contracts or terms do you mean? (e.g. a vendor, a notice period, a date range.)" };
    }

    const results = await retrieve(workspaceId, parsed.data);

    let answer: string;
    try {
      answer = await chatText(SYNTH_SYSTEM, synthPrompt(message, results), priorTurns);
    } catch (err) {
      // If synthesis fails, still return the grounded results with a plain summary.
      answer = deterministicSummary(results);
      if (!(err instanceof OpenRouterError)) app.log.error(err);
    }

    return { status: "answered", answer, params: parsed.data, results };
  });
}

function synthPrompt(question: string, results: RetrievedDoc[]): string {
  return [
    `User question: ${question}`,
    ``,
    `Search results (JSON):`,
    JSON.stringify(results, null, 2),
    ``,
    `Write a short answer grounded only in these results.`,
  ].join("\n");
}

function deterministicSummary(results: RetrievedDoc[]): string {
  if (results.length === 0) return "No matching contracts were found.";
  const lines = results.slice(0, 10).map((r) => {
    const f = r.fields[0];
    const val = f?.value ? ` — ${f.fieldKey}: ${f.value}${f.clauseLabel ? ` (${f.clauseLabel})` : ""}` : "";
    return `• ${r.counterparty ?? r.filename}${val}`;
  });
  return `${results.length} matching contract(s):\n${lines.join("\n")}`;
}
