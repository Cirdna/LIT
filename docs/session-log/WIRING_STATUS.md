# Wiring status after Phase 2

Two things changed: the webapp can now get its `extracted_fields` from the real
Python pipeline reading the uploaded file, and `conflict.py` is reachable from
that pipeline instead of only from its own tests.

Both were traced end-to-end against a real PostgreSQL 16 and the real Fastify
API. **One substitution was necessary**: this machine has no
`OPENROUTER_API_KEY`, so Stage 2b's hosted model reply was scripted, exactly as
`tests/test_pipeline_integration.py` does it. Every other stage ran for real —
Stage 1 ingest/render, Stage 2a native text extraction, Stage 3 reconciliation
and the 85% threshold, Stage 4 schema, join-key population, both conflict
passes, the HTTP upload, and every database write. The hosted call itself is
untouched by this pass and is separately evidenced in `HANDOFF.md` §2.5.

---

## FIX 1 — real extraction into the webapp: **PASS**

### Where data stops being stub and starts being real

| Boundary | File / line | State |
|---|---|---|
| Fabricated fields (old path) | `webapp/scripts/stub-worker.ts` `fieldPlan()` L286 | still exists, now gated |
| Stub gate | `webapp/scripts/stub-worker.ts` L425 `if (!STUB_ALLOW_ANY && !DEMO_FILENAMES.has(doc.filename)) return { skipped: true }` | **stub can no longer answer for a real upload** |
| Real read of the file | `webapp/scripts/real-worker.ts` `processDocument()` → `storage.resolveKey(doc.storageKey)` | real |
| Real pipeline call | `webapp/scripts/real-worker.ts` `runPython(["-m","pdf_analyzer.cli","analyze",…,"--contract-id",documentId])` | real |
| CUAD → webapp fields | `webapp/scripts/lib/cuad-map.ts` `mapAnalysisToFields()` | real |
| Confidence derived, not chosen | `cuad-map.ts` `toRow()`: `v.is_grounded ? "verbatim" : "unverified"`, `vlmAgreement = score/100` | real Stage 3 output |
| Row insert | `real-worker.ts` `prisma.extractedField.create` | real |

### Traced run

Upload of two born-digital PDFs through `POST /api/documents`, then `npm run worker`:

```
> job d1c463da… doc=e390f61e…   fields: 3 real (0 unverified), counterparty=Acme Distribution Corp
> job a3a0ae40… doc=6e8995fc…   fields: 2 real (0 unverified), counterparty=Acme Distribution Corp
```

Rows actually in `extracted_fields`:

| filename | field_key | tier | stage-3 score | clause label | value (truncated) |
|---|---|---|---|---|---|
| Acme Master Supply Agreement.pdf | `liability_cap` | verbatim | 1.000 | Clause 9.2 (page 1) | "9.2 Limitation of Liability. The aggregate liability…" |
| Acme Master Supply Agreement.pdf | `notice_period` | verbatim | 1.000 | Clause 3.2 (page 1) | "3.2 Either party may prevent renewal by giving 60 da…" |
| Acme Master Supply Agreement.pdf | `party_a` | verbatim | 1.000 | Preamble (page 1) | "Meridian Retail Pte Ltd and Acme Distribution Corp." |
| Acme Statement of Work 4.pdf | `party_a` | verbatim | 1.000 | Preamble (page 1) | "Meridian Retail Pte Ltd and Acme Distribution Corp." |
| Acme Statement of Work 4.pdf | `term_end` | verbatim | 1.000 | Clause 2.4 (page 1) | "2.4 Term. This Statement of Work expires on 31 Decem…" |

`model_version` on every row is `pdf_analyzer.cli@0.1.0`, not `stub-worker@0.1.0`.
`GET /api/documents/:id` returns those fields with `status: ready` and the real
`counterparty`. `GET /api/integrity` returns `{"ok":true}` — no dangling
anchors, no invalid tiers, no null value missing an absence reason.

The `unverified` branch was verified separately on a mapped field whose quote is
not on the page: tier `unverified`, score `0.000`, value kept as the model's
claim so a reviewer can see what failed verification.

