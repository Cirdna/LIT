"""Stage 2, Pipeline 1: VLM path — semantic scan of each rendered page image
against the 41 CUAD classes, extracting verbatim target clauses and key
entities.

Backed by a local open-weight vision-language model (default: Qwen2.5-VL via
`transformers`). This runs real local inference — no external API calls —
per the gameplan's [Qwen2.5-VL / InternVL] pipeline box. Local inference of
a 7B+ VLM is slow/impractical without a CUDA or MPS-capable GPU with enough
VRAM/unified memory; see README for hardware notes and a smaller-model
fallback.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from .cuad_classes import CUAD_CLASSES

logger = logging.getLogger(__name__)

DEFAULT_QWEN_MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"
DEFAULT_INTERNVL_MODEL_ID = "OpenGVLab/InternVL2_5-8B"


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


class VlmBackend(ABC):
    """Common interface so the pipeline can swap Qwen2.5-VL <-> InternVL
    (or any other VLM) without touching Stage 3 reconciliation."""

    @abstractmethod
    def extract_page(self, image_path: Path, page_number: int) -> VlmPageResult: ...

    def extract_document(self, page_image_paths: dict[int, Path]) -> dict[int, VlmPageResult]:
        return {
            page_number: self.extract_page(path, page_number)
            for page_number, path in page_image_paths.items()
        }


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


def build_vlm_backend(backend: str = "qwen", **kwargs) -> VlmBackend:
    if backend == "qwen":
        return QwenVLBackend(**kwargs)
    if backend == "internvl":
        return InternVLBackend(**kwargs)
    raise ValueError(f"Unknown VLM backend: {backend!r} (expected 'qwen' or 'internvl')")
