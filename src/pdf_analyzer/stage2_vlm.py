"""Stage 2, Pipeline 1: VLM path — semantic scan of each rendered page image
against the 41 CUAD classes, extracting verbatim target clauses and key
entities.

Three interchangeable backends behind one `VlmBackend` interface:

  openrouter -- a hosted frontier model over the OpenRouter API (default).
  qwen       -- local Qwen2.5-VL via `transformers`.
  internvl   -- local InternVL via `transformers`.

The default is hosted because the local 7B models proved to be the
pipeline's accuracy bottleneck on real contracts. Scored against expert
annotations of the Armstrong Flooring IP Agreement, Qwen2.5-VL-7B missed
clauses whose text was demonstrably present in the OCR word array
(non-disparagement, IP assignment, covenant-not-to-sue), filed others under
the wrong category, and on some pages enumerated all 41 categories with
"not specified" placeholders instead of reading the page. Stages 1, 2a, 3
and 4 were all doing their jobs; only the semantic layer was failing.

Local inference of a 7B+ VLM also needs a CUDA or MPS-capable GPU to be
practical — a 20-page contract took ~84 minutes on an M4 — whereas the
hosted path runs pages concurrently in seconds each.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .cuad_classes import CUAD_CLASSES, CUAD_DEFINITIONS

logger = logging.getLogger(__name__)

DEFAULT_QWEN_MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"
DEFAULT_INTERNVL_MODEL_ID = "OpenGVLab/InternVL2_5-8B"

# Any vision-capable OpenRouter model slug works; override with --model-id.
# See https://openrouter.ai/models for the current catalogue.
DEFAULT_OPENROUTER_MODEL_ID = "google/gemini-3.8-flash"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class VlmClauseExtraction:
    cuad_class: str  # snake_case key, matches cuad_classes.CUAD_CLASSES
    vlm_text: str  # verbatim (as best the VLM can reproduce) target clause/entity
    clause_label: str  # the VLM's own label for the clause/section it came from


@dataclass
class VlmPageResult:
    page_number: int
    extractions: list[VlmClauseExtraction]


def _build_prompt() -> str:
    """Build the per-page CUAD extraction prompt.

    The wording here is load-bearing and was settled empirically against real
    CUAD contract pages. An earlier version listed the categories, asked for
    verbatim JSON, and closed with "if nothing is present, return []" — against
    real pages of the Armstrong Flooring IP Agreement that version returned a
    bare `[]` every time, for pages that plainly contained a title, named
    parties, dates, and a governing-law clause. The model could read those
    pages fine (asked to simply describe one, it transcribed the text
    correctly), so the failure was one of instruction-following, not vision.

    Two changes fixed it: dropping the trailing "return []" sentence, which a
    7B model treats as the cheapest way to satisfy the request, and adding a
    worked example of the output shape. Keep both if you edit this.
    """
    class_list = "\n".join(f"- {key}: {name}" for key, name in CUAD_CLASSES.items())
    return f"""You are a contract analysis engine reviewing one page of a legal contract.

Extract every piece of text on this page that belongs to any of these {len(CUAD_CLASSES)} CUAD categories:

{class_list}

Read the page carefully. Contract pages almost always contain several of these
categories -- titles, party names, dates, and clause headings all map to
categories above. Extract each one you can actually see on the page.

Copy the text VERBATIM from the image. Do not paraphrase, summarize, or invent text.

The "cuad_class" value must be one of the snake_case keys listed above, exactly as
written. Do not invent new category names.

Output format -- a JSON array, nothing else. Example of the exact shape:
[
  {{"cuad_class": "document_name", "vlm_text": "SOFTWARE LICENSE AGREEMENT", "clause_label": "Title"}},
  {{"cuad_class": "parties", "vlm_text": "Initech LLC and Umbrella Corp", "clause_label": "Preamble"}},
  {{"cuad_class": "governing_law", "vlm_text": "governed by the laws of the State of New York", "clause_label": "Governing Law"}}
]

