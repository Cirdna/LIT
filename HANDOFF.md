# Handoff — PDF Contract Analyzer

Every change made, what testing established about it, and what is still
broken or unverified. Written to be picked up cold.

**Status:** working end-to-end on two real contracts. 63 tests pass.
**Biggest open risk:** validated on two documents, one of which has expert
annotations. Treat accuracy numbers as indicative, not established.

---

## 1. What this is

A five-stage pipeline that extracts the 41 CUAD contract clause categories
from a PDF and grounds every extraction back to exact coordinates on the
page, so a reviewer can click a finding and jump to the text.

```
Stage 1  ingest      DOCX/HTML/RTF -> PDF (LibreOffice/Playwright), render pages @300 DPI
Stage 2a text        native PDF text layer -> word boxes  (Tesseract only if no text layer)
Stage 2b VLM         per-category extraction via OpenRouter (or local Qwen/InternVL)
Stage 3  reconcile   align VLM text to page words, compute bbox, score confidence
Stage 4  schema      emit answers for all 41 categories + conflict-detection fields
Stage 5  frontend    React/pdf.js viewer, click-to-jump with bbox highlight
```

The architectural premise worth preserving: **Stage 2b and Stage 2a are
independent sources, and Stage 3 checks one against the other.** That is the
anti-hallucination guarantee. If a single model ever produces both the
extraction and its grounding evidence, that check becomes circular and the
guarantee is gone while the numbers still look fine.

### Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export OPENROUTER_API_KEY=sk-or-...        # or put it in .env (git-ignored)

python -m pdf_analyzer.cli analyze contract.pdf \
  --output result.json --prompt-mode granular