### Stub containment (confirmed, not assumed)

Running `npm run stub` against those same two uploads:

```
> job 208829b8… doc=f02f582a…
  skipped 208829b8…: not seeded demo corpus; requeued for the real worker
```

`extracted_fields`, `document_pages`, `conflicts` all still `0` afterwards. The
stub only fabricates for the eight seeded `scripts/corpus.ts` filenames, or with
`STUB_ALLOW_ANY=1` set deliberately. The real worker also deletes any prior
`text_lines` / `document_pages` / `document_segments` / `extracted_fields` /
`calendar_events` / `document_text` for a document before writing, so stub
geometry cannot sit next to real extraction on the same record.

---

## FIX 2 — conflict library connected: **PASS**

### What was empty before

`pipeline.analyze_document` left `counterparties`, `assets`,
`contract_family` and `structured_clauses` at `[]`/`None`, so every grouping
pass had nothing to group. Now, in `src/pdf_analyzer/pipeline.py`:

- `_counterparties_from_findings()` — builds join keys from the extracted
  `parties` category, `ResolutionMethod.EXACT_NAME` only. Ungrounded
  extractions are skipped: a key built from text Stage 3 could not find on the
  page is how a phantom conflict starts.
- `_structured_clauses_from_findings()` — puts the ten CUAD restrictive
  categories into `StructuredClause` form (nine clause types; both no-solicit
  categories collapse onto one).
- `scan_for_conflicts()` — the entry point to `build_review_queue`, which runs
  the party and asset passes independently.
- `analyze_document(..., contract_id=...)` and `cli analyze --contract-id` — so
  a flagged pair names webapp document UUIDs.
- `cli conflicts <dir> --output queue.json` — deterministic scan over stored
  analyses, no model call.

### Traced run

