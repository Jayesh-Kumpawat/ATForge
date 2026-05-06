"""Provider registry — drop-in plug-and-play storage of LlmProvider instances.

Adding a new provider: drop a file in `llm/providers/foo.py` exposing a class with
`name`, `default_model`, `complete`, `supports`, then call `registry.register(FooProvider(...))`
from `build_default_registry`. Zero changes to router, mutate node, or ratchet.
"""

from __future__ import annotations

from typing import Any

from atforge.llm.types import LlmProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LlmProvider] = {}

    def register(self, provider: LlmProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> LlmProvider | None:
        return self._providers.get(name)

    def chain(self, priority: list[str]) -> list[LlmProvider]:
        return [self._providers[n] for n in priority if n in self._providers]

    def names(self) -> list[str]:
        return list(self._providers)


def build_default_registry(settings: Any) -> ProviderRegistry:
    """Construct a `ProviderRegistry` from a settings object.

    Cloud providers register only when their API key is non-empty. Ollama is gated by
    `settings.enable_ollama` (default off — local 14B model is heavy and not all machines
    can run it).

    Adding a new provider here is a single block — no other changes elsewhere needed.
    """
    reg = ProviderRegistry()
    default_model = getattr(settings, "llm_default_model", "gemini-2.5-flash")

    if getattr(settings, "google_api_key", None):
        from atforge.llm.providers.gemini import GeminiProvider

        reg.register(GeminiProvider(api_key=settings.google_api_key, default_model=default_model))

    if getattr(settings, "groq_api_key", None):
        from atforge.llm.providers.groq import GroqProvider

        reg.register(GroqProvider(api_key=settings.groq_api_key))

    if getattr(settings, "openrouter_api_key", None):
        from atforge.llm.providers.openrouter import OpenRouterProvider

        reg.register(OpenRouterProvider(api_key=settings.openrouter_api_key))

    if getattr(settings, "cerebras_api_key", None):
        from atforge.llm.providers.cerebras import CerebrasProvider

        reg.register(CerebrasProvider(api_key=settings.cerebras_api_key))

    if getattr(settings, "nvidia_api_key", None):
        from atforge.llm.providers.nvidia import NvidiaProvider

        reg.register(NvidiaProvider(api_key=settings.nvidia_api_key))

    if getattr(settings, "enable_ollama", False):
        from atforge.llm.providers.ollama import OllamaProvider

        reg.register(
            OllamaProvider(base_url=getattr(settings, "ollama_base_url", "http://localhost:11434"))
        )

    return reg
