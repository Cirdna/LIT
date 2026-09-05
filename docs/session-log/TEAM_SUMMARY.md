# AITHENA — what exists, who built it, and how to merge it

Written for someone who has not read any prior session. Plain English first,
file paths second. Nothing here is credited as working unless it was traced from
real input to real output; where that was not possible it says so.

**Repo state as of writing**

| | |
|---|---|
| Local branch | `testing-branch` at `62f3c6b` |
| `origin/main` | `c50cab9` — **one commit ahead of us**, containing a large teammate change |
| This session's work | uncommitted, in the working tree, based on `62f3c6b` |
| Contributors in git history | Hannah (12 commits), andric (2 commits) |
| Python tests | 137 passing |

The single most important fact in this document: **`origin/main` now contains a
second, independent implementation of the same webapp↔pipeline integration this
session built.** See §3 before merging anything.

---

## 1. What exists and works, by feature area

### Reading a document (ingestion)

A user drops up to 25 files at once onto the upload panel. Each file is sniffed
by its magic bytes rather than trusting the extension, stored, and given a job on
a queue. A background worker then hands the file to the Python engine, which
converts whatever it is into a standardised PDF and renders every page to an
image. Word-for-word text comes from the PDF's own text layer when it has one,
and from OCR (Tesseract) when it does not — so a scanned lease and a born-digital
contract both come out as the same thing downstream.

What a user actually experiences: PDFs and Word documents work. Images
(PNG/JPG/TIFF) and plain text are accepted by the upload screen and then fail in
the worker, because the Python side does not convert them. Word documents need
LibreOffice installed on the machine running the worker, and scanned documents
need Tesseract; neither absence is caught early, so the failure arrives as a
failed job rather than a clear message at upload time.

`webapp/src/routes/documents.ts`, `webapp/src/lib/magic.ts`,
`src/pdf_analyzer/stage1_ingest.py`, `src/pdf_analyzer/stage2_ocr.py`

### Pulling terms out (extraction)

A vision model reads each page image and returns the clauses it thinks match a
fixed list of contract topics (the 41 CUAD categories). Every span it returns is
then hunted for in the page's real word list; if it can be located to at least
85% confidence, the extraction is marked as grounded and gets a real bounding box
and page number. If it cannot be located, it is kept but marked as a suspected
error rather than silently dropped or silently shown.

What a user actually experiences: a document detail screen with seven groups of
fields. Fields the engine found show the sentence from the contract, with the
clause it came from. Fields the engine cannot extract at all say "Not extracted",
and a banner at the top names them explicitly rather than leaving blanks to be
misread. In the live trace, a one-page distribution agreement produced 7
populated fields out of 22, and the banner named all 11 fields with no extractor.

`src/pdf_analyzer/stage2_vlm.py`, `stage3_reconcile.py`,
`webapp/scripts/lib/cuad-map.ts`, `webapp/scripts/real-worker.ts`

### Telling found from guessed (grounding and confidence)

Every value on screen carries one of three labels, and only three: **Quoted**
(green — the text was located on the cited page), **Inferred** (yellow —
extracted but not located, so check it), **NA** (red — nothing was extracted).
There are no percentages anywhere, because non-experts misread them. A filter at
the top of the field list lets you hide any of the three, with a count beside
each. The engine's finer five-tier vocabulary still travels in the data and
drives the plain-language "why" lines under a value, but exactly one function
decides what a reader sees.

What a user actually experiences: it is possible to look at a screen and know, in
one glance, which numbers came out of the document and which did not.

`webapp/frontend/src/lib/confidence.tsx`,
`webapp/frontend/src/components/FieldValue.tsx`

### Deadlines (the calendar)

A calendar screen shows what is coming up, with quick filters for Today, This
Week, 30 / 60 / 90 days, defaulting to 90. The filtering is done by the server,
not by hiding rows in the browser.

What a user actually experiences: **for the demo corpus this works; for a real
uploaded contract the calendar stays empty.** Nothing on the real pipeline path
writes calendar entries — the extraction path deliberately does not invent dates
it has not parsed. This is the largest functional hole in the local tree, and
`origin/main` closes it (see §3).

`webapp/src/routes/calendar.ts`, `webapp/frontend/src/routes/Calendar.tsx`,
written only by `webapp/scripts/stub-worker.ts:559`

