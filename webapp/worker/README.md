# The real ingestion worker

This is the Python worker that replaces the Node **stub worker**
([`scripts/stub-worker.ts`](../scripts/stub-worker.ts)) with genuine extraction.
It runs the `pdf_analyzer` pipeline (the rest of this repo) against uploaded
contracts and writes the results into the same PostgreSQL schema the API reads.

It obeys the seam contract in [`docs/INTEGRATION.md`](../docs/INTEGRATION.md) to
the letter: it never calls the Node API, only the database and `./storage`. The
stub and this worker share the `jobs` table, so they are interchangeable — run
the stub for a no-API-key demo, run this for real output.

```
uploaded PDF ─▶ Stage 1 render ─▶ Stage 2a words + 2b VLM ─▶ Stage 3 reconcile
                                                                     │
                                          CUAD-41 findings ──────────┘
                                                     │
                                    crosswalk (worker/mapping.py)
                                                     ▼
        document_pages · text_lines · extracted_fields · calendar_events
```

## What it does per job

1. Claims one `queued` ingest job with `FOR UPDATE SKIP LOCKED`.
2. Reads the original from `storage/originals/<sha256>` and runs Stages 1–4.
3. Groups word boxes into `text_lines` (bbox in **PDF points**), copies the
   rendered page PNGs into `storage/pages/<id>/`, and writes `document_text`.
4. Maps the 41 CUAD findings onto the 21 webapp fields, resolves each value's
   anchor lines, and writes `extracted_fields`.
5. Computes the forward calendar from the extracted dates.
6. Sets the document's status, provenance, doc-type, counterparty and warnings.
7. Marks the job `done`. A 15-minute stall reaper requeues (≤3 attempts).

## Run it

From the **repo root**, once:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,webapp]"          # pipeline + psycopg
export OPENROUTER_API_KEY=sk-or-...      # or put it in the repo-root .env
```

Then from **`webapp/`** (so `webapp/.env` — DATABASE_URL, STORAGE_ROOT — is found):

```bash
python -m worker                 # poll forever
python -m worker --once          # process a single job then exit
python -m worker --prompt-mode granular   # accurate mode (see below)
```

Point the frontend/API at the same database and upload a PDF; the portfolio
shows live progress exactly as it does with the stub.

## Accuracy vs. cost

`--prompt-mode single` (default) asks about all 41 categories in one call per
page: cheap, and the pipeline's default. `--prompt-mode granular` asks each
category separately (41 calls/page) and is materially more accurate
(HANDOFF.md §2.7, §6.1) at ~41× the API volume. Use granular for a real review;
single for a quick demo.

## The CUAD → webapp mapping

The webapp displays the pipeline's own vocabulary: **all 41 CUAD categories**,
organised into the document-detail screen's eight groups (the seven original
lifecycle groups + **IP & Licensing**). So [`mapping.py`](mapping.py) is a direct
projection — one `extracted_fields` row per CUAD category, `field_key` = the CUAD
key — not a lossy crosswalk. The grouping lives in
[`webapp/src/lib/domain.ts`](../src/lib/domain.ts) (and its frontend mirror).

Each category becomes a field like so:

| Pipeline finding | webapp field |
|---|---|
| Grounded quote, left as text | tier `verbatim`, value = the page span |
| Grounded date/duration category, parsed | tier `normalised`, `value_normalized` set |
| Present but the quote was **not** found on the page | tier `unverified` (suspected error) |
| No extraction on the page for this category | value `NULL`, `absence_reason='not_found'` |

Only a handful of categories carry a parsed machine value:
`agreement_date` / `effective_date` / `expiration_date` → `{date}`,
`renewal_term` / `warranty_duration` → `{months}`,
`notice_period_to_terminate_renewal` → `{days}`. Everything else is a grounded
clause quote (or absent). The **calendar** is derived from the expiration date,
renewal term, and notice period — the notice period sets the action-by date
ahead of expiry. `unverified` values never feed the calendar.

## Known limitations (inherited from the pipeline)

- **No cross-document conflicts / handoffs yet.** `conflict.py` exists but is
  unfed — nothing extracts the entity-resolution and structured-clause data it
  needs (HANDOFF.md §6.5). The Conflicts and Handoffs screens stay empty for
  real uploads until that stage is built. The worker never fabricates a
  conflict.
- **Coverage is bounded by the 21-field view.** The pipeline finds all 41 CUAD
  categories; the extra 20+ (governing law, IP assignment, audit rights, …) are
  extracted but not surfaced, because the frontend's field groups are fixed.
  Surfacing them is a frontend change, not a worker one.
- Accuracy is validated on two born-digital US contracts (HANDOFF.md §6.4); the
  scanned/OCR path is wired but lightly exercised.
