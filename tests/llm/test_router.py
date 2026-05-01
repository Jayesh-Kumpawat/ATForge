from __future__ import annotations

import pytest

from atforge.llm.registry import ProviderRegistry
from atforge.llm.router import complete_with_fallback
from atforge.llm.types import (
    AuthError,
    FatalError,
    LlmExhausted,
    LlmRequest,
    LlmResponse,
    RateLimitError,
    TransientError,
)


class _ScriptedProvider:
    """Provider that replays a list of responses/exceptions in order."""

    def __init__(
        self, name: str, script: list[LlmResponse | Exception], default_model: str = "fake-1"
    ) -> None:
        self.name = name
        self.default_model = default_model
        self._script = list(script)
        self.calls = 0

    def complete(self, request: LlmRequest) -> LlmResponse:
        self.calls += 1
        if not self._script:
            raise AssertionError(f"{self.name}: complete() called with empty script")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def supports(self, model: str) -> bool:
        return True


def _ok_response(provider: str = "fake", text: str = "hi") -> LlmResponse:
    return LlmResponse(
        text=text,
        model="fake-1",
        provider=provider,
        input_tokens=1,
        output_tokens=1,
        latency_ms=10,
    )


@pytest.fixture
def no_sleep() -> list[float]:
    """Replace router sleep with a recorder so tests don't actually sleep."""
    return []


def _make_sleep(record: list[float]):
    def _sleep(s: float) -> None:
        record.append(s)

    return _sleep


def test_happy_path_returns_first_provider_response(no_sleep: list[float]) -> None:
    reg = ProviderRegistry()
    p = _ScriptedProvider("gemini", [_ok_response("gemini")])
    reg.register(p)

    resp = complete_with_fallback(
        LlmRequest(prompt="hi"),
        registry=reg,
        priority=["gemini"],
        sleep=_make_sleep(no_sleep),
    )
    assert resp.provider == "gemini"
    assert p.calls == 1
    assert no_sleep == []


def test_retry_on_rate_limit_then_success(no_sleep: list[float]) -> None:
    reg = ProviderRegistry()
    p = _ScriptedProvider(
        "gemini", [RateLimitError("429"), RateLimitError("429"), _ok_response("gemini")]
    )
    reg.register(p)

    resp = complete_with_fallback(
        LlmRequest(prompt="hi"),
        registry=reg,
        priority=["gemini"],
        max_retries=3,
        base_delay=0.1,
        sleep=_make_sleep(no_sleep),
    )
    assert resp.provider == "gemini"
    assert p.calls == 3
    # Two backoff sleeps: base*1, base*2
    assert no_sleep == pytest.approx([0.1, 0.2])


def test_retry_on_transient_then_success(no_sleep: list[float]) -> None:
    reg = ProviderRegistry()
    p = _ScriptedProvider("gemini", [TransientError("503"), _ok_response("gemini")])
    reg.register(p)

    resp = complete_with_fallback(
        LlmRequest(prompt="hi"),
        registry=reg,
        priority=["gemini"],
        max_retries=3,
        base_delay=0.05,
        sleep=_make_sleep(no_sleep),
    )
    assert resp.provider == "gemini"
    assert p.calls == 2


def test_auth_error_falls_through_to_next_provider(no_sleep: list[float]) -> None:
    reg = ProviderRegistry()
    a = _ScriptedProvider("gemini", [AuthError("401")])
    b = _ScriptedProvider("groq", [_ok_response("groq")])
    reg.register(a)
    reg.register(b)

    resp = complete_with_fallback(
        LlmRequest(prompt="hi"),
        registry=reg,
        priority=["gemini", "groq"],
        max_retries=3,
        base_delay=0.0,
        sleep=_make_sleep(no_sleep),
    )
    assert resp.provider == "groq"
    assert a.calls == 1  # not retried
    assert b.calls == 1


def test_fatal_error_falls_through_without_retry(no_sleep: list[float]) -> None:
    reg = ProviderRegistry()
    a = _ScriptedProvider("gemini", [FatalError("400 bad")])
    b = _ScriptedProvider("groq", [_ok_response("groq")])
    reg.register(a)
    reg.register(b)

    resp = complete_with_fallback(
        LlmRequest(prompt="hi"),
        registry=reg,
        priority=["gemini", "groq"],
        max_retries=3,
        base_delay=0.0,
        sleep=_make_sleep(no_sleep),
    )
    assert resp.provider == "groq"
    assert a.calls == 1


def test_rate_limit_exhaustion_falls_through(no_sleep: list[float]) -> None:
    reg = ProviderRegistry()
    a = _ScriptedProvider("gemini", [RateLimitError("429")] * 3)
    b = _ScriptedProvider("groq", [_ok_response("groq")])
    reg.register(a)
    reg.register(b)

    resp = complete_with_fallback(
        LlmRequest(prompt="hi"),
        registry=reg,
        priority=["gemini", "groq"],
        max_retries=3,
        base_delay=0.05,
        sleep=_make_sleep(no_sleep),
    )
    assert resp.provider == "groq"
    assert a.calls == 3


def test_all_providers_fail_raises_exhausted(no_sleep: list[float]) -> None:
    reg = ProviderRegistry()
    a = _ScriptedProvider("gemini", [RateLimitError("429")] * 3)
    b = _ScriptedProvider("groq", [AuthError("401")])
    reg.register(a)
    reg.register(b)

    with pytest.raises(LlmExhausted):
        complete_with_fallback(
            LlmRequest(prompt="hi"),
            registry=reg,
            priority=["gemini", "groq"],
            max_retries=3,
            base_delay=0.0,
            sleep=_make_sleep(no_sleep),
        )


def test_empty_chain_raises_exhausted(no_sleep: list[float]) -> None:
    reg = ProviderRegistry()
    with pytest.raises(LlmExhausted):
        complete_with_fallback(
            LlmRequest(prompt="hi"),
            registry=reg,
            priority=["gemini"],
            sleep=_make_sleep(no_sleep),
        )


def test_skips_missing_providers_in_priority(no_sleep: list[float]) -> None:
    reg = ProviderRegistry()
    p = _ScriptedProvider("groq", [_ok_response("groq")])
    reg.register(p)

    resp = complete_with_fallback(
        LlmRequest(prompt="hi"),
        registry=reg,
        priority=["gemini", "groq"],  # gemini missing — skipped
        sleep=_make_sleep(no_sleep),
    )
    assert resp.provider == "groq"
