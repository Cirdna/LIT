import type { FieldDTO } from "../lib/api";
import { ConfidenceBadge, TIER_META, reasonsFor } from "../lib/confidence";

const ABSENCE_COPY: Record<string, { text: string; cls: string }> = {
  not_present: { text: "Not in this contract.", cls: "text-muted" },
  not_found: { text: "Could not find this in the document.", cls: "text-warn" },
  illegible: { text: "Could not read this — the page was illegible.", cls: "text-alert" },
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
}: {
  label: string;
  field: FieldDTO;
  page?: number | null;
  active?: boolean;
  onCite?: (field: FieldDTO) => void;
}) {
  const m = TIER_META[field.confidenceTier];
  const reasons = reasonsFor(field);
  const bench = benchmarkLine(field);
  const canCite = field.anchorLineIds.length > 0 && !!onCite;
  const hasValue = field.valueVerbatim != null;

  return (
    <div
      className={`${m.barBorder} rounded-r bg-surface px-3 py-2.5 ${active ? "ring-2 ring-navy" : ""} ${
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
        <ConfidenceBadge tier={field.confidenceTier} size="sm" />
      </div>

      <div className="mt-1">
        {bench ? (
          <p className="text-[1.05rem] text-warn">{bench}</p>
        ) : hasValue ? (
          <p
            className={`text-[1.05rem] ${
              field.confidenceTier === "unverified" ? "text-alert" : "text-ink"
            }`}
          >
            {field.confidenceTier === "unverified" ? (
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

      {/* Citation — a clause is a stronger citation than a page alone (§12). */}
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
      </div>

      {reasons.length > 0 && (
        <ul className="mt-1.5 space-y-0.5 border-t border-rule/60 pt-1.5 text-sm text-muted">
          {reasons.map((r, i) => (
            <li key={i} className="flex gap-1.5">
              <span aria-hidden className={m.text}>
                •
              </span>
              <span>{r}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
