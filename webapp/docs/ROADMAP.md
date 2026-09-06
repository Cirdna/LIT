# Build instructions: RAG chat, benchmarking, invoice reconciliation, UI updates

This is the implementation brief for the next phase of AITHENA, synthesised from
the two feature prompts (backend workflow + UI updates) **and reconciled against
what already exists in this repo**. Read it before starting: several requirements
already have foundations here, a few conflict with existing design decisions, and
one (invoices) contradicts current behaviour. Each section says exactly which
files to touch and what to reuse rather than rebuild.

Everything here obeys the seam contract in [INTEGRATION.md](INTEGRATION.md):
Node/React never call Python directly; work crosses the boundary through the
database + `./storage` + the `jobs` table.

---

## 0. Principles and global decisions

### 0.1 Non-negotiables that these features must not break
From [DESIGN.md](DESIGN.md) and the confidence system in
[confidence.tsx](../frontend/src/lib/confidence.tsx):

- **Every displayed value carries a confidence tier and a citation.** This
  extends to *new* surfaces: a RAG chat answer that asserts a contract value
  must show its tier + clause citation; a benchmark figure must say which
  contracts it averaged; an invoice match must cite the dates/parties it matched.
- **Never colour alone.** Confidence and risk use label + glyph + border, so
  they survive colour-blindness and a projector. Reuse `ConfidenceBadge`.
- **No percentages for *confidence*.** Scores become words (`reasonsFor`).
  Benchmark *deviation* is a different axis and may show numbers (see §2).

### 0.2 The existing confidence vocabulary vs the "quoted / inferred / NA" ask
The UI prompt asks for three labels (`quoted`→green, `inferred`→yellow,
`NA`→red). We already have a richer **5-tier** system that these three collapse
onto cleanly — do **not** replace it, derive from it:

| Coarse label (new) | Colour | Derived from existing tier / state |
|---|---|---|
| `quoted` | green (`ok`) | `verbatim`, `normalised` |
| `inferred` | yellow (`warn`) | `assembled`, `inferred` |
| `NA` | red (`alert`) | `unverified`, or absent (`absence_reason` set) |

Add a helper `coarseLabel(field): "quoted" | "inferred" | "NA"` in
[confidence.tsx](../frontend/src/lib/confidence.tsx). The five-tier badge stays;
the coarse label is a compact view + the axis the new filter (§UI-2) toggles on.

### 0.3 One LLM model config, not three hard-coded strings
The prompts name `google/gemini-1.5-pro`; the pipeline is standardised on
`google/gemini-3.8-flash` ([stage2_vlm.py](../../src/pdf_analyzer/stage2_vlm.py)
`DEFAULT_OPENROUTER_MODEL_ID`). Don't scatter model strings. Add env vars, read
in one place:

- `OPENROUTER_CHAT_MODEL` (default `google/gemini-3.8-flash`) — chat + invoice
  extraction reasoning.
- Keep `OPENROUTER_API_KEY` (already in `webapp/.env`, git-ignored).

> **Decision needed:** `gemini-1.5-pro` is older/slower/pricier than the
> pipeline's current model. Recommend defaulting chat to the same model the
> pipeline uses for consistency, overridable per deployment. Confirm before
> building.

### 0.4 A text-LLM helper (new, small)
The only OpenRouter client today is **vision** (`OpenRouterBackend`). Chat and
invoice extraction need **text/JSON** completions. Add a thin
`webapp/worker/llm.py` (or `src/pdf_analyzer/openrouter_chat.py`) that reuses the
same auth header, retry/back-off, and error type (`OpenRouterError`) as
[stage2_vlm.py](../../src/pdf_analyzer/stage2_vlm.py), exposing:

```python
def chat_json(system: str, user: str, *, schema_hint: str, model: str | None = None) -> dict
def chat_text(system: str, user: str, *, model: str | None = None) -> str
```

`chat_json` must request a JSON object and validate/parse defensively (the model
will occasionally wrap JSON in prose).

---

## 1. Feature — Interactive RAG chatbot (natural-language query)

Goal: a query loop over the contract portfolio with a clarification step, then
structured retrieval, then a synthesised, **cited** answer.

### 1.1 Retrieval strategy — structured-first, semantic-second (important)
Most portfolio questions ("which contracts auto-renew in the next 90 days",
"who has a notice period under 30 days", "show Globex agreements") are
**structured filters**, and we already store exactly the fields they need:
`extracted_fields.value_normalized` (`{date}`,`{days}`,`{months}`,`{amount}`),
`documents.doc_type` / `counterparty` / dates, `calendar_events`. So:

- **Phase 1 (no new infra): structured retrieval.** The LLM converts the (clarified)
  query into a structured JSON payload; a new query builder turns that into a
  parameterised SQL query over `documents` + `extracted_fields` +
  `calendar_events`. This is fast, exact, and reuses everything.
