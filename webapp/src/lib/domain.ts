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

// The 41 CUAD categories, organised into the document-detail screen's eight
// groups (the original seven lifecycle groups + IP & Licensing). Every group is
// always shown, even when empty. Field keys are the exact CUAD category keys the
// pipeline emits (see src/pdf_analyzer/cuad_classes.py) so the worker writes
// them 1:1 with no crosswalk.
export const FIELD_GROUPS: { key: string; title: string; fields: string[] }[] = [
  {
    key: "parties",
    title: "Parties",
    fields: ["document_name", "parties", "governing_law", "third_party_beneficiary"],
  },
  {
    key: "term",
    title: "Term",
    fields: ["agreement_date", "effective_date", "expiration_date", "warranty_duration"],
  },
  {
    key: "renewal",
    title: "Renewal",
    fields: ["renewal_term", "notice_period_to_terminate_renewal", "post_termination_services"],
  },
  {
    key: "termination",
    title: "Termination",
    fields: ["termination_for_convenience", "change_of_control", "anti_assignment", "rofr_rofo_rofn"],
  },
  {
    key: "payments",
    title: "Payments",
    fields: [
      "revenue_profit_sharing",
      "price_restrictions",
      "minimum_commitment",
      "volume_restriction",
      "most_favored_nation",
    ],
  },
  {
    key: "liability",
    title: "Liability",
    fields: [
      "cap_on_liability",
      "uncapped_liability",
      "liquidated_damages",
      "insurance",
      "audit_rights",
      "covenant_not_to_sue",
    ],
  },
  {
    key: "restrictions",
    title: "Restrictions",
    fields: [
      "non_compete",
      "exclusivity",
      "no_solicit_of_customers",
      "no_solicit_of_employees",
      "non_disparagement",
      "competitive_restriction_exception",
    ],
  },
  {
    key: "ip_licensing",
    title: "IP & Licensing",
    fields: [
      "ip_ownership_assignment",
      "joint_ip_ownership",
      "license_grant",
      "non_transferable_license",
      "affiliate_license_licensor",
      "affiliate_license_licensee",
      "unlimited_all_you_can_eat_license",
      "irrevocable_or_perpetual_license",
      "source_code_escrow",
    ],
  },
];

export const ALL_FIELD_KEYS: string[] = FIELD_GROUPS.flatMap((g) => g.fields);
