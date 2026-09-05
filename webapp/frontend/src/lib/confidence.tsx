// The confidence encoding. This is the product's one non-negotiable: every value
// carries a label, and low-confidence values must be distinct from high-confidence
// ones AT A GLANCE — including for colour-blind users and on a projector at 3
// metres. So the encoding is never colour alone: it combines a verbal label, a
// glyph, and a border treatment. No percentages anywhere — non-experts misread them.
//
// There are exactly THREE labels a reader ever sees ABOUT AN EXTRACTED VALUE:
//
//   Quoted   (green)  — grounded: Stage 3 located this text on the cited page
//   Inferred (yellow) — extracted but not grounded, or assembled/deduced
//   NA       (red)    — nothing extracted, or no field at all
//
// The pipeline's five-tier vocabulary still travels in the data (and still drives
// the plain-language reasons below), but `labelForField` / `labelForTier` are the
// ONLY things that decide what a reader sees. Every display component calls one
// of them — scattering that decision is how the confidence signal drifts apart
// between screens.
//
// A FOURTH badge exists for the statute layer:
//
//   Statute  (navy)   — supplied by legislation, not read from this contract
//
// It sits outside the green/yellow/red ramp on purpose. Those three all answer
// "how well did we read the page?", and a statutory default has no page to read:
// it is what the law provides when the contract is silent. Giving it any of the
// three would be a false claim about the document — Quoted would be a lie, and
// Inferred/NA would both imply we tried and failed to find it in the text. So it
// gets its own colour, its own glyph (§), and no confidence tier at all. The
// meaning of the other three is unchanged.
import type { ConfidenceTier, FieldDTO } from "./api";

/** The three labels that describe how well we read the contract. */
export type DisplayLabel = "quoted" | "inferred" | "na";

/** Everything the badge can render, including the non-confidence statute state. */
export type BadgeLabel = DisplayLabel | "statutory";

type LabelMeta = {
  rank: number; // lower = more confident; drives upward sorting of uncertainty
  short: string;
  label: string;
  glyph: string;
  text: string;
  bg: string;
  border: string;
  barBorder: string; // left-rule treatment (structural cue)
};

export const LABEL_META: Record<BadgeLabel, LabelMeta> = {
  quoted: {
    rank: 0,
    short: "Quoted",
    label: "Quoted from the contract — found on the cited page",
    glyph: "✓",
    text: "text-ok",
    bg: "bg-okbg",
    border: "border-ok/40",
    barBorder: "border-l-4 border-l-ok border-solid",
  },
  inferred: {
    rank: 1,
    short: "Inferred",
    label: "Inferred — not found verbatim on the cited page, so check it",
    glyph: "~",
    text: "text-warn",
    bg: "bg-warnbg",
    border: "border-warn/50",
    barBorder: "border-l-4 border-l-warn border-dashed",
  },
  na: {
    rank: 2,
    short: "NA",
    label: "Not extracted — this tool has no value for this field",
    glyph: "—",
    text: "text-alert",
    bg: "bg-alertbg",
    border: "border-alert/50",
    barBorder: "border-l-4 border-l-alert border-dotted",
  },
  statutory: {
    rank: 3, // sorts last; it is not a rung on the confidence ladder
    short: "Statute",
    label: "Supplied by statute — this is not quoted from your contract",
    glyph: "§",
    text: "text-navy",
    bg: "bg-navybg",
    border: "border-navy/40",
    barBorder: "border-l-4 border-l-navy border-double",
  },
};

/** The filter's vocabulary: the three read-quality labels only. */
export const LABEL_ORDER: DisplayLabel[] = ["quoted", "inferred", "na"];

/** For anything that always carries a value (calendar events, conflicts). */
export function labelForTier(tier: ConfidenceTier | string): DisplayLabel {
  return tier === "verbatim" || tier === "normalised" ? "quoted" : "inferred";
}

/**
 * The one mapping for a field. A field with no value is NA whatever tier the
 * pipeline attached to the absence — "we have nothing" is the honest reading,
 * and it must not borrow the confidence of a value that does not exist.
 */
export function labelForField(field: Pick<FieldDTO, "confidenceTier" | "valueVerbatim">): DisplayLabel {
  if (field.valueVerbatim == null) return "na";
  return labelForTier(field.confidenceTier);
}

/** A field key with no row at all reads the same as an empty one: NA. */
export function labelForMissingField(): DisplayLabel {
  return "na";
}

export function labelRank(label: BadgeLabel): number {
  return LABEL_META[label].rank;
}

export function ConfidenceBadge({ label, size = "md" }: { label: BadgeLabel; size?: "sm" | "md" }) {
  const m = LABEL_META[label];
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
 * Plain-language evidence for a field's confidence. A label alone is an
 * assertion; these reasons are what make the tool calibrated rather than
 * confident (§9). Scores become words, never numbers.
 *
 * This is where the five-tier detail still earns its keep: collapsing the badge
 * to three labels must not lose WHY something is uncertain.
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
