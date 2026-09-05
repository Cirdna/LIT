# AITHENA - Master Summary

**Read this first.** It replaces reading the five other status reports in this repo.

Where things live now: the detailed session reports are archived in
[`docs/session-log/`](docs/session-log/) (with an index explaining what each one uniquely
holds), the design specs are in [`docs/spec/`](docs/spec/), and
[`PHASE2_VERIFICATION.md`](PHASE2_VERIFICATION.md) at the root is the live checklist for the
34 unverified statute chunks.

| | |
|---|---|
| Branch | `testing-branch` @ `62f3c6b` |
| Session work | **entirely uncommitted** in the working tree |
| `origin/main` | `c50cab9`, one commit ahead of us, **not merged** (see §6) |
| Python tests | **165 passing**, 0 failing |
| Backend typecheck | clean |
| Frontend typecheck | clean |
| Git operations this session | none - no fetch, no pull, no merge, no push, no commit |
| Design specs | `docs/spec/` - recovered this session; previously not in the repo at all |

> **Run tests with the venv, not the system Python:** `.\.venv\Scripts\python.exe -m pytest -q`.
> The system interpreter lacks `pytesseract` and silently drops 37 tests (you get 128
> passing and 5 collection errors, which looks like breakage and is not).

---

## 1. Timeline: what was built, in order

Each item below is scored **PASS** (traced end to end from real input to real output),
**PARTIAL** (works, with a named substitution or gap), or **NOT DONE**. Nothing is
rounded up.

### Fix 1 - real extraction into the webapp - **PARTIAL**

Before this, the webapp's only worker was `stub-worker.ts`, which produced field values
by matching on filename. A user uploading a document got a canned profile. Now
`webapp/scripts/real-worker.ts` (new, 470 lines) shells out to `python -m
pdf_analyzer.cli analyze`, reads the analysis JSON back, and writes real
`extracted_fields` rows with real page/bbox anchors and real confidence tiers. Four of
the twelve documents currently in the database went through this path
(`pipeline_version = pdf_analyzer.cli@0.1.0`).

Why PARTIAL and not PASS: the end-to-end trace was run with **Stage 2b's hosted VLM reply
scripted**, because this machine has no `OPENROUTER_API_KEY`. Every other stage ran for
real - Stage 1 ingest and render, Stage 2a native text extraction, Stage 3 fuzzy spatial
reconciliation with the 85% threshold, Stage 4 schema assembly, join-key population, the
HTTP upload, and all database writes. The hosted call itself is evidenced separately in
`HANDOFF.md` A2.5, not by this session.

Files: `webapp/scripts/real-worker.ts`, `webapp/scripts/lib/`, `src/pdf_analyzer/cli.py`,
`webapp/prisma/schema.prisma`, `webapp/src/routes/documents.ts`.

### Fix 2 - conflict library connected - **PASS**

`src/pdf_analyzer/conflict.py` existed and was well tested but was reachable only from
its own unit tests: the pipeline never populated the join keys it compares, so every
conflict pass was a no-op on real documents. This session added
`_counterparties_from_findings` and `_structured_clauses_from_findings` to
`pipeline.py`, which build counterparty join keys by **exact name only** and convert
restrictive clauses into the comparable form the passes need.

The result is a genuinely detected conflict in the database: an MFN clause held by
"Meridian Retail Pte Ltd" in *Acme Master Supply Agreement.pdf* against pricing terms
agreed with the same counterparty in *Acme Statement of Work 4.pdf*
(`party.mfn_trigger`, deterministic, Clause 5.1 p1 vs Clause 2.3 p1). That is a real
pair found by a real rule over real extracted text.

Deliberate limitation: matching is exact-name only. "Acme Industries Pte Ltd" and "Acme
Industrial Ltd" never group, which is the required behaviour for a near-miss pair -
merging them would invent a conflict. Consequence: two spellings of the same company are
missed, and that is a knowingly accepted false-negative.

Files: `src/pdf_analyzer/pipeline.py`, `src/pdf_analyzer/schema.py`,
`webapp/scripts/real-worker.ts`, `tests/test_conflict_wiring.py`.

### Stage 1 - UI honesty pass - **PASS**

Four user-visible changes, all confirmed against the running app rather than against
memory (the statute work had since touched the same files): confidence labels now read
in plain English instead of internal tier names; the document list has a working filter;
dates render in one consistent human format everywhere; and the calendar view groups by
action window. Nothing here is new capability - it is making the existing capability
legible.