### Contradictions between contracts (conflict detection)

After each document is analysed, all analyses in the workspace are scanned
together. Contracts are grouped by counterparty using exact-name matching only,
then deterministic rules look for pairs worth a human's attention — for example a
most-favoured-nation promise in one agreement sitting alongside pricing agreed in
another with the same party. Rules are ordinary code, not a model, so a flagged
pair can always be explained by naming the rule that fired.

What a user actually experiences: a conflicts screen listing pairs with both
sides quoted. In the live trace, two real uploaded contracts sharing a
counterparty produced a real `mfn_trigger` row from the rule library.

Two limits are structural. There is a second class of conflict — same *asset* or
territory rather than same *party* — whose code exists but never runs, because
nothing in the pipeline resolves what asset a clause is about. And clause date
ranges are never parsed, so "overlapping period" is assumed rather than checked.

`src/pdf_analyzer/conflict.py`, `src/pdf_analyzer/pipeline.py`,
`webapp/scripts/real-worker.ts` (`scanForConflicts`)

### What the law says even when the contract does not (statute layer)

Six Singapore statutes are encoded, in two roles. Three of them (Sale of Goods,
Supply of Goods, Contracts (Rights of Third Parties)) supply terms that apply
*because the law supplies them* — implied promises about title, quality, fitness
for purpose, third-party enforcement. These are attached before extraction runs,
and then marked as displaced if the contract turns out to deal with the topic
itself, naming the clause that displaced them. The other three (UCTA,
Misrepresentation Act, Frustrated Contracts Act) read clauses after extraction
and raise a flag when a clause engages a provision.

What a user actually experiences: a navy panel titled "Supplied by statute",
visually separate from the extracted fields and badged **Statute** rather than
Quoted/Inferred/NA — because none of those three would be honest about something
that has no clause to cite. Underneath a field, where relevant, sits the flag: in
the live trace the liability-cap field showed its own quoted value *and* two UCTA
flags, one citing s.2(1) (which the Act allows no reasonableness escape from) and
one citing s.2(2) (which turns on a reasonableness test the tool explicitly
declines to attempt).

The layer states triggers, never conclusions. It never says a clause is
unenforceable; it says which provision the clause engages and what a lawyer would
have to decide. It also never quotes an Act verbatim — statutory wording is
paraphrased and marked as such, because a tool whose whole premise is that
quotations must be checkable does not get an exception for quoting legislation.

`src/pdf_analyzer/statutes/` (10 modules), `webapp/frontend/src/components/StatutePanel.tsx`,
`StatuteFlagNote.tsx`

### Handing off to a lawyer (escalation briefs)

There is a brief format — what the boundary was, what the tool established with
citations, and the single specific question a lawyer needs to answer — and a
screen that renders it as something you could paste into an email.

What a user actually experiences: **on a real document, only if they press a
button, and the "what we established" section comes back empty.** The only
automatic trigger in the repo fires on two hardcoded demo filenames. This is
covered in detail in `GAP_REPORT.md` §8; it is the weakest of the must-haves.

`webapp/src/lib/handoff.ts`, `webapp/src/routes/handoffs.ts`,
`webapp/frontend/src/routes/HandoffBrief.tsx`

### Natural-language portfolio query (chatbot)

**Not built.** Intentionally deferred, not missing — see §5.

---

## 2. Who built what

| Area | Built by | Evidence |
|---|---|---|
| Python engine: stages 1–4, schema, 41 CUAD classes, VLM backends (OpenRouter / Qwen / InternVL), reconciliation, `conflict.py` rule library, `api/main.py`, the older standalone viewer in `frontend/` | **Hannah** — pre-existing, 12 commits on 2026-09-05 | `git log 81c0d81..9439c1b` |
| Webapp: Fastify API, Prisma schema, React frontend, demo corpus, `stub-worker.ts`, seed, `docs/` | **andric** — pre-existing, `62f3c6b` | `git show --stat 62f3c6b` |
| **Second integration: Python worker `webapp/worker/` (1,286 lines) + rewrite of both `domain.ts` files to the 41 CUAD keys** | **andric — teammate work, on `origin/main` only, NOT in our tree** | `c50cab9`, 2026-09-06 |
| Fix 1: real extraction into the webapp (`real-worker.ts`, `cuad-map.ts`) | this session | untracked files |
| Fix 2: conflict library wired to pipeline output (`pipeline.py` join keys + structured clauses, `cli.py conflicts`, `test_conflict_wiring.py`) | this session | working-tree diff |
| Statute layer: 6 statutes, shared reasonableness gate, `schema.py` additions, pipeline wiring, 7 test files | this session | `src/pdf_analyzer/statutes/` |
| UI: three-label confidence system, field filter, unified date format, calendar quick filters | this session | working-tree diff |
| Statute layer surfaced in the UI: 2 new tables, additive worker read, fourth badge, flags beside fields | this session | working-tree diff |

