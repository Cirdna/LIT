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


# CUAD's own category descriptions, verbatim from the Atticus Project's
# category_descriptions.csv (github.com/TheAtticusProject/cuad). These are the
# questions the dataset's expert annotators actually answered, so they define
# each category's real scope -- not a paraphrase of it.
#
# An earlier version of this file was written from memory instead, and the
# difference was not academic: the hand-written Covenant Not to Sue read "or on
# bringing claims against them", dropping the official qualifier "for matters
# unrelated to the contract". On the Chase affiliate agreement that omission
# matched a routine service-interruption liability waiver -- a clause arising
# squarely under the contract, which the real scope excludes.
#
# Only whitespace was normalized and smart quotes flattened. Do not reword:
# if a category's scope seems wrong, the fix belongs in CUAD_TRIGGER_PHRASES
# below, or upstream with Atticus.
CUAD_DESCRIPTIONS: dict[str, str] = {
    "document_name": 'The name of the contract',
    "parties": 'The two or more parties who signed the contract',
    "agreement_date": 'The date of the contract',
    "effective_date": 'The date when the contract is effective',
    "expiration_date": "On what date will the contract's initial term expire?",
    "renewal_term": (
        'What is the renewal term after the initial term expires? This includes '
        'automatic extensions and unilateral extensions with prior notice.'
    ),
    "notice_period_to_terminate_renewal": 'What is the notice period required to terminate renewal?',
    "governing_law": "Which state/country's law governs the interpretation of the contract?",
    "most_favored_nation": (
        'Is there a clause that if a third party gets better terms on the licensing '
        'or sale of technology/goods/services described in the contract, the buyer '
        'of such technology/goods/services under the contract shall be entitled to '
        'those better terms?'
    ),
    "non_compete": (
        'Is there a restriction on the ability of a party to compete with the '
        'counterparty or operate in a certain geography or business or technology '
        'sector?'
    ),
    "exclusivity": (
        'Is there an exclusive dealing commitment with the counterparty? This '
        'includes a commitment to procure all "requirements" from one party of '
        'certain technology, goods, or services or a prohibition on licensing or '
        'selling technology, goods or services to third parties, or a prohibition '
        'on collaborating or working with other parties), whether during the '
        'contract or after the contract ends (or both).'
    ),
    "no_solicit_of_customers": (
        'Is a party restricted from contracting or soliciting customers or partners '
        'of the counterparty, whether during the contract or after the contract '
        'ends (or both)?'
    ),
    "competitive_restriction_exception": (
        'This category includes the exceptions or carveouts to Non-Compete, '
        'Exclusivity and No-Solicit of Customers above.'
    ),
    "no_solicit_of_employees": (
        "Is there a restriction on a party's soliciting or hiring employees and/or "
        'contractors from the counterparty, whether during the contract or after '
        'the contract ends (or both)?'
    ),
    "non_disparagement": 'Is there a requirement on a party not to disparage the counterparty?',
    "termination_for_convenience": (
        'Can a party terminate this contract without cause (solely by giving a '
        'notice and allowing a waiting period to expire)?'
    ),
    "rofr_rofo_rofn": (
        'Is there a clause granting one party a right of first refusal, right of '
        'first offer or right of first negotiation to purchase, license, market, or '
        'distribute equity interest, technology, assets, products or services?'
    ),
    "change_of_control": (
        'Does one party have the right to terminate or is consent or notice '
        'required of the counterparty if such party undergoes a change of control, '
        'such as a merger, stock sale, transfer of all or substantially all of its '
        'assets or business, or assignment by operation of law?'
    ),
    "anti_assignment": (
        'Is consent or notice required of a party if the contract is assigned to a '
        'third party?'
    ),
    "revenue_profit_sharing": (
        'Is one party required to share revenue or profit with the counterparty for '
        'any technology, goods, or services?'
    ),
    "price_restrictions": (
        'Is there a restriction on the ability of a party to raise or reduce prices '
        'of technology, goods, or services provided?'
    ),
    "minimum_commitment": (
        'Is there a minimum order size or minimum amount or units per-time period '
        'that one party must buy from the counterparty under the contract?'
    ),
    "volume_restriction": (
        "Is there a fee increase or consent requirement, etc. if one party's use of "
        'the product/services exceeds certain threshold?'
    ),
    "ip_ownership_assignment": (
        'Does intellectual property created by one party become the property of the '
        'counterparty, either per the terms of the contract or upon the occurrence '
        'of certain events?'
    ),
    "joint_ip_ownership": (
        'Is there any clause providing for joint or shared ownership of '
        'intellectual property between the parties to the contract?'
    ),
    "license_grant": (
        'Does the contract contain a license granted by one party to its '
        'counterparty?'
    ),
    "non_transferable_license": (
        'Does the contract limit the ability of a party to transfer the license '
        'being granted to a third party?'
    ),
    "affiliate_license_licensor": (
        'Does the contract contain a license grant by affiliates of the licensor or '
        'that includes intellectual property of affiliates of the licensor?'
    ),
    "affiliate_license_licensee": (
        'Does the contract contain a license grant to a licensee (incl. '
        'sublicensor) and the affiliates of such licensee/sublicensor?'
    ),
    "unlimited_all_you_can_eat_license": (
        'Is there a clause granting one party an "enterprise," "all you can eat" or '
        'unlimited usage license?'
    ),
    "irrevocable_or_perpetual_license": (
        'Does the contract contain a license grant that is irrevocable or '
        'perpetual?'
    ),
    "source_code_escrow": (
        'Is one party required to deposit its source code into escrow with a third '
        'party, which can be released to the counterparty upon the occurrence of '
        'certain events (bankruptcy, insolvency, etc.)?'
    ),
    "post_termination_services": (
        'Is a party subject to obligations after the termination or expiration of a '
        'contract, including any post-termination transition, payment, transfer of '
        'IP, wind-down, last-buy, or similar commitments?'
    ),
    "audit_rights": (
        'Does a party have the right to audit the books, records, or physical '
        'locations of the counterparty to ensure compliance with the contract?'
    ),
    "uncapped_liability": (
        "Is a party's liability uncapped upon the breach of its obligation in the "
        'contract? This also includes uncap liability for a particular type of '
        'breach such as IP infringement or breach of confidentiality obligation.'
    ),
    "cap_on_liability": (
        "Does the contract include a cap on liability upon the breach of a party's "
        'obligation? This includes time limitation for the counterparty to bring '
        'claims or maximum amount for recovery.'
    ),
    "liquidated_damages": (
        'Does the contract contain a clause that would award either party '
        'liquidated damages for breach or a fee upon the termination of a contract '
        '(termination fee)?'
    ),
    "warranty_duration": (
        'What is the duration of any warranty against defects or errors in '
        'technology, products, or services provided under the contract?'
    ),
    "insurance": (
        'Is there a requirement for insurance that must be maintained by one party '
        'for the benefit of the counterparty?'
    ),
    "covenant_not_to_sue": (
        "Is a party restricted from contesting the validity of the counterparty's "
        'ownership of intellectual property or otherwise bringing a claim against '
        'the counterparty for matters unrelated to the contract?'
    ),
    "third_party_beneficiary": (
        'Is there a non-contracting party who is a beneficiary to some or all of '
        'the clauses in the contract and therefore can enforce its rights against a '
        'contracting party?'
    ),
}