Files: `webapp/frontend/src/lib/confidence.tsx`, `lib/format.ts`,
`components/FieldValue.tsx`, `routes/Calendar.tsx`, `routes/DocumentDetail.tsx`,
`routes/HandoffBrief.tsx`, `tailwind.config.js`.

### Stage 2 - six-statute Role A/B engine - **PASS**

A new `src/pdf_analyzer/statutes/` package implementing two roles. Role A supplies the
statutory default position *before* extraction runs, so the output shows what the law
provides and which parts the contract displaced - computing it afterwards would invert
that and make the law look like a fallback for fields the extractor missed. Role B reviews
what the contract actually says and raises review flags.

Six Acts are covered by hand-written modules: Sale of Goods, Supply of Goods, Unfair
Contract Terms, Misrepresentation, Contracts (Rights of Third Parties), and Frustrated
Contracts, plus a shared reasonableness gate. Every `effect` string is an explicit
paraphrase and `verbatim_text` is unconditionally `None` - at this stage there was no
verified source of statutory wording, and a paraphrase presented as a quotation is a
fabricated citation.

Files: `src/pdf_analyzer/statutes/*.py` (9 modules), `tests/test_statute_*.py`.

### Statute UI surfacing - **PASS**

Statutory defaults and flags render in their own panel, visually separated from extracted
fields, because a statutory default has no citation in the contract. If it shared a
component with extraction it would inevitably pick up an extraction's confidence badge
and read as something the document says.

Files: `webapp/frontend/src/components/StatutePanel.tsx`, `StatuteFlagNote.tsx`,
`webapp/prisma/schema.prisma` (separate `statutory_defaults` table, deliberately not in
`extracted_fields`).

### Feature 1 - portfolio chatbot - **PARTIAL**

Natural-language questions over the portfolio. An LLM converts the question into a
*structured filter* over existing `extracted_fields` rows - it never reads or summarises
contract text, so it cannot hallucinate a term. Vague questions trigger a clarification
loop instead of a guess. If the model invents a field key the query **fails closed**
(zero matches, `noSuchField: true`) rather than matching everything, which was a real bug
found and fixed during the build.

Why PARTIAL: verified end to end only against a **local fake OpenRouter server**, because
the configured `OPENROUTER_API_KEY` was the placeholder `"test-key-not-real"`. The
integration logic and data flow are proven; the live model's actual behaviour is not.

Files: `webapp/src/routes/chat.ts`, `webapp/src/lib/llm.ts`,
`webapp/frontend/src/routes/Ask.tsx`.

### Feature 2 - portfolio benchmarking - **PASS**

A field's value on one document is compared against the mean and median across the
portfolio, with a traffic-light indicator. Fully deterministic, no LLM, computed at
request time from existing rows. Because `value_normalized` is `NULL` on every real row,
durations and dates are parsed out of the verbatim text by
`webapp/src/lib/quantities.ts`.

Files: `webapp/src/routes/benchmark.ts`, `webapp/src/lib/quantities.ts`,
`webapp/frontend/src/components/BenchmarkLine.tsx`.

### Feature 3 - invoice-to-contract matching - **PARTIAL**

Extracts parties and line items from an invoice, matches them to a contract by
exact-name resolution (the same rule as Fix 2, ported to Node in
`webapp/src/lib/parties.ts`), then validates the invoice date against the contract's
effective and expiration dates. The UI keeps model-read invoice data visually separate
from contract-grounded citations, so the reader can see which half is trustworthy.

Why PARTIAL: same blocker as Feature 1 - the LLM extraction step was verified against the
fake OpenRouter server only.

Files: `webapp/src/routes/invoices.ts`, `webapp/src/lib/parties.ts`,
`webapp/frontend/src/components/InvoiceMatch.tsx`.

### Statute knowledge library, Phase 1 - **PASS** (as a draft; see the caveat)

34 provision-level JSON chunks across the same six Acts, transcribed from the official
Singapore Statutes Online pages, each carrying its source URL, retrieval date and Revised
Edition. **All 34 are `unverified_draft` and none can be quoted.**
`StatuteChunk.quotable_wording()` raises unless a human has marked the chunk verified, and
it deliberately does not fall back to the summary - a silent fallback would put unverified
text in front of a user under a different label. The in-memory field is named
`draft_wording` so that any code reaching past the gate is visibly a choice.

