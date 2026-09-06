"""Text/JSON LLM client for the worker (invoice extraction).

The pipeline's `stage2_vlm` client is vision-only; this is the text equivalent,
sharing the same OpenRouter key and one configurable model
(OPENROUTER_CHAT_MODEL, default matches the pipeline's model). It reuses the
`requests` dependency the pipeline already ships.
"""

from __future__ import annotations

import json
import os

import requests

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


class LlmError(RuntimeError):
    pass


def _model() -> str:
    return os.environ.get("OPENROUTER_CHAT_MODEL", "google/gemini-3.8-flash")


def chat_json(system: str, user: str, *, model: str | None = None, timeout: float = 120.0) -> dict:
    """Request a JSON object and parse it defensively."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise LlmError("OPENROUTER_API_KEY is not set (add it to webapp/.env or the repo-root .env).")

    resp = requests.post(
        _ENDPOINT,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-Title": "AITHENA",
        },
        json={
            "model": model or _model(),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise LlmError(f"OpenRouter {resp.status_code}: {resp.text[:300]}")
    content = resp.json()["choices"][0]["message"]["content"]
    return _parse_json(content)


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise LlmError("Model did not return valid JSON.")
