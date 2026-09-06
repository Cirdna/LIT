"""The 41 CUAD categories and their STRICT, element-based classifier rules.

Provenance note: the definitions here are the "Revised Generalized Version"
from `CUAD_41_Strict_Classifier_Definitions_Revised.md`, archived in
`reference/`. They supersede the earlier strict-classifier rules that were
generated from the Atticus Project's `category_descriptions.csv`.

The governing design principle is unchanged and load-bearing:

  Retrieval finds potentially relevant language. Validation decides whether
  the language legally satisfies the CUAD category.

A category is YES only when the contractual text establishes the *operative
legal effect* the category requires — never on the strength of a keyword,
a section heading, a defined term, a recital, or a reference to a related
concept. This directly targets the failure mode named in HANDOFF.md §6.8:
a quote can be perfectly grounded yet filed under the wrong category.
Grounding proves the text exists; these classifiers decide whether it
legally satisfies the category.

The output-schema/architecture recommendations in the source document
(element-level YES/NO/UNRESOLVED with evidence_status + review_flag)
are a larger, separate change to the extraction contract and are NOT
applied here — only the definitions/rules are.
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


# Universal rules applied to EVERY category. Injected once per extraction prompt.
STRICT_CLASSIFICATION_RULES = """Apply the following rules strictly to every category.

1. NO FORCED POSITIVES. A contract is not required to contain every CUAD
   category. If the required legal elements are absent, return NO. If
   necessary text is redacted, missing, or incorporated from an unavailable
   document, return UNRESOLVED.

2. OPERATIVE LEGAL EFFECT CONTROLS. A YES classification requires operative legal effect —
   contractual language that actually creates the required right, obligation,
   prohibition, restriction, trigger, exception, ownership rule, payment
   rule, or duration.

3. KEYWORDS ARE ONLY RETRIEVAL SIGNALS. Do NOT classify based merely on
   keywords or vocabulary. Do not classify solely because a clause contains
   words such as "competitor", "exclusive", "assignment", "affiliate",
   "perpetual", "audit", "warranty", "insurance", "beneficiary", or similar
   category vocabulary.

4. DEFINITIONS ARE SUPPORTING CONTEXT, NOT OPERATIVE CLAUSES. A defined term
   may explain the scope of an operative clause, but a definition by itself
   does not create a restriction/right/obligation. For example, a definition
   of "Competitor" does not by itself establish a non-compete restriction.

5. HEADINGS ARE NON-DISPOSITIVE. A section heading can help retrieve context
   but cannot establish the category without qualifying operative text.

6. RECITALS/BACKGROUND ARE GENERALLY NON-OPERATIVE. Do not rely on a recital
   or statement of commercial intent if the operative provisions do not
   implement it.

7. IDENTIFY LEGAL ELEMENTS BEFORE RETURNING YES. For restrictions, identify
   the restricted actor + restricted conduct + protected object/scope. For
   rights, identify the right-holder + right + trigger/scope. For obligations,
   identify obligated party + required conduct + trigger/scope.

8. USE CROSS-REFERENCES ONLY WHEN LEGALLY CONNECTED. Retrieve definitions and
   directly referenced provisions necessary to interpret the candidate. Do not
   combine unrelated provisions merely because they are semantically similar.

9. REDACTIONS STAY UNRESOLVED. If a material element is [***], blacked out,
   omitted, or only found in an unavailable incorporated agreement, do not
   guess what it says.

10. ALLOW LEGITIMATE MULTI-LABELING. A clause may satisfy more than one
    category only where it independently satisfies the legal elements of each.
    Do not duplicate categories merely because they are commercially related.

11. DISTINGUISH PERMISSION FROM RESTRICTION. Language such as "nothing shall
    preclude", "may", "is free to", or "whether or not competitive" may negate
    a restriction or constitute an exception rather than establish the
    underlying restriction.

12. DISTINGUISH THE AGREEMENT FROM SUB-COMPONENTS. A right to terminate a
    single order, office-space license, statement of work, or product license
    does not automatically equal a right to terminate the whole contract.

13. PREFER THE SMALLEST SUFFICIENT EVIDENCE. Quote the smallest operative
    passage that proves the category, but include a definition/cross-reference
    where it is necessary to understand the operative text.

14. DO NOT INFER LEGAL RELATIONSHIPS THAT ARE NOT ESTABLISHED. For example,
    do not assume "users" are the counterparty's "customers", or that every
    affiliate has license rights merely because "Affiliate" is defined.

15. NEGATIVE EVIDENCE DOES NOT BECOME A POSITIVE. A clause saying there are
    "no third-party beneficiaries", no insurance requirement, or that
    competition is permitted should result in NO for the corresponding
    positive category."""


# Clause-role taxonomy. Before the final category decision, classify the
# candidate's role. A category-specific YES should normally require the
# appropriate operative role.
CLAUSE_ROLE_GATE = """Before making the final category decision, classify the
candidate clause's role as one of:

  OPERATIVE_RIGHT            — grants a party a legally enforceable entitlement
  OPERATIVE_OBLIGATION       — imposes a duty on a party
  OPERATIVE_RESTRICTION      — prohibits or limits a party's conduct
  OPERATIVE_OWNERSHIP_RULE   — establishes who owns specified IP/assets
  OPERATIVE_PAYMENT_RULE     — determines what payment is owed and how
  OPERATIVE_DURATION_RULE    — governs when rights/obligations begin or end
  EXCEPTION_OR_CARVEOUT      — removes conduct from an operative clause
  SUPPORTING_DEFINITION      — defines a term used in operative provisions
  PERMISSION                 — expressly allows conduct that might otherwise be restricted
  RELATED_BUT_DIFFERENT_CATEGORY — operative, but belongs under a different CUAD category
  BACKGROUND_OR_RECITAL      — states intent or context without operative effect
  IRRELEVANT                 — no legal relationship to the category
  UNRESOLVED                 — necessary text is missing, redacted, or contradictory

A category-specific YES should normally require the appropriate OPERATIVE_*
role. For example, Non-Compete = YES requires OPERATIVE_RESTRICTION, not
SUPPORTING_DEFINITION."""


# Per-category, element-based classifiers. Each states TASK, what QUALIFIES,
# what DOES NOT QUALIFY, required elements, and context rules.
CUAD_CLASSIFIERS: dict[str, str] = {
    "document_name": """TASK: Extract the formal name/title of the document being reviewed.

RETURN A VALUE only when the document itself identifies its title.

QUALIFIES:
- The heading/title on the agreement itself, e.g. "Supply Agreement",
  "Trademark License Agreement", "Distribution and Services Agreement".
- A formal title stated in the opening sentence if no separate heading exists.
- If the document being reviewed is an amendment, addendum, side letter, or
  schedule that is itself the operative document, return that document's own
  formal title.

DOES NOT QUALIFY:
- SEC exhibit labels such as "Exhibit 10.5" standing alone.
- A filename created by a filing system.
- The title of a different agreement merely referenced or incorporated.
- A section heading such as "Term and Termination".
- A descriptive phrase that is not used as the document's title.

CONTEXT RULE:
Use the cover/title page and opening paragraph together when necessary. If
multiple titles appear, prefer the title that identifies the actual document
being executed rather than an incorporated or historical agreement.

OUTPUT: Return the exact or minimally normalized contract title. If no title
is stated, return UNRESOLVED rather than inventing one.""",

    "parties": """TASK: Identify the legal entities or individuals that are actual
contracting parties to the document.

REQUIRED: The person/entity must be legally bound as a party to the
agreement, as shown by the preamble, operative party definition, or execution
block.

QUALIFIES:
- Entities introduced as "by and between", "among", "Party", "Parties",
  "Buyer", "Seller", "Licensor", "Licensee", etc.
- A fund, trust series, partnership, corporation, LLC, individual, or other
  legal person expressly entering the agreement.
- A party whose name is established by the signature block where the preamble
  is incomplete.

DOES NOT QUALIFY:
- Affiliates merely mentioned in the agreement.
- Customers, dealers, distributors, subcontractors, investment advisers,
  beneficiaries, licensors of upstream rights, or other third parties unless
  they themselves enter the agreement.