```

`--prompt-mode granular` is the accurate mode and what all results below use.
It is **not** the default (`single` is), because it costs 41x more API calls.
See §6.1.

---

## 2. Changes, in order, with what testing showed

### 2.1 Initial build — `81c0d81`
26 files, ~2,050 lines. All five stages, 15 tests.

**Untested at this point.** No contract had been run through it.

---

### 2.2 Four bugs found by running it on a real contract — `708ffc0`

First run against the Armstrong Flooring IP Agreement (40 pages, real CUAD
corpus). Every one of these was invisible until real data hit it.

| bug | symptom | fix |
|---|---|---|
| MPS buffer limit | `Invalid buffer size: 14.43 GiB` loading Qwen | load without `device_map` on MPS/CPU |
| Attention blowup | tried to allocate **55 GiB** for one page | cap image pixels fed to VLM (`--max-pixels`) |
| Prompt returned `[]` | every page, incl. pages with obvious clauses | drop the "if nothing, return `[]`" escape hatch; add a worked example |
| Aligner window | clauses below the top of a page scored 0.00 with empty bbox | search whole page for anchor, keep best-recall alignment |

**Test result:** verified extractions on a 5-page subset went **7/14 → 13/14**.
The prompt bug was diagnosed by a control test — asked to simply *describe* a
page, the model transcribed it correctly, proving vision worked and
instruction-following was the failure.

---

### 2.3 Evidence-mass scoring — `cf73bed`

**Problem:** recall alone can't tell a real match from a spurious one. The
phrase `"Arizona and Company"` scored a perfect 1.00 against unrelated text
(`"Arizona Copyright Grant. Subject to the terms and conditions..."`) because
recall normalizes by the phrase's own tokens — a phrase of page-common words
recalls 100% of itself off anything.

**Fix:** `score = recall × min(1, evidence_mass / 2.0)`, where evidence mass
sums each matched token's page-relative IDF. Page-relative matters: a term can
be globally rare yet ubiquitous in one contract ("Arizona" is a party name
here), and such a term cannot pin down a location.

**Test result** on real pages:

| case | mass | before | after |
|---|---|---|---|
| "Arizona and Company" (spurious) | 1.54 | 1.00 ✗ | **0.77 flagged** ✓ |
| Delaware governing law | 13.69 | 1.00 | 1.00 ✓ |
| "December 31, 2018" | 2.60 | 1.00 | 1.00 ✓ |

Verified 13/14 → 9/14 — and that drop is correct: all 4 newly-flagged items
were noise (2 section headings misfiled as `document_name`, an SEC footer
date, and the spurious match).

**Caveat:** the 2.0 threshold is calibrated, not derived. Obvious cases
separate hugely (13.69 vs 0.79) but short phrases cluster in a narrow band
(1.54 bad vs 1.77 junk-but-passing). Expect it to need adjustment on a
different corpus.

---

### 2.4 Cross-contract conflict schema — `e571ff4`

Implements the conflict-detection spec. A flat per-contract schema cannot
answer "does this contradict something else we signed" — two leases for the
same room are each individually valid; the conflict lives in the relationship.

Added:
- **Join keys** — `counterparties`, `assets`, `contract_family`, each an
  `EntityLink` with a resolution method and a confidence tier derived from it
  (registration number → high, fuzzy name → medium, LLM-suggested → low and
  always human-reviewed). `canonical_id=None` is a first-class abstention.
- **`StructuredClause`** for the nine conflict-capable clause types, with
  comparable scope tags, date ranges, and quantities.
- **`ClauseRef` supersession**, so an amendment reads as an intended update
  rather than a conflict.
- **`conflict.py`** — party-based and asset-based passes run *independently*.
  All rules deterministic; no model call in the search path.

**Test result:** 9 tests covering the spec's judging scenario — planted asset
conflict ✓, planted MFN trigger ✓, near-miss entity pair correctly **not**
merged ✓, unit-mismatch abstention ✓, amendment suppression ✓.

> **Never run on real data.** See §6.5.

Also closed two gaps the ground truth exposed: all 41 categories now always
get an answer (absence is expressible), and `evidence_status` carries legal
semantics (direct/derived/inferred/unresolved) rather than being a readout of
the OCR score. The OCR signal moved to a separately-named `OcrVerification`.

---

### 2.5 Hosted VLM backend — `580b1cf`, `940a08b`

**Problem:** local Qwen2.5-VL-7B was the accuracy ceiling, not just slow. It
missed clauses whose exact text was sitting in the OCR, misfiled others, and
on some pages abandoned reading entirely to enumerate all 41 categories with
`"not specified"` placeholders.

**Test result — same 20 pages, same ground truth:**

| | Qwen2.5-VL-7B (local) | gemini-3.8-flash (hosted) |
|---|---|---|
| Runtime | **84 minutes** | **70 seconds** |
| Correct, right page (of 17) | 9 | **12** |
| True misses | 6 | **3** |
| Placeholder junk rows | 64/183 (35%) | **0** |

`torch`/`transformers` moved to an optional `[local]` extra — a hosted install
skips ~2.5 GB of wheels. Local backends remain available via `--backend qwen`.

---

### 2.6 Granular prompt mode — `1848022`

One API call **per category** (41/page) instead of one call covering all 41.
Rationale: the single-shot prompt forces a ranking when a clause satisfies
several categories at once, so it files the ownership paragraph under
`ip_ownership_assignment` and silently drops `joint_ip_ownership` and
`covenant_not_to_sue`.

**Test result — and this is the one that went against the hypothesis:**

| | single-shot | granular v1 |
|---|---|---|
| Correct (of 16 GT anchors, pages 1–10) | **11** | 10 |
| The 3 misfiling targets it was built to fix | 0 recovered | **0 recovered** |
| `non_disparagement` | ✓ found | **lost** |

Granular was *worse*. Asked in isolation, the model answered "no" to text it
had already located during the 41-way sweep. The structural fix was real (a
unit test proves the same clause lands under two categories when asked twice)
but useless if the isolated question can't find the clause at all.

Diagnosis: the 41-category list was doing double duty as *context*. Stripping
it removed noise **and** signal.

---

### 2.7 Category definitions + loosened conservatism — `56d4913`

Two changes to rescue granular mode:
1. Give every category a real definition plus the wording contracts actually
   use ("Non-Disparagement" → look for *tarnish*, *disrepute*).
2. Drop "do not force a match." Stage 3 already verifies everything; that is
   where over-eager matches should be caught, not in the extraction prompt.

**Test result — pages 1–10, same ground truth:**

| | correct | false positives |
|---|---|---|
| single-shot | 11/16 | 0 |
| granular v1 (bare labels) | 10/16 | 0 |
| **granular v2 (+definitions)** | **16/16** | **0** |

All five previously-missed categories recovered —
`affiliate_license_licensor`, `post_termination_services`,
`uncapped_liability`, `covenant_not_to_sue`, `third_party_beneficiary` — each
a 100%-grounded verbatim match to the ground truth's exact citation. 36/36
extractions grounded; the loosened prompt produced *more correct* findings,
not a flood of weak guesses.

**Out-of-sample check (pages 11–20, not used to build the definitions):**
granular 3/3 GT anchors vs single-shot 2/3. Both correctly avoided the
`change_of_control` false-positive trap. Smaller margin, same direction.

---

### 2.8 Native PDF text layer — `fa633e9`

**Problem found while reviewing flagged results:** three `expiration_date`
extractions on a domain-name table scored 37–63% and were flagged. Cause was
not accuracy — Tesseract read the table **column-major** (every domain, then
every date) while the VLM read it **row-major**. They could never align.
Separately, Tesseract differed from the PDF's own text on 1–2% of words per
page (`WHEREOF` → `WHEREOPF`). All 40 pages were born-digital: we were
OCR-ing a document that already contained exact text.

**Fix:** read `page.get_text("words", sort=True)`; fall back to Tesseract only
for pages with no text layer. Coordinates rescale from PDF points into the
same pixel space the render uses, derived from actual `PageRender` dimensions
rather than an assumed DPI — so `OcrWord`'s contract is unchanged and nothing
downstream needed touching.

**Test result** — same VLM output re-grounded under both extractors (no new
API calls, isolating the change):

| | improved | regressed | unchanged |
|---|---|---|---|
| 49 extractions, both page ranges | **5** | **0** | 44 |

The three table extractions went 63→94.7, 50→100, 37→100 — flagged to
verified. Zero regressions.

---

### 2.9 Official CUAD descriptions — `b6194de`

**Problem — provenance.** The definitions in §2.7 were written from my own
recollection, not from any source, and the commit overstated them as "mined
from expert ground truth." The Chase contract then produced a false positive
tracing directly to that: my Covenant Not to Sue said "or on bringing claims
against them", while CUAD's actual description says "...for matters
**unrelated to the contract**". Missing that qualifier, it matched a routine
service-interruption liability waiver.

**Fix:** fetched `category_descriptions.csv` from the Atticus Project's CUAD
repo and generated the descriptions programmatically. Split into two dicts
with distinct provenance:

- `CUAD_DESCRIPTIONS` — verbatim CUAD, marked *do not reword*
- `CUAD_TRIGGER_PHRASES` — ours, empirically observed in real contracts

Source CSV archived in `reference/` so the mapping stays auditable.

**Test result — Chase contract (precision):**

| | before | after |
|---|---|---|
| Extractions | 25 | 21 |
| Known false positives | 4 | **0** |
| True positives lost | — | **0** |

Four FPs removed. Two I had flagged (`covenant_not_to_sue`,
`no_solicit_of_employees`); **two I had not noticed** — `ip_ownership_assignment`
on a statement of *existing* ownership (official scope requires IP to *become*
the counterparty's), and `termination_for_convenience` on revoking a *license*
rather than terminating *the contract*.

**Test result — Armstrong pages 1–10 (recall did not regress):**

| | my definitions | official CUAD |
|---|---|---|
| GT anchors correct | 16/16 | **16/16** |
| Total extractions | 36 | 34 |
| Grounded | 100% | 100% |

The 3 dropped were noise (a *different* contract's date, a license grant
misfiled as anti-assignment, a grant clause misfiled as expiration). One
genuine **addition**: `ip_ownership_assignment` p9, which fits the official
"upon the occurrence of certain events" wording better than mine did.

---

## 3. Current accuracy summary

**Armstrong Flooring IP Agreement** (40pp, expert annotations supplied):

| pages | correct | false positives | grounded |
|---|---|---|---|
| 1–10 | 16/16 GT anchors | 0 | 34/34 (100%) |
| 11–20 | 3/3 GT anchors | 0 | 10/13 * |

\* the 3 ungrounded were the domain-table rows, since fixed by §2.8.

**Chase Affiliate Agreement** (12pp, no annotations; manually verified):

| extractions | grounded | known FPs | mean score |
|---|---|---|---|
| 21 | 21 (100%) | 0 | 99.3 |

---

## 4. Test suite — 63 tests

| file | n | covers |
|---|---|---|
| `test_openrouter_backend.py` | 22 | key handling, image downscaling, retry/fail-fast, granular fan-out |
| `test_stage3_reconcile.py` | 12 | alignment, normalization, evidence mass, both aligner regressions |
| `test_conflict.py` | 9 | party/asset passes, near-miss abstention, supersession |
| `test_cuad_classes.py` | 7 | 41 classes, provenance guards, the "unrelated matters" qualifier |
| `test_schema.py` | 6 | round-trip, absent-vs-unresolved, tier derivation |
| `test_stage2_ocr.py` | 6 | coordinate rescaling, reading order, OCR fallback |
| `test_pipeline_integration.py` | 1 | full wiring, real Stage 1 + 2a, fake VLM |

`pytest` — no API key or network needed; the VLM/HTTP layers are stubbed.

---

## 5. Layout

```
src/pdf_analyzer/
  cuad_classes.py    41 categories, official CUAD descriptions + trigger phrases
  stage1_ingest.py   conversion + DPI-standardized rendering
  stage2_ocr.py      native text layer, Tesseract fallback
  stage2_vlm.py      OpenRouter / Qwen / InternVL behind one interface
  stage3_reconcile.py anchor alignment, bbox envelope, evidence-mass scoring
  schema.py          output models + conflict-detection fields
  conflict.py        party-based and asset-based passes
  pipeline.py        orchestration
  cli.py             entrypoint