**Cannot attribute:** Hannah's commits are all dated 2026-09-05 with a single
authorship string, so it is not possible to tell from git whether the engine was
written by one person, pair-written, or partly generated. The same applies to
`c50cab9` — it is attributed to `andric`, but whether a person or a tool wrote
the 1,286 lines of `webapp/worker/` is not knowable from the repository. Do not
read the table above as a claim about individual effort.

---

## 3. Merge risk map

Every file this session touched, and whether it collides with `c50cab9`.

### Needs a second reviewer regardless of author (per the standing rule)

| File | This session did | `c50cab9` did | Risk |
|---|---|---|---|
| `src/pdf_analyzer/pipeline.py` | added join keys, structured clauses, statute pre-fill/review | untouched | **Low textual, high blast radius.** Every consumer of the analysis JSON depends on it. |
| `src/pdf_analyzer/schema.py` | added `StatutoryDefault`, `StatuteFlag`, `StatuteRole`; two new `ContractAnalysis` fields | untouched | **Low textual.** Additive and JSON-compatible; old readers ignore the new keys. |
| `webapp/scripts/real-worker.ts` | created (Fix 1 + Fix 2), then +126 lines for the statute layer | untouched — but `c50cab9` adds a **rival worker** | **Highest risk in the repo.** Not a text conflict; a duplication. See below. |
| `webapp/src/lib/domain.ts` | untouched | **rewrote FIELD_GROUPS: 22 keys / 7 groups → 41 CUAD keys / 8 groups** | **Breaking.** See below. |

### Direct textual conflicts with `c50cab9`

| File | Nature |
|---|---|
| `webapp/scripts/stub-worker.ts` | Both sides edited it. We added the demo-filename gate (lines 38–39, 425); `c50cab9` changed 137 lines of its field/profile logic to the new vocabulary. **Will conflict.** |
| `webapp/src/routes/documents.ts` | We added the statute includes and serializers to the detail route; `c50cab9` changed one line in the portfolio query (`term_end` → `expiration_date`). Small, mechanical. |

### The two problems that a merge tool will not tell you about

**(a) `cuad-map.ts` breaks the moment `main` lands.** It validates its output
against `ALL_FIELD_KEYS` and throws on anything unrecognised:

```160:160:webapp/scripts/lib/cuad-map.ts
  if (unknown.length > 0) throw new Error(`mapped unknown field keys: ${unknown.join(", ")}`);
```

`c50cab9` replaces the 22 field keys with the 41 CUAD category keys. `party_a`,
`term_end`, `notice_period`, `liability_cap` and the rest cease to exist, so Fix
1 throws on every document. This is a hard break, not a degradation.

**(b) Two workers, one queue, opposite trade-offs.** `webapp/worker/` (Python,
in-process) and `webapp/scripts/real-worker.ts` (TypeScript, subprocess) claim
jobs with byte-identical SQL, no worker identity, and no `job_type` filter, and
both delete-then-rewrite the same derived tables. Running both at once means the
last one to finish wins. They are not substitutes:

| | Python `webapp/worker/` (main) | TS `real-worker.ts` (ours) |
|---|---|---|
| Page images + real bounding boxes | **yes** | no |
| Calendar events | **yes** | no |
| Parsed dates / durations | **yes** | no |
| `doc_type`, provenance | yes (heuristic) | left unset on purpose |
| Field coverage | all 41 CUAD keys | ~10 mapped keys |
| **Cross-contract conflict scan** | **no** | **yes** |
| **Statute layer (defaults + flags)** | **no** | **yes** |
| `vlm_agreement` score | never written | written |

