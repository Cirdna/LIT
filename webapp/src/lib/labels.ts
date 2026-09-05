// Server-side mirror of the UI's three display labels.
//
// KNOWN DUPLICATION — tracked in STATUS_UPDATE.md. The authoritative mapping is
// `labelForField` in frontend/src/lib/confidence.tsx. It lives in the frontend
// because that is where the rule belongs, but the chatbot has to FILTER by label
// server-side (you cannot page through a portfolio in the browser to find the
// unquoted values), so the same two-line rule now exists twice.
//
// It is duplicated rather than moved because moving it means either the frontend
// importing from src/ (it does not today) or a shared package (a bigger change
// than this pass should make while a merge decision is pending). If these two
// ever disagree, confidence.tsx wins.
import type { ExtractedField } from "@prisma/client";

export const DISPLAY_LABELS = ["quoted", "inferred", "na"] as const;
export type DisplayLabel = (typeof DISPLAY_LABELS)[number];

/** Mirrors confidence.tsx:labelForTier. */
export function labelForTier(tier: string): DisplayLabel {
  return tier === "verbatim" || tier === "normalised" ? "quoted" : "inferred";
}

/** Mirrors confidence.tsx:labelForField — no value means NA, whatever the tier. */
export function labelForField(f: Pick<ExtractedField, "confidenceTier" | "valueVerbatim">): DisplayLabel {
  if (f.valueVerbatim == null) return "na";
  return labelForTier(f.confidenceTier);
}

/** The tiers that produce a given label, for translating a filter into a query. */
export function tiersForLabel(label: DisplayLabel): string[] {
  switch (label) {
    case "quoted":
      return ["verbatim", "normalised"];
    case "inferred":
      return ["assembled", "inferred", "unverified"];
    case "na":
      return []; // NA is decided by a null value, not by a tier
  }
}