- Directors, officers, employees, attorneys, or representatives who sign only
  on behalf of an entity.
- A person who merely "acknowledges" the agreement unless the text also makes
  that person a contracting party.
- A third-party beneficiary solely because it has enforceable rights.

CONTEXT RULE: Resolve contractual labels to the underlying legal name. If a
signature block materially conflicts with the preamble, return UNRESOLVED
rather than guessing.

OUTPUT: Return the legal names of all contracting parties.""",

    "agreement_date": """TASK: Extract the date identified as the date of the contract/document
itself.

QUALIFIES:
- "This Agreement is dated as of..."
- "Entered into as of..."
- "Agreement dated..."
- A defined "Date of the Agreement" that expressly means the date on which
  the agreement is executed or entered into.
- If the contract expressly states that its date is the later/last signature
  date, derive it only if all required signature dates are available.

DOES NOT QUALIFY:
- Effective Date unless the document expressly equates it with the Agreement
  Date.
- Signature dates standing alone when the contract does not identify which
  one is the agreement date.
- Filing date, amendment date of another document, shipment date, launch
  date, commencement date, renewal date, invoice date, or expiration date.
- A blank or placeholder date such as "[•], 2019" as a completed date.

CONTEXT RULE: Do not assume the first date appearing in the document is the
Agreement Date. If the rule is known but the date cannot be calculated
because a signature/date is missing or redacted, return UNRESOLVED and
preserve the stated mechanism.

OUTPUT: Date in the requested normalized format, or UNRESOLVED.""",

    "effective_date": """TASK: Extract the date on which the agreement expressly becomes legally
effective.

QUALIFIES:
- A date expressly defined as "Effective Date".
- "This Agreement shall become effective on..."
- "Effective as of..."
- A rule stating that the agreement becomes effective on the later/last date
  of signature, where that date can be determined from the document.

DOES NOT QUALIFY:
- Agreement Date merely because it is nearby, unless the text makes the
  dates the same.
- Commercial launch, service commencement, delivery, payment, closing, or
  first-use dates unless expressly defined as the agreement's Effective Date.
- The start date of a particular license/service if the agreement itself
  became effective earlier.
- A placeholder or redacted effective date as if it were known.

CONTEXT RULE: The Agreement Date and Effective Date may be identical, but
only treat them as identical when the contract says so or necessarily makes
them so. If effectiveness depends on an unmet/unknown condition, return the
condition/mechanism as UNRESOLVED rather than inventing a calendar date.

OUTPUT: Date, or UNRESOLVED with the stated effectiveness mechanism.""",

    "expiration_date": """TASK: Determine when the INITIAL TERM of the contract expires.

QUALIFIES:
- An express calendar expiration date.
- A determinable initial-term end date calculated from an express
  start/effective date plus a stated duration.
- An initial term stated to continue "in perpetuity" or without expiration,
  where the contract clearly has no initial-term end date.
- A term running until a defined event only if that event functions as the
  contract's initial-term endpoint; if the event date is unknown, return the
  mechanism as UNRESOLVED.

DOES NOT QUALIFY:
- The end of a renewal period.
- A possible early termination date.
- A cure deadline.
- A warranty, license, project, purchase-order, shipment, or service-specific
  expiry unless it is also the contract's initial-term expiry.
- Automatic renewal itself as evidence that the initial term is perpetual.

CONTEXT RULE: Distinguish (1) agreement term, (2) license term, (3)
project/service term, and (4) renewal term. If an initial term is "X years
from Commercial Launch Date" but the launch date is unavailable, the
existence/duration is DIRECT but the calendar expiration date is UNRESOLVED.

OUTPUT: Exact date if determinable; otherwise "Perpetual" or UNRESOLVED with
the stated mechanism.""",

    "renewal_term": """TASK: Identify the duration of each renewal/extension period AFTER the
initial term.

QUALIFIES:
- Automatic renewal for successive one-year, six-month, monthly, or other
  stated periods.
- A unilateral extension option that, once exercised, extends the contract
  for a stated period.
- A renewal that requires approval/conditions but still specifies the length
  of the renewed term.
- Perpetual renewal only where the renewal itself is expressly perpetual.

DOES NOT QUALIFY:
- The initial term.
- The advance notice needed to stop renewal.
- A clause stating only that the parties "may renew" or "will negotiate an
  extension" without a definite renewal period.
- A continuation solely to complete outstanding work, wind down, or sell
  remaining stock.
- A new agreement that must be separately negotiated.

CONTEXT RULE: If the contract says "successive annual periods" subject to
annual approval, the renewal term is still one year; the approval condition
is separate. If the renewal duration is redacted but automatic renewal is
clear, classify the mechanism as present but the value as UNRESOLVED.

OUTPUT: "[Successive] X years/months/days", "Perpetual", or UNRESOLVED.""",

    "notice_period_to_terminate_renewal": """TASK: Extract the advance notice specifically required to prevent, cancel,
or opt out of a renewal/automatic extension.

REQUIRED:
1. A renewal/extension mechanism exists; AND
2. The notice is tied to preventing or ending that renewal.

QUALIFIES:
- "Either party may prevent automatic renewal by giving 60 days' prior
  written notice."
- Notice required before the end of the initial or renewal term to stop the
  next renewal.
- A non-renewal notice period even if the contract uses words such as
  "termination notice" rather than "non-renewal".

DOES NOT QUALIFY:
- Termination-for-convenience notice that can be given at any time.
- Termination-for-breach notice or cure periods.
- Notice for assignment/change of control.
- General notices provisions describing delivery methods.
- A renewal election/approval deadline that is not a notice to
  terminate/non-renew.

CONTEXT RULE: If no renewal exists, return NO/Not Applicable. If the notice
period is redacted, return YES for the mechanism but UNRESOLVED for the
numeric period.

OUTPUT: Number of days/months/years, or UNRESOLVED/Not Applicable.""",

    "governing_law": """TASK: Identify the jurisdiction whose substantive law governs the agreement
and/or its interpretation.

QUALIFIES:
- "This Agreement shall be governed by the laws of the State of New York."
- "Construed in accordance with the laws of..."
- A choice-of-law clause naming a country, state, province, or other
  governing jurisdiction.
- Multiple governing regimes only when the contract expressly says both apply
  (e.g. a national law plus CISG).

DOES NOT QUALIFY:
- Venue/forum-selection language alone.
- Exclusive jurisdiction of a court alone.
- Arbitration seat/place.
- Place of execution or performance.
- A party's state/country of incorporation.
- References to statutes/regulations governing a particular activity without
  a general choice-of-law rule.

CONTEXT RULE: Do not "correct" an unusual governing-law clause. Extract what
the contract states. Separate governing law from forum/jurisdiction.

OUTPUT: Name of the stated jurisdiction(s), or UNRESOLVED.""",

    "most_favored_nation": """TASK: Determine whether a party is contractually entitled to terms at least
as favorable as terms given to a third party for comparable technology,
goods, services, licenses, distribution, or sale arrangements.

REQUIRED ELEMENTS:
1. A third-party comparator or class of third parties;
2. More favorable/better/lower/higher terms given or potentially given to
   that third party;
3. A contractual consequence benefiting the counterparty, such as automatic
   matching, adjustment, reimbursement, or entitlement to equivalent/better
   terms.

QUALIFIES:
- "If Licensor offers a lower royalty rate to another licensee, Licensee
  shall receive that lower rate."
- "Prices shall be no less favorable than those offered to any other customer
  for comparable products."
- A clause requiring adjustment to match more favorable third-party pricing
  or commercial terms.

DOES NOT QUALIFY:
- "Competitive pricing" or "market rates".
- A requirement to negotiate in good faith if better terms exist, without an
  entitlement to matching/equivalent terms.
- Price benchmarking without a contractual matching remedy.
- Uniform pricing that applies to dealers but is not triggered by better
  third-party terms.
- A definition/list of competitors.
- A representation that current terms are favorable.
- A general non-discrimination clause unrelated to third-party commercial
  terms.

CONTEXT RULE: The clause need not use "most favored nation"/"MFN", but the
third-party comparison and matching entitlement must be present.

