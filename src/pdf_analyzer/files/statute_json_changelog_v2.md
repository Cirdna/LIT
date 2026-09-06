# Statute Knowledge Store — v2 Changelog

Driven by stress-testing the six statute JSON files against `armstrong_result.json`
(an Intellectual Property Agreement between Armstrong Flooring, Inc. and AFI
Licensing LLC, governed by Delaware law). Contract JSON was not modified — read
only, per instruction. All changes below are to the statute files.

## 1. New field on every chunk (36 → 40 chunks, all files): `jurisdiction_gate`

No chunk previously checked governing law at all. The sample contract is
expressly governed by Delaware law with a conflict-of-laws override — every
chunk would have fired regardless, which is the §1 "inapplicable-statute
citation" failure mode on a different axis (jurisdiction, not contract type).

Every chunk now carries:
```json
"jurisdiction_gate": {
  "condition": "Governing law is Singapore, or silent/unresolved. If expressly a
                 non-Singapore jurisdiction and Singapore law isn't also specified,
                 this chunk must not fire.",
  "on_fail": "NA",
  "na_reason": "governing_law_excluded"
}
```
`governing_law_excluded` is a new `na_reason` value, alongside the five from the
tier-mapping doc (`no_anchor`, `classification_failed`, `condition_not_met`,
`scope_excluded`, `dependency_unavailable`). Recommend checking this gate
**first**, before any contract-type or clause-level condition — it's cheaper to
evaluate and short-circuits everything else.

## 2. New field on every chunk: `extraction_schema_status`

The pipeline evidenced by the sample produces CUAD's 41 fixed categories. Cross-
checking all 18 distinct `target_fields` used across the six files against that
list:

- **2 clean matches**: `uncapped_liability` (exact), `liability_cap` → renamed to
  `cap_on_liability` to match CUAD's actual field name (was a pure naming
  mismatch, same concept).
- **3 partial proxies**: `crtpa_exclusion_status`, `third_party_rights` →
  CUAD's `third_party_beneficiary` detects the clause but not whether an express
  CRTPA-exclusion exists; `counterparty_type` → CUAD's `parties` gives raw names,
  not a consumer/business classification.
- **13 gaps with no CUAD category at all**: `title_warranty`,
  `quiet_possession`, `encumbrances`, `description_conformity`,
  `satisfactory_quality`, `fitness_for_purpose`, `sample_conformity`,
  `entire_agreement_clause`, `misrepresentation_liability`, `rescission_risk`,
  `force_majeure`, `frustration_default`, `performance_standard`.

Practical effect: every SOGA/Supply of Goods Act quality/title/fitness chunk,
every Frustrated Contracts Act chunk, and the Misrepresentation Act's core
entire-agreement trigger currently have **no field to attach to** in this
pipeline's actual output. They're not wrong, just unwired — either add
supplemental extraction categories or accept these modules stay dormant until
that happens. This is now visible on each chunk rather than a silent gap.

## 3. New contract type: `ip_agreement`

The sample contract fit none of the seven existing types and would have fallen
to `other_unclassified` (zero statutory overlay) despite having a live,
CRTPA-relevant indemnification/third-party-beneficiary clause (Section 10.1,
extending indemnity to each party's Affiliates, employees, directors, officers,
agents and successors).

Added `ip_agreement` to `applicable_contract_types` on:
- All 3 CRTPA role_b/role_a chunks with third-party relevance
- All 3 Misrepresentation Act chunks
- All 4 Frustrated Contracts Act chunks
- **`ucta_first_schedule_scope_exclusions` only**, among UCTA's chunks

The substantive UCTA ss.2–4 chunks (`s2_1`, `s2_2`, `s3`, the two split `s6_*`
sale-of-goods chunks, `s7_3a`, `s7_2_3`) deliberately do **not** get
`ip_agreement` added — First Schedule para 1(c) excludes IP-related contracts
from ss.2–4 outright, so those modules should never be eligible to run against
this type. `ip_agreement` was added to the First Schedule chunk specifically so
the engine can produce an affirmative, citable "UCTA ss.2–4 do not apply — First
Schedule para 1(c)" statement instead of silently never evaluating it.

*Not yet wired into `grounded_legal_engine_spec_v2_2.md` §2's type list — that
edit wasn't in scope for this pass since you asked for statute-JSON-only
changes. Flagging so it doesn't get missed.*

## 4. New contract type: `goods_hire` (split out of `lease`)

`suppgoods_s7_hire_title`, `suppgoods_s9_2_satisfactory_quality_hire`,
`suppgoods_s9_4_fitness_hire` covered goods/equipment hire but were mapped to
`lease` — the files' own prior notes already flagged this as an imprecise
best-fit against real-property leases. Reclassified all three to a dedicated
`goods_hire` type. Unrelated to the Armstrong contract itself; fixed now while
already in the files with full autonomy over them.

## 5. Split chunks: UCTA s.6(1) and s.6(2)/(3)

Both previously covered a Sale of Goods Act limb and a Hire Purchase Act 1969
limb in one chunk. The Hire Purchase Act text isn't in this knowledge store, so
the whole chunk was previously unfireable — including the sale-of-goods limb,
which *is* verifiable. Split each into two chunks:

| Old ID | New IDs |
|---|---|
| `ucta_s6_1_title_absolute_bar` | `ucta_s6_1a_title_absolute_bar_sale_of_goods` (fireable) / `ucta_s6_1b_title_absolute_bar_hire_purchase` (`engine_status: dependency_unavailable`) |
| `ucta_s6_2_3_quality_fitness` | `ucta_s6_2_3a_quality_fitness_sale_of_goods` (fireable) / `ucta_s6_2_3b_quality_fitness_hire_purchase` (`engine_status: dependency_unavailable`) |

Net effect: UCTA file goes from 12 to 14 chunks. The sale-of-goods limbs now
fire normally instead of being needlessly suppressed by an unrelated gap in the
hire-purchase limb.

## Not changed

- Contract JSON (`armstrong_result.json`) — read-only per instruction.
- The four main output tiers (`Quoted` / `Inferred` / `Evaluation Required` /
  `NA`) and the `evaluation_type` / `inference_source` sub-flags from the prior
  pass — untouched, as requested.
- `employment`, `nda`, `distribution`, `other_commercial` contract types —
  untouched.
