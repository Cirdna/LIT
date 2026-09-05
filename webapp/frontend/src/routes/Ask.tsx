// Feature 1 — asking the portfolio a question.
//
// The screen is deliberately not a chat transcript. A chat bubble invites the
// reader to treat the reply as an assertion; what actually comes back is a SEARCH,
// so the screen shows the search it ran and the rows it found, each with the same
// badge and citation it has on its own document page. The model's contribution —
// turning the question into a filter — is shown as a filter, not as prose.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, type AskMatch, type AskResponse, type PortfolioFilter } from "../lib/api";
import { ConfidenceBadge, labelForField, LABEL_META, reasonsFor } from "../lib/confidence";
import { formatDateValue, formatDatesInText } from "../lib/format";
import { EmptyState, ErrorState, SectionTitle, Skeleton } from "../components/ui";

const EXAMPLES = [
  "Which contracts have a notice period under 60 days?",
  "Show me every liability cap we could quote",
  "Which contracts are missing a liability cap?",
  "Anything with exclusivity terms?",
];

/** The filter, in words. Shows the reader exactly what was searched. */
function FilterSummary({ filter }: { filter: PortfolioFilter }) {
  const parts: string[] = [];
  if (filter.fieldKeys.length) parts.push(`fields: ${filter.fieldKeys.join(", ")}`);
  if (filter.duration) {
    const op = { lt: "under", lte: "at most", gt: "over", gte: "at least", eq: "exactly" }[filter.duration.op];
    parts.push(`duration ${op} ${filter.duration.days} days`);
  }
  if (filter.date) {
    if (filter.date.op === "between") parts.push(`date between ${filter.date.from} and ${filter.date.to}`);
    else parts.push(`date ${filter.date.op} ${filter.date.from ?? filter.date.to}`);
  }
  if (filter.valueContains) parts.push(`text contains “${filter.valueContains}”`);
  if (filter.counterpartyContains) parts.push(`counterparty like “${filter.counterpartyContains}”`);
  if (filter.labels?.length) parts.push(`labelled ${filter.labels.join(" or ")}`);

  return (
    <div className="rounded border border-rule bg-paper px-3 py-2 text-sm text-muted">
      <span className="font-medium text-ink">Searched: </span>
      {parts.length ? formatDatesInText(parts.join(" · ")) : "every extracted field"}
    </div>
  );
}

function MatchRow({ m }: { m: AskMatch }) {
  const label = labelForField(m.field);
  const meta = LABEL_META[label];
  const reasons = reasonsFor(m.field);

  return (
    <li className={`bg-surface py-3 pl-3 pr-3 ${meta.barBorder}`}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Link to={`/documents/${m.documentId}`} className="link font-medium">
          {m.filename}
        </Link>
        <span className="text-sm text-faint">{m.field.fieldKey}</span>
        <span className="ml-auto">
          <ConfidenceBadge label={label} size="sm" />
        </span>
      </div>

      {m.field.valueVerbatim ? (
        <p className="mt-1.5 text-ink">{formatDateValue(m.field.valueVerbatim)}</p>
      ) : (
        <p className="mt-1.5 text-muted italic">No value was extracted for this field.</p>
      )}

      <div className="mt-1 flex flex-wrap items-center gap-x-3 text-sm text-muted">
        {m.field.clauseLabel && <span>Cited: {m.field.clauseLabel}</span>}
        {m.comparison?.kind === "duration" && (
          <span>
            Read as {m.comparison.days} days
            {m.comparison.from === "parsed" && " (parsed from the quoted text)"}
          </span>
        )}
        {m.comparison?.kind === "date" && (
          <span>
            Read as {formatDateValue(m.comparison.date)}
            {m.comparison.from === "parsed" && " (parsed from the quoted text)"}
          </span>
        )}
      </div>

      {reasons.length > 0 && (
        <ul className="mt-1.5 space-y-0.5 text-sm text-muted">
          {reasons.map((r) => (
            <li key={r}>· {r}</li>
          ))}
        </ul>
      )}

      {/* The statute layer keeps its own badge here too, rather than being folded
          into the extraction's label. */}
      {m.statuteFlags.map((f) => (
        <div key={f.id} className="mt-2 rounded border border-navy/30 bg-navybg px-2.5 py-2 text-sm">
          <div className="flex items-baseline gap-2">
            <ConfidenceBadge label="statutory" size="sm" />
            <span className="font-medium text-ink">
              {f.statute} {f.citation}
            </span>
          </div>
          <p className="mt-1 text-ink">{f.trigger}</p>
        </div>
      ))}
    </li>
  );
}

