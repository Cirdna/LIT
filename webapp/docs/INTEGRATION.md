# Integration contract: Node ⇄ Python worker

This is the seam. **Node and Python never call each other.** They communicate
only through the PostgreSQL database and the shared `./storage` directory. Either
side can be developed, restarted, or replaced independently. The stub worker
([`scripts/stub-worker.ts`](../scripts/stub-worker.ts)) and the real Python
worker are interchangeable with no API changes.

- **Everything the pipeline writes is a fact about a document** (pages, lines,
  fields, calendar events, status).
- **Everything Node writes is a fact about a user action** (upload,
  acknowledge, dismiss, handoff).

Neither side writes the other's tables. Prisma owns the schema and migrations;
Python treats the schema as **read-only truth** and talks to it with `psycopg`
and plain SQL.

---

## 1. Environment the worker needs

| Thing | Value |
|---|---|
| `DATABASE_URL` | Same Postgres the API uses (see `.env`). |
| `STORAGE_ROOT` | Same directory the API uses. Defaults to `./storage`. |

## 2. Storage layout (§5)

```
storage/
  originals/<sha256>.<ext>            # uploaded file, deduplicated by content hash — Node writes, worker reads
  ocr/<sha256>.pdf                    # OCR'd PDF with text layer — worker writes
  pages/<document_id>/p<N>@<dpi>.png  # rendered page images — worker writes
  tmp/
```

The worker resolves the original from `documents.storage_key` (a path relative
to `STORAGE_ROOT`). Page images must be written to the path stored in
`document_pages.image_key`, and Node serves them verbatim.

## 3. Claiming a job (§6)

A `jobs` row is created by Node on upload (`job_type = 'ingest'`,
`status = 'queued'`). Claim exactly one with `SKIP LOCKED` — safe with multiple
workers, no external broker:

```sql
UPDATE jobs SET status='running', started_at=now(), attempts=attempts+1
WHERE id = (
  SELECT id FROM jobs
  WHERE status='queued'
  ORDER BY created_at
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
RETURNING *;
```

Update `stage` (human-readable, e.g. `'ocr page 4/12'`) and `progress` (0..1) as
you go — the frontend polls `GET /api/documents/:id/status` every 2 seconds and
renders the string. On success set `status='done'`, `finished_at=now()`. On
failure set `status='failed'`, `error=<message>`.

**Reaper (already implemented in the stub, replicate it):** a job stuck in
`running` for more than 15 minutes is requeued (up to 3 attempts), then marked
`failed`. A failed document must never block the batch.

## 4. The worker's responsibilities, in order

1. Claim a `queued` job with `FOR UPDATE SKIP LOCKED`.
2. Read the original from `storage/originals/<sha256>`.
3. Set `documents.status = 'processing'`.
4. Write `document_pages`, `text_lines`, `document_text`, and page PNGs to
   `storage/pages/`. Also write `document_segments` (clause structure).
5. Write `extracted_fields` — every row with a `confidence_tier`, and where a
   value exists, at least one entry in `anchor_line_ids` **unless the tier is
   `inferred`**.
6. Compute and write `calendar_events`.
7. Update `documents.status` to `ready`, `degraded`, or `failed`, set
   `provenance_quality`, `page_count`, `ocr_applied`, `doc_type`,
   `counterparty`, `warnings`, `pipeline_version`, and `processed_at`.
8. Mark the job `done`.

## 5. Controlled vocabularies

| Column | Allowed values |
|---|---|
| `documents.status` | `queued` `processing` `ready` `degraded` `failed` `unsupported` |
| `documents.provenance_quality` | `exact` `degraded` `text_only` |
| `documents.doc_type` | `nda` `lease` `msa` `distribution` `employment` `other` `not_a_contract` |
| `document_pages.extraction_method` | `pdf_text` `ocr` `docx` `plain_text` |
| `document_pages.page_role` | `cover` `operative` `signature` `schedule` `exhibit` `other` |
| `document_segments.confidence` | `structural` `heuristic` `fallback` |
| `extracted_fields.confidence_tier` | `verbatim` `normalised` `assembled` `inferred` `unverified` |
| `extracted_fields.claim_type` | `contract_text` `computed` `benchmark` |
| `extracted_fields.absence_reason` | `not_present` `not_found` `illegible` (required when value is NULL) |
| `calendar_events.event_type` | `expiry` `auto_renewal` `notice_deadline` `payment_due` |
| `jobs.status` | `queued` `running` `done` `failed` |

### `value_normalized` shapes

Store verbatim and normalized **separately, always**. The verbatim string is
verified against the anchor lines; the normalized value is what the calendar
computes with.

```json
{"date": "2026-03-15"}
{"days": 60}
{"months": 12}
{"amount": 50000, "currency": "SGD"}
{"value": true}
```

### Bounding boxes

`text_lines.bbox` is `{x0, y0, x1, y1}` in **PDF points with a top-left origin**.
Page images are rendered at `document_pages.image_dpi`; the UI scales by
`dpi / 72`. Keep this consistent or the overlay will not sit on the words.

## 6. Invariants Node relies on — and validates

`GET /api/integrity` reports violations of all of these (should be empty):

- Every `anchor_line_ids` entry resolves to an existing `text_lines` row for the
  same document.
- `confidence_tier` is one of the five defined values.
- A field with `value_verbatim = NULL` has a non-null `absence_reason`.
- `calendar_events.action_by_date <= event_date` where both are present.

## 7. Boundary states the pipeline must signal (§9)

| Situation | What to write |
|---|---|
| Not a contract | `doc_type = 'not_a_contract'`, do **not** write contract fields. |
| Page below OCR quality floor | The field for that page: `value_verbatim = NULL`, `absence_reason = 'illegible'`. |
| Extraction passes disagree | Low `consistency_score`; put the competing readings in `value_normalized.competing = [a, b]`. |
| Quoted text not found in cited clause | `confidence_tier = 'unverified'` — a fabrication signal. |
| Value has no cap / clause absent | `absence_reason = 'not_present'` (distinct from `'not_found'`). |

## 8. Cross-document conflicts and handoffs

The pipeline (or a `detect_conflicts` job) writes `conflicts` rows referencing
two or more `document_ids` and the `field_ids` in tension. When a boundary is
tripped, it should also write a `handoff_briefs` row with a **specific** question
naming the clauses — see [`src/lib/handoff.ts`](../src/lib/handoff.ts) for the
shape Node expects in `established` (an array of
`{label, detail, citation, confidenceTier}`).