Now produce the JSON array for THIS page:"""


def _parse_vlm_json(raw_text: str) -> list[VlmClauseExtraction]:
    text = raw_text.strip()
    # Models sometimes wrap output in ```json ... ``` despite instructions.
    fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        array_match = re.search(r"\[.*\]", text, re.DOTALL)
        if array_match:
            text = array_match.group(0)

    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        logger.warning(
            "VLM output was not parseable as JSON; dropping page result. First 300 chars: %r",
            raw_text[:300],
        )
        return []

    extractions: list[VlmClauseExtraction] = []
    for item in items:
        cuad_class = item.get("cuad_class")
        vlm_text = item.get("vlm_text")
        if not cuad_class or not vlm_text:
            continue
        if cuad_class not in CUAD_CLASSES:
            # The model does occasionally invent plausible-sounding categories
            # ("jurisdiction", "waiver_of_jury_trial"). Dropping them keeps the
            # output schema closed over the 41 real CUAD classes; logging them
            # keeps that silent filtering visible.
            logger.debug("Dropping non-CUAD class from VLM output: %r", cuad_class)
            continue
        extractions.append(
            VlmClauseExtraction(
                cuad_class=cuad_class,
                vlm_text=vlm_text,
                clause_label=item.get("clause_label", ""),
            )
        )
    return extractions


def _build_single_category_prompt(category_key: str) -> str:
    """Build a prompt asking about exactly one CUAD category.

    The one-shot 41-category prompt above causes misfiling: when a clause
    genuinely satisfies more than one category at once (an ownership
    acknowledgment paragraph is simultaneously IP Ownership Assignment,
    Joint IP Ownership, and Covenant Not To Sue evidence in the Armstrong
    Flooring contract), a single pass has to force it into one bucket and
    picks the most obvious one, silently dropping the others.

    Asking about one category at a time removes the forced choice entirely
    -- the model can, and does, answer "yes" to several separate questions
    about the same paragraph, because each question only requires a binary
    judgment about one thing rather than a ranking across 41. Since the
    category is fixed by which prompt was sent, the response doesn't need to
    name it at all, which also removes the "model invents a category name"
    failure mode the 41-way prompt has to filter for.

    Two more things this version fixes, found by scoring granular mode's
    first real run against expert ground truth (it recovered none of the
    three misfiling targets above, and lost one clean hit):

    - The bare category label isn't enough to find the clause. Handed just
      "Non-Disparagement", the model has to independently deduce that
      "shall not tarnish or bring into disrepute the reputation of ...
      goodwill" is an instance -- and often didn't, despite that exact text
      being present. CUAD_DEFINITIONS below gives each category a real
      definition plus the wording contracts actually use for it, mined from
      the same ground truth that exposed the gap.
    - "Do not force a match" turned out to be *too* conservative once
      isolated per category: recall got worse, not better, when the prompt
      leaned this hard against reporting anything uncertain. Stage 3 already
      verifies every extraction against the page's OCR text and discounts
      ungrounded or low-evidence matches (see stage3_reconcile.py) -- that
      is where over-eager matches should get caught, not here. So this
      version asks for anything plausibly relevant instead of holding back.
    """
    category_name = CUAD_CLASSES[category_key]
    definition = CUAD_DEFINITIONS[category_key]
    return f"""You are a contract analysis engine reviewing one page of a legal contract.

Does this page contain text addressing this specific category: {category_name}?

Definition and what to look for:
{definition}

Read the page carefully against that definition -- the contract's own wording
is very often different from the category name itself (a non-disparagement
clause may say "tarnish" or "disrepute" and never use the word "disparage";
a covenant not to sue may say "contest" or "challenge" and never say "sue").

If you find text that plausibly matches, report it even if you are not fully
certain -- a downstream step separately verifies every match against the
source text, so it is better to report a plausible candidate than to hold
back. Copy the text VERBATIM from the image (do not paraphrase, summarize,
or invent text), and give a short label for the clause or section it appears
under.

If there is truly nothing on this page relating to "{category_name}", answer
with found: false.

