# Phase 2: Human Verification Worklist

Phase 1 produced **34 provision-level chunks** across the six scoped Acts. **Zero are
verified.** Nothing in this library can be quoted to a user until a human checks it.

```
  0/6   Sale of Goods Act 1979 (2020 Rev Ed)
  0/9   Supply of Goods Act 1982 (2020 Rev Ed)
  0/9   Unfair Contract Terms Act 1977 (2020 Rev Ed)
  0/4   Contracts (Rights of Third Parties) Act 2001 (2020 Rev Ed)
  0/2   Misrepresentation Act 1967 (2020 Rev Ed)
  0/4   Frustrated Contracts Act 1959 (2020 Rev Ed)
```

Run `python scripts/statute_coverage.py` at any time for the current state.

---

## What Phase 1 did and did not do

**Did:** fetched each Act from Singapore Statutes Online and transcribed the relevant
provisions from the retrieved page into JSON chunks, with the source URL, retrieval date
and Revised Edition recorded per chunk.

**Did not:** verify anything. Every chunk is `unverified_draft`. The wording was
transcribed from the source rather than recalled from memory, which is a meaningfully
lower risk than the alternative — but "transcribed by a model" is not "checked by a
lawyer", and the difference is the entire point of this phase.

The provenance field records this distinction explicitly. `transcription` must be
`machine_assisted_from_source` or `human_transcribed`; the loader **rejects**
`model_recall`, and a test covers that. Wording recalled from model memory must never
enter this library.

---

## The gate

`StatuteChunk.quotable_wording()` is the only accessor that returns wording for display,
and it raises `UnverifiedQuotationError` unless `verification_status == "verified"`.

It deliberately does **not** fall back to the summary. A silent fallback would let
unverified text reach a user under a different label, which is the same defect wearing a
disguise. Callers who want a paraphrase ask for `.summary` explicitly.

The in-memory field is named `draft_wording`, not `exact_wording`, so that any code
reaching past the gate is visibly making a choice and shows up in review. The on-disk key
stays `exact_wording` per the schema.

Tests that pin this: `test_unverified_wording_cannot_be_quoted`,
`test_gate_does_not_fall_back_to_the_summary`, `test_no_shipped_chunk_can_be_quoted_yet`.

---

## How to verify one chunk

1. Open the URL in the chunk's `provenance.retrieved_from`.
2. **Prefer the PDF download over the HTML view.** SSO renders provisions as HTML tables
   and sub-paragraphs can appear out of order; the PDF is authoritative for layout.
3. Compare `exact_wording` character-for-character. Watch specifically for:
   - curly vs straight apostrophes (`’` vs `'`) — the drafts use curly, matching SSO
   - em/en dashes vs hyphens around paragraph lead-ins
   - the exact punctuation joining `(a)`/`(b)` paragraphs
   - `shall` vs `must` (2020 RevEd modernised some, not all)
4. Fix any discrepancy in the JSON.
5. Set `"verification_status": "verified"`, and add `"verified_as_at": "YYYY-MM-DD"` and
   `"verified_by": "<your name or process>"`. The schema requires both — a verified chunk
   without a stamp fails validation.
6. Update `test_every_shipped_chunk_is_still_an_unverified_draft` in the same commit as
   your evidence. That test currently asserts nothing is verified; it is a tripwire
   against someone flipping a status without doing the work, so it should only change
   alongside a record of the check.

Verify in this order: **stitched chunks first**, then the provisions the product actually
cites today. Verifying a chunk nothing reads is not progress.

---

## Priority 1 — the 7 stitched chunks

These were reassembled from separate table rows on the SSO page. The content is confident;
the punctuation and the paragraph ordering are inferred. **These are where wording is most
likely wrong.**

| Chunk | Provision | Why it needs care |
|---|---|---|
| `sg_ucta_s11_4` | UCTA s.11(4) | Lead-in + (a) + (b). **Verify first** — this is the most directly useful provision for reviewing a monetary liability cap (resources available, insurance). |
| `sg_soga_s14_3` | SOGA s.14(3) | Four rows reassembled into one long sentence; the credit-broker limb makes the ordering non-obvious. |
| `sg_soga_s15_2` | SOGA s.15(2) | Two paragraphs in Singapore, three in the older UK formulation. Confirm there is no "reasonable opportunity of comparing" limb here. |
| `sg_sga1982_s5_2` | SGA 1982 s.5(2) | Three paragraphs — this one **does** have the comparison limb, unlike SOGA s.15(2). Easy to conflate. |
| `sg_misrep_s3` | Misrep s.3 | The lead-in appeared *after* (a), (b) and the closing text in the page's table order. Highest reassembly risk in the set. |
| `sg_crtpa_s2_1` | CRTPA s.2(1) | Lead-in plus (a)/(b) out of order. Also note the 2020 gender-neutral redraft ("the third party's own right") — a quotation copied from a pre-2020 source will not match. |
| `sg_fca_s3_5` | FCA s.3(5) | Lead-in plus (a)/(b)/(c), including a cross-reference to Sale of Goods Act s.7. |

---

## Priority 2 — three substantive findings that need a legal decision

These are not transcription issues. They are places where the authentic text contradicts
what the codebase or the brief currently assumes, and someone has to decide what to do.

### 1. `statutes/supply_of_goods.py` cites the wrong sections (live defect)

The transfer set is **off by one throughout**:

