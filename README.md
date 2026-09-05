# PDF Contract Analyzer Engine

Implementation of the 5-stage gameplan: DOCX/HTML/PDF ingestion → dual VLM+OCR
extraction against the 41 CUAD clause/entity classes → fuzzy spatial
reconciliation → enriched JSON → click-to-jump PDF viewer.

## Architecture

| Stage | Module | What it does |
|---|---|---|
| 1 | [`src/pdf_analyzer/stage1_ingest.py`](src/pdf_analyzer/stage1_ingest.py) | Converts DOCX/RTF (LibreOffice `soffice`) and HTML (headless Chromium via Playwright) to a standardized PDF; validates native PDFs; renders every page to a 300 DPI PNG via PyMuPDF. |
| 2a | [`src/pdf_analyzer/stage2_vlm.py`](src/pdf_analyzer/stage2_vlm.py) | Semantic extraction against all 41 CUAD classes using a **local** vision-language model — Qwen2.5-VL by default, InternVL as a drop-in alternative (`VlmBackend` interface). |
| 2b | [`src/pdf_analyzer/stage2_ocr.py`](src/pdf_analyzer/stage2_ocr.py) | Verbatim word-level OCR with exact pixel bounding boxes, via Tesseract (`pytesseract`). |
| 3 | [`src/pdf_analyzer/stage3_reconcile.py`](src/pdf_analyzer/stage3_reconcile.py) | Aligns each VLM phrase to the OCR word array with an n-gram sliding window + Levenshtein similarity (`rapidfuzz`), computes the bounding envelope, normalizes to the 0–1000 grid, and applies the ≥85% verification guardrail. |
| 4 | [`src/pdf_analyzer/schema.py`](src/pdf_analyzer/schema.py) | Pydantic models for the enriched CUAD JSON output. |
| 5 | [`frontend/`](frontend/) + [`api/main.py`](api/main.py) | React + `react-pdf` viewer: click an extracted entity, jump to its page, draw a glowing SVG overlay over the exact bbox. FastAPI backend runs the pipeline as a background job. |

[`src/pdf_analyzer/pipeline.py`](src/pdf_analyzer/pipeline.py) orchestrates stages 1–4; [`src/pdf_analyzer/cli.py`](src/pdf_analyzer/cli.py) exposes it as a command.

## Setup

### System dependencies

Xcode Command Line Tools are installed on this machine (needed for
`python3`/`pip` to work at all); Tesseract, LibreOffice, and Node still need
installing — see "What's been verified" below for exactly what has and
hasn't been run here.

```bash
# macOS, via Homebrew
brew install tesseract          # OCR engine
brew install --cask libreoffice # DOCX/RTF -> PDF conversion (soffice)
brew install node               # frontend tooling
```

### Python environment

```bash
cd pdf-contract-analyzer
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium     # HTML -> PDF conversion
```

The local VLM backends need ~2.5GB of extra wheels and are optional — install
them only if you want to run `--backend qwen` / `--backend internvl`:

```bash
pip install -e ".[local]"
```

### API key (default backend)

Stage 2 defaults to a hosted model over OpenRouter:

```bash
export OPENROUTER_API_KEY=sk-or-...     # https://openrouter.ai/keys
```

### Frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
```

### API server

```bash
uvicorn api.main:app --reload --port 8000
```

## Running the pipeline

CLI (no server needed):

```bash
python -m pdf_analyzer.cli analyze contract.docx --output result.json

# local instead of hosted (needs `pip install -e ".[local]"`):
python -m pdf_analyzer.cli analyze contract.pdf --backend qwen --device mps
```

Or full stack: start the API (`uvicorn api.main:app`) and the frontend
(`npm run dev` in `frontend/`), then upload a document in the browser UI. The
API's backend is set via `PDF_ANALYZER_BACKEND` / `PDF_ANALYZER_MODEL_ID`
env vars, defaulting to OpenRouter.

## VLM backend choice

Three backends behind one `VlmBackend` interface
([`stage2_vlm.py`](src/pdf_analyzer/stage2_vlm.py)), swappable without
touching Stage 3 reconciliation or the output schema:

| backend | model | needs | pages processed |
|---|---|---|---|
| `openrouter` (default) | any vision-capable slug, default `google/gemini-3.8-flash` | `OPENROUTER_API_KEY` | concurrently (default 4) |
| `qwen` | Qwen2.5-VL-7B-Instruct | `pip install -e ".[local]"` + a GPU | serially |
| `internvl` | InternVL2_5-8B | `pip install -e ".[local]"` + a GPU | serially |

**The local backends were the pipeline's accuracy bottleneck, not just slow.**
Scored against expert annotations of a real 40-page CUAD contract
(Armstrong Flooring IP Agreement, in `tests/sample_data/`), Qwen2.5-VL-7B
missed clauses whose exact text was sitting in the OCR word array
(non-disparagement, IP assignment, covenant-not-to-sue), filed others under
the wrong CUAD category, and on some pages gave up and enumerated all 41
categories with `"not specified"` placeholders instead of reading the page.
Stages 1, 2a (OCR), 3 (reconciliation) and 4 (schema) were all doing their
jobs correctly — the semantic layer was the failure, and a 20-page run took
~84 minutes on an M4 to get those wrong answers. That's why hosted is now
the default rather than an alternative.

If you do need the local path (offline, cost, data residency), smaller
checkpoints reduce the footprint: `--model-id Qwen/Qwen2.5-VL-3B-Instruct`
or `--backend internvl --model-id OpenGVLab/InternVL2_5-2B` — but expect the
same accuracy ceiling, since it wasn't a sizing problem.

## Tests

```bash
pytest
```

`tests/test_stage3_reconcile.py` and `tests/test_schema.py` cover the parts of
the pipeline that don't require GPU inference or system binaries (OCR/VLM
integration is exercised through the `OcrPageResult`/`VlmPageResult`
dataclasses, not live Tesseract/Qwen calls). Drop real sample contracts into
`tests/sample_data/` for end-to-end manual runs.

## What's been verified vs. not

Xcode Command Line Tools got installed during this build (`python3` needs them
to run at all), which unblocked real execution:

- **Verified by running it**: all 15 tests pass (`pytest tests/`) — schema
  round-trips, coordinate normalization, and Stage 3's fuzzy reconciliation
  (exact-match, paraphrase, hallucination-rejection, and out-of-order-token
  cases), plus a full `pipeline.analyze_document` integration test against a
  real PyMuPDF-rendered PDF with fake OCR/VLM results standing in for
  Tesseract/Qwen. The FastAPI app (`api/main.py`) was started for real and
  confirmed to route `/jobs`, `/jobs/{job_id}`, `/jobs/{job_id}/pdf` correctly.
  This process caught and fixed two real bugs: an edge case in the sliding
  window search that could silently drop matches on short pages, and a
  Pydantic model using `str | None` syntax that breaks on Python 3.9 at
  runtime (fixed to `Optional[str]`).
- **Not verified here**: actual Tesseract OCR, actual Qwen2.5-VL/InternVL
  inference, LibreOffice/Playwright document conversion, and the React
  frontend — this machine has no Tesseract, no LibreOffice, no Node/npm, and
  no GPU for local VLM inference. Install the system dependencies above and
  run the CLI/API/frontend end-to-end on real contracts to validate those
  paths.