Respond with ONLY JSON, no markdown fences, no commentary, in exactly this shape:
{{"found": true, "vlm_text": "<verbatim text>", "clause_label": "<section heading>"}}
or
{{"found": false}}"""


def _parse_single_category_response(raw_text: str, category_key: str) -> VlmClauseExtraction | None:
    text = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        obj_match = re.search(r"\{.*\}", text, re.DOTALL)
        if obj_match:
            text = obj_match.group(0)

    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        logger.warning(
            "VLM output for category %r was not parseable as JSON; dropping. First 200 chars: %r",
            category_key,
            raw_text[:200],
        )
        return None

    if not obj.get("found"):
        return None
    vlm_text = obj.get("vlm_text")
    if not vlm_text:
        return None

    return VlmClauseExtraction(
        cuad_class=category_key,
        vlm_text=vlm_text,
        clause_label=obj.get("clause_label", ""),
    )


class VlmBackend(ABC):
    """Common interface so the pipeline can swap hosted <-> local models
    without touching Stage 3 reconciliation or the output schema."""

    #: Pages processed concurrently. Local backends hold a single model on one
    #: device and must stay serial; network-bound backends override this.
    concurrency = 1

    @abstractmethod
    def extract_page(self, image_path: Path, page_number: int) -> VlmPageResult: ...

    def extract_document(self, page_image_paths: dict[int, Path]) -> dict[int, VlmPageResult]:
        if self.concurrency <= 1:
            return {
                page_number: self.extract_page(path, page_number)
                for page_number, path in page_image_paths.items()
            }

        items = sorted(page_image_paths.items())
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            results = pool.map(lambda kv: (kv[0], self.extract_page(kv[1], kv[0])), items)
            return dict(results)


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter cannot be reached or refuses the request."""