| Field | Module cites | Actual SGA 1982 |
|---|---|---|
| `transfer_title` | s.3 | **s.2(1)** |
| `transfer_correspondence_with_description` | s.4 | **s.3(2)** |
| `transfer_quality_and_fitness` | s.5 | **s.4(2)** (quality) / **s.4(5)** (fitness) |
| `transfer_sample` | s.6 | **s.5(2)** |

s.6 is in fact the *definition* of "contract for the hire of goods", not the sample
provision. The hire set (s.7–s.10) is correct. The module's docstring said these "should be
checked against the current Revised Edition before being relied on" — they now have been,
and four were wrong.

Quality and fitness also need splitting: the module bundles them under one citation, but
they are separate subsections with different preconditions (fitness requires a purpose to
have been made known, and has its own reliance carve-out in s.4(6)).

`test_supply_of_goods_transfer_citations_match_the_act` pins the correct mapping so this
cannot silently drift back.

### 2. The Supply of Goods Act does not cover services or hire-purchase

The brief's scope table assigns this Act to `[services, hire_purchase]`. Both are wrong for
Singapore:

- **Services:** Singapore never adopted the UK's Supply of Goods *and Services* Act
  provisions. There is no statutory implied term of reasonable care and skill for a pure
  services contract here — that is common law. s.1(3) does say a contract can be a transfer
  contract whether or not services are also provided under it, which is how work-and-
  materials falls in, but that is not the same as the Act covering services.
- **Hire-purchase:** s.1(2)(b) makes a hire-purchase agreement an *excepted contract*, and
  s.6(1) excludes it from "contract for the hire of goods". Hire-purchase is the
  Hire-Purchase Act 1969.

No chunk in `supply_of_goods_1982_draft.json` is eligible for either type, and
`test_supply_of_goods_chunks_never_fire_on_services_or_hire_purchase` enforces it. **Someone
should confirm no other module inherits the brief's assumption** — firing goods-quality
defaults on a services agreement is the SOGA-on-an-NDA bug one layer deeper.

### 3. UCTA's Second Schedule is confined to ss.6 and 7

s.11(2) directs the Second Schedule guidelines to "the purposes of section 6 or 7" — the
goods provisions. On the face of the Act they are **not** the test for a s.2(2) negligence
exclusion. Courts commonly treat them as helpful by analogy, but a flag that recites Second
Schedule factors against a s.2(2) trigger as though they were the statutory test overstates
the Act.

Decision needed: either restrict the reasonableness gate's Second Schedule factors to s.6/7
triggers, or keep them everywhere but label them "applied by analogy" in the output. The
second is probably right; it should be explicit either way.

Separately confirmed from source: **Misrepresentation Act s.3 imports only UCTA s.11(1)**,
not the Second Schedule. The brief was right about this.

---

## Priority 3 — known gaps, deliberately left empty

Nothing was invented to fill these. Each is a real hole to close.

| Gap | What is missing | Why it was left |
|---|---|---|
| **UCTA Second Schedule** | The reasonableness guidelines themselves | Not present in the retrieved page body. Needs a separate fetch. No wording was drafted from memory. |
| **`sg_misrep_s3_nonreliance` authority** | The Singapore case establishing that non-reliance / entire-agreement clauses fall within s.3 | The bare section does not say this; it is judicial gloss. `supporting_authority` reads `UNRESOLVED` and the chunk's own applicability conditions forbid it firing while that is true. **A plausible-looking case name was not guessed** — that is exactly the fabricated-citation failure the grounding mandate treats as fatal. Phase 2 must supply the authority or delete the chunk. |
| **UCTA s.6(1)** | Title obligations cannot be excluded against anyone | Noted in `sg_soga_s12_1`'s note but not drafted as its own chunk. |
| **UCTA s.12** | Definition of "dealing as consumer" | Needed to make the s.6(3)/s.7(3) consumer distinction operable. |
| **SOGA s.14(2B)** | The list of quality aspects (fitness for common purposes, appearance and finish, minor defects, safety, durability) | Useful for explaining *why* quality is unsatisfactory. |
| **CRTPA s.2(5), s.3(1)** | Remedies available to a third party; consent to variation | `statutes/crtpa.py` already cites both and its citations check out; chunks not yet drafted. |
| **FCA s.2(4)** | Valuable benefit / just sum | Referenced by `statutes/frustration.py` prose but not chunked. |

---

## Citation format decision (needs sign-off)

Phase 1 uses **2020 Revised Edition titles** as each chunk's `source`, with the superseded
Cap number in `legacy_citation` for cross-reference:

```
source:           "Unfair Contract Terms Act 1977 (2020 Rev Ed)"
legacy_citation:  "Cap 396 (1994 Rev Ed)"
```

The brief's scope table used Cap numbers (Cap 393, 394, 396, 53B, 390, 115). Those are the
1994/1999/2002 editions and citing them as current is itself a mild citation error.
`test_no_chunk_cites_a_cap_number_as_its_current_source` enforces the new format.

The existing Python modules already use RevEd titles in their `STATUTE` constants, so they
agree with the library. Only the brief's table needs updating.

---

## Not yet wired

This library **loads, validates and gates, but nothing reads from it yet.** The existing
`statutes/*.py` modules still supply their own hand-written paraphrases, and
`_catalogue.py` still sets `verbatim_text=None` unconditionally.

That is the correct sequencing — wiring verified wording into output before any wording is
verified would put unverified quotations in front of users, which the gate exists to
prevent. The wiring step should happen **per Act, as that Act's chunks reach `verified`**,
not as one switchover.