Merging `main` as-is silently drops conflict detection and the statute layer.
Keeping only ours drops page highlighting and the calendar. Neither branch alone
satisfies the brief.

### Low risk, no overlap

`src/pdf_analyzer/cli.py` (new `conflicts` subcommand), `webapp/prisma/schema.prisma`
(two new tables, additive), `webapp/src/lib/serialize.ts` (two new serializers),
`webapp/frontend/src/lib/{confidence.tsx,format.ts,api.ts}`,
`webapp/frontend/src/routes/{DocumentDetail,Calendar,Conflicts,HandoffBrief}.tsx`,
`webapp/frontend/src/components/FieldValue.tsx`, `tailwind.config.js`,
`webapp/package.json`, `webapp/.gitignore`, all new test files, all new statute
modules, `StatutePanel.tsx`, `StatuteFlagNote.tsx`.

Note that `c50cab9` also rewrote `webapp/frontend/src/lib/domain.ts` (the field
labels). We did not touch that file, but `DocumentDetail.tsx` — which we
rewrote — iterates it. No text conflict; the screen will simply render 41 rows
instead of 22 once merged, and the filter and counts will follow automatically
because they are computed from the same structure.

---

## 4. Suggested merge order

The ordering principle: land the thing that changes the shared vocabulary first,
adapt to it once, and never have two workers live at the same time.

1. **Decide the worker question before writing any merge code.** This is a
   product decision, not a rebase. The cheapest path that keeps everything is to
   keep `webapp/worker/` as the extraction worker (it is strictly better at
   extraction, geometry, dates and the calendar) and port the two things only we
   have — the conflict scan and the statute-layer write — into it. The
   alternative, porting geometry and calendar writing into `real-worker.ts`, is
   more work for a worse result.
2. **Merge `origin/main` (`c50cab9`) into `testing-branch` first, on its own.**
   It is one commit and it owns the vocabulary. Resolve `stub-worker.ts` by
   taking main's field logic and re-applying our 3-line demo gate on top;
   resolve `documents.ts` by taking both changes.
3. **Land the statute layer's Python half** — `schema.py`, `src/pdf_analyzer/statutes/`,
   `pipeline.py` pre-fill/review, and the 7 test files. Purely additive, no
   vocabulary dependency, and it is the piece with the least chance of needing
   rework later. Confirm 137 tests still pass.
4. **Land Fix 2** (`pipeline.py` join keys and structured clauses, `cli.py
   conflicts`, `test_conflict_wiring.py`). Also vocabulary-independent, because it
   works on CUAD categories rather than webapp field keys.
5. **Land the UI work** — three-label confidence, the filter, date formatting,
   calendar quick filters, the fourth badge, `StatutePanel`, `StatuteFlagNote`,
   and the two new Prisma tables. Under main's vocabulary the statute flags land
   *better* than they do today: flag identity is the CUAD category, and after the
   merge the webapp field keys **are** the CUAD categories, so the
   "Other clauses a statute touches" fallback section should empty out and the
   Misrepresentation flag should attach directly to `anti_assignment`.
6. **Land the chosen worker last**, once there is exactly one, and delete or
   clearly quarantine the other. Whichever survives must write the statute tables
   and run the conflict scan, or steps 3–5 are invisible on screen.
7. **Separately, and not urgent:** decide what to do with the older standalone
   viewer in `frontend/`, which is a second React app nobody has mentioned.

Do not merge steps 5 and 6 in the other order — the UI reads tables the worker
writes, and reviewing a screen with no data in it proves nothing.

---

## 5. Deliberately not done

**Stage 3 (natural-language portfolio query).** Blocked and left blocked. The
scope of item 3 in the request ("Extract" in Althea's note) was never clarified,
and the instruction was explicit: do not guess at it. Items 1 and 2 of that stage
(a chatbot with one clarifying round-trip over a structured filter, and measuring
a selected date field against the portfolio average) are independent of the
blocker and could be built, but were not reached in this pass — the audit in
`GAP_REPORT.md` was the higher-priority deliverable. Recorded here as **deferred,
not missing**, so nobody re-derives it as an oversight.

**Everything in `GAP_REPORT.md`.** Findings there were not fixed. That was the
instruction, and it applies especially to teammate code: nothing in
`webapp/worker/` or `c50cab9` was modified, and the gap report describes it
factually rather than patching it.