class OpenRouterBackend(VlmBackend):
    """Hosted VLM via the OpenRouter API (OpenAI-compatible chat completions).

    Page images are sent inline as base64 data URIs. The API key is read from
    the OPENROUTER_API_KEY environment variable and never logged.
    """

    def __init__(
        self,
        model_id: str = DEFAULT_OPENROUTER_MODEL_ID,
        api_key: str | None = None,
        max_new_tokens: int = 4096,
        max_image_edge: int = 1600,
        timeout: float = 180.0,
        max_retries: int = 4,
        concurrency: int | None = None,
        prompt_mode: str = "single",
        granular_concurrency: int = 8,
        site_url: str | None = None,
        app_name: str = "pdf-contract-analyzer",
    ):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise OpenRouterError(
                "No OpenRouter API key. Set OPENROUTER_API_KEY in the environment "
                "or pass api_key=... . Get one at https://openrouter.ai/keys"
            )
        if prompt_mode not in ("single", "granular"):
            raise ValueError(f"prompt_mode must be 'single' or 'granular', got {prompt_mode!r}")

        self.model_id = model_id
        self.max_new_tokens = max_new_tokens
        self.max_image_edge = max_image_edge
        self.timeout = timeout
        self.max_retries = max_retries
        self.prompt_mode = prompt_mode
        self.granular_concurrency = granular_concurrency
        self.site_url = site_url
        self.app_name = app_name

        # Granular mode already issues 41 concurrent calls per page (bounded
        # by granular_concurrency); also parallelizing across pages on top of
        # that would multiply in-flight requests past what's reasonable for
        # one API key, so default page-level concurrency down to 1 there
        # unless the caller explicitly overrides it.
        if concurrency is not None:
            self.concurrency = concurrency
        else:
            self.concurrency = 1 if prompt_mode == "granular" else 4

    def _headers(self) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": self.app_name,
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        return headers

    def _encode_image(self, image_path: Path) -> str:
        """Downscale the 300 DPI render and return a base64 PNG data URI.

        Pages are rendered at 300 DPI for OCR's benefit, which is far more
        resolution than a hosted VLM needs and inflates both payload size and
        token cost. Capping the long edge keeps contract body text legible
        while keeping requests small. PNG rather than JPEG, since JPEG
        ringing around small serif text is exactly the wrong tradeoff here.
        """
        from PIL import Image

        with Image.open(image_path) as img:
            img = img.convert("RGB")
            longest = max(img.size)
            if longest > self.max_image_edge:
                scale = self.max_image_edge / longest
                new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
                img = img.resize(new_size, Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format="PNG", optimize=True)

        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def _post(self, payload: dict) -> dict:
        import requests

        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    OPENROUTER_URL,
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = f"network error: {exc}"
            else:
                if response.status_code == 200:
                    return response.json()

                # 429 and 5xx are transient; anything else is a request
                # problem that retrying will not fix (bad key, unknown model,
                # image too large), so fail fast with the server's reason.
                if response.status_code not in (429, 500, 502, 503, 504):
                    raise OpenRouterError(
                        f"OpenRouter returned {response.status_code}: {response.text[:400]}"
                        + (
                            f"\nCheck that '{self.model_id}' is a valid vision-capable slug "
                            "at https://openrouter.ai/models"
                            if response.status_code in (400, 404)
                            else ""
                        )
                    )
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"

            backoff = 2**attempt
            logger.warning(
                "OpenRouter attempt %d/%d failed (%s); retrying in %ds",
                attempt + 1,
                self.max_retries,
                last_error,
                backoff,
            )
            time.sleep(backoff)

        raise OpenRouterError(f"OpenRouter failed after {self.max_retries} attempts: {last_error}")

    def _chat(self, prompt_text: str, image_uri: str) -> str:
        """One chat-completion call; returns the response's text content."""
        payload = {
            "model": self.model_id,
            "max_tokens": self.max_new_tokens,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": image_uri}},
                    ],
                }
            ],
        }
        data = self._post(payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise OpenRouterError(f"Unexpected OpenRouter response shape: {str(data)[:400]}") from exc

        if isinstance(content, list):  # some models return content parts
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return content

    def extract_page(self, image_path: Path, page_number: int) -> VlmPageResult:
        if self.prompt_mode == "granular":
            return self._extract_page_granular(image_path, page_number)
        return self._extract_page_single(image_path, page_number)

    def _extract_page_single(self, image_path: Path, page_number: int) -> VlmPageResult:
        """One call per page, asking about all 41 categories at once."""
        content = self._chat(_build_prompt(), self._encode_image(image_path))
        extractions = _parse_vlm_json(content)
        logger.info("page %d (single): %d extractions from %s", page_number, len(extractions), self.model_id)
        return VlmPageResult(page_number=page_number, extractions=extractions)

    def _extract_page_granular(self, image_path: Path, page_number: int) -> VlmPageResult:
        """One call per category (41 per page), each a narrow yes/no + quote
        question. See _build_single_category_prompt's docstring for why: it
        removes the forced 41-way choice that causes the single-shot prompt
        to misfile a clause that genuinely satisfies more than one category.
        """
        image_uri = self._encode_image(image_path)

        def call_one(category_key: str) -> VlmClauseExtraction | None:
            content = self._chat(_build_single_category_prompt(category_key), image_uri)
            return _parse_single_category_response(content, category_key)

        extractions: list[VlmClauseExtraction] = []
        with ThreadPoolExecutor(max_workers=self.granular_concurrency) as pool:
            futures = {pool.submit(call_one, key): key for key in CUAD_CLASSES}
            for future in futures:
                key = futures[future]
                try:
                    result = future.result()
                except OpenRouterError as exc:
                    logger.warning("page %d, category %r failed: %s", page_number, key, exc)
                    continue
                if result is not None:
                    extractions.append(result)

        logger.info(
            "page %d (granular): %d/%d categories matched from %s",
            page_number,
            len(extractions),
            len(CUAD_CLASSES),
            self.model_id,
        )
        return VlmPageResult(page_number=page_number, extractions=extractions)


class QwenVLBackend(VlmBackend):
    """Local Qwen2.5-VL inference via `transformers` + `qwen-vl-utils`."""

    def __init__(
        self,
        model_id: str = DEFAULT_QWEN_MODEL_ID,
        device: str | None = None,
        max_new_tokens: int = 2048,
        min_pixels: int = 256 * 28 * 28,
        max_pixels: int = 1280 * 28 * 28,
    ):
        import torch
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        self._torch = torch
        resolved_device = device or ("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
        self.device = resolved_device
        self.max_new_tokens = max_new_tokens
        # A 300 DPI page render (~2550x3300px, ~8.4M pixels) has roughly 8x
        # more pixels than Qwen2.5-VL's own examples typically use, which
        # translates into thousands of vision tokens; self-attention over
        # that many tokens needs an amount of memory quadratic in token
        # count. Without a flash-attention kernel (MPS and CPU both fall
        # back to a naive SDPA path that materializes the full attention
        # matrix), that blows past any reasonable memory budget — this
        # capped it at ~55GB for a single page on this machine. Capping the
        # image to a bounded pixel budget here (applied per-image in
        # qwen_vl_utils.process_vision_info, not just at the processor
        # level) keeps token count, and therefore memory, bounded regardless
        # of the source render's DPI.
        self.min_pixels = min_pixels
        self.max_pixels = max_pixels

        if resolved_device == "cuda":
            # device_map dispatch is safe (and enables multi-GPU sharding) on CUDA.
            self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                model_id, dtype="auto", device_map=resolved_device
            )
        else:
            # On MPS, transformers' device_map-driven `caching_allocator_warmup`
            # tries to pre-allocate the whole model as one Metal buffer, which
            # exceeds MPS's per-allocation size cap and raises "Invalid buffer
            # size". Loading onto CPU first and moving the whole model to the
            # target device afterward sidesteps that codepath entirely.
            self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                model_id,
                dtype=torch.float16 if resolved_device != "cpu" else torch.float32,
                low_cpu_mem_usage=True,
            ).to(resolved_device)
        self.processor = AutoProcessor.from_pretrained(model_id)

    def extract_page(self, image_path: Path, page_number: int) -> VlmPageResult:
        from qwen_vl_utils import process_vision_info

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": str(image_path),
                        "min_pixels": self.min_pixels,
                        "max_pixels": self.max_pixels,
                    },
                    {"type": "text", "text": _build_prompt()},
                ],
            }
        ]

        text_prompt = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[text_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self.model.device)

        generated_ids = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens)
        trimmed = [
            out_ids[len(in_ids):]
            for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]

        extractions = _parse_vlm_json(output_text)
        return VlmPageResult(page_number=page_number, extractions=extractions)


