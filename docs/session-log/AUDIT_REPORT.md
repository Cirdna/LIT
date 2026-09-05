# AITHENA / LIT codebase audit (Phase 1)

**Date:** 2026-09-06  
**Branch:** `testing-branch`  
**Scope:** literal code-path audit. A feature is **IMPLEMENTED** only if a live execution path exists. It is **working end-to-end** only if that path runs from real input to output with no stub, mock, or hardcoded scenario data in between.  
**Prompt note:** the request was cut off at must-have 6 (“structured summary (issue + relevant”). This report covers the six listed must-haves plus material findings needed to score them honestly.

There are **two disconnected stacks**. They do not share a worker, schema, or field vocabulary.

| Stack | What it is | Talks to the other? |
|---|---|---|
| `src/pdf_analyzer/` + `api/main.py` + `frontend/` | Real CUAD extract-and-ground pipeline, single-file CLI/API | No. Writes JSON / in-memory jobs. Never writes Postgres. |
| `webapp/` (AITHENA) | Portfolio / calendar / conflicts / handoff UI | No. The only “worker” is `webapp/scripts/stub-worker.ts`. `docs/INTEGRATION.md` describes a Python worker; **that file does not exist**. |

`conflict.py` is imported only by `tests/test_conflict.py`. `pipeline.py` never calls it. The webapp never imports the Python package.

---

## Scorecard

| # | Requirement | Score |
|---|---|---|
| 1 | Batch ingestion, mixed format + live OCR fallback | ⚠️ PARTIAL |
| 2 | Field extraction coverage (listed fields, real input) | ⚠️ PARTIAL |
| 3 | Forward calendar (90-day) end-to-end | ⚠️ PARTIAL |
| 4 | Cross-contract conflict detection | ⚠️ PARTIAL |
| 5 | Grounding + confidence; category-correctness check | ⚠️ PARTIAL |
| 6 | Escalation / handoff brief | ⚠️ PARTIAL |

Nothing on this list is **IMPLEMENTED** as a working end-to-end product path. Several pieces are real algorithms sitting behind fixtures or a stub demo.

---

## 1. Batch ingestion, mixed format

**Score: ⚠️ PARTIAL**

### What exists

**Single-file conversion (Python) is real.** `convert_to_pdf` routes by suffix:

- `.pdf` → validate + copy (`stage1_ingest.py` `_validate_and_copy_pdf`, ~63–74)
- `.docx` / `.doc` / `.rtf` / `.odt` → LibreOffice (`_convert_office_to_pdf`, ~77–108)
- `.html` / `.htm` → Playwright Chromium (`_convert_html_to_pdf`, ~111–134)

`ingest()` (`stage1_ingest.py` 170–183) then renders pages. `cli.py` 31–32 and `analyze_document()` (`pipeline.py` 114–121) take **one** `input_path`. FastAPI `POST /jobs` (`api/main.py` 77–91) accepts **one** `UploadFile`. There is no folder walk, no glob, no multi-file CLI command.

**Webapp multi-file upload is real; processing is not.** `POST /api/documents` (`webapp/src/routes/documents.ts` 44–128) loops multipart parts and can queue many files in one request. `Uploader.tsx` 28, 73–78 uses `multiple` and copy that says “Drop a folder of contracts.” Accepted types (`magic.ts` 7, 39–52): pdf, docx, png, jpg, tiff, txt. **Not HTML. Not RTF.** Images/txt are sniffed and stored; nothing in this repo converts them through Stage 1.

Jobs are `jobType: "ingest"` (`documents.ts` 119–121). The only consumer is `stub-worker.ts`. It **does not read the uploaded bytes**. `processDocument` (407–411) loads the DB row, then `profileForFilename(doc.filename)` and writes synthetic pages/fields. A real mixed-format folder would be stored, then ignored.

### OCR / scanned-document path

**Wired, not proven live.**

`extract_document_words` (`stage2_ocr.py` 145–162) calls `native_text_page`; if that returns `None` (no extractable text, lines 117–119), it calls `ocr_page` (Tesseract, 59–96). That is a real branch.

It is **not** working end-to-end on a scanned contract:

- `test_extract_document_words_falls_back_to_ocr_for_textless_page` (`tests/test_stage2_ocr.py` 116–139) **stubs** `ocr_page` and never opens Tesseract.
- `HANDOFF.md` §6.4 states the Tesseract fallback has **never run on a real scanned contract**.
- The webapp “scanned + illegible” demo (`stub-worker.ts` 113–114, 337–340) sets `ocrApplied: true` and `absence: "illegible"` from a filename profile. No Tesseract, no page image of a real lease.

### Verdict

You can convert one office/HTML/PDF file in Python, and you can upload many files in the webapp. You cannot run “a folder of mixed contracts” through extraction. The OCR function exists; the scanned path is unexercised except via a monkeypatched test and a hardcoded stub flag.

---

## 2. Field extraction coverage

**Score: ⚠️ PARTIAL**

Two taxonomies. Neither is a complete, live implementation of the required list.

### A. Python CUAD pipeline (real VLM → JSON, single document)

Extraction is `vlm_backend.extract_document` then `cuad_extractions[item.cuad_class]` (`pipeline.py` 130–146). Categories are the 41 CUAD keys in `cuad_classes.py` 9–51. Prompts are in `stage2_vlm.py` (`_build_extraction_prompt` ~81, `_build_single_category_prompt` 150).

This path **can** run on a real PDF if `OPENROUTER_API_KEY` is set. It does **not** populate the webapp’s `extracted_fields` table. It does **not** emit structured dates/amounts for a calendar.

| Required field | CUAD key(s) | Live extract logic? | Distinct from neighbours? |
|---|---|---|---|
| Parties | `parties` | Yes — VLM class + prompt | Yes |
| Term / duration | `effective_date`, `expiration_date` only | Partial. No `initial_term`, no duration-as-a-span field. Expiration is a date question, not “the term is 24 months.” |
| Renewal mechanics | `renewal_term` | Yes | Separate class from notice |
| Notice periods | `notice_period_to_terminate_renewal` | Yes — own class (`cuad_classes.py` 16, 81) | **Not conflated** with `renewal_term` |
| Termination rights | `termination_for_convenience` only | Partial. No for-cause, no general termination, no cure period |
| Payment obligations | — | **Missing.** Closest: `revenue_profit_sharing`, `price_restrictions`, `minimum_commitment`. No rent/fee/invoice field |
| Liability caps | `cap_on_liability`, `uncapped_liability` | Yes | Yes |
| Exclusivity / restrictive covenants | `exclusivity`, `non_compete`, `no_solicit_of_customers`, `no_solicit_of_employees`, `non_disparagement` | Yes | Yes |

`HANDOFF.md` §3 claims scored runs on two real contracts (Armstrong, Chase). That is evidence the VLM path has been used; it is not a substitute for wiring those findings into the product fields below.

### B. Webapp field set (the judged UI)

`FIELD_GROUPS` (`webapp/src/lib/domain.ts` 37–64) is the screen contract: `party_a` / `party_b`, `initial_term` / `term_end`, `notice_period` vs `renewal_term`, `termination_for_cause`, `payment_amount`, `liability_cap`, etc.

Every value is written by `fieldPlan()` in `stub-worker.ts` 273–354. That function **does not open a document**. It uses `today()`, `meta.partyA`, and profile overrides (`distribution_acme`, `lease_scanned_illegible`, …). Example: `payment_amount` is hardcoded `"S$50,000 per quarter"` (line 305) unless a profile overwrites it.

Notice **is** a distinct key from renewal in the stub (`notice_period`, `notice_deadline` vs `renewal_term`, `auto_renews`). That only proves the **schema** separated them. Nothing extracts notice from a real clause.

### Verdict

Python: some required concepts exist as CUAD classes and can be extracted from a real page; term duration and payment obligations do not. Webapp: all eight groups appear on screen from canned JSON-shaped rows. **No field on the required list is extracted from real input into the product UI.**

---

## 3. Forward calendar (90-day)

**Score: ⚠️ PARTIAL**

### What is real (read path)

The API default window is 90 days:

```38:38:webapp/src/routes/calendar.ts
    const to = q.to ?? addDays(today, 90);
```

Events are filtered by `actionByDate ?? eventDate` (`calendar.ts` 51–60). Portfolio `actionsNext90` uses the same rule (`portfolio.ts` 17–18, 49–51). The UI defaults to a 90-day range (`Calendar.tsx` 9, 19, 57) and bands overdue / 7 / 30 / 90 (`format.ts` `bandFor`, 31–37).

That is a real **display filter**. It is not date arithmetic from extracted clauses.

### What is not real (write path)

`INTEGRATION.md` §4 step 6 says the worker must “Compute and write `calendar_events`.” The only writer is `calendarPlan(meta)` (`stub-worker.ts` 367–399). Inputs are `meta.autoRenews`, `meta.renewalDate`, `meta.noticeDeadline`, `meta.termEnd`, `meta.paymentDue` — set in `metaFor()` from **filename profiles** (lines ~92–148), e.g. `termEnd: addDays(t, 20)` for the overdue NDA. `sourceFieldIds` is always `[]` (552).

The Python pipeline has **no** calendar module, no 90-day computation, no `notice_deadline` derivation from `expiration_date` − `notice_period`.

Frontend calendar fetch sets `to=2999-01-01` (`Calendar.tsx` 29) and re-filters client-side. So even the API’s default 90-day cap is bypassed by the UI; the “90-day product” is a client toggle over stub rows.

### End-to-end trace (honest)

1. Seed / upload → job queued.  
2. Stub picks dates from a demo profile, not from `extracted_fields`.  
3. Rows land in `calendar_events`.  
4. GET `/api/calendar` and the React view filter them.

**Dates are extracted (in the stub) but the extraction is fake; a forward calendar is surfaced, but nothing computes it from real renewal/notice/termination text.**

---

## 4. Cross-contract conflict detection

**Score: ⚠️ PARTIAL**

Split this; the spec asked several independent questions.

### 4a. `counterparty_id` / `asset_id` / `contract_family_id` as schema fields

**Python (`schema.py` 306–321): ⚠️ PARTIAL — different names, real fields.**

`ContractAnalysis` has:

- `counterparties: List[EntityLink]`
- `assets: List[EntityLink]`
- `contract_family: Optional[EntityLink]`

IDs live on `EntityLink.canonical_id` (`schema.py` 154–163), not columns named `counterparty_id` / `asset_id` / `contract_family_id`. That is close enough **as a model**. `pipeline.analyze_document` never sets them (154–162): they stay `[]` / `None`.

**Prisma / product DB: ❌ MISSING.**

`webapp/prisma/schema.prisma` has `documents.counterparty` (string denorm, line 45), `conflicts.documentIds` / `fieldIds`. **No** `counterparty_id`, `asset_id`, or `contract_family_id`.

### 4b. Separate party-based and asset-based passes

**Algorithm: ✅ IMPLEMENTED (library only).**

- `asset_based_pass` — `conflict.py` 134–176  
- `party_based_pass` — `conflict.py` 196–210  
- `build_review_queue` runs them independently and tags `detected_by` (338–357)

Test: `test_both_passes_run_independently_and_are_distinguishable` (`tests/test_conflict.py` 288–315).

**Product path: ❌ MISSING.** `build_review_queue` is never called from `pipeline.py`, `cli.py`, or `api/main.py`. Grep: imports only from `tests/test_conflict.py`.

Webapp conflict write is `maybeRaiseExclusivityConflict` (`stub-worker.ts` 586–623): if filenames contain `"Acme Distribution"` and `"Borden Distribution"`, insert one `exclusivity_breach` row. One merged comparison, filename-gated, not two passes.

### 4c. Deterministic rule, no LLM

**✅ IMPLEMENTED as a function; ⚠️ PARTIAL as a system.**

`DateRange.overlaps` (`schema.py` 243–256) is plain date logic.  
`asset_based_pass` uses it with `RULE_ASSET_EXCLUSIVE_OVERLAP` (`conflict.py` 49, 151–163).  
`party_based_pass` adds `RULE_PARTY_MFN_TRIGGER` (`_mfn_trigger_rule`, 219) and `RULE_PARTY_CUMULATIVE_COMMITMENT` (`_cumulative_commitment_rule`, 270).  
`DetectionProvenance.DETERMINISTIC` is set on those conflicts. No model call in this module.

These functions run only on **hand-built** `ContractAnalysis` objects in tests. Live analyses have empty `structured_clauses`, so a real run would return an empty queue.

### 4d. Confidence tiers on entity resolution

**Schema + factory: ✅. Resolver: ❌.**

`ResolutionMethod` and `_TIER_BY_METHOD` (`schema.py` 131–151): `registration_number` / `exact_name` → high, `fuzzy_name` → medium, `llm_suggested` → low. `EntityLink.build` (171–188) sets `requires_human_review` for anything below high.

There is **no** function that takes two party strings and returns an `EntityLink`. No registration lookup, no fuzzy matcher, no LLM-suggest path. Tiers exist so tests can stamp them on.

### 4e. Near-miss must NOT merge

**Test of grouping, not of resolution.**

`test_near_miss_entities_are_not_merged_and_produce_no_conflict` (`test_conflict.py` 150–168) builds two links with `canonical_id=None` and `ResolutionMethod.UNRESOLVED`, then asserts `party_based_pass` is empty. `_group_by_key` (`conflict.py` 98–113) skips `canonical_id is None`.

That tests: **if you already abstained, you will not group.** It does **not** test that “Acme Industries Pte Ltd” vs “Acme Industrial Ltd” are recognized as different. Nothing in the repo performs that recognition. A near-miss on live data cannot occur because IDs are never assigned.

### Verdict

The conflict engine is a well-tested library over synthetic records. The product plants one exclusivity story. Join-key **names** from the brief do not exist in Postgres. Entity resolution — the thing that would make the library runnable — is not built. `HANDOFF.md` §6.5 already says this; the code agrees.

---

## 5. Grounding + confidence signal

**Score: ⚠️ PARTIAL**

### 85% threshold: real code

```49:49:src/pdf_analyzer/stage3_reconcile.py
VERIFICATION_THRESHOLD = 85.0
```

```295:295:src/pdf_analyzer/stage3_reconcile.py
        is_verified=match_score >= threshold,
```

`reconcile_phrase` (243–301) aligns VLM tokens to the page word array, scales recall by evidence mass, and sets `is_verified`. CLI `--threshold` defaults to that constant (`cli.py` 44–47). Pipeline copies `is_grounded` from `match.is_verified` (`pipeline.py` 41, 53–58) and flags the category if nothing grounds (`pipeline.py` 99–110). Tests assert `>= 85.0` / `< 85.0` (`test_stage3_reconcile.py` 41–61, 84–90).

This is **not** a diagram. It is also **only alignment confidence** (how much of the claimed phrase sits on the page, discounted if the tokens are too common).

### Category-correctness: **not fixed**

Nothing after Stage 3 asks “is this quote a liability cap or a warranty?” The VLM’s `cuad_class` is trusted. `_finding_for` flags missing/ungrounded text only.

`HANDOFF.md` §6.8 still states the gap: Stage 3 cannot catch a correctly grounded quote filed under the wrong category; Chase false positives scored 100 with healthy evidence mass. **No subsequent commit in this tree adds a classifier check, second-pass category verify, or review_flag for misfile.**

Webapp “confidence” is a different enum (`verbatim|normalised|assembled|inferred|unverified`, `domain.ts` 7–13). The stub assigns those labels. `unverified` is a planted fabrication signal (`msa_unverified` profile), not Stage 3 output.

### Verdict

VLM-vs-page reconciliation and the 85% gate are implemented and unit-tested. Confidence measures **quote-on-page**, not **right-clause**. Misclassification with a perfect ground score is still invisible.

---

## 6. Escalation / handoff brief

**Score: ⚠️ PARTIAL**

(The prompt ended at “structured summary (issue + relevant”. Scoring what is in the repo.)

### Structured brief builder: real function, demo inputs

`buildBriefFromConflict` (`webapp/src/lib/handoff.ts` 21–59) returns:

- `trigger` — `conflict:${conflict.conflictType}`
- `issue` — `conflict.summary`
- `established[]` — `{ label, detail, citation, confidenceTier }` from extracted fields
- `question` — clause-named question, not “please review”
- `documentIds`

`POST /api/handoffs` (`handoffs.ts` 37–73) persists that shape, or accepts a manual body. `GET /api/handoffs/:id` + `HandoffBrief.tsx` render it.

Automatic create: `maybeRaiseExclusivityConflict` (`stub-worker.ts` 611–621) after the Acme/Borden filename match. The Conflicts UI can POST a brief for an existing row (`Conflicts.tsx` 48–61).

### What this is not

- Not generated from Python `FlaggedConflict` / `ConflictReviewQueue`.
- Not triggered by unverified OCR, illegible pages, or low-tier entity links (Scope.tsx *claims* those cases produce a brief; only the stubbed exclusivity conflict does).
- `established` is copied from stub fields, including invented clause labels.

### Verdict

A structured (issue + established facts + specific question) generator exists and the UI can show it. End-to-end it fires on a **hardcoded two-filename scenario**, not on a detected legal boundary in real contracts.

---

## Cross-cutting facts (needed to avoid over-credit)

1. **No Python webapp worker.** `INTEGRATION.md` specifies `psycopg` + job claim SQL. There is no `worker.py` / `scripts/worker.py`. Interchangeability is documentation.
2. **Click-to-jump Python frontend** (`frontend/`) is a second UI. `HANDOFF.md` §6.6: never opened against real pipeline output.
3. **`pipeline` integration test** (`tests/test_pipeline_integration.py`) uses a real Stage 1 PDF and **fake** OCR/VLM. It does not prove hosted extraction.
4. **Default prompt mode is `single`**, not the more accurate `granular` (`cli.py` 75–81; `HANDOFF.md` §6.1). Anyone running the CLI without the flag is not on the path the accuracy table describes.

---

## What would have to exist to flip scores to ✅

Phase 2 (not done in this pass). Minimum honest bar:

1. **Ingestion:** folder or multi-file job that runs `ingest()` per file, including HTML; invoke real `ocr_page` on a textless page and persist `source="ocr"`.
2. **Fields:** map CUAD (or a dedicated extractor) into the webapp keys, including a real payment field and a duration/term-length field; write `extracted_fields` from document text, not `fieldPlan`.
3. **Calendar:** derive `eventDate` / `actionByDate` from those normalized dates (term end, notice period → notice deadline); set `sourceFieldIds`; drop filename `addDays` profiles.
4. **Conflicts:** entity-resolution stage that fills `counterparties` / `assets` / `structured_clauses`; call `build_review_queue` from the worker; persist results; add a test that similar names are left unresolved **by the resolver**, not by the test author.
5. **Grounding:** keep 85%; add a category-consistency check or explicit `review_flag` when a grounded span fails a category rubric (the known gap).
6. **Handoff:** generate briefs from real `FlaggedConflict` / unverified / illegible triggers, not `filename.contains("Acme Distribution")`.

Until those paths exist, treat AITHENA’s portfolio as a **scripted demo** and the Python repo as a **single-document CUAD extractor with an unused conflict library**.