assert set(CUAD_DESCRIPTIONS) == set(CUAD_CLASSES), (
    "CUAD_DESCRIPTIONS must cover exactly the 41 CUAD classes; "
    f"missing={set(CUAD_CLASSES) - set(CUAD_DESCRIPTIONS)}, "
    f"extra={set(CUAD_DESCRIPTIONS) - set(CUAD_CLASSES)}"
)


# The wording contracts actually use, which is frequently nothing like the
# category name. This half is ours, earned empirically: each phrase here was
# observed in a real contract during failure analysis (the Armstrong Flooring
# IP Agreement and the Chase affiliate agreement), usually because its absence
# had just caused a miss. A non-disparagement clause said "tarnish" and
# "bring into disrepute" and never "disparage"; post-termination obligations
# said "cease all use" and never "services".
#
# Where an explicit negative is the giveaway ("non-exclusive" proves there is
# no exclusivity, "royalty-free" proves there is no revenue share), that is
# called out too, since a well-supported "no" is a reportable finding.
CUAD_TRIGGER_PHRASES: dict[str, str] = {
    "document_name": (
        'The heading at the top of the first page, e.g. "MASTER SERVICES '
        'AGREEMENT".'
    ),
    "parties": (
        '"by and between", "entered into by", defined roles like ("Seller"), '
        '("Buyer"), ("Licensor"), and the signature blocks.'
    ),
    "agreement_date": '"dated as of", "made this __ day of", "entered into on", "Last Updated:".',
    "effective_date": (
        '"Effective Date", "shall commence on", "effective as of", "will take '
        'effect if and when".'
    ),
    "expiration_date": (
        '"shall expire", "term ending", "for a period of __ months/years '
        'thereafter", defined terms like "License Term". A contract may set several '
        'different terms for different assets rather than one end date.'
    ),
    "renewal_term": (
        '"automatically renew", "successive one-year periods", "renewal term", '
        '"shall be extended".'
    ),
    "notice_period_to_terminate_renewal": (
        '"written notice at least __ days prior to the end of the term", "notice of '
        'non-renewal". A cure period for breach is NOT this.'
    ),
    "governing_law": '"governed by the laws of", "construed in accordance with the laws of".',
    "most_favored_nation": (
        '"no less favorable than", "most favored", "terms offered to any other '
        'customer".'
    ),
    "non_compete": (
        '"shall not compete", "competing product", "Competitors", "shall not engage '
        'in any business that".'
    ),
    "exclusivity": (
        '"exclusive", "sole and exclusive", "shall not grant to any third party". '
        'The explicit word "non-exclusive" is direct evidence there is NO '
        'exclusivity.'
    ),
    "no_solicit_of_customers": (
        '"shall not solicit any customer", "shall not approach any client of", '
        '"will not poach or contact ... directly".'
    ),
    "competitive_restriction_exception": (
        '"except", "provided, however", "shall not apply to", "nothing herein shall '
        'prevent" appearing near a restrictive covenant.'
    ),
    "no_solicit_of_employees": (
        '"shall not solicit or hire any employee", "no-poach", "shall not induce '
        'any employee to leave". Must concern employees or contractors specifically '
        '-- a restriction on poaching business partners or affiliates is No-Solicit '
        'of Customers, not this.'
    ),
    "non_disparagement": (
        '"shall not disparage", "shall not tarnish", "bring into disrepute", '
        '"damage the reputation or goodwill of". The word "disparage" is often '
        'absent.'
    ),
    "termination_for_convenience": (
        '"terminate for convenience", "without cause", "at any time, with or '
        'without cause", "for any reason or no reason upon __ days notice". '
        'Termination only for material breach is NOT this.'
    ),
    "rofr_rofo_rofn": '"right of first refusal", "right of first offer", "first negotiation".',
    "change_of_control": (
        '"change of control", "merger, acquisition or sale of all or substantially '
        'all assets", "change in ownership", "by operation of law".'
    ),
    "anti_assignment": (
        '"shall not be assigned without the prior written consent", "may not assign '
        'this Agreement", "any assignment shall be void".'
    ),
    "revenue_profit_sharing": (
        '"royalty", "revenue share", "percentage of net sales", "commission", "will '
        'pay ... a fee for each". The phrase "royalty-free" is direct evidence '
        'there is NO revenue sharing.'
    ),
    "price_restrictions": (
        '"shall not increase the price", "price shall remain fixed", "price cap", '
        '"may not pay ... higher than".'
    ),
    "minimum_commitment": (
        '"minimum purchase", "shall purchase at least", "minimum annual volume". '
        'Careful: a specification like a minimum logo size is a branding rule, NOT '
        'a commercial minimum commitment.'
    ),
    "volume_restriction": (
        '"in excess of __ units", "exceeds the permitted volume", "additional fees '
        'shall apply above".'
    ),
    "ip_ownership_assignment": (
        '"hereby assigns", "agrees to assign", "shall be the sole and exclusive '
        'property of", "work made for hire".'
    ),
    "joint_ip_ownership": (
        '"jointly own", "joint ownership", "shall be owned by the parties '
        'together". Explicit statements that each party solely owns its own IP and '
        'the other "will not acquire any ownership rights" are direct evidence '
        'there is NO joint ownership.'
    ),
    "license_grant": (
        '"hereby grants", "grants to the Company a ... license", "right to use", '
        '"licenses to".'
    ),
    "non_transferable_license": (
        '"non-transferable", "nontransferable", "non-assignable", "non- '
        'sublicensable", "personal to the licensee".'
    ),
    "affiliate_license_licensor": (
        'Definitions of the licensed property reading "owned by ... or their '
        'respective Affiliates", or "Licensor and its Affiliates hereby grant". '
        'Often established in the DEFINITIONS section rather than the grant clause '
        'itself.'
    ),
    "affiliate_license_licensee": (
        '"may sublicense to its Affiliates", "the Company and its Subsidiaries", '
        '"controlled Affiliates, or any holding company that is a direct or '
        'indirect parent".'
    ),
    "unlimited_all_you_can_eat_license": (
        '"unlimited", "enterprise-wide", "without restriction as to volume or '
        'number of users". A license described as "limited" or restricted to a '
        'named field of use is direct evidence this is NOT unlimited.'
    ),
    "irrevocable_or_perpetual_license": '"perpetual", "irrevocable", "in perpetuity", "shall not expire".',
    "source_code_escrow": (
        '"source code escrow", "escrow agent", "deposit the source code", "release '
        'conditions", "upon bankruptcy or insolvency".'
    ),
    "post_termination_services": (
        '"upon termination shall", "cease all use of", "shall survive expiration or '
        'termination", "wind-down period", "transition assistance", "must be '
        'removed immediately". The word "services" is usually absent.'
    ),
    "audit_rights": (
        '"right to audit", "inspect the books and records", "upon reasonable notice '
        'examine". Merely requesting a list or a report is NOT a full audit right.'
    ),
    "uncapped_liability": (
        'Indemnification covering "any and all losses, costs, liabilities, claims '
        'and expenses" with NO stated maximum; "unlimited liability"; carve-outs '
        'from a cap for IP infringement, confidentiality breach, gross negligence '
        'or willful misconduct. The absence of any cap in a broad indemnity is '
        'itself the signal.'
    ),
    "cap_on_liability": (
        '"shall not exceed", "aggregate liability arising under ... shall not '
        'exceed", "in no event shall either party be liable for more than", "must '
        'bring any claim within __ months".'
    ),
    "liquidated_damages": '"liquidated damages", "termination fee", "genuine pre-estimate of loss".',
    "warranty_duration": (
        '"warrants for a period of __", "warranty period", "for __ months following '
        'delivery". Disclaimers ("AS IS", no warranties of "merchantability or '
        'fitness for a particular purpose") are direct evidence there is NO '
        'warranty duration.'
    ),
    "insurance": (
        '"shall maintain insurance", "commercial general liability coverage of not '
        'less than $__", "name the other party as an additional insured".'
    ),
    "covenant_not_to_sue": (
        '"shall not contest", "shall not challenge the validity", "covenant not to '
        'sue", "take any action adverse to ... ownership of or rights in". The word '
        '"sue" is usually absent -- this is most often an IP non-challenge clause. '
        "Note the official scope: an ordinary liability waiver about the contract's "
        'own performance (e.g. not holding a party responsible for service '
        'interruptions) is NOT this, because it concerns matters arising under the '
        'contract rather than unrelated claims.'
    ),
    "third_party_beneficiary": (
        '"third party beneficiary", or indemnification/benefits extending to a '
        'party\'s "Affiliates and their respective employees, directors, officers, '
        'agents and successors", often collectively defined as "Indemnified '
        'Parties".'
    ),
}

assert set(CUAD_TRIGGER_PHRASES) == set(CUAD_CLASSES), (
    "CUAD_TRIGGER_PHRASES must cover exactly the 41 CUAD classes; "
    f"missing={set(CUAD_CLASSES) - set(CUAD_TRIGGER_PHRASES)}, "
    f"extra={set(CUAD_TRIGGER_PHRASES) - set(CUAD_CLASSES)}"
)


def category_definition(key: str) -> str:
    """The full prompt-ready definition: CUAD's authoritative scope, then the
    contract wording to look for."""
    return f"{CUAD_DESCRIPTIONS[key]}\n\nWording to look for: {CUAD_TRIGGER_PHRASES[key]}"


# Kept for callers that just want the composed text per category.
CUAD_DEFINITIONS: dict[str, str] = {key: category_definition(key) for key in CUAD_CLASSES}
