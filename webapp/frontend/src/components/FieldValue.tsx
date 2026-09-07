import { useState } from "react";
import type { FieldDTO, FieldState } from "../lib/api";
import { COARSE_LABELS, COARSE_META, CoarseTag, coarseLabel, reasonsFor } from "../lib/confidence";

const ABSENCE_COPY: Record<string, { text: string; cls: string }> = {
  not_present: { text: "Not in this contract.", cls: "text-muted" },
  not_found: { text: "Could not find this in the document.", cls: "text-warn" },
  illegible: { text: "Could not read this — the page was illegible.", cls: "text-alert" },
};

const BAR_COLOR: Record<FieldState, string> = {
  quoted: "border-l-ok",
  inferred: "border-l-warn",
  evaluation_required: "border-l-navy",
  na: "border-l-alert",
};

function benchmarkLine(field: FieldDTO): string | null {
  if (field.claimType !== "benchmark") return null;
  const n = field.valueNormalized ?? {};
  const range = typeof n.reference_range === "string" ? n.reference_range : "our reference range";
  const assessment = typeof n.assessment === "string" ? n.assessment : "within";
  return `${assessment === "below" ? "Below" : assessment === "above" ? "Above" : "Within"} our reference range of ${range}.`;
}

export function FieldValue({
  label,
  field,
  page,
  active,
  onCite,
  onSave,
}: {
  label: string;
  field: FieldDTO;
  page?: number | null;
  active?: boolean;
  onCite?: (field: FieldDTO) => void;
  onSave?: (fieldId: string, patch: { state: FieldState; value: string | null }) => Promise<void>;
}) {
  const state = coarseLabel(field);
  const reasons = reasonsFor(field);
  const bench = benchmarkLine(field);
  const hasValue = field.valueVerbatim != null;
  const suspected = field.confidenceTier === "unverified" && !field.humanEdited;

  const [editing, setEditing] = useState(false);
  const [draftValue, setDraftValue] = useState(field.valueVerbatim ?? "");
  const [draftState, setDraftState] = useState<FieldState>(state);
  const [saving, setSaving] = useState(false);

  const canCite = field.anchorLineIds.length > 0 && !!onCite && !editing;

  function startEdit(e: React.MouseEvent) {
    e.stopPropagation();
    setDraftValue(field.valueVerbatim ?? "");
    setDraftState(state);
    setEditing(true);
  }

  async function save() {
    if (!onSave) return;
    setSaving(true);
    try {
      await onSave(field.id, { state: draftState, value: draftState === "na" ? null : draftValue.trim() });
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className={`border-l-4 ${BAR_COLOR[state]} rounded-r bg-surface px-3 py-2.5 ${active ? "ring-2 ring-navy" : ""} ${
        canCite ? "cursor-pointer hover:bg-paper" : ""
      }`}
      onClick={canCite ? () => onCite!(field) : undefined}
      role={canCite ? "button" : undefined}
      tabIndex={canCite ? 0 : undefined}
      onKeyDown={
        canCite
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onCite!(field);
              }
            }
          : undefined
      }
    >
      <div className="flex items-start justify-between gap-3">
        <span className="text-sm font-medium text-muted">{label}</span>
        <div className="flex items-center gap-1.5">
          <CoarseTag label={state} />
          {onSave && !editing && (
            <button onClick={startEdit} className="text-xs text-muted hover:text-navy" title="Edit value and state">
              Edit
            </button>
          )}
        </div>
      </div>

      {editing ? (
        <div className="mt-2 space-y-2" onClick={(e) => e.stopPropagation()}>
          <select
            value={draftState}
            onChange={(e) => setDraftState(e.target.value as FieldState)}
            className="w-full rounded border border-rule bg-paper px-2 py-1 text-sm"
          >
            {COARSE_LABELS.map((s) => (
              <option key={s} value={s}>
                {COARSE_META[s].label}
              </option>
            ))}
          </select>
          {draftState !== "na" && (
            <textarea
              value={draftValue}
              onChange={(e) => setDraftValue(e.target.value)}
              rows={2}
              placeholder="Value / quoted text…"
              className="w-full rounded border border-rule bg-paper px-2 py-1 text-sm"
            />
          )}
          <div className="flex gap-2">
            <button className="btn btn-sm btn-primary" disabled={saving} onClick={save}>
              {saving ? "Saving…" : "Save"}
            </button>
            <button className="btn btn-sm" disabled={saving} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="mt-1">
            {bench ? (
              <p className="text-[1.05rem] text-warn">{bench}</p>
            ) : hasValue ? (
              <p className={`text-[1.05rem] ${suspected ? "text-alert" : "text-ink"}`}>
                {suspected ? (
                  <>
                    <span className="line-through decoration-alert/60">{field.valueVerbatim}</span>{" "}
                    <span className="text-sm font-medium">(suspected error)</span>
                  </>
                ) : (
                  field.valueVerbatim
                )}
              </p>
            ) : (
              <p className={`text-[1.02rem] ${ABSENCE_COPY[field.absenceReason ?? "not_found"]?.cls ?? "text-muted"}`}>
                {ABSENCE_COPY[field.absenceReason ?? "not_found"]?.text ?? "Not available."}
              </p>
            )}
          </div>

          {/* Citation — a clause is a stronger citation than a page alone. */}
          <div className="mt-1 text-sm">
            {field.clauseLabel ? (
              <span className="text-muted">
                {field.clauseLabel}
                {page ? <span className="text-faint"> · page {page}</span> : null}
              </span>
            ) : page ? (
              <span className="text-faint italic">page {page} only — no clause identified</span>
            ) : null}
            {canCite && <span className="ml-2 text-navy">· show on page →</span>}
            {field.humanEdited && (
              <span className="ml-2 text-faint" title={field.editedBy ? `edited by ${field.editedBy}` : "human edited"}>
                · edited
              </span>
            )}
          </div>

          {reasons.length > 0 && (
            <ul className="mt-1.5 space-y-0.5 border-t border-rule/60 pt-1.5 text-sm text-muted">
              {reasons.map((r, i) => (
                <li key={i} className="flex gap-1.5">
                  <span aria-hidden className={COARSE_META[state].text}>
                    •
                  </span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
