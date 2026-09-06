// Shared visual language for statute review — the four AI flag statuses, the
// human review states, avatars — used by both the standalone /statutes page and
// the per-contract "Applicable statutes" panel. Colour always travels with a
// glyph (house rule).
import type { AiStatus, ReviewStatus } from "./api";

export const AI_META: Record<AiStatus, { cls: string; glyph: string; dot: string }> = {
  Quoted: { cls: "border-ok/40 bg-okbg text-ok", glyph: "✓", dot: "bg-ok" },
  Inferred: { cls: "border-warn/50 bg-warnbg text-warn", glyph: "~", dot: "bg-warn" },
  "Evaluation Required": { cls: "border-navy/40 bg-navy/10 text-navy", glyph: "?", dot: "bg-navy" },
  NA: { cls: "border-alert/50 bg-alertbg text-alert", glyph: "—", dot: "bg-alert" },
};

export const REVIEW_META: Record<ReviewStatus, { label: string; cls: string; glyph: string } | null> = {
  open: null,
  human_verified: { label: "Human Verified", cls: "border-ok/50 bg-okbg text-ok", glyph: "✓" },
  overridden: { label: "Overridden", cls: "border-warn/50 bg-warnbg text-warn", glyph: "✗" },
  manual_review: { label: "Manual Review", cls: "border-navy/40 bg-navy/10 text-navy", glyph: "⚑" },
};

const REASON_LABEL: Record<string, string> = {
  governing_law_excluded: "Governing law excludes this statute",
  dependency_unavailable: "Depends on a statute not in the knowledge store",
  contract_type_excluded: "Out of scope for this contract type",
};

export function reasonLabel(reason: string | null): string | null {
  if (!reason) return null;
  return REASON_LABEL[reason] ?? reason.replace(/_/g, " ");
}

export function reviewDotColor(s: ReviewStatus): string {
  return s === "human_verified" ? "text-ok" : s === "overridden" ? "text-warn" : s === "manual_review" ? "text-navy" : "text-muted";
}

export function StatusBadge({ status }: { status: AiStatus }) {
  const m = AI_META[status];
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs font-medium ${m.cls}`}>
      <span aria-hidden className="font-bold">{m.glyph}</span>
      {status}
    </span>
  );
}

export function ReviewBadge({ status }: { status: ReviewStatus }) {
  const m = REVIEW_META[status];
  if (!m) return null;
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs font-medium ${m.cls}`}>
      <span aria-hidden>{m.glyph}</span>
      {m.label}
    </span>
  );
}

export function StatusDot({ status }: { status: AiStatus }) {
  return <span aria-hidden className={`h-2 w-2 flex-none rounded-full ${AI_META[status].dot}`} title={status} />;
}

export function Avatar({ author }: { author: string }) {
  const initials = author
    .replace(/@.*/, "")
    .split(/[.\-_ ]/)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .slice(0, 2)
    .join("");
  return (
    <span className="grid h-7 w-7 flex-none place-items-center rounded-full bg-navy/10 text-xs font-semibold text-navy">
      {initials || "?"}
    </span>
  );
}
