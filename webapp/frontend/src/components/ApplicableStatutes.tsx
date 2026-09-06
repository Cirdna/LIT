import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ContractStatute } from "../lib/api";
import { formatDate } from "../lib/format";
import { AI_META, Avatar, ReviewBadge, StatusBadge, StatusDot, reasonLabel, reviewDotColor } from "../lib/statuteStatus";

// Per-contract statute review, embedded in the contract detail view. Which
// statutes apply (and whether they fire or resolve to NA) is computed from the
// contract's governing law + type; the human then verifies each flag, with a
// per-contract audit trail.
export function ApplicableStatutes({ documentId }: { documentId: string }) {
  const q = useQuery({ queryKey: ["docStatutes", documentId], queryFn: () => api.documentStatutes(documentId) });
  const [openId, setOpenId] = useState<string | null>(null);

  if (q.isLoading) return null;
  if (q.isError || !q.data) return null;
  const { statutes, jurisdiction } = q.data;
  if (statutes.length === 0) return null;

  const fired = statutes.filter((s) => s.status !== "NA").length;

  return (
    <section className="panel p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-ink">Applicable statutes</h2>
          <p className="text-xs text-muted">
            Singapore statutory overlay for this contract.{" "}
            {jurisdiction === "excluded"
              ? "Governing law is not Singapore — all resolve to N/A."
              : `${fired} of ${statutes.length} apply.`}
          </p>
        </div>
      </div>

      <div className="mt-3 space-y-2">
        {statutes.map((s) => (
          <StatuteCard
            key={s.id}
            documentId={documentId}
            s={s}
            open={openId === s.id}
            onToggle={() => setOpenId(openId === s.id ? null : s.id)}
          />
        ))}
      </div>
    </section>
  );
}

function StatuteCard({
  documentId,
  s,
  open,
  onToggle,
}: {
  documentId: string;
  s: ContractStatute;
  open: boolean;
  onToggle: () => void;
}) {
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const [flash, setFlash] = useState(false);
  const invalidate = () => qc.invalidateQueries({ queryKey: ["docStatutes", documentId] });

  const addNote = useMutation({
    mutationFn: (body: string) => api.addDocStatuteNote(documentId, s.id, body),
    onSuccess: () => {
      setNote("");
      invalidate();
    },
  });
  const verify = useMutation({
    mutationFn: (action: "agree" | "disagree" | "manual_review") =>
      api.verifyDocStatute(documentId, s.id, action, note.trim() || undefined),
    onSuccess: () => {
      setNote("");
      setFlash(true);
      setTimeout(() => setFlash(false), 1200);
      invalidate();
    },
  });

  const canDecide = s.status === "Inferred" || s.status === "Evaluation Required";

  return (
    <div className={`rounded border ${AI_META[s.status].cls.split(" ").find((c) => c.startsWith("border")) ?? "border-rule"} ${flash ? "ring-2 ring-ok/40" : ""}`}>
      <button onClick={onToggle} className="flex w-full items-center gap-2 px-3 py-2 text-left">
        <StatusDot status={s.status} />
        <span className="min-w-0 flex-1">
          <span className="text-sm font-medium text-ink">
            {s.source} · {s.provision}
          </span>
          {s.reason && <span className="ml-1 text-xs text-muted">— {reasonLabel(s.reason)}</span>}
        </span>
        {s.reviewStatus !== "open" && <ReviewBadge status={s.reviewStatus} />}
        <StatusBadge status={s.status} />
        <span aria-hidden className="text-faint">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div className="border-t border-rule/60 px-3 py-2">
          {s.summary && <p className="text-sm text-muted">{s.summary}</p>}
          <blockquote className="mt-2 border-l-4 border-rule bg-surface px-3 py-1.5 text-sm leading-relaxed text-ink">
            {s.exactWording}
          </blockquote>
          {s.caseCitation && <p className="mt-1 text-xs text-faint">{s.caseCitation}</p>}

          {/* Note + action bar */}
          <div className="mt-3">
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder="Append note / justification…"
              className="w-full rounded border border-rule bg-paper px-2.5 py-1.5 text-sm"
            />
            <div className="mt-1 flex flex-wrap gap-2">
              <button className="btn btn-sm" disabled={!note.trim() || addNote.isPending} onClick={() => addNote.mutate(note.trim())}>
                Add note
              </button>
              {canDecide && (
                <>
                  <button className="btn btn-sm border-ok text-ok hover:bg-okbg disabled:opacity-50" disabled={verify.isPending} onClick={() => verify.mutate("agree")}>
                    ✓ Agree
                  </button>
                  <button className="btn btn-sm border-warn text-warn hover:bg-warnbg disabled:opacity-50" disabled={verify.isPending} onClick={() => verify.mutate("disagree")}>
                    ✗ Disagree
                  </button>
                </>
              )}
              <button className="btn btn-sm border-navy text-navy hover:bg-navy/5 disabled:opacity-50" disabled={verify.isPending} onClick={() => verify.mutate("manual_review")}>
                ⚑ Manual Review
              </button>
            </div>
          </div>

          {/* Audit trail */}
          {s.annotations.length > 0 && (
            <ul className="mt-3 space-y-2 border-t border-rule/60 pt-2">
              {s.annotations.map((a) => (
                <li key={a.id} className="flex gap-2">
                  <Avatar author={a.author} />
                  <div className="min-w-0 flex-1">
                    <div className="text-xs text-muted">
                      <span className="font-medium text-ink">{a.author}</span>{" "}
                      {a.kind === "note" ? "added a note" : a.kind === "agree" ? "agreed" : a.kind === "disagree" ? "disagreed" : "raised manual review"} ·{" "}
                      {formatDate(a.createdAt)}
                    </div>
                    {a.body && <p className="mt-0.5 text-sm text-ink">{a.body}</p>}
                  </div>
                </li>
              ))}
            </ul>
          )}
          {s.reviewStatus !== "open" && (
            <p className="mt-2 text-xs">
              <span className="text-muted">Status: </span>
              <span className={reviewDotColor(s.reviewStatus)}>{s.reviewStatus.replace(/_/g, " ")}</span>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
