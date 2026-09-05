# AITHENA — full-repo gap report

Audited against the five AITHENA must-haves plus the Grounding, Calibration and
Escalation requirements. Same standard as the Phase 1 audit: something counts as
implemented only if there is an unbroken chain of calls from real user input to
real rendered output, and every claim below cites the line that executes it.

**Scope.** The entire repository, including code no one in this session wrote:
Hannah's Python engine, andric's webapp, and — importantly — teammate commit
`c50cab9` on `origin/main`, which is **one commit ahead of our branch and not in
our working tree**. Claims made in chat were not treated as evidence.

**Two conventions.** "Local" means `testing-branch` + this session's uncommitted
work. "On main" means `c50cab9`, verified by checking that commit out separately.
Where the two differ the report says so, because a gap that is closed on an
unmerged branch is still a gap today.

**Verification method.** Two real PDFs were generated, uploaded through the real
`POST /api/documents` endpoint, processed by `real-worker.ts` calling the real
Python CLI, and the result read back through the real HTTP API and screenshotted
in the running UI. The only substitution was the vision model itself (no
`OPENROUTER_API_KEY` in this environment); it was replaced by a backend that
returns verbatim spans from the page text, so Stage 3's grounding was genuinely
computed rather than asserted. Stages 1, 2a, 3, 4, the statute layer, the schema
and the conflict library all ran as production code.

---

## 1. Batch ingestion, mixed format + scanned documents — ⚠️ PARTIAL

**Works.** Genuine multi-file batch upload: the route iterates every multipart
part and does not abort the batch when one file fails
(`webapp/src/routes/documents.ts:44-48`, limit of 25 files at
`webapp/src/config.ts:22`). Type detection is by magic bytes, not extension
(`webapp/src/lib/magic.ts:39-52`). The Python side converts PDF, DOCX/DOC/RTF/ODT
and HTML to a standardised PDF and renders every page
(`src/pdf_analyzer/stage1_ingest.py:53-60`, `77-108`, `137-167`).

**Real OCR, and it is reachable.** Stage 2a prefers the PDF's own text layer and
falls back to Tesseract per page when that layer is empty — not dead code:

```156:159:src/pdf_analyzer/stage2_ocr.py
            native = native_text_page(doc, page.page_number, page.width_px, page.height_px)
            results[page.page_number] = native if native is not None else ocr_page(
                page.image_path, page.page_number
            )
```

**Missing.** Three things.

- The upload screen accepts formats the engine cannot read. `magic.ts` admits
  PNG, JPG, TIFF and TXT; `stage1_ingest.py:60` raises `ConversionError` for all
  four. A user uploading a photographed contract gets `status: "queued"` and then
  a failed job — the worst possible ordering.
- `pytesseract.image_to_data` is called with no guard at
  `src/pdf_analyzer/stage2_ocr.py:69`; a machine without the Tesseract binary
  crashes the run rather than degrading. Same for LibreOffice
  (`stage1_ingest.py:78-83`) and Playwright for HTML. All three are documented
  requirements, none is checked before work is accepted.
- **On our path, scanned-document output never reaches the screen.**
  `real-worker.ts:20-23` states it writes no page images or text lines, and
  `:125-127` deletes any that exist. The OCR boxes are computed and then thrown
  away. The page pane in the live trace read "Page images are not ready yet."

**On main this is materially better.** `webapp/worker/process.py:83-88` copies the
rendered PNGs into shared storage and `webapp/worker/geometry.py:72-158` converts
real Stage 2a word boxes into line-level anchors in PDF points. Scanned documents
would show highlights on main. That code is not in our tree.

---

## 2. Field extraction coverage — ⚠️ PARTIAL

**Works.** Real extraction, real grounding, honest absence. The live trace on a
one-page distribution agreement produced 7 populated fields, all tier `verbatim`,
each with a clause label, and named the gaps explicitly in a banner:

> No extractor exists for: signatories, initial_term, auto_renews,
> notice_deadline, termination_for_cause, cure_period, payment_amount,
> payment_schedule, escalation, cap_carve_outs, indemnities. Those are reported as
> not extracted rather than guessed.

