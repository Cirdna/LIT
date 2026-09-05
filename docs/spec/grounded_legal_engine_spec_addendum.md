# 📘 ADDENDUM: Building the Statute Knowledge Library

> **Provenance note (added when this file was created, not part of the original text).**
> Unlike its two companion specs, this addendum was never a file — it was pasted directly
> into the chat on 2026-09-06 at 04:02 (UTC+8). The body below is recovered verbatim from
> that message. Two things were dropped, neither part of the document: the `<user_query>`
> wrapper, and a trailing `@c:\Users\USER\Downloads\Telegram Desktop\grounded_legal_engine_spec_v2_1.md`
> attachment marker. One typo is preserved as written: an apostrophe appears where a `>`
> blockquote marker belongs, in the line beginning "chunk without exception".

*This extends `grounded_legal_engine_spec.md`. That file defines the target
architecture (Role A/B, the JSON chunk schema, the reasonableness gate).
This file defines how to actually produce the chunk data — the part that
was still an open question.*

---

## Why not just dump the whole Act in

Confirmed approach (do not deviate): **no raw HTML, no full-Act text
files fed into any pipeline.** A full statute is mostly irrelevant to
contract review — penalty provisions, definitions sections, procedural
rules — and dumping it in bloats tokens and gives a retrieval/keyword
system noise to sift through instead of a clean, small, curated set.

The target is **15–40 provision-level JSON chunks total**, covering
only the sections that actually matter to the six statutes already
scoped. That's a small, finite, known list — not something that needs
a scraper or an automated pipeline to maintain.

---

## The two-phase build process

**Phase 1 — Machine-assisted first pass (fast, but not trusted yet)**

Feed the *plain text* of each Act (a clean `.docx` or `.txt` export
from Singapore Statutes Online — not raw HTML, no scraper needed) to
an LLM with instructions to:

1. Scan the full Act.
2. Identify every section that is plausibly relevant to commercial
   contract review — specifically anything touching the fields and
   concepts already in scope (see the section list below).
3. For each candidate section, draft a JSON chunk in the schema below,
   copying the section text as closely as possible.
4. **Mark every single chunk `"verification_status": "unverified_draft"`.**
   The LLM does this step; it does not get to mark anything verified.

This phase turns "read a 50-page Act" into "review a short list of
candidate chunks" — which is the point. It does not turn the LLM's
transcription into something safe to ship.

**Phase 2 — Human verification (required, not optional)**

A person opens SSO, finds each flagged section, and checks the
`exact_wording` field **character-for-character** against the official
text. This step exists because the whole architecture is built on the
rule that quoted legal text must be verifiable — an LLM-transcribed
quote that's 95% right but paraphrased is exactly the fabricated/
distorted-citation failure the grounding mandate exists to prevent.

Only after this check does a chunk flip to `"verification_status":
"verified"`.

**Hard rule for the pipeline:** any code that renders a chunk's
`exact_wording` to a user must check `verification_status == "verified"`
first. An `unverified_draft` chunk can exist in the repo (useful for
continuing work) but must never be shown as if it were checked.

---

## Scope: statutes and sections already identified as relevant

Use this as the starting candidate list for Phase 1 — confirm/expand,
don't narrow below this without checking with the team first:

| Act | Sections likely relevant |
|---|---|
| Sale of Goods Act (Cap 393) | s.12 (title), s.13 (description), s.14 (satisfactory quality, fitness for purpose), s.15 (sale by sample) |
| Supply of Goods Act (Cap 394) | equivalent implied-terms sections for services/hire-purchase where SOGA doesn't apply |
| Unfair Contract Terms Act (Cap 396) | s.2(1) (death/personal injury — no reasonableness escape), s.2(2) (other loss, negligence — reasonableness test), s.3, s.6, s.7, s.11 (the reasonableness test itself), Second Schedule (reasonableness guidelines) |
| Contracts (Rights of Third Parties) Act (Cap 53B) | s.1–s.3 (when a third party may enforce a term, and how it's excluded) |
| Misrepresentation Act (Cap 390) | s.3 (exclusion of misrepresentation liability, importing UCTA s.11(1) only — not the Second Schedule) |
| Frustrated Contracts Act (Cap 115) | core loss-allocation provisions (loss lies where it falls, recovery of prepayments/expenses) |

This is roughly 15–20 sections. If Phase 1 surfaces more candidates,
that's fine — more candidates just means more to verify, not a problem.

---

## JSON chunk schema (as originally specified, plus verification status)

```json
{
  "id": "sg_ucta_s2_2",
  "category": "statute",
  "source": "Unfair Contract Terms Act (Cap 396)",
  "provision": "Section 2(2)",
  "exact_wording": "In the case of other loss or damage, a person cannot so exclude or restrict his liability for negligence except in so far as the term or notice satisfies the requirement of reasonableness.",
  "summary": "Liability for negligence (other than death or injury) can only be excluded if reasonable.",
  "role_type": "role_b_validator",
  "target_fields": ["liability_cap", "uncapped_liability"],
  "trigger_keywords": ["negligence", "exclude", "restrict", "liability"],
  "verification_status": "unverified_draft"
}
```

`verification_status` is new. Every other field is unchanged from the
original spec. Valid values: `"unverified_draft"` | `"verified"`.

---

## Instructions for Claude Code (Phase 1 execution)

> Paste the plain text of one Act at a time (not all six at once — keep
> each pass scoped to one statute so it's easier to review).
>
> Prompt:
>
> "Here is the full text of [Act name]. Identify every section that is
> plausibly relevant to reviewing commercial contracts — specifically
> anything touching: implied terms about goods/services quality,
> exclusion or limitation of liability, reasonableness tests for
> exclusion clauses, third-party enforcement rights, misrepresentation
> liability exclusions, or frustration/loss-allocation on contract
> failure. For each relevant section, output a JSON chunk in this exact
> schema: [paste schema above]. Set `role_type` to `role_a_default` if
> the section states a default legal position that applies unless the
> contract says otherwise, or `role_b_validator` if the section only
> matters once a specific type of clause is already present in the
> contract. Set `verification_status` to `unverified_draft` for every
' chunk without exception — do not mark anything verified. Copy
> `exact_wording` as closely as possible to the source text, but flag
> in a `note` field any section where you're not fully confident the
> wording is character-exact."
>
> Save the output as `statutes/{act_name}_draft.json` — one file per
> Act, all chunks starting as `unverified_draft`.

## Instructions for whoever does Phase 2 (human verification)

For each chunk in each `_draft.json` file:
1. Open the section on sso.agc.gov.sg.
2. Compare `exact_wording` character-for-character against the
   official text.
3. Fix any discrepancy directly in the JSON.
4. Flip `verification_status` to `"verified"`.
5. Once every chunk in a file is verified, rename it (drop `_draft`)
   or move it to a `statutes/verified/` folder — whichever the
   pipeline expects — so the loader can distinguish clean files from
   in-progress ones at a glance.

**Do not skip step 2.** This is the one manual step in the whole
pipeline that can't be automated without reintroducing the exact
fabrication risk the grounding mandate is built to prevent.
