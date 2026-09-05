import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, type ConflictDTO, type DocumentSummary, type FieldDTO } from "../lib/api";
import { ConfidenceBadge, labelForField, labelForTier } from "../lib/confidence";
import { formatDateValue, formatDatesInText } from "../lib/format";
import { EmptyState, ErrorState, Skeleton } from "../components/ui";

const SEVERITY: Record<string, string> = {
  high: "border-alert/50 bg-alertbg text-alert",
  medium: "border-warn/50 bg-warnbg text-warn",
  low: "border-rule bg-paper text-muted",
};

export default function Conflicts() {
  const q = useQuery({ queryKey: ["conflicts"], queryFn: () => api.conflicts() });

  if (q.isLoading) return <Skeleton className="h-64" />;
  if (q.isError) return <ErrorState message={(q.error as Error).message} />;
  const conflicts = q.data!.conflicts;

  return (
    <div>
      <h1 className="mb-1 text-2xl font-bold text-ink">Conflicts across your contracts</h1>
      <p className="mb-5 text-muted">
        Where two agreements say things that cannot both be true. Each side is shown with its own citation and
        confidence — a conflict is exactly the kind of question a lawyer should settle.
      </p>

      {conflicts.length === 0 ? (
        <EmptyState title="No conflicts found across your contracts.">
          <p>When two agreements grant overlapping or contradictory terms, they will appear here.</p>
        </EmptyState>
      ) : (
        <div className="space-y-6">
          {conflicts.map((c) => (
            <ConflictCard key={c.id} conflict={c} />
          ))}
        </div>
      )}
    </div>
  );
}

function ConflictCard({ conflict }: { conflict: ConflictDTO }) {
  const navigate = useNavigate();
  const docById = new Map(conflict.documents.map((d) => [d.id, d]));
  const create = useMutation({
    mutationFn: () => api.createHandoff(conflict.id),
    onSuccess: (brief) => navigate(`/handoffs/${brief.id}`),
  });

  return (
    <section className="panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule bg-paper px-4 py-3">
        <div className="flex items-center gap-3">
          <span className={`rounded border px-2 py-0.5 text-sm font-medium ${SEVERITY[conflict.severity] ?? SEVERITY.low}`}>
            {conflict.severity} severity
          </span>
          <ConfidenceBadge label={labelForTier(conflict.confidenceTier)} size="sm" />
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => create.mutate()} disabled={create.isPending}>
          {create.isPending ? "Preparing…" : "Create handoff brief"}
        </button>
      </div>

      <p className="px-4 py-3 text-ink">{formatDatesInText(conflict.summary)}</p>

      <div className="grid gap-px bg-rule md:grid-cols-2">
        {conflict.fields.slice(0, 2).map((f) => (
          <ClauseSide key={f.id} field={f} doc={docById.get(f.documentId)} />
        ))}
      </div>
    </section>
  );
}

function ClauseSide({ field, doc }: { field: FieldDTO; doc?: DocumentSummary }) {
  return (
    <div className="bg-surface p-4">
      <div className="mb-1 text-sm font-medium text-navy">{doc?.filename ?? "Document"}</div>
      <div className="mb-2 flex items-center gap-2 text-sm text-muted">
        <span>{field.clauseLabel ?? "Clause not identified"}</span>
        <ConfidenceBadge label={labelForField(field)} size="sm" />
      </div>
      <blockquote className="border-l-4 border-rule pl-3 text-ink">
        “{field.valueVerbatim ? formatDateValue(field.valueVerbatim) : "—"}”
      </blockquote>
    </div>
  );
}