Against the brief's required fields: parties ⚠️, term ✅, renewal ✅, notice ✅,
termination ⚠️, payments ❌, liability caps ✅, exclusivity / restrictive
covenants ✅.

**Missing.**

- **Payments are absent entirely on our path.** `payment_amount`,
  `payment_schedule` and `escalation` have no CUAD equivalent in
  `webapp/scripts/lib/cuad-map.ts:82-87` and are always NA. The brief asks for
  payment terms; the tool cannot produce them.
- **Parties are not split.** The trace put the whole string
  `"Meridian Retail Pte. Ltd. (Supplier) and Acme Distribution Corp.
  (Distributor)"` into `party_a`, leaving `party_b` empty. CUAD has one `parties`
  category and `cuad-map.ts:mapParties` splits positionally when it can; on this
  document it could not, and the result is a field that reads as if one party is
  the whole agreement.
- 11 of 22 field keys have no extractor at all. Coverage is roughly a third of
  the declared vocabulary.
- No value is normalised: `real-worker.ts:139` writes `valueNormalized:
  undefined`, so `term_end` reaches the portfolio as the sentence
  "The term of this Agreement expires on 28 February 2029." rather than a date.
  This is why the calendar cannot be derived (§3).

**On main.** All 41 CUAD categories are written 1:1 (`webapp/worker/mapping.py:227-229`)
and dates/durations are parsed (`mapping.py:67-169`), which fixes normalisation
and widens coverage. It does not add `payment_amount` or `initial_term`, because
CUAD has no such category — that gap is in the taxonomy, not the code.

---

## 3. Forward 90-day calendar — ⚠️ PARTIAL

**The read path is real.** `GET /api/calendar` defaults its window to today + 90
days server-side (`webapp/src/routes/calendar.ts:37-38`), and the UI's five quick
filters (Today / This Week / 30 / 60 / 90, defaulting to 90) drive that query
parameter rather than hiding rows in the browser
(`webapp/frontend/src/routes/Calendar.tsx`).

**The write path does not exist on the real pipeline.** Exactly one line in the
repository creates a calendar event:

```559:559:webapp/scripts/stub-worker.ts
    await prisma.calendarEvent.create({
```

That is the fabricating demo worker, and its dates come from a filename-selected
profile (`stub-worker.ts:98-166`, `380-412`), not from any document.
`real-worker.ts:129` **deletes** calendar events and creates none.

**Confirmed by trace, not by reading.** After processing two real contracts the
workspace held 7 calendar events — all from the seeded demo corpus, none from
either real document. A judge who uploads their own contract and clicks Calendar
sees nothing.

**On main this gap is closed.** `webapp/worker/` parses expiry and notice dates
and inserts calendar rows, deliberately excluding `unverified` values
(`webapp/worker/mapping.py:337-340`, `359-386`). Merging it is the fix; nothing
needs to be invented.

---

## 4. Cross-contract conflict detection — ⚠️ PARTIAL

### Party-based class — ✅ IMPLEMENTED

Real, and reachable end to end. Contracts are grouped by counterparty using
exact-name matching only (`src/pdf_analyzer/pipeline.py:_counterparties_from_findings`,
using `ResolutionMethod.EXACT_NAME`, and only from grounded extractions);
`src/pdf_analyzer/conflict.py:196` runs the party pass; `real-worker.ts:216-282`
writes the result. In the live trace two real uploaded contracts sharing a
counterparty produced a real `mfn_trigger` row with severity derived from the
weakest join key rather than hardcoded.

### Asset-based class — ❌ MISSING

`conflict.py:134 asset_based_pass` exists and is unit-tested, but nothing
populates `ContractAnalysis.assets` or any `ScopeTag`, so it can never group
anything. The worker log from the live trace states it outright:

> Scanned 3 analyses (**4 party groups, 0 asset groups**); flagged 2 conflict(s)

The second required class of conflict is code that cannot fire.

### Two further limits on the class that does work