Two real uploads sharing an exactly-named counterparty ("Meridian Retail Pte
Ltd" quoted identically in both preambles), one holding an MFN clause and the
other pricing terms:

```
Scanned 2 analyses (2 party groups, 0 asset groups); flagged 2 conflict(s)
! wrote 1 real conflict row(s) from the library path
```

The row in `conflicts`, served by `GET /api/conflicts` and rendered by the
Conflicts screen:

> **mfn_trigger** · high · Counterparty 'Meridian Retail Pte Ltd' holds an MFN in
> Acme Master Supply Agreement.pdf while pricing terms were agreed in Acme
> Statement of Work 4.pdf over an overlapping period; the MFN may be triggered.
> (party.mfn_trigger, deterministic; Clause 5.1 p1 vs Clause 2.3 p1)

`GET /api/portfolio/summary` reports `conflictsFound: 1`. This is **not** the
filename-gated Acme/Borden stub conflict — `maybeRaiseExclusivityConflict` only
fires for two seeded demo filenames and was not involved.

The library reports one pair per shared counterparty, so the same two clauses
arrived twice (2 flagged → 1 row). `real-worker.ts` `scanForConflicts` keeps one
row per `(conflict_class, document pair)`; the full detail stays in
`storage/tmp/conflict-queue.json`.

### New tests

`tests/test_conflict_wiring.py` (6 tests) proves the wire from real pipeline
output rather than hand-built fixtures: join keys populated with `EXACT_NAME`,
comparable clauses built, an ungrounded party span refused as a join key, the
MFN rule firing deterministically on two analyses, near-miss names staying
unmerged, and the asset pass documented as inert. Full suite: **69 passed**
(was 63).

---

## Still stub, still missing

Honest list. None of this was in scope for this pass.

1. **The hosted VLM call was not exercised here.** No API key on this machine.
   Set `OPENROUTER_API_KEY` and re-run to close this.
2. **`asset_based_pass` cannot fire.** It matches `scope[].canonical_id`;
   nothing assigns canonical asset IDs. So the "two exclusive grants on one
   room" scenario still detects nothing on real data, even though exclusivity is
   extracted and marked `is_exclusive`. Needs an entity/scope resolution stage.
3. **Clause date ranges are open.** No stage parses a clause's active period, so
   `DateRange.overlaps` returns true for any pair. A flagged pair therefore
   proves a *relationship*, not a proven date collision. Every `FlaggedConflict`
   carries `requires_human_review`.
4. **Cumulative-commitment rule inert** — needs parsed quantities.
5. **Party keys are only as good as the quoted span.** Exact-name matching, by
   instruction. A `parties` span returned as prose ("This Agreement is between X
   and Y") yields one usable name and one junk key. Junk keys match nothing, so
   the failure mode is abstention, not a wrong pairing — but two real contracts
   will often *not* group. That is the main reason a real-world demo may show
   zero conflicts.
6. **`party_a` holds the whole parties span**; `party_b` gets a row only when
   the pipeline reports a second `parties` extraction. Splitting one quote into
   two named parties is name parsing, and a wrong split is a wrong fact.
7. **No page images, `text_lines`, or `document_segments` on the real path.** So
   click-to-jump highlighting does not work for real-pipeline documents; the
   page viewer shows "Page images are not ready yet" and citations show clause +
   page instead. `anchorLineIds` is `[]`, which is why integrity stays green.
8. **No `calendar_events` on the real path**, and `valueNormalized` is null — no
   date/amount parsing, so nothing feeds the 90-day calendar. Calendar
   derivation was explicitly out of scope.
9. **`provenanceQuality`, `ocrApplied`, `docType` left unset** — the analysis
   JSON does not report per-page extraction method or a document class, and
   guessing would be a claim.
10. **Fields with no CUAD equivalent get no row at all**: `signatories`,
    `initial_term`, `auto_renews`, `notice_deadline`, `termination_for_cause`,
    `cure_period`, `payment_amount`, `payment_schedule`, `escalation`,
    `cap_carve_outs`, `indemnities`. The UI renders "Not extracted." for these.
    Each document also carries a warning naming them.
11. **Misclassification is still invisible** (`HANDOFF.md` §6.8). A correctly
    grounded quote filed under the wrong category still scores `verbatim`.
    Out of scope by instruction.
12. **Handoff briefs are still only conflict/stub-triggered.** Not wired to the
    real queue.
13. **Deleting a document leaves its `storage/analysis/<id>.json`.** The scan
    skips conflicts whose contract IDs are not documents in the workspace, so a
    stale file cannot create a dangling row, but the file is not cleaned up.
14. **Run one worker at a time.** `npm run stub` and `npm run worker` claim from
    the same `jobs` table with `SKIP LOCKED`; running both races.

---

## Demoing the real path

```bash
cd webapp
docker compose up -d                 # Postgres 16
cp .env.example .env
npm install && npx prisma generate && npx prisma db push
npm run dev                          # terminal A — API on :3001

# terminal B
export OPENROUTER_API_KEY=sk-or-...          # required: Stage 2b is a hosted call
export PYTHON_BIN=../.venv/bin/python        # any interpreter that can import pdf_analyzer
export PDF_ANALYZER_PROMPT_MODE=granular     # accurate mode; 41 calls/page (HANDOFF.md §6.1)
npm run worker
```

Then upload through the UI (`cd frontend && npm run dev`, :5173) or:

```bash
curl -X POST http://127.0.0.1:3001/api/documents \
  -F "files=@contract-one.pdf" -F "files=@contract-two.pdf"
```

**Do not** run `npm run seed` / `npm run stub` for this demo — that is the
fabricated corpus, and the point of the real path is that nothing is fabricated.

### What the two documents need, to make FIX 2 visible

The conflict is real only if the deterministic rule can fire, so the pair must:

1. quote **the same counterparty name identically** in both preambles (exact-name
   matching — "Acme Corp" and "Acme Corp." will not group), and
2. have one contract containing an **MFN** clause and the other containing
   **pricing or revenue-sharing** terms.

The exclusivity/asset scenario will not raise anything yet — see limitation 2.

To reproduce the traced run without an API key, point `PDF_ANALYZER_ROOT` at a
directory holding a shim `src/pdf_analyzer/cli.py` that delegates to the real
package with a scripted VLM. That is a verification trick, not part of the
product, and nothing like it was added to the repo.