api/main.py          FastAPI job service
frontend/            React + react-pdf viewer
reference/           CUAD category_descriptions.csv (provenance)
tests/sample_data/   two real CUAD contracts
```

---

## 6. Problems and unfinished work

### 6.1 Granular mode costs 41x and is not the default
Every result in §3 uses `--prompt-mode granular`. The default is `single`,
which scored 11/16 where granular scored 16/16. **Anyone running this for
accuracy must pass the flag.** Defaulting it is a cost decision, not a
technical one.

### 6.2 Rate limiting
`google/gemini-3.8-flash` is capped at 300 req/min *shared across all
OpenRouter users*. Granular mode hits this constantly. Retries recover
(verified: no calls dropped) but runs take longer than the call count implies.

### 6.3 Trigger phrases are still unvalidated authorship
`CUAD_DESCRIPTIONS` is now authoritative. `CUAD_TRIGGER_PHRASES` is not — it
is my drafting, observed from two contracts. The two scope notes added to fix
the Chase false positives were confirmed by re-running; the rest have not been
individually tested.

### 6.4 Two contracts is a thin basis
Both are US commercial agreements with clean born-digital text layers.
Untested: scanned documents (the Tesseract fallback path has **never run on a
real scanned contract**), non-English, handwriting, non-US contract forms.

### 6.5 Conflict detection has never seen real data
`conflict.py` passes 9 unit tests against synthetic fixtures. It has never run
on a real corpus, because nothing upstream populates `counterparties`,
`assets`, `contract_family`, or `structured_clauses` — **no entity-resolution
or structured-clause extraction stage exists.** The schema and the algorithms
are ready; the thing that fills them in is not built.

### 6.6 Frontend and API are unexercised
`frontend/` builds cleanly and `api/main.py` starts and serves correct routes
(verified). But the viewer has **never been opened in a browser against real
output**, so click-to-jump and bbox highlighting are unverified end-to-end.
Both were written against an older schema shape and updated blind when the
schema changed.

### 6.7 Known schema gaps (designed, not built)
- No `negating_evidence` — a *Direct* "No" (e.g. "non-exclusive" proving no
  exclusivity) has nowhere to put its quote.
- `review_flag` conflates "OCR couldn't confirm" with "needs legal judgment."
- No structured multi-value answer — `expiration_date` genuinely has three
  different terms; we surface all three citations but can't express that.
- No `rationale` field for reasoned exclusions.
- No `related_categories` cross-links.
- No multi-category tagging per extraction (moot in granular, not in single).

### 6.8 Misclassification is invisible to the guardrail
Stage 3 confirms text is real and locatable. It cannot catch a correctly
grounded quote filed under the wrong category — the two Chase FPs both scored
100 with healthy evidence mass. **Grounding is not correctness.**

### 6.9 Smaller items
- No per-page progress logging in the VLM stage; long runs are opaque.
- Evidence-mass threshold (2.0) calibrated on one document (§2.3).
- `_align_tokens` caps candidate starts at 200 for cost; untested at that bound.
- Local `qwen`/`internvl` backends untouched since §2.5 and unlikely to work
  well regardless.
- Deterministic OCR-lexicon candidate nomination — proposed as a safety net
  (a keyword miss is inspectable; a model's "found: false" is not). Not built.

---

## 7. If picking this up

1. **Run `pytest`** (63 should pass), then run granular mode on
   `tests/sample_data/` to reproduce §3.
2. **Get a third contract**, ideally scanned, ideally annotated. §6.4 is the
   biggest threat to everything claimed here.
3. **Open the frontend against real output** (§6.6) — it is the one stage never
   visually confirmed.
4. **Decide on conflict detection** (§6.5): either build entity resolution and
   structured-clause extraction to feed it, or acknowledge it as unwired.

Method note: nearly every real bug in this project was found by running the
thing on a real contract and checking the output against ground truth, not by
reasoning about the code. Two hypotheses that seemed obviously right (granular
prompting; page-window context for cross-page clauses) were wrong, and the
data said so. Keep scoring against annotations.
