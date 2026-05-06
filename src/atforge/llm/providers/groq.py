"""Groq provider — OpenAI-compatible chat completions."""

from __future__ import annotations

from atforge.llm.providers._openai_compat import OpenAICompatProvider


class GroqProvider(OpenAICompatProvider):
    name = "groq"
    base_url = "https://api.groq.com"
    chat_path = "/openai/v1/chat/completions"
    default_model = "llama-3.1-8b-instant"
    supports_tools = True