- **Date overlap is assumed, not checked.** Clause `date_range` is left open
  because no stage parses a clause's active period (`pipeline.py:230-235`), so
  `DateRange.overlaps` at `conflict.py:151` is always true. A flagged pair proves
  a *relationship*, not a *collision*. The summary text nonetheless says "over an
  overlapping period", which overstates what was verified.
- **There are two competing producers writing the same table.** Besides the rule
  library, the stub worker manufactures a conflict from two hardcoded filenames:

```607:608:webapp/scripts/stub-worker.ts
  const acme = await prisma.document.findFirst({ where: { workspaceId, filename: { contains: "Acme Distribution" }, ...
  const borden = await prisma.document.findFirst({ where: { workspaceId, filename: { contains: "Borden Distribution" }, ...
```

  with `severity: "high"` and `confidenceTier: "verbatim"` hardcoded
  (`:618-624`). The live trace showed **both kinds side by side** in
  `GET /api/conflicts` — one fabricated `exclusivity_breach`, one real
  `mfn_trigger` — and nothing on screen distinguishes them except the wording of
  the summary. A judge scrolling the conflicts page cannot tell which one the
  system actually detected.

**On main, this must-have regresses to zero.** `webapp/worker/` contains no
conflict scanning at all. Merging main and retiring our worker deletes the only
working party-based path.

---

## 5. Grounding + confidence distinguishing found from inferred — ⚠️ PARTIAL

**The core is real and is the strongest part of the system.** Stage 3 aligns each
model span against the page's actual word list, weights the score by evidence mass
rather than recall alone, and gates on a real threshold:

```49:49:src/pdf_analyzer/stage3_reconcile.py
VERIFICATION_THRESHOLD = 85.0
```

`is_grounded` follows from that computation (`pipeline.py:41-58`),
`cuad-map.ts:118` maps grounded → `verbatim` and ungrounded → `unverified`, and
the UI collapses everything to three labels through a single function
(`webapp/frontend/src/lib/confidence.tsx:69-81`). Ungrounded values are shown
struck through and captioned "(suspected error)" rather than hidden — a genuinely
good decision, since hiding them would make the tool look more accurate than it is.

**Three real weaknesses.**

- **"Quoted" is asserted without a usable citation on our path.**
  `real-worker.ts:143` writes `anchorLineIds: []`, so nothing is clickable, yet
  `DocumentDetail.tsx:241` still tells the reader "Click any value on the left to
  highlight the exact text it came from" and the page pane says "Page images are
  not ready yet" (both confirmed in the trace screenshot). The badge is honest;
  the surrounding copy is not.
- **Grounding proves location, not correctness.** It answers "is this string on
  the page?" — not "is this a complete clause?" and not "is it in the right
  category?". This surfaced accidentally during the trace: a fixture PDF whose
  text layer merged two clauses produced an extraction that scored **100%
  grounded** for a sentence that never existed as drafted. Category correctness
  remains unmeasured, exactly as the Phase 1 audit found. `vlmAgreement` is
  stored but is a Stage 3 alignment score, not a second opinion; there is no
  second extraction pass, so `consistencyScore` is always null
  (`real-worker.ts:146`).
