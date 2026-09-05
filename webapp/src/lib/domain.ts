// Domain vocabulary shared across the API, seed, and stub worker. These are the
// values the seam contract (docs/INTEGRATION.md) pins down; the frontend keeps
// its own mirror of the display-facing ones.

// Confidence tiers, ordered most→least trustworthy. Order matters: the UI sorts
// uncertain values upward and the review queue keys off this ranking.
export const CONFIDENCE_TIERS = [
  "verbatim", // quoted directly from the contract, anchored to lines
  "normalised", // a verbatim value parsed into a machine value (a date, a number)
  "assembled", // stitched together from more than one clause
  "inferred", // deduced, may have no verbatim anchor
  "unverified", // quoted text was NOT found in the cited clause — a fabrication signal
] as const;
export type ConfidenceTier = (typeof CONFIDENCE_TIERS)[number];

export const CLAIM_TYPES = ["contract_text", "computed", "benchmark"] as const;
export type ClaimType = (typeof CLAIM_TYPES)[number];

export const DOC_STATUSES = [
  "queued",
  "processing",
  "ready",
  "degraded",
  "failed",
  "unsupported",
] as const;
export type DocStatus = (typeof DOC_STATUSES)[number];

export const ABSENCE_REASONS = ["not_present", "not_found", "illegible"] as const;
export type AbsenceReason = (typeof ABSENCE_REASONS)[number];

export const JOB_STATUSES = ["queued", "running", "done", "failed"] as const;
export const CALENDAR_STATUSES = ["open", "acknowledged", "dismissed"] as const;

// The eight required extractions, grouped exactly as the document-detail screen
// renders them (§9). Every group is always shown, even when empty.
export const FIELD_GROUPS: { key: string; title: string; fields: string[] }[] = [
  { key: "parties", title: "Parties", fields: ["party_a", "party_b", "signatories"] },
  { key: "term", title: "Term", fields: ["effective_date", "initial_term", "term_end"] },
  {
    key: "renewal",
    title: "Renewal",
    fields: ["auto_renews", "renewal_term", "notice_period", "notice_deadline"],
  },
  {
    key: "termination",
    title: "Termination",
    fields: ["termination_for_convenience", "termination_for_cause", "cure_period"],
  },
  {
    key: "payments",
    title: "Payments",
    fields: ["payment_amount", "payment_schedule", "escalation"],
  },
  {
    key: "liability",
    title: "Liability",
    fields: ["liability_cap", "cap_carve_outs", "indemnities"],
  },
  {
    key: "restrictions",
    title: "Restrictions",
    fields: ["exclusivity", "non_compete", "non_solicit"],
  },
];

export const ALL_FIELD_KEYS: string[] = FIELD_GROUPS.flatMap((g) => g.fields);