export default function Ask() {
  const caps = useQuery({ queryKey: ["ask", "capabilities"], queryFn: api.askCapabilities });

  const [input, setInput] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  // Set when the previous reply was a clarifying question. Its presence is what
  // guarantees the loop is at most ONE round-trip: the next call carries it, and
  // the API refuses a second question.
  const [pending, setPending] = useState<{ originalQuery: string; question: string } | null>(null);

  const ask = useMutation({
    mutationFn: (q: string) => api.ask(q, pending ?? undefined),
    onSuccess: (res, q) => {
      if (res.mode === "clarify") {
        setPending({ originalQuery: pending?.originalQuery ?? q, question: res.question });
        setResult(res);
      } else {
        setPending(null);
        setResult(res);
      }
      setInput("");
    },
  });

  const reset = () => {
    setPending(null);
    setResult(null);
    ask.reset();
  };

  if (caps.isLoading) return <Skeleton className="h-40" />;
  if (caps.isError) return <ErrorState message={(caps.error as Error).message} />;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-ink">Ask the portfolio</h1>
        <p className="mt-1 max-w-[70ch] text-muted">
          Questions are turned into a search over the clauses this tool already extracted. The
          answer is the rows it found, with the same labels and citations as everywhere else — no
          value on this screen was written by a language model.
        </p>
      </div>

      {!caps.data!.llmConfigured && (
        <div className="rounded border border-warn/50 bg-warnbg px-3 py-2 text-sm text-ink">
          <span className="font-medium">Not configured.</span> Set <code>OPENROUTER_API_KEY</code> in
          the API environment to turn questions into searches. Benchmarking and every other screen
          work without it.
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          const q = input.trim();
          if (q.length >= 2) ask.mutate(q);
        }}
        className="space-y-2"
      >
        {pending && (
          <div className="rounded border border-navy/30 bg-navybg px-3 py-2 text-sm">
            <p className="font-medium text-ink">One thing first: {pending.question}</p>
            <p className="mt-0.5 text-muted">
              Asked once only — whatever you answer, the next step is a search.
            </p>
          </div>
        )}
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={pending ? "Your answer…" : "e.g. which contracts have a notice period under 60 days?"}
            aria-label={pending ? "Answer the clarifying question" : "Ask about the portfolio"}
            disabled={!caps.data!.llmConfigured || ask.isPending}
            className="flex-1 rounded border border-rule bg-surface px-3 py-2 text-ink placeholder:text-faint disabled:bg-paper"
          />
          <button
            type="submit"
            disabled={!caps.data!.llmConfigured || ask.isPending || input.trim().length < 2}
            className="rounded bg-navy px-4 py-2 font-medium text-white disabled:opacity-40"
          >
            {ask.isPending ? "Searching…" : pending ? "Answer" : "Ask"}
          </button>
          {(result || pending) && (
            <button type="button" onClick={reset} className="rounded border border-rule px-3 py-2 text-muted">
              Clear
            </button>
          )}
        </div>
        {!pending && !result && (
          <div className="flex flex-wrap gap-2 pt-1">
            {EXAMPLES.map((e) => (
              <button
                key={e}
                type="button"
                onClick={() => setInput(e)}
                className="rounded-full border border-rule px-3 py-1 text-sm text-muted hover:bg-paper"
              >
                {e}
              </button>
            ))}
          </div>
        )}
      </form>

      {ask.isError && <ErrorState message={(ask.error as Error).message} />}

      {result?.mode === "results" && (
        <section className="space-y-3">
          <SectionTitle right={<span className="text-sm text-muted">{result.totalMatched} found</span>}>
            Results
          </SectionTitle>

          {result.restated && <p className="text-muted">{formatDatesInText(result.restated)}</p>}
          <FilterSummary filter={result.filter} />

          {/* Every way this search could be narrower than the reader assumes. */}
          {result.noSuchField && (
            <div className="rounded border border-alert/50 bg-alertbg px-3 py-2 text-sm text-ink">
              This tool has no field called <code>{result.unknownKeys.join(", ")}</code>, so nothing
              was searched. Fields it does hold: {caps.data!.searchableFieldKeys.join(", ")}.
            </div>
          )}
          {result.skippedUnparseable > 0 && (
            <div className="rounded border border-warn/50 bg-warnbg px-3 py-2 text-sm text-ink">
              {result.skippedUnparseable} field(s) matched the field name but their quoted text held
              no readable number or date, so they could not be compared and were left out.
            </div>
          )}
          {result.truncated && (
            <div className="rounded border border-rule bg-paper px-3 py-2 text-sm text-muted">
              Showing the first {result.matches.length} of {result.totalMatched}.
            </div>
          )}

          {result.matches.length === 0 && !result.noSuchField ? (
            <EmptyState title="Nothing matched that search.">
              This searches extracted values only. If a term exists in a contract but was never
              extracted, no wording of the question will find it — so treat this as “not extracted”,
              not as “not in your contracts”.
            </EmptyState>
          ) : (
            <ul className="divide-y divide-rule overflow-hidden rounded border border-rule">
              {result.matches.map((m) => (
                <MatchRow key={m.field.id} m={m} />
              ))}
            </ul>
          )}

          <p className="text-sm text-faint">{result.note}</p>
        </section>
      )}

      <section className="rounded border border-rule bg-paper px-4 py-3">
        <h2 className="font-medium text-ink">What this can’t do</h2>
        <ul className="mt-1.5 space-y-1 text-sm text-muted">
          {caps.data!.limits.map((l) => (
            <li key={l}>· {l}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
