"""End-to-end fallback tests using real provider classes (httpx.MockTransport)."""

from __future__ import annotations

import httpx

from atforge.llm.providers.gemini import GeminiProvider
from atforge.llm.providers.groq import GroqProvider
from atforge.llm.registry import ProviderRegistry
from atforge.llm.router import complete_with_fallback
from atforge.llm.types import LlmRequest


def _silent_sleep(_: float) -> None:
    return


def _gemini_handler(status: int, body: dict | None = None):
    def _h(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body or {"error": "x"})

    return _h


def _gemini_ok() -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": "from-gemini"}]}}],
        "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
    }


def _groq_handler(status: int, body: dict | None = None):
    def _h(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body or {"error": "x"})

    return _h


def _groq_ok() -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": "from-groq"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }


def _gemini_with(handler) -> GeminiProvider:
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://generativelanguage.googleapis.com/v1beta",
    )
    return GeminiProvider(api_key="K", client=client)


def _groq_with(handler) -> GroqProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.groq.com")
    return GroqProvider(api_key="K", client=client)


def test_chain_uses_first_when_healthy() -> None:
    reg = ProviderRegistry()
    reg.register(_gemini_with(_gemini_handler(200, _gemini_ok())))
    # Groq handler that would FAIL the test if called.
    reg.register(_groq_with(lambda _r: (_ for _ in ()).throw(AssertionError("groq must not run"))))

    resp = complete_with_fallback(
        LlmRequest(prompt="hi"),
        registry=reg,
        priority=["gemini", "groq"],
        sleep=_silent_sleep,
        base_delay=0.0,
    )
    assert resp.provider == "gemini"
    assert resp.text == "from-gemini"


def test_chain_falls_through_on_rate_limit() -> None:
    reg = ProviderRegistry()
    reg.register(_gemini_with(_gemini_handler(429, {"error": "quota"})))
    reg.register(_groq_with(_groq_handler(200, _groq_ok())))

    resp = complete_with_fallback(
        LlmRequest(prompt="hi"),
        registry=reg,
        priority=["gemini", "groq"],
        max_retries=2,
        base_delay=0.0,
        sleep=_silent_sleep,
    )
    assert resp.provider == "groq"
    assert resp.text == "from-groq"


def test_chain_falls_through_on_auth_error() -> None:
    reg = ProviderRegistry()
    reg.register(_gemini_with(_gemini_handler(401, {"error": "bad key"})))
    reg.register(_groq_with(_groq_handler(200, _groq_ok())))

    resp = complete_with_fallback(
        LlmRequest(prompt="hi"),
        registry=reg,
        priority=["gemini", "groq"],
        sleep=_silent_sleep,
        base_delay=0.0,
    )
    assert resp.provider == "groq"


def test_chain_falls_through_on_5xx() -> None:
    reg = ProviderRegistry()
    reg.register(_gemini_with(_gemini_handler(503, {"error": "down"})))
    reg.register(_groq_with(_groq_handler(200, _groq_ok())))

    resp = complete_with_fallback(
        LlmRequest(prompt="hi"),
        registry=reg,
        priority=["gemini", "groq"],
        max_retries=2,
        base_delay=0.0,
        sleep=_silent_sleep,
    )
    assert resp.provider == "groq"
