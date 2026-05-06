"""Cerebras provider — OpenAI-compatible, ~2600 tok/s, 1M tokens/day free."""

from __future__ import annotations

from atforge.llm.providers._openai_compat import OpenAICompatProvider


class CerebrasProvider(OpenAICompatProvider):
    name = "cerebras"
    base_url = "https://api.cerebras.ai"
    default_model = "llama-3.3-70b"
    supports_tools = True
