// Frontend mirror of the field grouping. The document-detail screen renders
// these seven groups one-to-one onto the eight required extractions so a judge
// can tick them off (§9). Every group renders even when empty.
export const FIELD_GROUPS: { key: string; title: string; fields: { key: string; label: string }[] }[] = [
  {
    key: "parties",
    title: "Parties",
    fields: [
      { key: "party_a", label: "Party A" },
      { key: "party_b", label: "Party B" },
      { key: "signatories", label: "Signatories" },
    ],
  },
  {
    key: "term",
    title: "Term",
    fields: [
      { key: "effective_date", label: "Effective date" },
      { key: "initial_term", label: "Initial term" },
      { key: "term_end", label: "Term end" },
    ],
  },
  {
    key: "renewal",
    title: "Renewal",
    fields: [
      { key: "auto_renews", label: "Auto-renews" },
      { key: "renewal_term", label: "Renewal term" },
      { key: "notice_period", label: "Notice period" },
      { key: "notice_deadline", label: "Notice deadline" },
    ],
  },
  {
    key: "termination",
    title: "Termination",
    fields: [
      { key: "termination_for_convenience", label: "For convenience" },
      { key: "termination_for_cause", label: "For cause" },
      { key: "cure_period", label: "Cure period" },
    ],
  },
  {
    key: "payments",
    title: "Payments",
    fields: [
      { key: "payment_amount", label: "Amount" },
      { key: "payment_schedule", label: "Schedule" },
      { key: "escalation", label: "Escalation" },
    ],
  },
  {
    key: "liability",
    title: "Liability",
    fields: [
      { key: "liability_cap", label: "Liability cap" },
      { key: "cap_carve_outs", label: "Cap carve-outs" },
      { key: "indemnities", label: "Indemnities" },
    ],
  },
  {
    key: "restrictions",
    title: "Restrictions",
    fields: [
      { key: "exclusivity", label: "Exclusivity" },
      { key: "non_compete", label: "Non-compete" },
      { key: "non_solicit", label: "Non-solicit" },
    ],
  },
];

export const DOC_TYPE_LABELS: Record<string, string> = {
  nda: "NDA",
  lease: "Lease",
  msa: "Master services",
  distribution: "Distribution",
  employment: "Employment",
  other: "Other",
  not_a_contract: "Not a contract",
};
