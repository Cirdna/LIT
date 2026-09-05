import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type HandoffDTO } from "../lib/api";
import { ErrorState, Skeleton } from "../components/ui";

export default function HandoffBrief() {
  const { id = "" } = useParams();
  const [copied, setCopied] = useState(false);
  const q = useQuery({ queryKey: ["handoff", id], queryFn: () => api.handoff(id) });

  if (q.isLoading) return <Skeleton className="h-96" />;
  if (q.isError) return <ErrorState message={(q.error as Error).message} />;
  const brief = q.data!;

  async function copy() {
    await navigator.clipboard.writeText(asPlainText(brief));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="no-print mb-4 flex items-center justify-between">
        <Link to="/conflicts" className="text-sm text-muted hover:text-ink">
          ← Conflicts
        </Link>
        <div className="flex gap-2">
          <button className="btn btn-sm" onClick={copy}>
            {copied ? "Copied" : "Copy to clipboard"}
          </button>
          <button className="btn btn-sm" onClick={() => window.print()}>
            Print
          </button>
        </div>
      </div>

      <article className="panel p-6">
        <header className="mb-5 border-b border-rule pb-4">
          <p className="eyebrow">Handoff brief for a lawyer</p>
          <h1 className="mt-1 text-2xl font-bold text-ink">{brief.issue}</h1>
          <p className="mt-1 text-sm text-faint">
            Prepared {new Date(brief.createdAt).toLocaleDateString()} · AITHENA reports facts from the documents; the
            judgement below needs a human.
          </p>
        </header>

        <Section n={1} title="The issue">
          <p className="text-ink">{brief.issue}</p>
        </Section>

        <Section n={2} title="Documents and clauses involved">
          <ul className="space-y-3">
            {brief.established.map((item, i) => (
              <li key={i} className="border-l-4 border-rule pl-3">
                <div className="text-sm font-medium text-navy">{item.label}</div>
                {item.detail && <blockquote className="mt-0.5 text-ink">“{item.detail}”</blockquote>}
                <div className="mt-0.5 text-sm text-muted">
                  {item.citation ?? "Clause not identified"} · confidence: {item.confidenceTier}
                </div>
              </li>
            ))}
          </ul>
        </Section>

        <Section n={3} title="What AITHENA already established">
          <ul className="list-disc space-y-1 pl-5 text-ink">
            {brief.established.map((item, i) => (
              <li key={i}>
                {item.label}
                {item.detail ? `: "${item.detail}"` : ""}.
              </li>
            ))}
            {brief.documents && brief.documents.length > 0 && (
              <li>
                Documents:{" "}
                {brief.documents.map((d, i) => (
                  <span key={d.id}>
                    {i > 0 && ", "}
                    <Link to={`/documents/${d.id}`} className="link">
                      {d.filename}
                    </Link>
                  </span>
                ))}
                .
              </li>
            )}
          </ul>
        </Section>

        <Section n={4} title="The specific question needing human judgement">
          <p className="rounded border border-navy/30 bg-okbg p-3 text-lg font-medium text-ink">{brief.question}</p>
        </Section>
      </article>
    </div>
  );
}

function Section({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="mb-5">
      <h2 className="mb-2 text-base font-semibold text-ink">
        <span className="mr-2 text-faint tnum">{n}.</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

function asPlainText(brief: HandoffDTO): string {
  const lines: string[] = [];
  lines.push(`HANDOFF BRIEF — ${brief.issue}`, "");
  lines.push("1. THE ISSUE", brief.issue, "");
  lines.push("2. DOCUMENTS AND CLAUSES INVOLVED");
  for (const item of brief.established) {
    lines.push(`- ${item.label}`);
    if (item.detail) lines.push(`  "${item.detail}"`);
    lines.push(`  ${item.citation ?? "Clause not identified"} (confidence: ${item.confidenceTier})`);
  }
  lines.push("");
  lines.push("3. WHAT AITHENA ESTABLISHED");
  for (const item of brief.established) lines.push(`- ${item.label}${item.detail ? `: "${item.detail}"` : ""}`);
  lines.push("");
  lines.push("4. THE SPECIFIC QUESTION NEEDING HUMAN JUDGEMENT", brief.question);
  return lines.join("\n");
}