- **Phase 2 (new infra): semantic clause search.** For fuzzy questions ("find
  contracts about data-breach liability"), add `pgvector`: embed
  `document_text` (chunked per clause/segment) into a new `document_chunks`
  table with a `vector` column, embed the query, and ANN-search. Merge with the
  structured results. Ship Phase 1 first.

> **Decision needed for Phase 2:** embedding provider (OpenRouter/OpenAI
> `text-embedding-3-small` vs a local model) and whether to enable the `pgvector`
> extension on the demo Postgres. Until decided, Phase 1 fully satisfies the
> prompt's structured examples (dates, vendors, thresholds).

### 1.2 The clarification loop
1. `POST /api/chat` `{ conversationId?, message }`.
2. Send the message + a compact **schema description** (doc types, the 41 CUAD
   field keys from [domain.ts](../src/lib/domain.ts), the normalized value
   shapes) to `chat_json` with instructions to return one of:
   - `{ "status": "need_clarification", "question": "..." }` — too vague to
     search (missing vendor, date range, category, threshold); OR
   - `{ "status": "ready", "params": { docType?, counterparty?, fieldKey?,
     dateRange?, comparator?, threshold?, freeText? } }`.
3. If `need_clarification`, return the question; the client shows it and the user
   replies (keep turn history under `conversationId`).
4. If `ready`, run retrieval (§1.1), then a **synthesis** call that must answer
   **only from the retrieved rows** and attach, per cited value, its
   `documentId`, `fieldKey`, `clauseLabel`, and `confidenceTier`.

### 1.3 API + schema
- New route `webapp/src/routes/chat.ts`; register in
  [server.ts](../src/server.ts).
- Retrieval query builder in `webapp/src/lib/retrieval.ts` (whitelist the fields
  the LLM may filter on — never interpolate raw LLM text into SQL; use Prisma
  query objects / parameterised `$queryRaw`).
- Optional persistence: `chat_sessions` / `chat_messages` tables (Prisma). MVP
  may keep history client-side and stay stateless server-side.

### 1.4 Frontend
- New route `/chat` ([App.tsx](../frontend/src/App.tsx)) + nav entry
  ([Layout.tsx](../frontend/src/components/Layout.tsx)).
- Chat transcript; clarifying questions rendered distinctly; every answer value
  is a chip linking to `/documents/:id` and showing a `ConfidenceBadge`. Reuse
  `FieldValue` semantics — **no bare asserted values**.

### 1.5 Acceptance
- Vague query → a specific clarifying question (not a guess).
- "Notice period under 30 days" → returns the right contracts with citations.
- Every asserted contract value in an answer has a tier + clause link.
- No LLM free-text ever reaches SQL uninterpreted.

---

## 2. Feature — Dynamic portfolio benchmarking & risk scoring

Goal: measure a contract's term/date category against a **live** portfolio
average, with an absolute value, a deviation, and a traffic-light risk indicator.

### 2.1 What already exists (reuse, don't reinvent)
- `extracted_fields.value_normalized` already holds the comparable numbers:
  `renewal_term`→`{months}`, `notice_period_to_terminate_renewal`→`{days}`,
  `warranty_duration`→`{months}`; **term length** is `expiration_date −
  effective_date` (both `{date}`).
- The data model already anticipates this: `claim_type='benchmark'` +
  `value_normalized {assessment, reference_range}`, rendered by
  `benchmarkLine()` in [FieldValue.tsx](../frontend/src/components/FieldValue.tsx)
  and explained by `reasonsFor()`. The stub even emits one.
- Traffic-light colours already exist as `ok`/`warn`/`alert`
  ([tailwind.config.js](../frontend/tailwind.config.js)).

### 2.2 Service
Add `webapp/src/lib/benchmark.ts`:
1. **Dynamic average.** For a category, query all **active** contracts
   (`expiration_date >= today` or no expiry, `status in (ready,degraded)`),
   read the normalized number, compute the mean in real time. Skip
   `unverified`/absent values — a suspected error must not move the average.
2. **Comparison.** deviation = contractValue − mean; also percent deviation for
   the risk rule.
3. **Risk indicator (per prompt).** Green if value matches/better than average;
   Yellow for 1–15 % worse; Red for >15 % worse. "Worse" is category-specific —
   define direction per category (e.g. a *shorter* notice period is worse; a
   *longer* one is better). Encode direction in a small config map.

### 2.3 Output & the "no percentages" rule
Show the **absolute value and absolute deviation prominently** (as the prompt's
example does: "30 days (15 days below portfolio average of 45 days)"); the
percentage is the *risk* axis and may appear as secondary text. Render the
traffic light with **label + glyph**, not colour alone (reuse the badge idiom),
and keep it **visually distinct from the confidence badge** — risk and
confidence are different axes (a value can be confidently extracted yet risky).

### 2.4 API + frontend
- `GET /api/benchmark?category=<fieldKey>&documentId=<id>` → `{ value, unit,
  average, deviation, percentDeviation, sampleSize, risk: "green|yellow|red" }`.
- Optionally `GET /api/benchmark/summary` for a portfolio risk overview.
- In [DocumentDetail.tsx](../frontend/src/routes/DocumentDetail.tsx), show the
  risk chip next to benchmarkable fields; a value with `sampleSize < 3` should
  say "not enough data to benchmark" rather than show a misleading average.

### 2.5 Acceptance
- Average recomputes when contracts are added/removed (no cached constant).
- Direction handled correctly per category; sample size surfaced.
- Risk chip distinguishable from the confidence badge; absolute values dominant.

---

## 3. Feature — Invoice-to-contract matching & missing-contract detection

⚠️ **This contradicts current behaviour:** invoices are presently classified
`not_a_contract` and *excluded* from analysis (see `classify_doc_type` in
[worker/mapping.py](../worker/mapping.py) and the "Not analysed" state in
[DocumentDetail.tsx](../frontend/src/routes/DocumentDetail.tsx)). Invoices become
a **first-class document kind** with their own extraction + a reconciliation
pipeline. Contracts keep the CUAD path unchanged.

### 3.1 Schema (Prisma)
- Extend `documents.doc_type` to include `invoice` (stop routing invoices to
  `not_a_contract`; add an invoice detector in classification).
- New tables:
  - `invoice_headers` (documentId, billing_from, billing_to, invoice_date,
    invoice_number, currency, total, each with a confidence tier + anchor).
  - `invoice_line_items` (invoiceId, description, quantity, amount, anchorLineIds).
  - `invoice_matches` (invoiceId, contractDocumentId?, status, confidenceTier,
    reasons Json, matchedOn Json). `status` vocabulary below.
- `invoice_matches.status`: `HIGH_CONFIDENCE_MATCH`, `MISSING_CONTRACT_ROGUE`,
  `MULTIPLE_CONTRACTS_REVIEW`, `DATE_MISMATCH_REVIEW`. (Store as enums; render
  the human phrases from the prompt in the UI.)
- New `jobs.jobType = 'reconcile_invoice'` (the vocabulary already lists
  `ingest|extract|recompute_calendar|detect_conflicts`).

### 3.2 Invoice ingestion (worker)
Reuse Stage 1 render + Stage 2a text ([stage1_ingest.py](../../src/pdf_analyzer/stage1_ingest.py),
[stage2_ocr.py](../../src/pdf_analyzer/stage2_ocr.py)) exactly as contracts do,
then a **new invoice-extraction prompt** (via §0.4 `chat_json` over the page
text) that returns parties, invoice date, and line items — each with the
`exact_supporting_text` so the same grounding + anchor-line resolution
([worker/geometry.py](../worker/geometry.py)) applies. Write `invoice_headers` /
`invoice_line_items`.

### 3.3 Phase A — entity & scope verification
1. **Party match (fuzzy/semantic).** Reuse the entity-resolution ladder already
   designed in [schema.py](../../src/pdf_analyzer/schema.py)
   (`ResolutionMethod`: exact → normalized → fuzzy → llm_suggested) and the
   patterns in [conflict.py](../../src/pdf_analyzer/conflict.py). Match the
   invoice's billing party against `documents.counterparty` + the `parties`
   field. "Acme" vs "Acme LLC" → normalized/fuzzy match, flagged for review if
   below high tier.
2. **Scope map.** Compare invoice line items to contract scope (the
   `license_grant` / services / `revenue_profit_sharing` fields, or Phase-2
   semantic search over `document_text` from §1.1).
3. **Exceptions.** No aligning contract → `MISSING_CONTRACT_ROGUE`. Vendor has
   ≥2 plausible active contracts → `MULTIPLE_CONTRACTS_REVIEW`.

### 3.4 Phase B — temporal validation
Only when Phase A yields a single confident contract: check the invoice date
falls within `[effective_date, expiration_date]` of the matched contract (both
already extracted as `{date}`). In window → `HIGH_CONFIDENCE_MATCH`; outside →
`DATE_MISMATCH_REVIEW`. If either contract date is `unverified`/absent, do not
assert a pass — downgrade to review.

### 3.5 Frontend
- Invoices listed in the portfolio with a distinct kind + match-status pill
  (reuse `StatusPill` conventions).
- An invoice detail view showing extracted header/line items (with tiers +
  citations) and the reconciliation result: which contract, on what basis
  (party match method, scope overlap, date window), and the status phrase.
- A "rogue invoice" / "needs review" queue is a natural portfolio filter.

### 3.6 Acceptance
- Rogue invoice (no contract) → `MISSING_CONTRACT_ROGUE`.
- Vendor with two SOWs → `MULTIPLE_CONTRACTS_REVIEW`.
- In-window single match → `HIGH_CONFIDENCE_MATCH`; out-of-window →
  `DATE_MISMATCH_REVIEW`.
- Every match names its evidence (parties matched + how, date window checked).

---

## UI updates

### UI-1. Data-extraction labels & badges
Already implemented as the 5-tier `ConfidenceBadge`. To satisfy the prompt: add
`coarseLabel()` (§0.2) and render the coarse quoted/inferred/NA chip where a
compact tag is wanted, keeping the full badge on the field detail. Do **not**
drop glyphs for colour-only. Files:
[confidence.tsx](../frontend/src/lib/confidence.tsx),
[FieldValue.tsx](../frontend/src/components/FieldValue.tsx).

### UI-2. Multi-select label filter (per contract)
In [DocumentDetail.tsx](../frontend/src/routes/DocumentDetail.tsx) add a
multi-select over `["quoted","inferred","NA"]` that filters `doc.fields` by
`coarseLabel`. Decision: while a filter is active, the "always show every group"
rule is relaxed — hide non-matching fields and show a per-group "n hidden by
filter" hint so the reader knows data was filtered out (never silently).

### UI-3. Standardised date format `DD MMM YYYY`
[format.ts](../frontend/src/lib/format.ts) already uses native `Intl`
(`en-GB`, `month:"short"`) → "19 Nov 2026" (matches the prompt's "use existing
lib or native Intl"; no date lib is installed, so native is correct). Two tasks:
1. Change `day:"numeric"` → `day:"2-digit"` for strict `DD` ("01 Nov 2026").
2. Audit the frontend for any date rendered **not** via `formatDate` (stray
   `toLocaleDateString`, `new Date().toString()`, raw ISO) and route all through
   it. `formatDate` is the single source of truth.

### UI-4. Forward-looking action calendar filters
The calendar is already forward-looking with bands
([Calendar.tsx](../frontend/src/routes/Calendar.tsx),
[format.ts](../frontend/src/lib/format.ts) `bandFor`) and a 90/180/all range;
the backend route already supports forward `to`/`from`
([calendar.ts](../src/routes/calendar.ts)). To match the prompt:
1. Add a **60-day** band: extend `Band`, `bandFor`, `BAND_LABELS`, `BAND_ORDER`
   in [format.ts](../frontend/src/lib/format.ts) (currently
   overdue/this_week/next_30/in_90 — split in_90 into next_60/in_90).
2. Add quick-filter chips `today · this week · 30 · 60 · 90 days` that set the
   horizon (replace/augment the 90/180/all control). Keep the strict
   forward-from-today query (`currentDate → currentDate + N`).
3. Surface a compact **"upcoming actions" widget top-right** on the portfolio
   dashboard ([Portfolio.tsx](../frontend/src/routes/Portfolio.tsx)) linking to
   the full calendar — the prompt asks for the dashboard corner, which we don't
   have yet (today it's a separate page).

---

## Sequencing (suggested milestones)

1. **UI quick wins** (UI-1, UI-3): coarse label + strict date format. Low risk,
   immediately visible.
2. **Benchmarking** (Feature 2 + its risk chip): pure computation over data we
   already store; no new infra.
3. **Calendar filters + dashboard widget** (UI-4).
4. **RAG chat Phase 1** (structured retrieval + clarification loop); Phase 2
   (`pgvector`) after the embedding decision.
5. **Invoices** (Feature 3): the largest — new schema, extraction, two-phase
   reconciliation, and frontend. Do last; it depends on the fuzzy-match and
   (ideally) semantic-search groundwork from chat.

## Decisions to confirm before building
1. **Chat/extraction model** — default to the pipeline's current model, or the
   prompt's `gemini-1.5-pro`? (§0.3)
2. **Semantic search** — enable `pgvector` and pick an embedding model, or ship
   structured-only retrieval first? (§1.1)
3. **Benchmark "worse" direction** per category, and the exact 1–15 %/>15 %
   thresholds — confirm the traffic-light rule matches your risk appetite. (§2.2)
4. **Invoice storage** — extend `documents` with `doc_type='invoice'` (recommended)
   vs a separate table. (§3.1)

## Testing expectations
- Python: unit tests for invoice extraction mapping, party fuzzy-match, and
  temporal validation (mirror the existing `tests/` style; stub the LLM).
- Node: retrieval query-builder tests (LLM params → SQL, injection-safe),
  benchmark math (average/deviation/direction/sample-size), invoice status
  resolution.
- Frontend: type-check + build; verify no date bypasses `formatDate`.
- Keep `GET /api/integrity` green throughout.