The loader rejects `transcription: "model_recall"` outright and requires an
`sso.agc.gov.sg` URL. Seven chunks had to be reassembled from separate HTML table rows and
each says `STITCHED` in its note.

This pass also found three substantive problems, which are open items, not fixed code:
a systematic off-by-one in `supply_of_goods.py`'s citations, the Supply of Goods Act being
wrongly scoped to services and hire-purchase, and UCTA's Second Schedule being confined by
s.11(2) to sections 6 and 7. See §4 and `PHASE2_VERIFICATION.md`.

PASS means "Phase 1 delivered what Phase 1 was scoped to deliver". It does **not** mean
the wording is correct - that is exactly what Phase 2 is for, and Phase 2 has not started.

Files: `src/pdf_analyzer/statutes/library/` (schema, loader, 6 chunk files),
`tests/test_statute_library.py`, `scripts/statute_coverage.py`,
`PHASE2_VERIFICATION.md`.

### Final punch list (5 items) - **NOT DONE**

The last request covered five items: automatic handoff briefs on real conflicts,
asset-based conflict detection, demo-vs-real conflict labelling, live chatbot
verification, and calendar dates from real extraction. **That pass was interrupted during
investigation and produced no code changes.** All five remain unimplemented.

The investigation did produce concrete, verified findings, which are worth keeping because
they turn each item into a short job rather than a fresh hunt:

1. **Handoff briefs never fire on real conflicts.** `real-worker.ts` writes conflict rows
   but never calls `buildBriefFromConflict` (confirmed: no reference to it in the file).
   The only automatic brief comes from `stub-worker.ts:602`, gated on the filenames
   "Acme Distribution" and "Borden Distribution". The database confirms it: one brief
   exists, `trigger: conflict:exclusivity_breach`, from the demo path. The real
   `mfn_trigger` conflict has no brief.
   *Second, deeper problem - see the vocabulary gap below:* real conflict rows are written
   with `fieldIds: []`, and both `buildBriefFromConflict` and `Conflicts.tsx:69` read their
   content through those IDs. So a brief generated from a real conflict has **no established
   facts and a generic question**, and the Conflicts table renders **no clause panels at
   all** for real conflicts. One root cause, two visible symptoms.
