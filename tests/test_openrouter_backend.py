"""OpenRouter backend tests. The HTTP layer is stubbed, so these run with no
API key and make no network calls."""

import json
from pathlib import Path

import pytest
from PIL import Image

from pdf_analyzer.stage2_vlm import (
    DEFAULT_OPENROUTER_MODEL_ID,
    OpenRouterBackend,
    OpenRouterError,
    build_vlm_backend,
)


@pytest.fixture
def page_image(tmp_path) -> Path:
    """A 300 DPI-sized page render, as Stage 1 produces."""
    path = tmp_path / "page_0001.png"
    Image.new("RGB", (2480, 3509), "white").save(path)
    return path


@pytest.fixture
def backend():
    return OpenRouterBackend(api_key="test-key", max_retries=2)


def _response(content):
    return {"choices": [{"message": {"content": content}}]}


def test_missing_api_key_fails_with_actionable_message(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(OpenRouterError) as exc:
        OpenRouterBackend()
    assert "OPENROUTER_API_KEY" in str(exc.value)


def test_api_key_read_from_environment(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    assert OpenRouterBackend().api_key == "env-key"


def test_api_key_is_not_logged(backend, caplog):
    """The key goes in a header and must never reach the logs."""
    with caplog.at_level("DEBUG"):
        headers = backend._headers()
    assert headers["Authorization"] == "Bearer test-key"
    assert "test-key" not in caplog.text


def test_large_page_is_downscaled_before_upload(backend, page_image):
    """300 DPI renders are far more resolution than a hosted VLM needs, and
    the base64 payload is billed by the token."""
    import base64
    import io

    uri = backend._encode_image(page_image)
    assert uri.startswith("data:image/png;base64,")

    raw = base64.b64decode(uri.split(",", 1)[1])
    with Image.open(io.BytesIO(raw)) as img:
        assert max(img.size) == backend.max_image_edge
        assert img.width < 2480  # actually shrunk


def test_extract_page_parses_model_json(backend, page_image, monkeypatch):
    payload = json.dumps(
        [
            {
                "cuad_class": "governing_law",
                "vlm_text": "governed by the laws of the State of Delaware",
                "clause_label": "13.5 Governing Law",
            },
            {"cuad_class": "not_a_real_cuad_class", "vlm_text": "x", "clause_label": "y"},
        ]
    )
    monkeypatch.setattr(backend, "_post", lambda _payload: _response(payload))

    result = backend.extract_page(page_image, 13)

    assert result.page_number == 13
    # The invented category is dropped; the schema stays closed over the 41.
    assert len(result.extractions) == 1
    assert result.extractions[0].cuad_class == "governing_law"


def test_extract_page_handles_content_parts_list(backend, page_image, monkeypatch):
    """Some models return content as a list of parts rather than a string."""
    parts = [{"type": "text", "text": '[{"cuad_class":"parties","vlm_text":"Acme","clause_label":"1"}]'}]
    monkeypatch.setattr(backend, "_post", lambda _payload: _response(parts))

    result = backend.extract_page(page_image, 1)
    assert result.extractions[0].cuad_class == "parties"


def test_unexpected_response_shape_raises(backend, page_image, monkeypatch):
    monkeypatch.setattr(backend, "_post", lambda _payload: {"error": "nope"})
    with pytest.raises(OpenRouterError):
        backend.extract_page(page_image, 1)


def test_request_payload_is_well_formed(backend, page_image, monkeypatch):
    captured = {}

    def fake_post(payload):
        captured.update(payload)
        return _response("[]")

    monkeypatch.setattr(backend, "_post", fake_post)
    backend.extract_page(page_image, 1)

    assert captured["model"] == DEFAULT_OPENROUTER_MODEL_ID
    assert captured["temperature"] == 0  # extraction should be reproducible
    content = captured["messages"][0]["content"]
    kinds = [part["type"] for part in content]
    assert "text" in kinds and "image_url" in kinds
    assert content[kinds.index("image_url")]["image_url"]["url"].startswith("data:image/png;base64,")


def test_client_errors_fail_fast_without_retrying(backend, monkeypatch):
    """A bad key or unknown model won't fix itself; burning retries on it
    just delays a clear error."""
    calls = []

    class FakeResponse:
        status_code = 404
        text = "model not found"

    class FakeRequests:
        RequestException = Exception

        @staticmethod
        def post(*args, **kwargs):
            calls.append(1)
            return FakeResponse()

    monkeypatch.setitem(__import__("sys").modules, "requests", FakeRequests)
    with pytest.raises(OpenRouterError) as exc:
        backend._post({"model": "bogus/model"})

    assert len(calls) == 1
    assert "openrouter.ai/models" in str(exc.value)


def test_transient_errors_are_retried_then_surface(backend, monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 429
        text = "rate limited"

    class FakeRequests:
        RequestException = Exception

        @staticmethod
        def post(*args, **kwargs):
            calls.append(1)
            return FakeResponse()

    monkeypatch.setitem(__import__("sys").modules, "requests", FakeRequests)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    with pytest.raises(OpenRouterError):
        backend._post({})
    assert len(calls) == backend.max_retries


def test_document_pages_are_processed_concurrently(backend, page_image, monkeypatch):
    monkeypatch.setattr(backend, "_post", lambda _p: _response("[]"))
    pages = {n: page_image for n in range(1, 6)}

    results = backend.extract_document(pages)

    assert backend.concurrency > 1  # network-bound, so parallel unlike local backends
    assert sorted(results) == [1, 2, 3, 4, 5]
    assert all(results[n].page_number == n for n in results)


def test_factory_builds_openrouter_by_default(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    assert isinstance(build_vlm_backend(), OpenRouterBackend)
    assert isinstance(build_vlm_backend("openrouter"), OpenRouterBackend)


def test_factory_rejects_unknown_backend():
    with pytest.raises(ValueError):
        build_vlm_backend("gpt-42")


# --------------------------------------------------------------------------
# Granular prompt mode: one call per CUAD category instead of one per page.
# --------------------------------------------------------------------------


def test_granular_mode_defaults_page_concurrency_to_one(monkeypatch):
    """Granular mode already fans out 41 calls within a page; also
    parallelizing across pages on top of that would multiply in-flight
    requests past what's reasonable, so page-level concurrency defaults
    down unless the caller explicitly overrides it."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    granular = OpenRouterBackend(prompt_mode="granular")
    single = OpenRouterBackend(prompt_mode="single")
    assert granular.concurrency == 1
    assert single.concurrency == 4

    explicit = OpenRouterBackend(prompt_mode="granular", concurrency=3)
    assert explicit.concurrency == 3


def test_granular_mode_rejects_invalid_value(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    with pytest.raises(ValueError):
        OpenRouterBackend(prompt_mode="both")


def test_single_category_prompt_names_only_that_category():
    from pdf_analyzer.cuad_classes import CUAD_CLASSES
    from pdf_analyzer.stage2_vlm import _build_single_category_prompt

    prompt = _build_single_category_prompt("governing_law")
    assert "Governing Law" in prompt
    # Must not leak the other 40 category names into a supposedly narrow ask.
    other_names = [v for k, v in CUAD_CLASSES.items() if k != "governing_law"]
    assert not any(name in prompt for name in other_names)


def test_single_category_response_parses_found_true():
    from pdf_analyzer.stage2_vlm import _parse_single_category_response

    raw = '{"found": true, "vlm_text": "governed by Delaware law", "clause_label": "13.5"}'
    result = _parse_single_category_response(raw, "governing_law")

    assert result is not None
    assert result.cuad_class == "governing_law"
    assert result.vlm_text == "governed by Delaware law"


def test_single_category_response_parses_found_false():
    from pdf_analyzer.stage2_vlm import _parse_single_category_response

    result = _parse_single_category_response('{"found": false}', "insurance")
    assert result is None


def test_single_category_response_handles_malformed_json():
    from pdf_analyzer.stage2_vlm import _parse_single_category_response

    result = _parse_single_category_response("not json at all", "insurance")
    assert result is None


def test_granular_extract_page_issues_one_call_per_category(backend, page_image, monkeypatch):
    """The whole point of granular mode: a clause that satisfies multiple
    categories should show up under each one, because each is asked about
    independently rather than forced into a single choice."""
    from pdf_analyzer.cuad_classes import CUAD_CLASSES

    backend.prompt_mode = "granular"
    backend.granular_concurrency = 4
    shared_text = "Each party disclaims ownership of the other's intellectual property."

    calls = []

    def fake_chat(prompt_text, image_uri):
        calls.append(prompt_text)
        if "IP Ownership Assignment" in prompt_text or "Joint IP Ownership" in prompt_text:
            return json.dumps({"found": True, "vlm_text": shared_text, "clause_label": "8.1"})
        return json.dumps({"found": False})

    monkeypatch.setattr(backend, "_chat", fake_chat)

    result = backend.extract_page(page_image, 8)

    assert len(calls) == len(CUAD_CLASSES)  # one call per category, no more no less
    matched_classes = {e.cuad_class for e in result.extractions}
    # The same clause correctly lands under BOTH categories -- this is
    # exactly the misfiling case the single-shot prompt couldn't handle.
    assert matched_classes == {"ip_ownership_assignment", "joint_ip_ownership"}
    assert all(e.vlm_text == shared_text for e in result.extractions)


def test_granular_mode_tolerates_one_category_call_failing(backend, page_image, monkeypatch):
    """41 independent calls means 41 independent failure points; one bad
    call must not sink the other 40."""
    from pdf_analyzer.stage2_vlm import OpenRouterError

    backend.prompt_mode = "granular"
    backend.granular_concurrency = 4

    def flaky_chat(prompt_text, image_uri):
        if "Insurance" in prompt_text:
            raise OpenRouterError("simulated transient failure")
        return json.dumps({"found": False})

    monkeypatch.setattr(backend, "_chat", flaky_chat)

    result = backend.extract_page(page_image, 1)  # should not raise
    assert result.extractions == []


def test_single_mode_still_uses_one_call_per_page(backend, page_image, monkeypatch):
    """Regression guard: 'single' must stay a single call, not silently
    pick up granular's fan-out."""
    calls = []
    monkeypatch.setattr(backend, "_chat", lambda p, i: calls.append(1) or "[]")

    backend.extract_page(page_image, 1)
    assert len(calls) == 1
