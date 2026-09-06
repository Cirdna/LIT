import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ClauseAnnotation } from "../lib/api";
import { formatDate } from "../lib/format";
import { EmptyState, ErrorState, Skeleton } from "../components/ui";
import { Avatar, REVIEW_META, ReviewBadge, StatusBadge, StatusDot, reviewDotColor } from "../lib/statuteStatus";

type Filter = "all" | "open" | "resolved";

export default function StatuteReview() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  const list = useQuery({ queryKey: ["statutes"], queryFn: () => api.statutes() });

  if (list.isLoading) return <StatuteSkeleton />;
  if (list.isError) return <ErrorState message={(list.error as Error).message} />;
  const clauses = list.data!.clauses;

  const filtered = clauses.filter((c) =>
    filter === "all" ? true : filter === "open" ? c.reviewStatus === "open" : c.reviewStatus !== "open",
  );
  const bySource = groupBy(filtered, (c) => c.source);
  const activeId = selectedId ?? filtered[0]?.id ?? null;

  const openCount = clauses.filter((c) => c.reviewStatus === "open").length;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-ink">Clause assessment &amp; review</h1>
          <p className="text-muted">
            Verify each AI-flagged statutory clause. Agree, disagree, or escalate — every action is kept in the audit
            trail.
          </p>
        </div>
        <div className="flex overflow-hidden rounded border border-rule text-sm">
          {(["all", "open", "resolved"] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 capitalize ${filter === f ? "bg-navy text-white" : "bg-surface text-muted hover:bg-paper"}`}
            >
              {f}
              {f === "open" ? ` (${openCount})` : ""}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
        {/* Left rail: clause list grouped by Act. */}
        <aside className="max-h-[calc(100vh-11rem)] space-y-4 overflow-auto pr-1">
          {filtered.length === 0 ? (
            <EmptyState title="Nothing in this view.">
              <p>Switch the filter to see other clauses.</p>
            </EmptyState>
          ) : (
            [...bySource.entries()].map(([source, items]) => (
              <div key={source}>
                <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">{source}</h2>
                <ul className="space-y-1">
                  {items.map((c) => (
                    <li key={c.id}>
                      <button
                        onClick={() => setSelectedId(c.id)}
                        className={`flex w-full items-center gap-2 rounded border px-2 py-1.5 text-left text-sm transition ${
                          activeId === c.id ? "border-navy bg-navy/5" : "border-rule bg-surface hover:bg-paper"
                        }`}
                      >
                        <StatusDot status={c.aiStatus} />
                        <span className="min-w-0 flex-1 truncate text-ink">{c.provision}</span>
                        {REVIEW_META[c.reviewStatus] && (
                          <span aria-hidden className={`text-xs ${reviewDotColor(c.reviewStatus)}`}>
                            {REVIEW_META[c.reviewStatus]!.glyph}
                          </span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </aside>

        {/* Main: the selected clause, split into text + verification panel. */}
        <div>{activeId ? <ClausePanel id={activeId} /> : <EmptyState title="Select a clause to review." />}</div>
      </div>
    </div>
  );
}

function ClausePanel({ id }: { id: string }) {
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const [flash, setFlash] = useState(false);

  const detail = useQuery({ queryKey: ["statute", id], queryFn: () => api.statute(id) });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["statute", id] });
    qc.invalidateQueries({ queryKey: ["statutes"] });
  };

  const addNote = useMutation({
    mutationFn: (body: string) => api.addStatuteNote(id, body),
    onSuccess: () => {
      setNote("");
      invalidate();
    },
  });

  const verify = useMutation({
    mutationFn: (action: "agree" | "disagree" | "manual_review") =>
      api.verifyStatute(id, action, note.trim() || undefined),
    onSuccess: () => {
      setNote("");
      setFlash(true);
      setTimeout(() => setFlash(false), 1200);
      invalidate();
    },
  });

  if (detail.isLoading) return <Skeleton className="h-[32rem]" />;
  if (detail.isError) return <ErrorState message={(detail.error as Error).message} />;
  const c = detail.data!;
  const canDecide = c.aiStatus === "Inferred" || c.aiStatus === "Evaluation Required";
  const review = REVIEW_META[c.reviewStatus];
  const notes = c.annotations;

  return (
    <div
      className={`grid gap-4 rounded-lg border p-1 transition lg:grid-cols-2 ${
        flash ? "border-ok ring-2 ring-ok/40" : "border-transparent"
      }`}
    >
      {/* Left half: the statutory text (the "document"). */}
      <section className="panel p-4">
        <div className="mb-2 flex items-center gap-2">
          <StatusBadge status={c.aiStatus} />
          {review && <ReviewBadge status={c.reviewStatus} />}
        </div>
        <h2 className="text-lg font-bold text-ink">
          {c.source} · {c.provision}
        </h2>
        {c.summary && <p className="mt-2 text-sm text-muted">{c.summary}</p>}
        <blockquote className="mt-3 border-l-4 border-rule bg-surface px-3 py-2 text-[0.95rem] leading-relaxed text-ink">
          {c.exactWording}
        </blockquote>
        <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted">
          {c.authorityBasis && <Meta label="Authority" value={c.authorityBasis.replace(/_/g, " ")} />}
          {c.caseCitation && <Meta label="Citation" value={c.caseCitation} />}
          {c.naReason && <Meta label="Reason" value={c.naReason.replace(/_/g, " ")} />}
          {c.targetFields.length > 0 && <Meta label="Target fields" value={c.targetFields.join(", ")} />}
        </dl>
      </section>

      {/* Right half: AI flagging & verification panel. */}
      <section className="panel flex flex-col p-4">
        <h3 className="text-base font-semibold text-ink">Verification</h3>
        <p className="mt-0.5 text-sm text-muted">
          {canDecide
            ? "This flag needs a human decision."
            : c.aiStatus === "Quoted"
              ? "Directly quoted from the statute. Escalate only if something looks off."
              : "Flagged not applicable. Escalate if you believe it should apply."}
        </p>

        {/* Append Note / Justification */}
        <label className="mt-3 text-sm font-medium text-ink" htmlFor="note">
          Append Note / Justification
        </label>
        <textarea
          id="note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          placeholder="Reason for override, risk note, context…"
          className="mt-1 rounded border border-rule bg-paper px-2.5 py-1.5 text-sm"
        />
        <div className="mt-1">
          <button
            className="btn btn-sm"
            disabled={!note.trim() || addNote.isPending}
            onClick={() => addNote.mutate(note.trim())}
          >
            {addNote.isPending ? "Saving…" : "Add note"}
          </button>
        </div>

        {/* Resolution action bar */}
        <div className="mt-3 flex flex-wrap gap-2 border-t border-rule pt-3">
          {canDecide && (
            <>
              <button
                className="btn btn-sm border-ok text-ok hover:bg-okbg disabled:opacity-50"
                disabled={verify.isPending}
                onClick={() => verify.mutate("agree")}
                title="Agree with the AI flag → Human Verified"
              >
                ✓ Agree
              </button>
              <button
                className="btn btn-sm border-warn text-warn hover:bg-warnbg disabled:opacity-50"
                disabled={verify.isPending}
                onClick={() => verify.mutate("disagree")}
                title="Disagree → Overridden"
              >
                ✗ Disagree
              </button>
            </>
          )}
          <button
            className="btn btn-sm border-navy text-navy hover:bg-navy/5 disabled:opacity-50"
            disabled={verify.isPending}
            onClick={() => verify.mutate("manual_review")}
            title="Escalate to senior legal review"
          >
            ⚑ Raise Manual Review
          </button>
        </div>
        {review && (
          <p className="mt-2 text-sm">
            <span className="text-muted">Status: </span>
            <span className={reviewDotColor(c.reviewStatus)}>{review.label}</span>
          </p>
        )}

        {/* Audit trail */}
        <div className="mt-4 flex-1 border-t border-rule pt-3">
          <h4 className="mb-2 text-sm font-semibold text-ink">Audit trail</h4>
          {notes.length === 0 ? (
            <p className="text-sm text-muted">No notes or decisions yet.</p>
          ) : (
            <ul className="space-y-2.5">
              {notes.map((a) => (
                <AnnotationItem key={a.id} a={a} />
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}

function AnnotationItem({ a }: { a: ClauseAnnotation }) {
  const verb =
    a.kind === "note" ? "added a note" : a.kind === "agree" ? "agreed" : a.kind === "disagree" ? "disagreed" : "raised manual review";
  return (
    <li className="flex gap-2">
      <Avatar author={a.author} />
      <div className="min-w-0 flex-1">
        <div className="text-xs text-muted">
          <span className="font-medium text-ink">{a.author}</span> {verb} ·{" "}
          {formatDate(a.createdAt)} · {timeOf(a.createdAt)}
        </div>
        {a.body && <p className="mt-0.5 text-sm text-ink">{a.body}</p>}
      </div>
    </li>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="col-span-2">
      <dt className="inline font-medium text-ink">{label}: </dt>
      <dd className="inline">{value}</dd>
    </div>
  );
}

function groupBy<T>(items: T[], key: (t: T) => string): Map<string, T[]> {
  const m = new Map<string, T[]>();
  for (const it of items) (m.get(key(it)) ?? m.set(key(it), []).get(key(it))!).push(it);
  return m;
}

function timeOf(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function StatuteSkeleton() {
  return (
    <div>
      <Skeleton className="mb-4 h-8 w-72" />
      <div className="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <Skeleton className="h-96" />
        <Skeleton className="h-96" />
      </div>
    </div>
  );
}
