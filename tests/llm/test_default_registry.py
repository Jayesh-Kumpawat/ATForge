"""Tests for `build_default_registry(settings)` — config-driven provider registration."""

from __future__ import annotations

from dataclasses import dataclass

from atforge.llm.registry import build_default_registry


@dataclass
class _FakeSettings:
    google_api_key: str | None = None
    groq_api_key: str | None = None
    openrouter_api_key: str | None = None
    enable_ollama: bool = False
    ollama_base_url: str = "http://localhost:11434"
    llm_default_model: str = "gemini-2.5-flash"


def test_no_keys_yields_empty_registry() -> None:
    reg = build_default_registry(_FakeSettings())
    assert reg.names() == []


def test_only_gemini_registered_when_only_google_key_set() -> None:
    reg = build_default_registry(_FakeSettings(google_api_key="g"))
    assert reg.names() == ["gemini"]


def test_all_cloud_providers_registered() -> None:
    s = _FakeSettings(
        google_api_key="g",
        groq_api_key="q",
        openrouter_api_key="r",
    )
    reg = build_default_registry(s)
    assert sorted(reg.names()) == ["gemini", "groq", "openrouter"]


def test_ollama_gated_off_by_default() -> None:
    reg = build_default_registry(_FakeSettings(enable_ollama=False))
    assert "ollama" not in reg.names()


def test_ollama_registered_when_enabled() -> None:
    reg = build_default_registry(_FakeSettings(enable_ollama=True))
    assert "ollama" in reg.names()


def test_empty_string_key_treated_as_missing() -> None:
    reg = build_default_registry(_FakeSettings(google_api_key=""))
    assert "gemini" not in reg.names()
