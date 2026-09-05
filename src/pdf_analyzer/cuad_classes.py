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


# What each category actually means, plus the wording contracts really use for
# it. The bare label is not enough to find the clause: scored against expert
# annotations of the Armstrong Flooring IP Agreement, the model was handed the
# string "Non-Disparagement" and had to independently deduce that "shall not
# tarnish or bring into disrepute the reputation of or goodwill associated
# with" is an instance of it. It often didn't. The same gap lost
# Covenant Not To Sue (the clause says "contest, challenge", never "sue") and
# Post-Termination Services (the clause says "cease all use", never
# "services"). In all three the text was sitting in the OCR.
#
# Where an explicit *negative* is the giveaway ("non-exclusive" proves there is
# no exclusivity; "royalty-free" proves there is no revenue share), that is
# called out too, since the absence of a clause is itself a reportable finding.
CUAD_DEFINITIONS: dict[str, str] = {
    "document_name": (
        "The title of the contract itself. "
        "Look for: the heading at the top of the first page, e.g. "
        '"MASTER SERVICES AGREEMENT", "INTELLECTUAL PROPERTY AGREEMENT".'
    ),
    "parties": (
        "The entities that entered into the contract. "
        'Look for: "by and between", "entered into by", defined roles like '
        '("Seller"), ("Buyer"), ("Licensor"), and the signature blocks.'
    ),
    "agreement_date": (
        "The date the contract was made or signed. "
        'Look for: "dated as of", "made this __ day of", "entered into on".'
    ),
    "effective_date": (
        "The date the contract becomes effective, which may differ from the date signed. "
        'Look for: "Effective Date", "shall commence on", "effective as of".'
    ),
    "expiration_date": (
        "When the initial term ends. "
        'Look for: "shall expire", "term ending", "for a period of __ months/years '
        'thereafter", defined terms like "License Term". Note a contract may have '
        "several different terms for different assets rather than one end date."
    ),
    "renewal_term": (
        "Any renewal or extension period after the initial term, automatic or optional. "
        'Look for: "automatically renew", "successive one-year periods", "renewal term", '
        '"shall be extended".'
    ),
    "notice_period_to_terminate_renewal": (
        "Advance notice required to stop a renewal from happening. "
        'Look for: "written notice at least __ days prior to the end of the term", '
        '"notice of non-renewal". Note: a cure period for breach is NOT this.'
    ),
    "governing_law": (
        "Which jurisdiction's law governs the contract. "
        'Look for: "governed by the laws of", "construed in accordance with the laws of".'
    ),
    "most_favored_nation": (
        "A promise that if the counterparty gives a third party better terms, this party "
        "gets them too. "
        'Look for: "no less favorable than", "most favored", "terms offered to any other '
        'customer".'
    ),
    "non_compete": (
        "A restriction on a party competing with the counterparty, or operating in a given "
        "geography, market, or business line. "
        'Look for: "shall not compete", "competing product", "Competitors", "shall not '
        'engage in any business that".'
    ),
    "exclusivity": (
        "An exclusive dealing commitment: a promise to buy all requirements from one party, "
        "or not to license/sell/appoint anyone else. "
        'Look for: "exclusive", "sole and exclusive", "shall not grant to any third party". '
        'The explicit word "non-exclusive" is direct evidence there is NO exclusivity.'
    ),
    "no_solicit_of_customers": (
        "A restriction on soliciting or contracting with the counterparty's customers or partners. "
        'Look for: "shall not solicit any customer", "shall not approach any client of".'
    ),
    "competitive_restriction_exception": (
        "Carve-outs and exceptions to a non-compete, exclusivity, or no-solicit restriction. "
        'Look for: "except", "provided, however", "shall not apply to", "nothing herein '
        'shall prevent" appearing near a restrictive covenant.'
    ),
    "no_solicit_of_employees": (
        "A restriction on soliciting or hiring the counterparty's employees or contractors. "
        'Look for: "shall not solicit or hire any employee", "no-poach", "shall not induce '
        'any employee to leave".'
    ),
    "non_disparagement": (
        "A requirement not to speak badly of, damage the reputation of, or harm the goodwill "
        "of the counterparty. "
        'Look for: "shall not disparage", "shall not tarnish", "bring into disrepute", '
        '"damage the reputation or goodwill of". The word "disparage" is often absent.'
    ),
    "termination_for_convenience": (
        "The right to terminate without cause, just by giving notice. "
        'Look for: "terminate for convenience", "without cause", "for any reason or no '
        'reason upon __ days notice". Termination only for material breach is NOT this.'
    ),
    "rofr_rofo_rofn": (
        "A right of first refusal, first offer, or first negotiation over equity, products, "
        "services, or distribution. "
        'Look for: "right of first refusal", "right of first offer", "first negotiation".'
    ),
    "change_of_control": (
        "A right to terminate, or a consent/notice requirement, if the counterparty undergoes "
        "a change of ownership or control. "
        'Look for: "change of control", "merger, acquisition or sale of all or substantially '
        'all assets", "change in ownership".'
    ),
    "anti_assignment": (
        "A requirement for consent or notice before the contract can be assigned to a third party. "
        'Look for: "shall not be assigned without the prior written consent", "may not assign '
        'this Agreement", "any assignment shall be void".'
    ),
    "revenue_profit_sharing": (
        "An obligation to share revenue, profit, or pay royalties to the counterparty. "
        'Look for: "royalty", "revenue share", "percentage of net sales", "profit split". '
        'The phrase "royalty-free" is direct evidence there is NO revenue sharing.'
    ),
    "price_restrictions": (
        "A restriction on raising or changing prices of goods, technology, or services. "
        'Look for: "shall not increase the price", "price shall remain fixed", "price cap", '
        '"no more than __% increase per year".'
    ),
    "minimum_commitment": (
        "A minimum quantity, order size, or spend a party must commit to. "
        'Look for: "minimum purchase", "shall purchase at least", "minimum annual volume". '
        "Careful: specifications like a minimum logo size are branding rules, NOT a "
        "commercial minimum commitment."
    ),
    "volume_restriction": (
        "A usage threshold above which fees increase or consent is required. "
        'Look for: "in excess of __ units", "exceeds the permitted volume", "additional fees '
        'shall apply above".'
    ),
    "ip_ownership_assignment": (
        "IP created or held by one party becoming the property of the counterparty. "
        'Look for: "hereby assigns", "agrees to assign", "shall be the sole and exclusive '
        'property of", "work made for hire".'
    ),
    "joint_ip_ownership": (
        "IP owned jointly or shared between the parties. "
        'Look for: "jointly own", "joint ownership", "shall be owned by the parties '
        'together". Explicit statements that each party solely owns its own IP and the other '
        '"will not acquire any ownership rights" are direct evidence there is NO joint ownership.'
    ),
    "license_grant": (
        "Any license granted by one party to the other. "
        'Look for: "hereby grants", "grants to the Company a ... license", "right to use", '
        '"licenses to".'
    ),
    "non_transferable_license": (
        "A limit on transferring, assigning, or sublicensing the license granted. "
        'Look for: "non-transferable", "non-assignable", "non-sublicensable", "personal to '
        'the licensee".'
    ),
    "affiliate_license_licensor": (
        "The licensed IP includes IP belonging to the LICENSOR's affiliates, or affiliates of "
        "the licensor are granting rights. "
        'Look for: definitions of the licensed property that read "owned by ... or their '
        'respective Affiliates", "Licensor and its Affiliates hereby grant". This is often '
        "established in the DEFINITIONS section rather than the grant clause itself."
    ),
    "affiliate_license_licensee": (
        "The license extends to, or may be sublicensed to, the LICENSEE's affiliates, "
        "subsidiaries, or parent. "
        'Look for: "may sublicense to its Affiliates", "the Company and its Subsidiaries", '
        '"controlled Affiliates, or any holding company that is a direct or indirect parent".'
    ),
    "unlimited_all_you_can_eat_license": (
        "An unlimited, enterprise-wide, or 'all you can eat' usage license. "
        'Look for: "unlimited", "enterprise-wide", "without restriction as to volume or '
        'number of users". A license described as "limited" or restricted to a named field '
        "of use is direct evidence this is NOT unlimited."
    ),
    "irrevocable_or_perpetual_license": (
        "A license that is perpetual or cannot be revoked. "
        'Look for: "perpetual", "irrevocable", "in perpetuity", "shall not expire".'
    ),
    "source_code_escrow": (
        "Source code deposited with a third-party escrow agent, releasable on defined events. "
        'Look for: "source code escrow", "escrow agent", "deposit the source code", '
        '"release conditions".'
    ),
    "post_termination_services": (
        "Obligations that continue after termination or expiry: transition help, wind-down, "
        "return or destruction of materials, ceasing use, or clauses that expressly survive. "
        'Look for: "upon termination shall", "cease all use of", "shall survive expiration or '
        'termination", "wind-down period", "transition assistance". The word "services" is '
        "usually absent."
    ),
    "audit_rights": (
        "A right to inspect the counterparty's books, records, systems, or premises to verify "
        "compliance. "
        'Look for: "right to audit", "inspect the books and records", "upon reasonable notice '
        'examine". Merely requesting a list or a report is NOT a full audit right.'
    ),
    "uncapped_liability": (
        "Liability that is not limited by any ceiling, often via a broad indemnity. "
        'Look for: indemnification covering "any and all losses, costs, liabilities, claims '
        'and expenses" with NO stated maximum; "unlimited liability"; carve-outs from a cap '
        "for IP infringement, confidentiality breach, gross negligence or willful misconduct. "
        "The absence of any cap in a broad indemnity is itself the signal."
    ),
    "cap_on_liability": (
        "A ceiling on liability, or a time limit for bringing claims. "
        'Look for: "shall not exceed", "aggregate liability limited to", "in no event shall '
        'either party be liable for more than", "must bring any claim within __ months".'
    ),
    "liquidated_damages": (
        "A pre-agreed damages amount for breach, or a fee payable on termination. "
        'Look for: "liquidated damages", "termination fee", "genuine pre-estimate of loss".'
    ),
    "warranty_duration": (
        "How long a warranty against defects or errors lasts. "
        'Look for: "warrants for a period of __", "warranty period", "for __ months following '
        'delivery". Disclaimers ("AS IS", no warranties of "merchantability or fitness for a '
        'particular purpose") are direct evidence there is NO warranty duration.'
    ),
    "insurance": (
        "A requirement to obtain or maintain insurance for the counterparty's benefit. "
        'Look for: "shall maintain insurance", "commercial general liability coverage of not '
        'less than $__", "name the other party as an additional insured".'
    ),
    "covenant_not_to_sue": (
        "A restriction on challenging the counterparty's IP ownership or validity, or on "
        "bringing claims against them. "
        'Look for: "shall not contest", "shall not challenge the validity", "covenant not to '
        'sue", "take any action adverse to ... ownership of or rights in". The word "sue" is '
        "usually absent — this is most often an IP non-challenge clause."
    ),
    "third_party_beneficiary": (
        "A non-signatory who receives rights under the contract and could enforce them. "
        'Look for: "third party beneficiary", or indemnification/benefits extending to a '
        'party\'s "Affiliates and their respective employees, directors, officers, agents and '
        'successors", often collectively defined as "Indemnified Parties".'
    ),
}

assert set(CUAD_DEFINITIONS) == set(CUAD_CLASSES), (
    "CUAD_DEFINITIONS must cover exactly the 41 CUAD classes; "
    f"missing={set(CUAD_CLASSES) - set(CUAD_DEFINITIONS)}, "
    f"extra={set(CUAD_DEFINITIONS) - set(CUAD_CLASSES)}"
)
