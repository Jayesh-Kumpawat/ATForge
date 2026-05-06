"""NVIDIA NIM provider — OpenAI-compatible, 100+ models, 40 RPM free."""

from __future__ import annotations

from atforge.llm.providers._openai_compat import OpenAICompatProvider


class NvidiaProvider(OpenAICompatProvider):
    name = "nvidia"
    base_url = "https://integrate.api.nvidia.com"
    default_model = "meta/llama-3.3-70b-instruct"
    supports_tools = True
