import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { api, type ChatResult } from "../lib/api";
import { ConfidenceBadge } from "../lib/confidence";
import { DOC_TYPE_LABELS } from "../lib/domain";

type Msg = { role: "user" | "assistant"; content: string; results?: ChatResult[] };

const EXAMPLES = [
  "Which contracts auto-renew in the next 90 days?",
  "Show me distribution agreements with Acme",
  "Which contracts have a notice period under 30 days?",
  "What expires before the end of 2027?",
];

export default function Chat() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");

  const send = useMutation({
    mutationFn: (text: string) =>
      api.chat(
        text,
        messages
          .filter((m) => m.role === "user" || m.role === "assistant")
          .map((m) => ({ role: m.role, content: m.content })),
      ),
    onSuccess: (res) => {
      if (res.status === "need_clarification") {
        setMessages((m) => [...m, { role: "assistant", content: res.question }]);
      } else {
        setMessages((m) => [...m, { role: "assistant", content: res.answer, results: res.results }]);
      }
    },
    onError: (e: unknown) =>
      setMessages((m) => [...m, { role: "assistant", content: `Sorry — ${(e as Error).message}` }]),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || send.isPending) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    send.mutate(text);
  }

  function ask(example: string) {
    setMessages((m) => [...m, { role: "user", content: example }]);
    send.mutate(example);
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      <h1 className="text-2xl font-bold text-ink">Ask your portfolio</h1>
      <p className="mb-4 text-muted">
        Ask in plain language. Answers come only from your contracts, with a citation and a confidence level on every
        value. If a question is too vague, you'll get a clarifying question back.
      </p>

      {messages.length === 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => ask(ex)}
              className="rounded-full border border-rule bg-surface px-3 py-1 text-sm text-muted hover:bg-paper"
            >
              {ex}
            </button>
          ))}
        </div>
      )}

      <div className="mb-4 space-y-3">
        {messages.map((m, i) => (
          <MessageBubble key={i} msg={m} />
        ))}
        {send.isPending && (
          <div className="max-w-[80%] rounded-lg border border-rule bg-surface px-3 py-2 text-sm text-muted">
            Searching your contracts…
          </div>
        )}
      </div>

      <form onSubmit={submit} className="sticky bottom-4 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. which NDAs expire this year?"
          className="flex-1 rounded border border-rule bg-paper px-3 py-2"
        />
        <button type="submit" className="btn btn-primary" disabled={send.isPending || !input.trim()}>
          Ask
        </button>
      </form>
    </div>
  );
}

function MessageBubble({ msg }: { msg: Msg }) {
  const isUser = msg.role === "user";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 ${
          isUser ? "bg-navy text-white" : "border border-rule bg-surface text-ink"
        }`}
      >
        <p className="whitespace-pre-wrap text-[0.98rem]">{msg.content}</p>
        {msg.results && msg.results.length > 0 && (
          <div className="mt-2 space-y-2">
            {msg.results.map((r) => (
              <ResultCard key={r.documentId} r={r} />
            ))}
          </div>
        )}
        {msg.results && msg.results.length === 0 && !isUser && (
          <p className="mt-1 text-sm text-muted">No matching contracts.</p>
        )}
      </div>
    </div>
  );
}

function ResultCard({ r }: { r: ChatResult }) {
  return (
    <div className="rounded border border-rule bg-paper px-2.5 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link to={`/documents/${r.documentId}`} className="font-medium text-navy hover:underline">
          {r.counterparty ?? r.filename}
        </Link>
        {r.docType && <span className="text-xs text-muted">{DOC_TYPE_LABELS[r.docType] ?? r.docType}</span>}
      </div>
      {r.fields.map((f, i) => (
        <div key={i} className="mt-1 flex flex-wrap items-center gap-2 text-sm">
          {f.value != null ? (
            <span className={f.confidenceTier === "unverified" ? "text-alert line-through" : "text-ink"}>{f.value}</span>
          ) : (
            <span className="text-muted italic">not present</span>
          )}
          <ConfidenceBadge tier={f.confidenceTier} size="sm" />
          {f.clauseLabel && <span className="text-xs text-faint">{f.clauseLabel}</span>}
        </div>
      ))}
    </div>
  );
}