class InternVLBackend(VlmBackend):
    """Local InternVL inference via `transformers` (trust_remote_code)."""

    def __init__(self, model_id: str = DEFAULT_INTERNVL_MODEL_ID, device: str | None = None, max_new_tokens: int = 2048):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self._torch = torch
        resolved_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.device = resolved_device
        self.max_new_tokens = max_new_tokens

        self.model = (
            AutoModel.from_pretrained(
                model_id,
                torch_dtype=torch.bfloat16 if resolved_device != "cpu" else torch.float32,
                low_cpu_mem_usage=True,
                trust_remote_code=True,
            )
            .to(resolved_device)
            .eval()
        )
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_id, trust_remote_code=True, use_fast=False
        )

    def extract_page(self, image_path: Path, page_number: int) -> VlmPageResult:
        from .internvl_image_utils import load_internvl_image

        pixel_values = load_internvl_image(image_path).to(self.model.dtype).to(self.device)
        generation_config = dict(max_new_tokens=self.max_new_tokens, do_sample=False)

        output_text = self.model.chat(
            self.tokenizer, pixel_values, _build_prompt(), generation_config
        )

        extractions = _parse_vlm_json(output_text)
        return VlmPageResult(page_number=page_number, extractions=extractions)


BACKENDS = ("openrouter", "qwen", "internvl")


def build_vlm_backend(backend: str = "openrouter", **kwargs) -> VlmBackend:
    if backend == "openrouter":
        return OpenRouterBackend(**kwargs)
    if backend == "qwen":
        return QwenVLBackend(**kwargs)
    if backend == "internvl":
        return InternVLBackend(**kwargs)
    raise ValueError(f"Unknown VLM backend: {backend!r} (expected one of {BACKENDS})")