- **Five vocabularies for one concept.** Webapp tiers
  (`webapp/src/lib/domain.ts:7-13`), Python join-key tiers
  (`schema.py:125-128`), Python `EvidenceStatus` (`schema.py:72-78`), UI display
  labels (`confidence.tsx:20`), and the OCR band words (`confidence.tsx:111-113`,
  on a 0–1 scale while Stage 3's threshold is on a 0–100 scale). Two lossy
  mappings sit between them (`confidence.tsx:69-70`; `real-worker.ts:189-193`).
  Nothing is wrong today, but there is no single source of truth, so drift is a
  matter of time.

**On main.** `webapp/worker/mapping.py:201-224` also keys off `is_grounded` and is
the more careful of the two mappers (it can produce `normalised` and `inferred`
too). But it writes `unverified` values with empty `anchor_line_ids`, which its
own seam contract (`webapp/docs/INTEGRATION.md` §4) forbids, and it never
populates `vlm_agreement`.

---

## 6. Grounding requirement — no unanchored legal claims — ⚠️ PARTIAL

**Where the rule is honoured, it is honoured well.** The statute layer was built
around this constraint:

- Statutory wording is **paraphrased and marked as such**; `StatutoryDefault
  .verbatim_text` is deliberately left `None` rather than reconstructing an Act
  from memory (`src/pdf_analyzer/statutes/__init__.py:24-29`).
- Role B skips ungrounded text entirely, so no statutory alarm can be attached to
  a sentence Stage 3 could not find (`statutes/__init__.py:180-181`).
- Flags state triggers, never conclusions, and each names the matched wording, the
  provision, and the clause and page it fired on. The trace produced
  *"This clause appears to exclude or restrict liability for negligence. Detected
  on the wording: 'shall not exceed', 'negligence'"* with
  `reasonablenessTestApplies: true` and an explicit refusal to attempt the test.
- Statutory defaults are stored in their own tables, rendered in their own panel,
  and badged **Statute** rather than borrowing an extraction's badge — because
  they have no clause to cite and any of the three confidence labels would be a
  false claim about the document.

**Where it is violated.**

- **Product copy promises a citation the real path cannot deliver:**
  `webapp/frontend/src/routes/Scope.tsx:18` ("Shows a citation for every value, so
  you can check it against the source page"), `Portfolio.tsx:51`,
  `Uploader.tsx:81`. On the real path there is no page image and no anchor.
- **The stub path fabricates citations.** `stub-worker.ts:310` labels a computed
  date `"Computed from Clause 3.1 + 3.2"`; `:339` invents clause text for a
  clause that does not exist; `:620-621` hardcodes a conflict narrative naming
  "Clause 4.1" and "Clause 2.3" of documents whose stored originals are
  `%PDF-1.7 % AITHENA demo placeholder` (`webapp/prisma/seed.ts:40`). Anyone
  demoing with `npm run stub` is showing invented citations.
- **The older standalone viewer displays model text regardless of grounding**
  (`frontend/src/App.jsx:99`). See §Teammate findings.

---

## 7. Calibration — visible competence boundary — ✅ IMPLEMENTED, with named gaps

The strongest requirement in the repo, and the one most consistently applied.
Verified on screen, not just in code:

- The extraction path **names the fields it cannot extract**, in the document's
  own warning banner, rather than leaving 11 silent blanks (trace output quoted in
  §2). It also states plainly that page images and calendar dates are not produced
  on that path.
- An **NA** badge and "Not extracted." for every field with no row, so an absent
  value never reads as an absent obligation.
- A **refusal path**: a document classified `not_a_contract` is not analysed at
  all, and the screen explains why — "doing so would invent obligations that are
  not there" (`DocumentDetail.tsx:143-153`).
- Statutory defaults **admit what they cannot check**. In the trace, 11 of 14
  standing defaults carried the caveat "AITHENA cannot detect whether this
  contract contracts out of this term, so check the document before relying on
  it" — because no extraction category corresponds to that topic. The tool
  distinguishes "the contract is silent" from "I could not tell".
- The reasonableness gate **refuses the legal question outright**: "A
  reasonableness review is required. This tool does not assess reasonableness —
  the factors below are what that assessment turns on."
- No percentages are shown anywhere; OCR quality is banded into words
  (`confidence.tsx:108-114`).
- A dedicated "What this tool won't tell you" route exists (`Scope.tsx`).

**Gaps.** No category-correctness signal, so the tool cannot say "I found a
sentence but I may have filed it under the wrong heading" (§5). The product copy
overclaims citations (§6). And on main, `doc_type` and `counterparty` are
keyword heuristics with fixed confidences of 0.6/0.75
(`webapp/worker/mapping.py:240-262`) presented in the header as document facts.

---

## 8. Escalation — a real handoff brief at a real boundary — ❌ MISSING (as specified)

The brief *format* is real and its content is derived from database rows, not
strings: `webapp/src/lib/handoff.ts:27-35` builds each "established" item from an
actual `ExtractedField`, carrying its value, clause label and confidence tier.

But the requirement is a brief raised **at a real boundary, not on a hardcoded
trigger**, and that is not what exists:

- **The only automatic trigger in the repository is hardcoded demo logic.**
  `stub-worker.ts:604-638` looks for a conflict of the fixed type
  `"exclusivity_breach"` between two documents whose filenames contain
  `"Acme Distribution"` and `"Borden Distribution"`, then calls
  `buildBriefFromConflict`. Rename either file and the escalation never happens.
- **The real path never escalates.** `real-worker.ts` contains no reference to
  `handoffBrief`. Detected conflicts — including the real `mfn_trigger` from the
  live trace — produce a conflict row and nothing else.
- **When a user does escalate manually, the brief is hollow.** The button posts to
  `webapp/src/routes/handoffs.ts:62`, which loads evidence via
  `conflict.fieldIds`. Real conflicts are written with `fieldIds: []`
  (`real-worker.ts:275`), so the "What AITHENA already established" section comes
  back empty and the brief degrades to the generic fallback question at
  `handoff.ts:48-49`.

So: a real format, real data plumbing, a genuinely well-chosen boundary in the
*statute* layer (every flag already carries `requires_human_review` and a specific
question) — and no wiring between them. The statute flags are arguably the best
escalation trigger in the codebase and are not connected to the brief at all.

---

## Gaps introduced by, or found in, teammate work

Reviewed: Hannah's engine (`src/pdf_analyzer/`, `api/`, `frontend/`), andric's
webapp (`62f3c6b`), and andric's `c50cab9` on `origin/main`. Stated factually;
nothing was patched.

**1. A duplicate implementation of Fix 1 exists on `origin/main`.** `c50cab9`
adds `webapp/worker/` — 1,286 lines of Python doing in-process what
`real-worker.ts` does by subprocess. It is better at extraction (all 41
categories), geometry (real OCR-derived bounding boxes, real page PNGs),
normalisation (parsed dates and durations) and the calendar. It has **no conflict
scanning and no statute layer**. The two are not substitutes in either direction;
see `TEAM_SUMMARY.md` §3.

**2. `c50cab9` will break `cuad-map.ts` on contact.** It replaces the 22 webapp
field keys with the 41 CUAD category keys in both `domain.ts` mirrors.
`cuad-map.ts:160` throws on any field key not in `ALL_FIELD_KEYS`, so Fix 1 fails
on every document the moment main is merged. Hard break, not a degradation.

**3. Three workers will claim the same queue.** `stub-worker.ts:654-664`,
`real-worker.ts:299-309` and `webapp/worker/db.py:102-114` use byte-identical
claim SQL with no worker identity and no `job_type` filter, and each
delete-then-rewrites the same derived tables. The Python worker additionally
filters nothing at all, so it will process demo-corpus documents whose stored
"originals" are placeholder bytes.

**4. New ungrounded assertions on main.** `classify_doc_type`
(`webapp/worker/mapping.py:240-262`) assigns document type from keywords with
hardcoded confidences; `counterparty_from` (`:276-303`) picks the second party by
positional convention. Both appear in the document header as facts with no
citation. Neither existed before `c50cab9`.

**5. Claims in main's own documentation that its code does not support.**
`webapp/worker/README.md:29-30` says it maps onto "the 21 webapp fields" (the code
maps 41, 1:1); `:97-100` says the extra categories are "not surfaced" (they are);
`webapp/docs/INTEGRATION.md` says the worker writes `document_segments` (it
deletes them and never inserts). Also, main's worker writes `unverified` values
with empty anchors, which INTEGRATION.md §4 forbids.

**6. A second, undiscussed React application.** `frontend/` (Hannah,
`81c0d81`) is a complete separate Vite app alongside `webapp/frontend/`. It
renders `item.vlm_text` whether or not it is grounded
(`frontend/src/App.jsx:99`) and shows categories with no extraction as answers
(`:116-118`) — i.e. it bypasses the confidence system entirely. Nobody has
mentioned it; it is unclear whether it is meant to be live.

**7. Pre-existing fabrication remains extensive and is only partially fenced.**
`stub-worker.ts` invents parties, dates, amounts, liability caps, clause
structure, OCR confidences, page geometry and conflict narratives across ~600
lines. This session gated it to the eight demo filenames
(`stub-worker.ts:38-39`, `425`), which stops it touching real uploads, but
`STUB_ALLOW_ANY=1` still enables it for anything, `corpus.ts:41-42` still routes
uploads to demo profiles by filename regex (`/invoice|receipt/`, `/scan/`), and
its rows are indistinguishable from real ones in the UI apart from
`pipelineVersion`.

**8. Duplicate or conflicting schema.** Five confidence vocabularies with two
lossy mappings (§5). Two conflict-type vocabularies —
`overlapping_exclusive_grant` / `mfn_trigger` /
`cumulative_commitment_exceeds_ceiling` from the library
(`conflict.py:160,250,314`) versus `exclusivity_breach` from the stub
(`stub-worker.ts:618`), which the library never emits. `FIELD_GROUPS` defined
twice, in `webapp/src/lib/domain.ts` and `webapp/frontend/src/lib/domain.ts`, kept
in sync by hand. Six independent date implementations, though UI *display* is now
unified through `webapp/frontend/src/lib/format.ts`.

---

## What is left, in priority order

### Must-have gaps

1. **Resolve the two-worker collision, and pick one.** Nothing else on this list
   can be trusted until there is one extraction path. Whichever survives must run
   the conflict scan and write the statute tables, or must-have #4 and the statute
   layer become invisible. This is the blocker for merging at all.
2. **Calendar events on the real path.** Must-have #3 is currently empty for any
   real upload. The fix already exists on `origin/main`; this is a merge, not a
   build.
3. **Asset-based conflict detection.** Must-have #4 explicitly asks for both
   classes. The rules are written and tested; what is missing is scope/asset
   resolution in `pipeline.py` so `asset_based_pass` has groups to work on.
4. **Clause date ranges**, so conflict overlap is checked rather than assumed, and
   so summaries stop asserting "an overlapping period" that was never verified.
5. **Ingest the formats the uploader accepts** (PNG/JPG/TIFF/TXT), or reject them
   at upload with a clear message. Accepting a file and failing later is worse than
   refusing it.
6. **Fail fast on missing Tesseract / LibreOffice / Playwright** instead of
   crashing mid-run.
7. **Payment terms and party splitting.** Two of the brief's named fields are
   structurally unavailable today.

### Calibration and escalation gaps

8. **Wire escalation to a real boundary.** Delete the filename-gated auto-brief,
   and trigger from something real. The statute flags are the obvious candidate:
   each already carries `requires_human_review`, a specific question and a
   citation.
9. **Populate `conflict.fieldIds`** (or give the brief builder a clause-level
   evidence path) so a manually created brief is not empty.
10. **Fix the copy that overclaims citations** in `Scope.tsx`, `Portfolio.tsx`,
    `Uploader.tsx` and `DocumentDetail.tsx:241`, or supply the anchors that would
    make it true. Right now the product promises exactly the thing the audit says
    it cannot do.
11. **A category-correctness signal.** Grounding proves a sentence is on the page;
    nothing yet says whether it was filed under the right heading.

### Merge-risk items

12. **`cuad-map.ts` vs the 41-key vocabulary** — a hard break the moment main
    lands. Decide it as part of item 1.
13. **Collapse the confidence vocabularies to one source of truth**, and generate
    the rest from it.
14. **Deduplicate `FIELD_GROUPS`** across the two `domain.ts` files.
15. **Reconcile the two conflict-type vocabularies**, and mark stub-produced rows
    so a reader can tell a fabricated conflict from a detected one.
16. **Decide the fate of the second React app in `frontend/`.** If it is live, it
    bypasses the confidence system; if it is dead, delete it.
17. **Correct main's stale documentation** (`webapp/worker/README.md`,
    `docs/INTEGRATION.md`) so the seam contract matches the code.

### Stretch

18. **Natural-language portfolio query** (Stage 3). Items 1 and 2 are buildable;
    item 3 is still blocked on clarifying "Extract" and should not be guessed at.
    Deliberately deferred — see `TEAM_SUMMARY.md` §5.
19. **Retire the stub worker**, once the real path writes geometry and calendar
    rows and no longer needs it for a demo.