OUTPUT: YES only if all required elements are established; otherwise
NO/UNRESOLVED.""",

    "non_compete": """TASK: Determine whether the contract imposes an OPERATIVE restriction on a
party's ability to compete with the counterparty or to operate in a
specified geography, business, market, product area, or technology sector.

CORE TEST: Return YES only where the text actually prohibits, restricts,
conditions, or materially limits a party (or its affiliates/personnel/
controlled entities) from engaging in business activity that competes with:
- the counterparty or its business;
- specified competing products/services/technology;
- a defined competitive business, field, market, industry, sector, or
  geography; or
- identified competitors because of their competitive status.

REQUIRED ELEMENTS:
1. RESTRICTED ACTOR — a party/person whose conduct is restricted;
2. OPERATIVE RESTRAINT — e.g. shall not, may not, agrees not to, must
   refrain, prohibited, only with consent, or equivalent;
3. COMPETITIVE NEXUS — the restricted conduct is competitive economic
   activity, not merely another contractual restriction.

QUALIFYING PATTERNS:
- Owning, managing, operating, controlling, financing, investing in,
  advising, working for, assisting, or participating in a competing business.
- Developing, researching, manufacturing, commercializing, marketing, selling,
  distributing, supplying, licensing, or providing competing
  products/services/technology.
- Representing, endorsing, collaborating with, or providing specified
  commercial support to a competitor because it is a competitor.
- Prohibiting specified business activity in a territory/market/field/
  technology sector.
- A territorial/customer allocation that actually prevents a party from
  competing or selling in the allocated area/segment.
- Direct or indirect restraints, including through affiliates or third
  parties.

DOES NOT QUALIFY:
- A definition/list of competitors by itself. A definition of "Competitor"
  or a competitor list is not an operative restraint on competing.