2. **Asset-based detection cannot fire.** `pipeline.py:259` sets `scope=[]` unconditionally
   and nothing populates `ContractAnalysis.assets`, so `asset_based_pass` groups nothing.
   Making it fire needs a scope key derived from the exclusivity clause text (a content
   hash of the normalised text works without any cross-document coordination, since two
   documents independently produce the same key when the text matches).
   *Blocker found:* only one real-pipeline document currently has an `exclusivity` field
   (*Acme Master Distribution Agreement.pdf*, "The Distributor is granted the exclusive
   right to distribute in Singapore."). A second real document sharing that clause has to
   be processed before the pass can fire on a real pair - and processing a new document
   needs a working `OPENROUTER_API_KEY` for Stage 2b.
3. **No demo-vs-real labelling.** No `detectionSource` column exists. The two conflicts sit
   in the same table with nothing distinguishing them: the real one's provenance is buried
   in prose at the end of its summary string, and the demo one has no marker at all.
4. **Live chatbot test still blocked** on a rotated key and a confirmed model slug.
5. **Calendar events are entirely stub-derived.** All 9 rows have empty `source_field_ids`.
   Worse, `real-worker.ts` *deletes* a document's calendar events and never writes any
   back, so real-pipeline documents end up with **no calendar entries at all** - the
   feature silently regresses for exactly the documents that were processed properly.

#### The vocabulary gap behind the empty `fieldIds` (investigated last; nothing built)

Populating `fieldIds` looked like a small job and is not. The reason real conflicts carry an
empty array is that **there is nothing in the database they could point at**:

- The webapp vocabulary is exactly 22 field keys. `most_favored_nation` and
  `price_restrictions` - the two categories the live MFN conflict pairs - are **not among
  them**.
- `CUAD_FIELD_MAP` in `webapp/scripts/lib/cuad-map.ts` maps only 9 field keys from CUAD
  categories, and neither conflict category is mapped.
- `select count(*) from extracted_fields where field_key in ('most_favored_nation',
  'price_restrictions')` returns **0**.

So `fieldIds: []` is the honest output of a writer that found nothing to reference, not a
forgotten assignment. Deriving the field key from `clause_id` (which has the form
`"{category_key}#p{page}.{index}"`, so `most_favored_nation#p1.1` does yield a key by
splitting on `#`) resolves nothing, because no row with that key exists. It would work for a
hypothetical `exclusivity` or `liability_cap` conflict and not for the only real conflict
the system has actually found.

**Two ways forward, neither started:**

1. *Read the clause evidence directly.* `ConflictEvidence` already carries `contract_id`,
   `clause_id`, `clause`, `page`, `excerpt` and `bbox_1000`, and the conflict carries
   `lowest_confidence_tier` - which is everything an established item needs. This needs a
   JSON `evidence` column on `Conflict` (the model has nowhere to put it today), a signature
   change to `buildBriefFromConflict`, and a display change in `Conflicts.tsx`. Recommended,
   because it makes the brief independent of whether a category happens to be in the
   vocabulary.
2. *Extend the vocabulary* by adding the two categories to `cuad-map.ts`. Smaller-looking,
   but `cuad-map.ts` is on the protected list, and widening the 22-key vocabulary would ripple
   into the chatbot's generated system prompt, the benchmarking field table and the invoice
   matcher, all of which were built against those 22 keys.

Recorded preference for when this resumes: **full scope** - schema, brief wiring, automatic
brief generation on real conflicts, and the Conflicts table panels - once the approach in (1)
vs (2) is settled.

---

## 2. What is real vs. what is still stub or demo

Current state, from direct database inspection - not carried over from an earlier report.

### Real

- **Extraction for 4 of 12 documents** (`pdf_analyzer.cli@0.1.0`): *Acme Master
  Distribution Agreement*, *Acme Master Supply Agreement*, and two copies of *Acme
  Statement of Work 4*. Real page anchors, real confidence tiers, real clause labels.
- **One cross-contract conflict** (`mfn_trigger`), found by a deterministic rule over real
  extracted text.
- **Statutory defaults and flags**, computed by the real Role A/B engine during real
  pipeline runs.
- **Benchmarking**, computed at request time from real rows.
- **The confidence and grounding model** end to end: tiers, absence reasons, and the Stage
  3 groundedness check that refuses to treat an unlocatable quote as evidence.
- **The statute chunk library**, in the sense that it loads, validates and gates
  correctly - but nothing reads from it yet and nothing in it may be quoted.

### Still stub or demo

- **Extraction for 8 of 12 documents** (`stub-worker@0.1.0`): filename-matched canned
  profiles. This is the visible demo corpus - the NDA, the lease, the employment
  agreement, the MSA, the invoice, and both Distribution Agreements.
- **The `exclusivity_breach` conflict**: hardcoded, gated on filenames, with a hand-written
  summary naming "Clause 4.1" and "Clause 2.3".
- **The only handoff brief in the database**: generated from that demo conflict.
- **All 9 calendar events**: from `calendarPlan()` in the stub worker, every one with empty
  `source_field_ids`.
- **Every LLM-dependent feature** (chatbot, invoice matching): logic verified against a
  local fake OpenRouter server, never against the live model.
- **Stage 2b's hosted VLM call in this session's traces**: scripted reply, no live key.
- **`value_normalized`**: `NULL` on every row, real or stub. Consumers parse verbatim text
  instead.
- **Asset-based conflict detection**: inert by construction.
- **Two React frontends** still exist in the repo (a known, logged duplication - not fixed).

---

## 3. Known open items

One line each. Detail lives in `PHASE2_VERIFICATION.md` or §1 above.

**Highest risk**
- `origin/main` contains a competing Python worker that overlaps Fix 1; merging is unresolved (§6).

**Statute correctness - needs legal sign-off**
- `supply_of_goods.py` transfer-set citations are off by one throughout (s.3/4/5/6 should be s.2/3/4/5).
- The Supply of Goods Act is wrongly scoped to services and hire-purchase; it covers neither in Singapore. **The error originates in `docs/spec/grounded_legal_engine_spec_v2_1.md` §4**, so the spec needs amending, not just the code - the chunk library currently contradicts the spec deliberately.
- UCTA s.11(2) confines the Second Schedule to ss.6-7, so citing it for a s.2(2) negligence exclusion overstates the Act.
- `supply_of_goods.py` bundles quality and fitness under one citation; they are separate subsections with different preconditions.

**Statute library**
- Phase 2 human verification has not started: 0 of 34 chunks verified, so nothing is quotable.
- The non-reliance chunk needs a real Singapore case citation or deletion; `supporting_authority` currently reads `UNRESOLVED`.
- UCTA's Second Schedule text is missing entirely and needs a separate fetch.
- Nothing reads from the library yet; wiring should happen per Act as each Act's chunks pass verification.
- Citation format (2020 RevEd titles vs Cap numbers) needs sign-off.

**Detection and data**
- Entity resolution is exact-name only; two spellings of one company will not group.
- Asset-based conflict detection is inert (`scope=[]`); scope matching, when built, will be exact-string only and will not handle "US" vs "North America".
- Real conflicts carry `fieldIds: []`, which empties both the handoff brief's established facts and the Conflicts table's clause panels - because `most_favored_nation` and `price_restrictions` are not in the webapp's 22-key vocabulary, so there is no row to reference. Needs an approach decision (see §1).
- No contract-type classification exists, so the statute layer cannot gate defaults by contract type in the live pipeline.
- `value_normalized` is never populated.

**Environment and verification**
- Live chatbot and invoice tests blocked on a rotated `OPENROUTER_API_KEY` and a team-confirmed model slug; the current default `google/gemini-3.8-flash` is a **fallback, not a decision**.
- Processing any new document is blocked by the same missing key (Stage 2b).
- Two React frontends coexist; one should be retired.
- All session work is uncommitted, so a bad `git checkout` would destroy it.

---

## 4. Test count and build status

```
Python      165 passed, 0 failed      .\.venv\Scripts\python.exe -m pytest -q
Backend     clean                     npm run typecheck            (webapp/)
Frontend    clean                     npx tsc --noEmit             (webapp/frontend/)
```

Test files added this session: `test_conflict_wiring.py`, `test_statute_library.py` (28
tests), and six per-Act statute suites (`test_statute_ucta.py`, `_sale_of_goods`,
`_supply_of_goods`, `_misrepresentation`, `_crtpa`, `_frustration`), plus
`test_statute_wiring.py`.

There is **no automated test suite for the webapp** - `package.json` has `typecheck` but no
test runner. Everything claimed about the webapp was verified by running it against the
live database and reading the rows back, not by tests. That is a real gap in the safety
net.

---

## 5. The `origin/main` situation

**This is the highest-risk open item. Nothing has been merged, fetched, pulled or pushed.**

```
testing-branch  62f3c6b   <- us; all session work uncommitted on top
origin/main     c50cab9   <- 1 commit ahead, already in the local ref, never merged
```

`git rev-list --left-right --count HEAD...origin/main` returns `0  1`: our branch has no
commits of its own, so **every line of this session's work exists only as uncommitted
working-tree changes.**

That teammate commit adds 1,651 lines, including an entire parallel Python worker:

```
webapp/worker/__main__.py, db.py, mapping.py, process.py, geometry.py, storage.py,
requirements.txt, README.md        (~1,300 lines - a second real worker)
webapp/scripts/stub-worker.ts      (+137/-  ) 
webapp/src/lib/domain.ts           (+64     )
webapp/frontend/src/lib/domain.ts  (+70/-   )
webapp/docs/INTEGRATION.md, webapp/README.md, pyproject.toml, src/routes/documents.ts
```

**The collision.** `webapp/worker/` solves the same problem as our `real-worker.ts` - get
real extraction into the webapp - by a different route: Python writing to Postgres
directly, versus our Node-owns-the-DB-and-shells-out-to-the-CLI seam. Both cannot survive.
Additionally, both sides modified `stub-worker.ts` and `documents.ts`, and `domain.ts`
changes on main may move the field vocabulary that Features 1-3 were built against.

**Two decisions are needed before anyone merges, and they are for the team, not for a tool
to pick:**

1. Which worker architecture wins - theirs (Python owns the DB) or ours (Node owns the DB,
   Python owns the document, one JSON file between them)?
2. Does `domain.ts` on main change the 22-key field vocabulary? If it does, the chatbot's
   generated system prompt, the benchmarking field table, and the invoice matcher all need
   revisiting.

**Before any merge attempt, commit or stash this session's work.** It is currently
unprotected: a checkout or reset would lose all of it, including everything described in
this document.
