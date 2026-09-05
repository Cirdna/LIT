// The confidence encoding. This is the product's one non-negotiable: every value
// carries a tier, and low-confidence values must be distinct from high-confidence
// ones AT A GLANCE — including for colour-blind users and on a projector at 3
// metres. So the encoding is never colour alone: it combines a verbal label, a
// glyph, and a border treatment. Lists additionally sort uncertain items upward
// (see `rank`). No percentages anywhere — non-experts misread them.
import type { ConfidenceTier, FieldDTO } from "./api";

type TierMeta = {
  rank: number; // lower = more confident; drives upward sorting of uncertainty
  short: string;
  label: string;
  glyph: string;
  text: string;
  bg: string;
  border: string;
  barBorder: string; // left-rule treatment (structural cue)
};

export const TIER_META: Record<ConfidenceTier, TierMeta> = {
  verbatim: {
    rank: 0,
    short: "Quoted",
    label: "Quoted from the contract",
    glyph: "✓",
    text: "text-ok",
    bg: "bg-okbg",
    border: "border-ok/40",
    barBorder: "border-l-4 border-l-ok border-solid",
  },
  normalised: {
    rank: 1,
    short: "Standardised",
    label: "Read and standardised from the contract",
    glyph: "=",
    text: "text-ok",
    bg: "bg-okbg",
    border: "border-ok/30",
    barBorder: "border-l-4 border-l-ok/70 border-solid",
  },
  assembled: {
    rank: 2,
    short: "Assembled",
    label: "Assembled from more than one clause",
    glyph: "+",
    text: "text-warn",
    bg: "bg-warnbg",
    border: "border-warn/40",
    barBorder: "border-l-4 border-l-warn border-solid",
  },
  inferred: {
    rank: 3,
    short: "Inferred",
    label: "Inferred — check this",
    glyph: "~",
    text: "text-warn",
    bg: "bg-warnbg",
    border: "border-warn/50",
    barBorder: "border-l-4 border-l-warn border-dashed",
  },
  unverified: {
    rank: 4,
    short: "Suspected error",
    label: "Suspected error — not found in the cited clause",
    glyph: "!",
    text: "text-alert",
    bg: "bg-alertbg",
    border: "border-alert/50",
    barBorder: "border-l-4 border-l-alert border-double",
  },
};

export function tierRank(t: ConfidenceTier): number {
  return TIER_META[t].rank;
}

export function ConfidenceBadge({ tier, size = "md" }: { tier: ConfidenceTier; size?: "sm" | "md" }) {
  const m = TIER_META[tier];
  const pad = size === "sm" ? "px-1.5 py-0.5 text-xs" : "px-2 py-0.5 text-sm";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border ${m.border} ${m.bg} ${m.text} ${pad} font-medium`}
      title={m.label}
    >
      <span aria-hidden className="grid h-4 w-4 place-items-center rounded-sm border border-current font-bold leading-none">
        {m.glyph}
      </span>
      {m.short}
    </span>
  );
}

/** Coarse OCR band in words — never a percentage (§9). */
export function ocrBand(mean: number | null): { word: string; tone: string } | null {
  if (mean == null) return null;
  if (mean >= 0.85) return { word: "high", tone: "text-ok" };
  if (mean >= 0.7) return { word: "moderate", tone: "text-warn" };
  return { word: "low", tone: "text-alert" };
}

/**
 * Plain-language evidence for a field's confidence. A tier badge alone is an
 * assertion; these reasons are what make the tool calibrated rather than
 * confident (§9). Scores become words, never numbers.
 */
export function reasonsFor(field: FieldDTO): string[] {
  const out: string[] = [];
  if (field.confidenceTier === "unverified")
    out.push("The quoted text was not found in the cited clause — treat this as a suspected error, not a value.");
  if (field.absenceReason === "illegible")
    out.push("The page it should appear on could not be read.");
  if (field.confidenceTier === "assembled" && field.clauseLabel)
    out.push(`Value assembled from ${field.clauseLabel}.`);
  if (field.consistencyScore != null && field.consistencyScore < 0.7)
    out.push("Two extraction passes disagreed on this value.");
  if (field.vlmAgreement != null && field.vlmAgreement < 0.7)
    out.push("The text reading and the image reading disagreed.");
  const competing = field.valueNormalized?.competing;
  if (Array.isArray(competing) && competing.length >= 2)
    out.push(`Competing readings: “${String(competing[0])}” vs “${String(competing[1])}”.`);
  if (field.claimType === "benchmark")
    out.push("This is our own reference range, not a statement about the law.");
  if (field.confidenceTier === "inferred" && field.anchorLineIds.length === 0)
    out.push("Inferred — there is no verbatim text in the document to point at.");
  return out;
}