- A clause saying parties remain independent/competing companies.
- Permission to compete ("whether or not competitive"; "nothing shall
  preclude competition").
- Confidentiality, data-use, trademark, advertising, customer-service,
  assignment, or IP-protection restrictions merely because they affect
  competitive conduct.
- Customer/employee non-solicitation, unless there is an independent broader
  competitive restraint.
- An exclusive procurement/supply/license arrangement that only limits
  third-party dealing and does not independently restrain competitive
  activity (classify Exclusivity).
- A field/territory limitation on the USE OF A LICENSE only; license scope
  is not automatically a non-compete.
- A product specification, minimum purchase commitment, or ordinary marketing
  rule.

OVERLAP RULE: A clause may be both Non-Compete and Exclusivity only if it
independently satisfies both legal effects. Do not duplicate labels merely
because exclusivity has competitive consequences.

REDACTION/CROSS-REFERENCE RULE: If the operative restriction is redacted or
contained only in an unavailable incorporated agreement, return UNRESOLVED.
Do not promote a nearby competitor definition to YES.

OUTPUT: For YES identify restricted party, restricted activity, competitive
object/field, geography/duration if stated, and the smallest operative
quote.""",

    "exclusivity": """TASK: Determine whether the agreement creates an exclusive dealing,
sourcing, sales, distribution, licensing, supply, marketing, collaboration,
or provider commitment.

CORE TEST: Return YES where one party receives exclusivity or another party
is prohibited/limited from dealing with alternative third parties in relation
to specified goods, services, technology, rights, customers, territories,
fields, channels, or activities.

REQUIRED ELEMENTS:
1. An identifiable party whose freedom to deal is restricted OR an
   identifiable party receiving legally exclusive rights;
2. Defined subject matter/scope of exclusivity;
3. An operative exclusive commitment, exclusive grant, sole-source
   requirement, or prohibition on competing third-party dealings.

QUALIFIES:
- "Buyer shall purchase all requirements exclusively from Seller."
- "Licensor grants Licensee an exclusive license" where "exclusive" has legal
  effect against other grants/uses.
- Exclusive distributor/marketing/sales rights for a territory or customer
  segment.
- "Company is the exclusive provider" where the agreement actually creates
  that status.
- A party may not license, sell, supply, distribute, procure, collaborate,
  or contract for the covered subject matter with third parties.
- A party may not enter discussions/agreements for similar covered services
  with alternative providers during the term.
- Sole-source/requirements commitments.

DOES NOT QUALIFY:
- "Exclusive jurisdiction", "exclusive remedy", "exclusive
  property/ownership", "exclusive right to prosecute a claim", or similar
  uses of "exclusive" unrelated to dealing.
- Preferred provider/manufacturer status alone.
- A right of first refusal/offer/negotiation where the right-holder can
  decline and the transaction may then go to others; classify ROFR/ROFO/ROFN.
- Minimum purchase obligations that still allow third-party purchases.
- Non-exclusive licenses.
- A party's independent right to set prices.
- A definition of "Exclusive Product" without an operative exclusive
  obligation.
- An ordinary non-compete unless it separately creates exclusive dealing.

IMPLIED-EXCLUSIVITY RULE: An express "exclusive license/right/distribution
appointment" can itself establish exclusivity even without the words "shall
not grant to others", provided the contractual usage clearly makes the right
legally exclusive. If the term "exclusive" is merely descriptive or
ambiguous, require surrounding operative context.

OUTPUT: For YES identify the party receiving exclusivity, the party
restricted, subject matter, territory/customer/channel/duration, and any
carve-outs.""",

    "no_solicit_of_customers": """TASK: Determine whether a party is restricted from soliciting, targeting,
contracting with, selling to, servicing, diverting, accepting business from,
or otherwise pursuing customers/clients/users/business partners of the
counterparty.

REQUIRED ELEMENTS:
1. Restricted actor;
2. Operative restriction on customer-facing business development or
   contracting;
3. Protected persons are customers/clients/users/partners of the counterparty
   or a contractually defined equivalent class.

QUALIFIES:
- "Company shall not solicit Customer's clients."
- A prohibition on bypassing the counterparty to contract directly with
  introduced/referred customers.
- A restriction on targeted marketing to the counterparty's customers where
  the purpose/effect is to solicit their business.
- A prohibition on accepting business from protected customers, if drafted
  as a no-dealing/no-solicit restriction.

DOES NOT QUALIFY:
- Confidentiality restrictions on customer lists/data without a restriction
  on contacting/contracting with those customers.
- General advertising rules unrelated to the counterparty's customers.
- Marketing to a party's own customers.
- Restrictions on use of personal data only.
- Employee non-solicitation.
- Definitions of "Customer", "User", "Partner", or "Referral Information"
  by themselves.
- A clause permitting general customer contacts; that may be an exception,
  not the underlying restriction.

RELATIONSHIP RULE: Do not assume "users", "subscribers", "dealers",
"prospects", or "partners" are the counterparty's customers unless the
agreement establishes the relationship or the category's protected class
clearly encompasses them.

OUTPUT: YES only if the protected customer/partner relationship and operative
restriction are established; otherwise NO/UNRESOLVED.""",

    "competitive_restriction_exception": """TASK: Identify an express exception, carve-out, safe harbor, permission,
exclusion, or exemption from a qualifying Non-Compete, Exclusivity, or
No-Solicit-of-Customers restriction.

REQUIRED ELEMENTS:
1. An underlying restriction that qualifies as Non-Compete, Exclusivity, or
   No-Solicit of Customers; AND
2. Language that removes specified conduct/persons/products/transactions/
   territories/customers/circumstances from that restriction.

QUALIFIES:
- "Notwithstanding the foregoing, Company may..."
- "Nothing in this Section shall prohibit..."
- "Except that..."
- Carve-outs for pre-existing customers, passive investments, general
  advertisements, existing businesses, specified accounts, pre-existing
  contracts, particular territories/products, or consented conduct —
  BUT only when tied to a qualifying competitive restriction.

DOES NOT QUALIFY:
- Confidentiality exceptions (public domain, previously known, required by
  law).
- Assignment exceptions/permitted assignments.
- Liability-cap carve-outs.
- Warranty, indemnity, termination, insurance, or IP exceptions.
- A standalone permission to compete where no underlying restriction exists.
- Generic "except", "provided however", or "notwithstanding" language
  unrelated to competitive restrictions.

CONTEXT RULE: Resolve "foregoing" and cross-references. If the underlying
restriction is redacted/unavailable, return UNRESOLVED rather than assuming
the exception is competitive.

OUTPUT: For YES quote both enough of the underlying restriction and the
carve-out to prove the relationship.""",

    "no_solicit_of_employees": """TASK: Determine whether a party is restricted from soliciting, recruiting,
inducing, hiring, employing, engaging, or causing employees/contractors of
the counterparty (or specified affiliates) to leave or change
employment/engagement.

REQUIRED ELEMENTS:
1. Restricted actor;
2. Operative restriction;
3. Protected personnel are employees, workers, consultants, or contractors
   of the counterparty/covered affiliates.

QUALIFIES:
- "Neither party shall solicit or hire employees of the other."
- "Shall not induce any employee to leave."
- No-hire restrictions covering employees who worked on the agreement.
- Consent-required hiring of protected personnel.
- Restrictions continuing after termination.

DOES NOT QUALIFY:
- Customer solicitation.
- A definition of employee/personnel.
- Confidentiality of employee information.
- General HR/employment obligations.
- A requirement merely to notify the other party after hiring.
- A recruitment fee alone unless the clause actually conditions/restricts
  hiring or solicitation.
- Restrictions on a party soliciting its own employees.

EXCEPTION RULE: General-advertising, unsolicited-application,
terminated-employee, or recruiter carve-outs are exceptions; do not classify
the exception as the underlying restriction by itself.

OUTPUT: For YES identify protected personnel, restricted conduct, duration,
affiliates covered, and any exceptions.""",

    "non_disparagement": """TASK: Determine whether a party is required not to disparage, demean,
defame, denigrate, portray adversely, or otherwise damage the reputation of
the counterparty or its products/services through specified communications,
uses, statements, acts, or omissions.

REQUIRED ELEMENTS:
1. Restricted actor;
2. An express negative/reputational standard (e.g. disparage, defamatory,
   derogatory, false/poor light, reflects adversely, denigrate, damage
   reputation);
3. The protected subject is the counterparty, its business,
   products/services, marks, personnel, or reputation.

QUALIFIES:
- "Neither party shall disparage the other."
- A prohibition on using the other party's trademarks in a manner that
  disparages it or portrays it/products in a false or poor light.
- "Licensee shall not use the Licensed Mark in any manner that disparages
  or reflects adversely on Licensor or its reputation."
- A ban on derogatory/defamatory/reputation-harming statements.

DOES NOT QUALIFY:
- General duties to act professionally, courteously, ethically,
  cooperatively, or in good faith.
- Customer-service standards that say conduct should "reflect favorably"
  without prohibiting adverse/disparaging expression.
- Comparative advertising restrictions that do not prohibit
  disparagement/false adverse portrayal.
- Confidentiality/publicity approval clauses without an anti-disparagement
  standard.
- Trademark quality-control requirements alone.
- Obligations to protect goodwill that do not prohibit disparaging conduct
  or communications.

CONTEXT RULE: The clause need not be a broad speech restriction; a
trademark-use or publicity-specific non-disparagement obligation qualifies
if it expressly prohibits disparagement/adverse portrayal.

OUTPUT: YES only for an express reputationally adverse restriction.""",

    "termination_for_convenience": """TASK: Determine whether a party may terminate the CONTRACT (not merely a
sub-license/order/service component) without breach/default or another
substantive cause, usually by giving notice and waiting for a stated period.

REQUIRED ELEMENTS:
1. Unilateral termination right held by one or both parties;
2. No cause/default/trigger is required for that termination path;
3. Termination of the agreement as a whole (or substantially all of it).

QUALIFIES:
- "Either party may terminate this Agreement upon 60 days' written notice."
- "Licensor may terminate at any time in its sole discretion on 30 days'
  notice."
- One-sided no-cause termination rights.
- No-penalty termination by notice, even where board/shareholder approval
  is required internally.

DOES NOT QUALIFY:
- Termination for material breach, insolvency, force majeure, regulatory
  failure, change of control, nonpayment, IP claim, fraud, or other cause.
- Mutual termination requiring both parties' agreement.
- Non-renewal only.
- Termination of a single office-space license, statement of work, purchase
  order, product license, or service component where the main agreement
  remains.
- Automatic expiration.

CONTEXT RULE: A clause may contain both cause-based and convenience rights;
classify YES if at least one independent no-cause termination path exists.

OUTPUT: Identify which party may terminate, notice/waiting period, and
whether the right applies to the whole agreement.""",

    "rofr_rofo_rofn": """TASK: Determine whether one party has a right of first refusal (ROFR),
right of first offer (ROFO), right of first negotiation (ROFN), or
functionally equivalent priority right before the counterparty may transact
with a third party.

REQUIRED ELEMENTS:
1. Right-holder;
2. Defined transaction/subject matter (equity, assets, IP/license, products,
   services, manufacturing, marketing, distribution, etc.);
3. Priority relative to third parties.

QUALIFIES:
- ROFR: right to match/accept a proposed third-party deal.
- ROFO: counterparty must first invite/consider an offer from the
  right-holder before going to third parties.
- ROFN: counterparty must first negotiate with the right-holder before
  negotiating elsewhere.
- "First right of refusal" on manufacturing requests/services, even if an
  alternate provider may be used after refusal/non-response/noncompetitive
  terms.
- A clearly equivalent "first opportunity" structure with enforceable
  priority.

DOES NOT QUALIFY:
- Preferred provider/supplier status alone.
- Ordinary renewal or extension rights.
- A purchase option exercisable independently of third-party dealings.
- Consent rights over assignment.
- Mere notice of a proposed transaction.
- General good-faith negotiation obligations.
- Exclusivity that gives sole rights rather than a first-priority
  opportunity.

OUTPUT: Identify ROFR/ROFO/ROFN type, right-holder, subject matter,
triggering event, response/matching period, and third-party fallback if
stated.""",

    "change_of_control": """TASK: Determine whether a change in ownership/control of a contracting
party triggers a contractual consequence such as termination, consent,
approval, notice, deemed assignment, or another counterparty right.

CHANGE-OF-CONTROL EVENTS MAY INCLUDE:
- Merger/consolidation;
- Sale/transfer of controlling equity or voting power;
- Acquisition of control;
- Sale of all or substantially all assets/business;
- Reorganization;
- Assignment by operation of law;
- A defined "Change of Control" event.

REQUIRED ELEMENTS:
1. A qualifying control/ownership event; AND
2. An operative consequence tied to that event (termination, consent,
   notice, approval, deemed assignment, etc.).

QUALIFIES:
- Change of control requires prior consent.
- Change of control gives the other party a termination right.
- Change of control is deemed an assignment and the assignment clause
  requires consent/notice.
- Mandatory notice of a merger/control sale.
- Automatic termination triggered by specified change-of-control event.

DOES NOT QUALIFY:
- A definition of "Change of Control" alone.
- A permitted change-of-control/assignment carve-out that imposes no
  consent, notice, termination, or other consequence.
- Ordinary anti-assignment language that says nothing about
  ownership/control.
- Corporate reorganizations described only as background.
- A party's ownership percentage definition used only to define "Affiliate".

REDACTION RULE: If the definition is visible but the consequence is
redacted, return UNRESOLVED, not YES.

OUTPUT: Identify affected party, triggering event, and contractual
consequence.""",

    "anti_assignment": """TASK: Determine whether assignment/transfer/delegation of the agreement or
contractual rights/obligations is prohibited, restricted, or conditioned on
consent or notice.

REQUIRED ELEMENTS:
1. Assignment, transfer, delegation, encumbrance, or equivalent transfer of
   the agreement/rights/duties; AND
2. Prohibition, prior consent/approval, notice, or other condition.

QUALIFIES:
- "Neither party may assign this Agreement without prior written consent."
- Assignment only to affiliates meeting stated conditions.
- Assignment permitted on sale of substantially all business subject to
  assumption/notice.
- A clause automatically terminating the contract upon assignment.
- Restrictions on delegation of contractual duties where they function as
  transfer restrictions.

DOES NOT QUALIFY:
- "This Agreement binds successors and assigns" without restricting
  assignment.
- A definition of "Assignment".
- A change-of-control clause with no assignment/transfer concept.
- Transfer of physical goods/property unrelated to the agreement.
- A restriction solely on transferring an IP license, where the main
  agreement remains assignable; classify Non-Transferable License (and
  Anti-Assignment only if the agreement/rights generally are also
  restricted).

CARVE-OUT RULE: Permitted affiliate, merger, reorganization, or asset-sale
assignments are exceptions to an anti-assignment restriction, not reasons to
classify the restriction as absent.

OUTPUT: Identify restricted party, what may not be assigned,
consent/notice standard, permitted assignments, and effect of prohibited
assignment if stated.""",

    "revenue_profit_sharing": """TASK: Determine whether one party must pay/share with the counterparty a
portion of revenue, gross proceeds, net proceeds, net sales, profits,
margins, or comparable transaction receipts generated from specified
goods/services/technology/content.

REQUIRED ELEMENTS:
1. Defined revenue/profit/proceeds/sales base; AND
2. Payment/allocation to the counterparty calculated as a share, percentage,
   or formula based on that base.

QUALIFIES:
- Percentage of Net Sales as royalties.
- Percentage of gross revenue or gross proceeds.
- Percentage of net proceeds/profit.
- "Higher of X% Gross Proceeds or Y% Net Proceeds."
- Revenue-share consideration in a distribution/content agreement.
- Tiered royalty percentages tied to annual Net Sales.

DOES NOT QUALIFY:
- Fixed fees, flat license fees, retainers, reimbursements, cost sharing, or
  per-unit prices unrelated to revenue/profit.
- Ordinary commissions unless the counterparty is contractually receiving a
  share of the relevant revenue/proceeds under the agreement.
- A definition of "Net Sales" or "Revenue" without a payment obligation.
- A party merely retaining its own sales proceeds.
- Milestone payments triggered by sales thresholds if the payment is a fixed
  amount rather than a share; those may be milestone/minimum/other payments,
  not revenue sharing.

OUTPUT: Identify payer, recipient, revenue/profit base,
percentage/formula, deductions, thresholds, and payment period if stated.""",

    "price_restrictions": """TASK: Determine whether the contract restricts a party's ability to set,
raise, reduce, discount, resell, or otherwise change the price of covered
technology, goods, services, shares, licenses, or other commercial
offerings.

REQUIRED: An operative constraint on pricing discretion, not merely a stated
contract price.

QUALIFIES:
- Required resale at a specified/public offering price.
- Minimum or maximum resale price.
- Price increases capped by a percentage/index.
- Price decreases/discounts prohibited below a floor.
- Price changes requiring counterparty consent/mutual agreement.
- Fixed-price period expressly preventing unilateral changes.
- Uniform commission/concession requirements if they legally restrict
  differential pricing/discounting.
- A formula that constrains the price a party may charge third parties.

DOES NOT QUALIFY:
- A price/fee schedule stating what one party must pay the other.
- A party independently setting its own price.
- A revenue/profit-sharing formula.
- A royalty rate.
- A most-favored-nation clause unless it independently constrains pricing.
- A requirement to negotiate new prices after legal/regulatory change without
  a current restriction on ordinary price-setting.
- "Competitive terms/pricing" language standing alone.
- Price definitions or invoicing mechanics.

CONTEXT RULE: Ask whether the party would breach the agreement merely by
charging a different price. If not, it is probably not a Price Restriction.

OUTPUT: Identify restricted party, product/service, pricing constraint,
permitted adjustment mechanism, and duration.""",

    "minimum_commitment": """TASK: Determine whether a party is obligated to purchase/order/use/pay
for at least a minimum quantity, amount, volume, units, spend, or
economically equivalent guaranteed minimum from the counterparty over a
stated period or transaction.

REQUIRED ELEMENTS:
1. Binding obligation (not forecast/target);
2. Minimum floor/quantity/spend/payment;
3. Purchase/procurement/use/payment relationship with the counterparty or an
   economically equivalent minimum guarantee.

QUALIFIES:
- Minimum annual/monthly purchase quantity.
- Minimum order size.
- Minimum spend.
- Take-or-pay obligation.
- Minimum guaranteed payment/royalty tied to the right to
  purchase/license/use covered goods/services, where payment is due
  regardless of actual usage.
- "At least X units" purchased from the counterparty.

DOES NOT QUALIFY:
- Non-binding forecasts, estimates, expected volumes, business plans,
  targets, or best-efforts goals.
- A minimum advertising/promotional activity obligation that is not a
  purchase from the counterparty.
- Minimum service levels the supplier must provide.
- Minimum insurance coverage.
- A threshold that merely triggers a higher fee when usage exceeds it
  (Volume Restriction).
- A fixed one-time purchase amount already defining the transaction, unless
  the clause is genuinely a minimum/floor commitment.
- A maximum/cap.

REDACTION RULE: If the obligation is clearly "at least [***]" but the
quantity is redacted, classify the existence as YES and the value as
UNRESOLVED.

OUTPUT: Identify committed party, minimum amount/units/spend, period,
take-or-pay/minimum-guarantee mechanics, and exceptions.""",

    "volume_restriction": """TASK: Determine whether exceeding a specified usage/volume/quantity/
capacity/transaction threshold causes an additional fee, price change,
consent/approval requirement, service restriction, loss of service level,
or other contractual consequence.

REQUIRED ELEMENTS:
1. A threshold/cap/volume level; AND
2. A consequence specifically triggered by exceeding (or sometimes crossing)
   that threshold.

QUALIFIES:
- Overage fees above X users/transactions/minutes/GB.
- Higher price tier once volume exceeds a threshold.
- Consent required before exceeding a usage cap.
- Service/support limitations when forecasted/contracted volume is materially
  exceeded, if a defined threshold/trigger is established.
- Contractual limitation or suspension tied to exceeding permitted volume.

DOES NOT QUALIFY:
- Minimum purchase commitments.
- Forecasts with no binding consequence.
- A party's unilateral right to reduce its own promotions because traffic is
  high, where the counterparty's use does not trigger a fee/consent/
  restriction.
- General capacity/technical descriptions.
- Ordinary per-unit pricing from the first unit with no threshold.
- High-usage indemnity/risk allocation without a threshold or usage cap.

REDACTION RULE: A redacted threshold can still establish the category if the
trigger/consequence relationship is clear; return the numeric value as
UNRESOLVED.

OUTPUT: Identify measured volume, threshold, consequence, affected party,
and period.""",

    "ip_ownership_assignment": """TASK: Determine whether intellectual property/work product CREATED or
DEVELOPED by one party (or its personnel/contractors) becomes owned by,
vests in, or is assigned to the counterparty.

REQUIRED ELEMENTS:
1. IP/work product is created, developed, authored, invented, conceived,
   reduced to practice, modified, enhanced, or otherwise generated;
2. Creator/source is one party or persons acting for it;
3. Ownership transfers/vests in the counterparty (automatically or upon a
   trigger).

QUALIFIES:
- Work-made-for-hire in favor of the counterparty.
- "Developer hereby assigns all right, title and interest in Deliverables
  to Customer."
- Future assignment covenants for created IP.
- One party assigns rights arising from its licensed use of the
  counterparty's mark back to the counterparty.
- Created derivative works/modifications assigned to the other party.
- Event-triggered transfer of created IP.

DOES NOT QUALIFY:
- Assignment of pre-existing IP as part of an asset sale unless the category
  is explicitly extended beyond created IP.
- A license grant without ownership transfer.
- Each party retaining its own pre-existing or independently developed IP.
- One party owning modifications it itself creates (no transfer to
  counterparty).
- Ownership of physical goods/documents only.
- A definition of "Work Product"/"IP" without an ownership transfer.

CONTEXT RULE: Identify creator and resulting owner separately. "All IP
remains with Licensor" is retention, not assignment, unless the
counterparty's newly created rights are expressly swept/assigned to
Licensor.

OUTPUT: Identify creator, IP type, assignee/owner, vesting/assignment
mechanism, and trigger.""",

    "joint_ip_ownership": """TASK: Determine whether specified intellectual property is
jointly/shared/co-owned by both contracting parties.

REQUIRED: An operative ownership rule granting both parties ownership
interests in the same IP.

QUALIFIES:
- "Jointly developed IP shall be jointly owned."
- Each party owns an equal/undivided interest.
- New software/hardware/IP developed jointly is expressly jointly owned.
- Joint inventions/works are co-owned, even if each party may exploit them
  independently.

DOES NOT QUALIFY:
- Joint development/collaboration without an ownership rule.
- Joint venture status without IP co-ownership.
- Each party owning the portion it creates.
- One party owning IP while licensing broad rights to the other.
- Mutual cross-licenses.
- Shared usage rights without shared title.
- "May be jointly owned if later mutually agreed" where a future agreement
  is still required to create ownership.
- A definition of "Joint IP" with no operative ownership clause.

OUTPUT: Identify the jointly owned IP, how it arises, ownership shares if
stated, exploitation/accounting rules, and exceptions for background IP.""",

    "license_grant": """TASK: Determine whether one party grants the counterparty an actual
license/permission to use or exploit intellectual property, proprietary
content, software, data, trademarks, patents, copyrights, know-how,
technology, or comparable protected rights.

REQUIRED ELEMENTS:
1. Grantor/licensor;
2. Grantee/licensee;
3. Protected/proprietary subject matter;
4. Operative authorization to use/exploit it.

QUALIFIES:
- "Licensor hereby grants Licensee a license to use..."
- Rights to reproduce, distribute, display, modify, make, sell, import,
  perform, transmit, sublicense, or otherwise exploit IP/content.
- A content distribution license.
- A software/technology right of use.
- A trademark license.
- An express proprietary-data/content license even if the word "license"
  is not used, where legal permission is clearly granted.

DOES NOT QUALIFY:
- A real-property/office-space license.
- Access to ordinary services with no proprietary/IP grant.
- Ownership transfer/assignment instead of a license.
- A promise to negotiate a future license.
- A definition of "Licensed IP/Product" without a grant.
- References to upstream/third-party licenses that do not grant rights
  between the contracting parties.
- Mere right to inspect/copy data for a limited operational task unless the
  agreement actually grants proprietary usage rights.

OUTPUT: Identify licensor, licensee, subject matter, licensed acts,
exclusivity, territory, field, duration, transfer/sublicense rights, and
payment status if stated.""",

    "non_transferable_license": """TASK: Determine whether an IP/proprietary license granted under the
contract is expressly non-transferable/non-assignable or otherwise
restricted from transfer to third parties.

REQUIRED ELEMENTS:
1. An actual qualifying License Grant; AND
2. A transfer/assignment restriction applying to that license or licensed
   rights.

QUALIFIES:
- "Non-transferable license."
- "Licensee may not assign or transfer the license without Licensor's
  consent."
- A personal license that expressly cannot be transferred.
- A license stated to be transferable only through specified permitted
  assignments.

DOES NOT QUALIFY:
- General anti-assignment of the contract if it does not clearly apply to
  the license/licensed rights.
- A non-exclusive license.
- A field/territory/use restriction.
- Ownership retention.
- A mere prohibition on sublicensing if transfer/assignment is otherwise
  permitted; treat sublicensing separately unless the drafting equates it
  with transfer.
- A definition using "non-transferable" without an operative license.

OVERLAP RULE: The same provision may support Anti-Assignment and
Non-Transferable License when it restricts both the agreement generally and
the license specifically.

OUTPUT: Identify license, transfer restriction, consent standard, permitted
transfers, and whether sublicensing is separately restricted.""",

    "affiliate_license_licensor": """TASK: Determine whether the license granted to the counterparty includes
IP/rights owned or controlled by affiliates of the licensor, or whether
licensor affiliates themselves grant licensed rights.

REQUIRED:
1. A qualifying license grant; AND
2. Licensor-side affiliates contribute licensed IP/rights or act as
   grantors.

QUALIFIES:
- "Licensed IP" expressly includes patents/trademarks/technology owned or
  controlled by Licensor and its Affiliates.
- Licensor grants rights under IP controlled by "Licensor or any Affiliate."
- Affiliates are express co-licensors/grantors.
- A grant covers affiliate-owned marks/content through an operative
  definition incorporated into the license.

DOES NOT QUALIFY:
- Merely defining "Affiliate."
- Licensor affiliates using the IP themselves.
- A recital saying licensor operates through affiliates.
- Licensee affiliates receiving/sublicensing rights (Affiliate
  License-Licensee).
- General contractual obligations covering affiliates.
- A license limited to the licensor's own IP.

CONTEXT RULE: A definition can establish the scope of "Licensed IP" only
when an operative license grant actually uses that defined term.

OUTPUT: Identify licensor, relevant affiliates, affiliate IP/rights
included, and operative grant.""",

    "affiliate_license_licensee": """TASK: Determine whether rights under a license extend to the licensee's
affiliates, including by direct grant or an express right to
sublicense/permit use to those affiliates.

REQUIRED:
1. A qualifying license grant; AND
2. Licensee-side affiliates are authorized recipients/users/sublicensees of
   licensed rights.

QUALIFIES:
- "Licensor grants Licensee and its Affiliates..."
- Licensee may use the IP through/on behalf of its affiliates.
- Licensee may sublicense the licensed rights to its Affiliates.
- Affiliates are expressly included in "Licensee" or "Authorized Users" for
  purposes of the license.

DOES NOT QUALIFY:
- Merely defining "Affiliate."
- Licensor affiliates owning the licensed IP.
- Affiliates merely receiving ordinary services.
- A sublicense right to third parties generally where affiliates are not
  specifically included, unless the category implementation intentionally
  treats any affiliate eligible under that right as established by context.
- Affiliate obligations unrelated to the license.

OUTPUT: Identify licensee, affiliates covered, whether rights are direct or
via sublicense, and any conditions.""",

    "unlimited_all_you_can_eat_license": """TASK: Determine whether a license expressly grants unlimited/enterprise/
all-you-can-eat usage along a commercially meaningful quantitative
dimension.

QUALIFIES:
- "Unlimited use."
- "Enterprise-wide" license with no material user/seat/device/site cap.
- Unlimited number of users/devices/copies.
- "Unlimited runs" of licensed content during the license term.
- Unlimited transactions/streams/distributions where expressly stated.

DOES NOT QUALIFY:
- Worldwide territory (geographic breadth only).
- Perpetual duration (time only).
- Irrevocable status.
- Royalty-free/fully paid-up pricing.
- Exclusive status.
- A broad grant covering "all" IP in a portfolio while usage remains
  quantitatively limited.
- "Without limitation" used rhetorically rather than to remove usage caps.
- Unlimited sublicensing alone if the licensee's own usage is still
  quantitatively limited.

CONTEXT RULE: A license may be unlimited in one dimension but limited by
field, territory, term, purpose, or content. That can still qualify if the
contract expressly makes usage unlimited in the relevant quantitative sense;
record the remaining limitations.

OUTPUT: Identify the unlimited dimension and all material
field/territory/term restrictions.""",

    "irrevocable_or_perpetual_license": """TASK: Determine whether an actual license grant is expressly irrevocable,
perpetual, permanent, or otherwise of indefinite permanent duration.

QUALIFIES:
- "Perpetual license."
- "Irrevocable license."
- License rights expressly surviving termination indefinitely.
- A license stated to "continue perpetually" even if subject to specified
  termination conditions; classify YES but record the qualification.
- Permanent/everlasting license language with equivalent effect.

DOES NOT QUALIFY:
- The agreement itself being perpetual while the license has a separate
  finite term.
- "During the Term."
- A license surviving for a limited post-termination period.
- Worldwide, royalty-free, fully paid-up, exclusive, or non-transferable
  language standing alone.
- A perpetual right that is not a license (e.g. perpetual confidentiality
  or ownership).
- A definition mentioning perpetual rights without an operative grant.

CONTEXT RULE: If the agreement elsewhere says all license rights cease on
termination, still record an express "perpetual" grant as qualifying but
flag the termination qualification/inconsistency for review rather than
silently discarding it.

OUTPUT: Identify whether perpetual, irrevocable, or both, and any
termination/condition limitations.""",

    "source_code_escrow": """TASK: Determine whether source code or specified technical materials must
be deposited with an independent escrow agent/third party for possible
release/access by the counterparty upon defined trigger events.

REQUIRED ELEMENTS:
1. Source code/technical deposit materials;
2. Escrow/deposit with a third party or required escrow arrangement;
3. Counterparty release/access rights on specified conditions.

QUALIFIES:
- Deposit source code with an escrow agent and release upon insolvency.
- Required entry into a separate source-code escrow agreement incorporated
  by reference.
- Release on failure to support/maintain, business cessation, bankruptcy,
  material breach, or other agreed trigger.

DOES NOT QUALIFY:
- Direct source-code delivery to the counterparty.
- Code repositories/backups without independent escrow.
- Document/payment escrow unrelated to source code.
- A vague statement that parties may consider an escrow later.
- Merely mentioning source code or disaster recovery.

OUTPUT: Identify depositor, escrow agent/arrangement, materials, release
triggers, and beneficiary.""",

    "post_termination_services": """TASK: Determine whether termination/expiration causes a substantive
affirmative obligation to continue, arise, transition, wind down, transfer,
pay, support, sell off, return/migrate, or otherwise perform after the
contract ends.

QUALIFYING OBLIGATIONS INCLUDE:
- Transition assistance/customer migration.
- Continued service/operation for a wind-down period.
- Sell-off/last-buy periods or final supply duties.
- Post-termination payment/settlement obligations specifically triggered by
  termination.
- Transfer/reassignment of IP, regulatory filings, data, domains, assets,
  inventory, customers, or operational materials.
- Mandatory deletion/renaming/discontinuation plus affirmative public notice
  or transition obligations.
- Return/migration assistance beyond ordinary record retention.

DOES NOT QUALIFY BY ITSELF:
- A generic statement that provisions "survive" without a concrete
  post-termination performance duty.
- Standard survival of confidentiality, indemnity, governing law, dispute
  resolution, audit, or accrued-rights clauses alone.
- A post-termination non-compete/no-solicit alone; classify those categories
  unless there is a separate transition/service/payment obligation.
- Mere cessation of rights ("license ends") without further affirmative
  performance.
- Ordinary accrued invoice obligations not specifically part of a
  post-termination arrangement.

CONTEXT RULE: A contract can have multiple post-termination duties. Extract
the concrete duty, duration, trigger, and responsible party.

OUTPUT: YES where at least one substantive post-termination obligation
exists; quote the actual obligation, not only the survival clause.""",

    "audit_rights": """TASK: Determine whether one party has a contractual right to inspect,
audit, examine, verify, or access the counterparty's books, records,
reports, systems, facilities, operations, inventory, or physical locations
to check compliance, payment, quality, security, usage, or another
contractual metric.

REQUIRED ELEMENTS:
1. Audit/inspection right held by a party or its auditor/representative;
2. Access to evidence/records/facilities/operations of the counterparty;
3. Verification/compliance purpose.

QUALIFIES:
- Audit royalty/sales/payment records.
- Inspect books and accounts.
- Independent CPA audit.
- Physical/facility/quality inspection rights.
- Reasonable inspection of the quality of licensed services/business
  operations to verify contractual standards.
- Audit after termination if still tied to compliance/payment.

DOES NOT QUALIFY:
- A party must provide reports/financial statements, with no inspection
  right.
- The counterparty's own internal audit.
- Government/regulator inspection rights not exercisable by the contracting
  party.
- A representation/certification without verification access.
- Access solely to perform services, not to inspect compliance.
- Receiving copies of an independent audit already prepared by the
  counterparty.

OUTPUT: Identify auditing party, audited party, scope, frequency, notice,
look-back period, auditor restrictions, cost allocation, and remedy for
discrepancies.""",

    "uncapped_liability": """TASK: Determine whether liability is expressly unlimited or expressly
excluded from an otherwise applicable liability cap/limitation.

QUALIFIES:
- "Liability for fraud shall be unlimited."
- "The limitations of liability in this Article shall not apply to..."
- Carve-outs from monetary caps for willful misconduct, gross negligence,
  confidentiality breach, IP infringement, indemnity, etc.
- "Nothing shall limit liability for..." where it clearly removes the cap.

DOES NOT QUALIFY:
- A broad indemnity clause by itself.
- "Shall be fully responsible" without establishing that liability is outside
  a cap.
- Mere absence of a cap elsewhere in the contract.
- A clause stating liability exists but not whether it is capped.
- Insurance limits.
- Exclusion of consequential damages without a statement that specified
  liability is uncapped.

WHOLE-CONTRACT RULE: Evaluate uncapped liability in context of the
limitation-of-liability regime. A carve-out only counts if it actually
removes a cap/limitation that would otherwise apply.

OUTPUT: Identify the uncapped party/claim type and the cap/limitation from
which it is excluded.""",

    "cap_on_liability": """TASK: Determine whether the contract expressly limits maximum recoverable
liability/damages or imposes a contractual time bar for bringing/notifying
claims.

QUALIFIES:
- Fixed monetary cap.
- Per-event and/or annual aggregate cap.
- Cap based on fees paid/payable, contract value, a multiple, or other
  formula.
- Separate caps for different claim types.
- Contractual claim limitation period ("no action may be brought more than
  one year after...").
- Mandatory damages-notification deadline where failure causes the claim to
  be waived, if it operates as a time limitation on claims.

DOES NOT QUALIFY BY ITSELF:
- Exclusion of consequential/indirect/special/punitive damages without a
  maximum amount/time bar.
- Insurance policy limits.
- A fixed contract price.
- Liquidated damages.
- Warranty duration.
- Statutory limitation references that do not create a contractual time cap.
- A limitation of a remedy that does not cap total liability.

CONTEXT RULE: A contract may simultaneously contain Cap on Liability and
Uncapped Liability carve-outs. Extract both separately.

OUTPUT: Identify cap amount/formula or claim-time limit, affected party,
covered claims, period, and exclusions.""",

    "liquidated_damages": """TASK: Determine whether the agreement predetermines damages/compensation
payable upon breach, delay, failure, prohibited conduct, or termination,
including a termination fee.

QUALIFIES:
- Express "liquidated damages".
- Fixed/per-day/per-unit damages for delay or breach.
- Early termination/cancellation fee.
- Predetermined amount/formula payable for violating a covenant (e.g. a
  specified number of months' salary for prohibited employee solicitation).
- Service credits/credits that function as agreed compensation for a
  service-level breach, especially where designated as liquidated damages or
  exclusive remedy.

DOES NOT QUALIFY:
- Ordinary unpaid fees/invoices.
- Interest on late payment.
- Reimbursement of actual losses/costs.
- General indemnity.
- Attorneys' fees.
- Liability cap.
- Refund of prepaid amounts unless it is expressly a termination/breach
  charge rather than restitution.
- A sales milestone payment not triggered by breach/termination.

FUNCTIONAL TEST: The amount/formula must be fixed in advance as the
consequence of breach/failure/termination, not simply calculated after the
fact from actual damages.

OUTPUT: Identify triggering event, payer, recipient, amount/formula,
whether exclusive remedy, and any cap.""",

    "warranty_duration": """TASK: Extract the duration of a warranty against defects, errors,
nonconformity, quality failures, workmanship defects, or performance defects
in technology, products, or services provided under the contract.

REQUIRED:
1. An actual warranty/guarantee of quality/performance/defect-free
   condition; AND
2. A time period during which that warranty applies.

QUALIFIES:
- "90-day warranty from acceptance."
- "Seller warrants the products for 12 months after delivery."
- A guarantee period tied to shipment, installation, acceptance, or
  completion.
- A determinable warranty period even if the word "warranty" is not used,
  where a defect/nonconformity guarantee and duration are clear.

DOES NOT QUALIFY:
- Contract term.
- Cure period for any breach.
- Claim-notice period unless it is expressly the warranty period.
- Inspection/acceptance window by itself.
- Maintenance/support term.
- Statute/contractual limitations period.
- Warranty disclaimer ("AS IS") with no positive warranty duration.
- A quality guarantee with no stated duration; classification/value should
  be UNRESOLVED/Does Not Exist for duration.

CONTEXT RULE: A short claims window after delivery is not automatically the
warranty duration; distinguish the time to notify a claim from the time the
product is warranted.

OUTPUT: Return the warranty duration and start event; if warranty exists but
duration is unstated, return UNRESOLVED.""",

    "insurance": """TASK: Determine whether a party is required to obtain, procure, carry,
maintain, or provide evidence of insurance in connection with the contract
for protection of the counterparty, transaction, goods, services, or covered
risks.

QUALIFIES:
- Commercial general liability/product liability/cyber/E&O/workers'
  compensation insurance requirements.
- Minimum policy limits.
- Counterparty named as additional insured.
- Certificates of insurance.
- Notice of cancellation/non-renewal requirements.
- Cargo/shipping insurance that a seller must procure for the covered
  goods/transaction.
- Insurance required before clinical testing/sale/use and maintained for a
  stated tail period.

DOES NOT QUALIFY:
- "No insurance requirement."
- Merely allocating risk/indemnity.
- Insurance proceeds mentioned without a procurement/maintenance obligation.
- Insurance charges/costs included in pricing.
- A party's representation that it currently has insurance without a duty
  to obtain/maintain it, unless the representation itself contractually
  requires continued coverage.
- Employee benefits unrelated to contractual risk protection.

OUTPUT: Identify insured party/obligor, coverage type, limits, duration,
additional insureds, certificates, and cancellation notice if stated.""",

    "covenant_not_to_sue": """TASK: Determine whether a party is contractually restricted from
contesting/challenging the counterparty's ownership, validity, or
enforceability of IP, or from bringing/maintaining specified claims against
the counterparty outside ordinary contract enforcement.

QUALIFIES:
- Express covenant not to sue.
- "Licensee shall not contest, dispute, or challenge Licensor's right,
  title and interest in the Licensed Mark."
- No-challenge clauses for patent/trademark/copyright validity or ownership.
- Prospective agreement not to bring specified claims against the
  counterparty.

DOES NOT QUALIFY:
- Arbitration or forum-selection clauses (they regulate where/how to sue).
- Waiver of jury trial.
- Claim limitation periods.
- Liability caps.
- Indemnity.
- Obligation to mediate/negotiate before litigation.
- General release of already accrued claims, unless it also contains a
  prospective covenant not to bring/maintain those claims.
- Acknowledgement of ownership without a "shall not challenge/contest"
  restriction.

CONTEXT RULE: For IP no-challenge provisions, the restriction itself is
sufficient even if the word "sue" never appears.

OUTPUT: Identify restricted party, prohibited claim/challenge, protected
right/subject, duration/scope, and exceptions.""",

    "third_party_beneficiary": """TASK: Determine whether a non-contracting person/entity is affirmatively
made an intended beneficiary with enforceable rights/protections/remedies
under some or all of the agreement.

REQUIRED ELEMENTS:
1. Beneficiary is not a contracting party;
2. Agreement intentionally grants that beneficiary rights/protections/
   benefits;
3. Text indicates intended beneficiary/enforceability, not merely incidental
   benefit.

QUALIFIES:
- "The Investment Advisor shall be a third-party beneficiary of this
  Agreement and shall have the rights and protections..."
- A clause expressly allowing a named non-party to enforce specified
  provisions.
- An expressly identified class of intended third-party beneficiaries with
  enforcement rights.

DOES NOT QUALIFY:
- "No third-party beneficiaries."
- Incidental commercial benefits to customers, affiliates, employees,
  subcontractors, etc.
- Indemnified affiliates/employees merely being protected by an indemnity
  unless the contract expressly grants them enforceable beneficiary rights
  or otherwise clearly makes them intended beneficiaries.
- A person signing only an acknowledgement, unless beneficiary rights are
  independently granted.
- Definitions/references to "third party."

OUTPUT: Identify beneficiary, provisions/rights enforceable, and any
exclusions of other third parties.""",
}

assert set(CUAD_CLASSIFIERS) == set(CUAD_CLASSES), (
    "CUAD_CLASSIFIERS must cover exactly the 41 CUAD classes; "
    f"missing={set(CUAD_CLASSES) - set(CUAD_CLASSIFIERS)}, "
    f"extra={set(CUAD_CLASSIFIERS) - set(CUAD_CLASSES)}"
)


# Group-level disambiguation for the categories most often confused with one
# another. Injected into the prompt so the model separates operative effect
# from shared terminology.
GROUP_DISAMBIGUATION_RULES = """COMPETITIVE RESTRICTIONS
NON-COMPETE: Restricts competing economic activity itself. Ask: is the party
  prohibited from participating in a competing business/market/product/
  service/territory?
EXCLUSIVITY: Restricts dealing with alternative third parties or creates
  exclusive rights. Ask: must the party deal only with one
  provider/licensee/distributor, or is a right legally exclusive?
NO-SOLICIT OF CUSTOMERS: Protects the counterparty's customers/clients/
  partners from solicitation/dealing.
COMPETITIVE RESTRICTION EXCEPTION: Does not create the restriction. It removes
  conduct from an otherwise qualifying NON-COMPETE, EXCLUSIVITY, or Customer
  No-Solicit.
Important: an exclusive territorial/customer allocation may satisfy both
NON-COMPETE and EXCLUSIVITY only if it independently restricts competitive
activity and creates exclusive dealing/rights.

TRANSFER RESTRICTIONS
Anti-Assignment: Assignment/transfer/delegation of the contract or contractual
  rights/duties.
Change of Control: Ownership/control event plus a consequence such as consent,
  notice, termination, or deemed assignment.
Non-Transferable License: Transfer/assignment restriction specifically on the
  licensed rights/license.
Do not collapse all three into a single "assignment" label.

LICENSE CATEGORIES
License Grant: The underlying IP/proprietary permission.
Affiliate License-Licensor: Affiliate IP is included on the grantor/licensor
  side.
Affiliate License-Licensee: Licensee affiliates can receive/use/sublicense
  the rights.
Unlimited/All-You-Can-Eat License: Quantitative usage breadth.
Irrevocable/Perpetual License: Duration/revocability.
Non-Transferable License: Transferability.
These dimensions are independent:
  worldwide != unlimited
  royalty-free != perpetual
  fully-paid != unlimited
  perpetual != irrevocable
  exclusive != perpetual
  sublicensable != transferable
  affiliate reference != affiliate license

PAYMENTS
Revenue/Profit Sharing: Payment is a share/percentage/formula based on
  revenue/profit/proceeds/net sales.
Price Restrictions: Restricts pricing discretion.
Minimum Commitment: Requires a minimum purchase/use/spend/payment floor.
Volume Restriction: Crossing a usage/volume threshold triggers a
  fee/consent/restriction/consequence.
Liquidated Damages: Predetermined payment for breach/failure/termination.
Do not classify the mere existence of a price or payment as all of the above.

IP OWNERSHIP
IP Ownership Assignment: Created IP moves from creator/source party to
  counterparty.
Joint IP Ownership: Both parties own the same IP.
License Grant: Permission to use IP without title transfer.
Ownership and license rights must be analyzed separately.

LIABILITY
Cap on Liability: Maximum recovery/formula or contractual claim-time bar.
Uncapped Liability: Express unlimited liability or carve-out from a cap.
A contract can contain both a general cap and uncapped carve-outs.
Liquidated Damages: Predetermined damages amount/formula; it is not the same
  as a cap.

TERMINATION
Termination for Convenience: No-cause unilateral termination of the contract.
Notice Period to Terminate Renewal: Notice only to stop renewal/extension.
Post-Termination Services: Substantive obligations after the contract ends.
Do not confuse cure periods, non-renewal notice, and transition obligations."""


def category_definition(key: str) -> str:
    """The strict, element-based classifier for one category (TASK /
    QUALIFIES / DOES NOT QUALIFY / required operative elements)."""
    return CUAD_CLASSIFIERS[key]


# Kept for callers that want the composed text per category.
CUAD_DEFINITIONS: dict[str, str] = {key: category_definition(key) for key in CUAD_CLASSES}
