from __future__ import annotations

import pytest

from atforge.llm.registry import ProviderRegistry
from atforge.llm.router import complete_with_fallback
from atforge.llm.types import (
    LlmExhausted,
    LlmRequest,
    LlmResponse,
    ToolCall,
    ToolSpec,
)


def _resp(text: str = "ok") -> LlmResponse:
    return LlmResponse(text=text, model="m", provider="p", input_tokens=1, output_tokens=1, latency_ms=0)


def _tool_resp() -> LlmResponse:
    return LlmResponse(
        text="",
        model="m",
        provider="tool-provider",
        input_tokens=1,
        output_tokens=1,
        latency_ms=0,
        tool_calls=(ToolCall(id="fn", name="fn", arguments={}),),
        stop_reason="tool_use",
    )


class _FakeProvider:
    supports_tools = False

    def __init__(self, name: str, response: LlmResponse | None = None):
        self.name = name
        self.default_model = "m"
        self._response = response or _resp()
        self.calls: int = 0

    def complete(self, request: LlmRequest) -> LlmResponse:
        self.calls += 1
        return self._response

    def supports(self, model: str) -> bool:
        return True


class _ToolAwareProvider(_FakeProvider):
    supports_tools = True


_TOOL = ToolSpec(
    name="fn",
    description="desc",
    parameters_schema={"type": "object", "properties": {}},
)
_TOOL_REQUEST = LlmRequest(prompt="go", tools=(_TOOL,))
_PLAIN_REQUEST = LlmRequest(prompt="go")


def _registry(*providers) -> ProviderRegistry:
    reg = ProviderRegistry()
    for p in providers:
        reg.register(p)
    return reg


def test_tools_request_filters_to_supports_tools_only() -> None:
    no_tools = _FakeProvider("no-tools")
    with_tools = _ToolAwareProvider("with-tools", _tool_resp())
    reg = _registry(no_tools, with_tools)

    resp = complete_with_fallback(_TOOL_REQUEST, registry=reg, priority=["no-tools", "with-tools"])
    assert resp.provider == "tool-provider"
    assert no_tools.calls == 0  # skipped entirely
    assert with_tools.calls == 1


def test_tools_request_raises_exhausted_when_no_capable_providers() -> None:
    p1 = _FakeProvider("a")
    p2 = _FakeProvider("b")
    reg = _registry(p1, p2)

    with pytest.raises(LlmExhausted, match="no tool-capable providers"):
        complete_with_fallback(_TOOL_REQUEST, registry=reg, priority=["a", "b"])


def test_plain_request_uses_full_chain_unchanged() -> None:
    p1 = _FakeProvider("a")
    p2 = _FakeProvider("b")
    reg = _registry(p1, p2)

    resp = complete_with_fallback(_PLAIN_REQUEST, registry=reg, priority=["a", "b"])
    assert resp.text == "ok"
    assert p1.calls == 1
    assert p2.calls == 0  # p1 succeeded; p2 never tried
