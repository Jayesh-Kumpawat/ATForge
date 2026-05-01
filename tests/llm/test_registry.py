from __future__ import annotations

from atforge.llm.registry import ProviderRegistry
from atforge.llm.types import LlmRequest, LlmResponse


class _FakeProvider:
    def __init__(self, name: str, default_model: str = "fake-1") -> None:
        self.name = name
        self.default_model = default_model

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
        return True


def test_register_and_get() -> None:
    reg = ProviderRegistry()
    p = _FakeProvider("gemini")
    reg.register(p)
    assert reg.get("gemini") is p


def test_get_missing_returns_none() -> None:
    reg = ProviderRegistry()
    assert reg.get("missing") is None


def test_chain_returns_in_priority_order() -> None:
    reg = ProviderRegistry()
    a = _FakeProvider("gemini")
    b = _FakeProvider("groq")
    c = _FakeProvider("openrouter")
    for p in (b, c, a):
        reg.register(p)
    chain = reg.chain(["gemini", "groq", "openrouter"])
    assert [p.name for p in chain] == ["gemini", "groq", "openrouter"]


def test_chain_skips_missing_providers() -> None:
    reg = ProviderRegistry()
    reg.register(_FakeProvider("gemini"))
    reg.register(_FakeProvider("openrouter"))
    chain = reg.chain(["gemini", "groq", "openrouter"])
    assert [p.name for p in chain] == ["gemini", "openrouter"]


def test_chain_empty_when_no_providers_match() -> None:
    reg = ProviderRegistry()
    reg.register(_FakeProvider("gemini"))
    chain = reg.chain(["groq", "openrouter"])
    assert chain == []


def test_register_overwrites_same_name() -> None:
    reg = ProviderRegistry()
    a = _FakeProvider("gemini", default_model="m1")
    b = _FakeProvider("gemini", default_model="m2")
    reg.register(a)
    reg.register(b)
    assert reg.get("gemini") is b


def test_names_lists_registered_providers() -> None:
    reg = ProviderRegistry()
    reg.register(_FakeProvider("gemini"))
    reg.register(_FakeProvider("groq"))
    assert sorted(reg.names()) == ["gemini", "groq"]
