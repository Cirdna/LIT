// Frontend mirror of the field grouping. The document-detail screen renders the
// 41 CUAD categories the pipeline extracts, organised into eight groups (the
// original seven lifecycle groups + IP & Licensing). Field keys match the CUAD
// category keys 1:1. Every group renders even when empty.
export const FIELD_GROUPS: { key: string; title: string; fields: { key: string; label: string }[] }[] = [
  {
    key: "parties",
    title: "Parties",
    fields: [
      { key: "document_name", label: "Document name" },
      { key: "parties", label: "Parties" },
      { key: "governing_law", label: "Governing law" },
      { key: "third_party_beneficiary", label: "Third-party beneficiary" },
    ],
  },
  {
    key: "term",
    title: "Term",
    fields: [
      { key: "agreement_date", label: "Agreement date" },
      { key: "effective_date", label: "Effective date" },
      { key: "expiration_date", label: "Expiration date" },
      { key: "warranty_duration", label: "Warranty duration" },
    ],
  },
  {
    key: "renewal",
    title: "Renewal",
    fields: [
      { key: "renewal_term", label: "Renewal term" },
      { key: "notice_period_to_terminate_renewal", label: "Notice to terminate renewal" },
      { key: "post_termination_services", label: "Post-termination services" },
    ],
  },
  {
    key: "termination",
    title: "Termination",
    fields: [
      { key: "termination_for_convenience", label: "Termination for convenience" },
      { key: "change_of_control", label: "Change of control" },
      { key: "anti_assignment", label: "Anti-assignment" },
      { key: "rofr_rofo_rofn", label: "ROFR / ROFO / ROFN" },
    ],
  },
  {
    key: "payments",
    title: "Payments",
    fields: [
      { key: "revenue_profit_sharing", label: "Revenue / profit sharing" },
      { key: "price_restrictions", label: "Price restrictions" },
      { key: "minimum_commitment", label: "Minimum commitment" },
      { key: "volume_restriction", label: "Volume restriction" },
      { key: "most_favored_nation", label: "Most-favored nation" },
    ],
  },
  {
    key: "liability",
    title: "Liability",
    fields: [
      { key: "cap_on_liability", label: "Cap on liability" },
      { key: "uncapped_liability", label: "Uncapped liability" },
      { key: "liquidated_damages", label: "Liquidated damages" },
      { key: "insurance", label: "Insurance" },
      { key: "audit_rights", label: "Audit rights" },
      { key: "covenant_not_to_sue", label: "Covenant not to sue" },
    ],
  },
  {
    key: "restrictions",
    title: "Restrictions",
    fields: [
      { key: "non_compete", label: "Non-compete" },
      { key: "exclusivity", label: "Exclusivity" },
      { key: "no_solicit_of_customers", label: "No-solicit of customers" },
      { key: "no_solicit_of_employees", label: "No-solicit of employees" },
      { key: "non_disparagement", label: "Non-disparagement" },
      { key: "competitive_restriction_exception", label: "Competitive restriction exception" },
    ],
  },
  {
    key: "ip_licensing",
    title: "IP & Licensing",
    fields: [
      { key: "ip_ownership_assignment", label: "IP ownership assignment" },
      { key: "joint_ip_ownership", label: "Joint IP ownership" },
      { key: "license_grant", label: "License grant" },
      { key: "non_transferable_license", label: "Non-transferable license" },
      { key: "affiliate_license_licensor", label: "Affiliate license (licensor)" },
      { key: "affiliate_license_licensee", label: "Affiliate license (licensee)" },
      { key: "unlimited_all_you_can_eat_license", label: "Unlimited license" },
      { key: "irrevocable_or_perpetual_license", label: "Irrevocable / perpetual license" },
      { key: "source_code_escrow", label: "Source-code escrow" },
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
