"""The 41 CUAD (Contract Understanding Atticus Dataset) clause/entity categories.

Reference: Hendrycks et al., "CUAD: An Expert-Annotated NLP Dataset for Legal
Contract Review" (2021). Keys are snake_case identifiers used throughout the
pipeline and as keys in the `cuad_extractions` output object; values are the
human-readable category names used in VLM prompts and UI labels.
"""

CUAD_CLASSES: dict[str, str] = {
    "document_name": "Document Name",
    "parties": "Parties",
    "agreement_date": "Agreement Date",
    "effective_date": "Effective Date",
    "expiration_date": "Expiration Date",
    "renewal_term": "Renewal Term",
    "notice_period_to_terminate_renewal": "Notice Period To Terminate Renewal",
    "governing_law": "Governing Law",
    "most_favored_nation": "Most Favored Nation",
    "non_compete": "Non-Compete",
    "exclusivity": "Exclusivity",
    "no_solicit_of_customers": "No-Solicit Of Customers",
    "competitive_restriction_exception": "Competitive Restriction Exception",
    "no_solicit_of_employees": "No-Solicit Of Employees",
    "non_disparagement": "Non-Disparagement",
    "termination_for_convenience": "Termination For Convenience",
    "rofr_rofo_rofn": "Rofr/Rofo/Rofn",
    "change_of_control": "Change Of Control",
    "anti_assignment": "Anti-Assignment",
    "revenue_profit_sharing": "Revenue/Profit Sharing",
    "price_restrictions": "Price Restrictions",
    "minimum_commitment": "Minimum Commitment",
    "volume_restriction": "Volume Restriction",
    "ip_ownership_assignment": "IP Ownership Assignment",
    "joint_ip_ownership": "Joint IP Ownership",
    "license_grant": "License Grant",
    "non_transferable_license": "Non-Transferable License",
    "affiliate_license_licensor": "Affiliate License-Licensor",
    "affiliate_license_licensee": "Affiliate License-Licensee",
    "unlimited_all_you_can_eat_license": "Unlimited/All-You-Can-Eat License",
    "irrevocable_or_perpetual_license": "Irrevocable Or Perpetual License",
    "source_code_escrow": "Source Code Escrow",
    "post_termination_services": "Post-Termination Services",
    "audit_rights": "Audit Rights",
    "uncapped_liability": "Uncapped Liability",
    "cap_on_liability": "Cap On Liability",
    "liquidated_damages": "Liquidated Damages",
    "warranty_duration": "Warranty Duration",
    "insurance": "Insurance",
    "covenant_not_to_sue": "Covenant Not To Sue",
    "third_party_beneficiary": "Third Party Beneficiary",
}

assert len(CUAD_CLASSES) == 41, f"expected 41 CUAD classes, got {len(CUAD_CLASSES)}"
