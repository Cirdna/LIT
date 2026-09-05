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
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from .cuad_classes import CUAD_CLASSES

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
    class_list = "\n".join(f"- {key}: {name}" for key, name in CUAD_CLASSES.items())
    return f"""You are a contract analysis engine. Examine this contract page image and
identify any text belonging to the following {len(CUAD_CLASSES)} CUAD clause/entity
categories:

{class_list}

For each category you find evidence of on THIS page, extract the text VERBATIM
(reproduce it exactly as it appears in the image, do not paraphrase or summarize)
along with the clause or section heading it appears under.

Respond with ONLY a JSON array (no markdown fences, no commentary), where each
element has this exact shape:
{{"cuad_class": "<snake_case key from the list above>", "vlm_text": "<verbatim extracted text>", "clause_label": "<section/clause heading or short description>"}}

If no categories are present on this page, respond with an empty JSON array: []
"""


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
        return []

    extractions: list[VlmClauseExtraction] = []
    for item in items:
        cuad_class = item.get("cuad_class")
        vlm_text = item.get("vlm_text")
        if not cuad_class or not vlm_text:
            continue
        if cuad_class not in CUAD_CLASSES:
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

    def __init__(self, model_id: str = DEFAULT_QWEN_MODEL_ID, device: str | None = None, max_new_tokens: int = 2048):
        import torch
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        self._torch = torch
        resolved_device = device or ("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
        self.device = resolved_device
        self.max_new_tokens = max_new_tokens

        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_id,
            torch_dtype="auto",
            device_map=resolved_device,
        )
        self.processor = AutoProcessor.from_pretrained(model_id)

    def extract_page(self, image_path: Path, page_number: int) -> VlmPageResult:
        from qwen_vl_utils import process_vision_info

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": str(image_path)},
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
