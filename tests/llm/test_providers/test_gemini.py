from __future__ import annotations

import json

import httpx
import pytest

from atforge.llm.providers.gemini import GeminiProvider
from atforge.llm.types import (
    AuthError,
    FatalError,
    LlmRequest,
    RateLimitError,
    TransientError,
)


def _client_with_handler(handler) -> httpx.Client:
    transport = httpx.MockTransport(handler)
    return httpx.Client(
        transport=transport, base_url="https://generativelanguage.googleapis.com/v1beta"
    )


def _ok_body(text: str = "hello world", prompt_tokens: int = 5, completion_tokens: int = 7) -> dict:
    return {
        "candidates": [
            {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"},
        ],
        "usageMetadata": {
            "promptTokenCount": prompt_tokens,
            "candidatesTokenCount": completion_tokens,
            "totalTokenCount": prompt_tokens + completion_tokens,
        },
    }


def test_provider_attributes() -> None:
    p = GeminiProvider(
        api_key="x", client=_client_with_handler(lambda req: httpx.Response(200, json=_ok_body()))
    )
    assert p.name == "gemini"
    assert p.default_model.startswith("gemini-")


def test_supports_filters_gemini_models() -> None:
    p = GeminiProvider(
        api_key="x", client=_client_with_handler(lambda req: httpx.Response(200, json=_ok_body()))
    )
    assert p.supports("gemini-2.5-flash")
    assert not p.supports("groq-llama3")


def test_happy_path_returns_response() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_body(text="42 is the answer"))

    p = GeminiProvider(api_key="K", client=_client_with_handler(handler))
    resp = p.complete(LlmRequest(prompt="ultimate question?", temperature=0.5, max_tokens=100))
    assert resp.text == "42 is the answer"
    assert resp.provider == "gemini"
    assert resp.input_tokens == 5
    assert resp.output_tokens == 7
    assert resp.latency_ms >= 0
    # Verify URL has the API key as query param
    assert "key=K" in captured["url"]
    # Verify request body shape
    assert captured["body"]["contents"][0]["parts"][0]["text"] == "ultimate question?"
    assert captured["body"]["generationConfig"]["temperature"] == 0.5
    assert captured["body"]["generationConfig"]["maxOutputTokens"] == 100


def test_system_instruction_passed_when_set() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_body())

    p = GeminiProvider(api_key="K", client=_client_with_handler(handler))
    p.complete(LlmRequest(prompt="x", system="you are a quant"))
    assert (
        captured["body"].get("systemInstruction", {}).get("parts", [{}])[0].get("text")
        == "you are a quant"
    )


def test_default_model_used_when_not_specified() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=_ok_body())

    p = GeminiProvider(
        api_key="K", default_model="gemini-2.5-flash", client=_client_with_handler(handler)
    )
    p.complete(LlmRequest(prompt="x"))
    assert "models/gemini-2.5-flash:generateContent" in captured["url"]


def test_explicit_model_overrides_default() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=_ok_body())

    p = GeminiProvider(api_key="K", client=_client_with_handler(handler))
    p.complete(LlmRequest(prompt="x", model="gemini-1.5-pro"))
    assert "models/gemini-1.5-pro:generateContent" in captured["url"]


def test_429_raises_rate_limit_error() -> None:
    p = GeminiProvider(
        api_key="K",
        client=_client_with_handler(lambda r: httpx.Response(429, json={"error": "quota"})),
    )
    with pytest.raises(RateLimitError):
        p.complete(LlmRequest(prompt="x"))


def test_401_raises_auth_error() -> None:
    p = GeminiProvider(
        api_key="K",
        client=_client_with_handler(lambda r: httpx.Response(401, json={"error": "bad key"})),
    )
    with pytest.raises(AuthError):
        p.complete(LlmRequest(prompt="x"))


def test_403_raises_auth_error() -> None:
    p = GeminiProvider(
        api_key="K",
        client=_client_with_handler(lambda r: httpx.Response(403, json={"error": "forbidden"})),
    )
    with pytest.raises(AuthError):
        p.complete(LlmRequest(prompt="x"))


def test_503_raises_transient_error() -> None:
    p = GeminiProvider(
        api_key="K",
        client=_client_with_handler(lambda r: httpx.Response(503, json={"error": "down"})),
    )
    with pytest.raises(TransientError):
        p.complete(LlmRequest(prompt="x"))


def test_400_raises_fatal_error() -> None:
    p = GeminiProvider(
        api_key="K",
        client=_client_with_handler(lambda r: httpx.Response(400, json={"error": "bad request"})),
    )
    with pytest.raises(FatalError):
        p.complete(LlmRequest(prompt="x"))


def test_timeout_raises_transient_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    p = GeminiProvider(api_key="K", client=_client_with_handler(handler))
    with pytest.raises(TransientError):
        p.complete(LlmRequest(prompt="x"))


def test_missing_candidates_returns_empty_text() -> None:
    p = GeminiProvider(
        api_key="K",
        client=_client_with_handler(
            lambda r: httpx.Response(200, json={"candidates": [], "usageMetadata": {}})
        ),
    )
    resp = p.complete(LlmRequest(prompt="x"))
    assert resp.text == ""
    assert resp.input_tokens == 0
    assert resp.output_tokens == 0


def test_multipart_text_concatenated() -> None:
    body = {
        "candidates": [
            {"content": {"parts": [{"text": "hello "}, {"text": "world"}]}},
        ],
        "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 2},
    }
    p = GeminiProvider(
        api_key="K", client=_client_with_handler(lambda r: httpx.Response(200, json=body))
    )
    resp = p.complete(LlmRequest(prompt="x"))
    assert resp.text == "hello world"
