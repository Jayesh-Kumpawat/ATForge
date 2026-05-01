from __future__ import annotations

import pytest

from atforge.llm import client
from atforge.llm.types import (
    AuthError,
    FatalError,
    LlmError,
    LlmExhausted,
    LlmProvider,
    LlmRequest,
    LlmResponse,
    RateLimitError,
    TransientError,
)


def test_llm_request_minimal_construction() -> None:
    req = LlmRequest(prompt="hello")
    assert req.prompt == "hello"
    assert req.model is None
    assert req.temperature == 0.7
    assert req.max_tokens == 1024


def test_llm_request_with_response_schema() -> None:
    class FakeSchema: ...

    req = LlmRequest(prompt="x", response_schema=FakeSchema)
    assert req.response_schema is FakeSchema


def test_llm_response_shape() -> None:
    resp = LlmResponse(
        text="ok",
        model="gemini-2.5-flash",
        provider="gemini",
        input_tokens=10,
        output_tokens=20,
        latency_ms=123,
    )
    assert resp.trace_id is None
    assert resp.latency_ms == 123


def test_error_hierarchy() -> None:
    for exc in (RateLimitError, AuthError, TransientError, FatalError, LlmExhausted):
        assert issubclass(exc, LlmError)
        assert issubclass(LlmError, Exception)


class _FakeProvider:
    name = "fake"
    default_model = "fake-1"

    def complete(self, request: LlmRequest) -> LlmResponse:
        return LlmResponse(
            text="x",
            model=request.model or self.default_model,
            provider=self.name,
            input_tokens=0,
            output_tokens=0,
            latency_ms=0,
        )

    def supports(self, model: str) -> bool:
        return model.startswith("fake-")


def test_llm_provider_protocol_runtime_check() -> None:
    p = _FakeProvider()
    assert isinstance(p, LlmProvider)


def test_client_module_reexports_types() -> None:
    assert client.LlmRequest is LlmRequest
    assert client.LlmResponse is LlmResponse
    assert client.LlmProvider is LlmProvider
    assert client.RateLimitError is RateLimitError


def test_client_complete_is_still_unimplemented() -> None:
    """Step 4 wires it; Step 3 only re-exports types."""
    with pytest.raises(NotImplementedError):
        client.complete(LlmRequest(prompt="x"))
