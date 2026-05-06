"""OpenRouter provider — OpenAI-compatible gateway to 20+ free + paid models."""

from __future__ import annotations

import httpx

from atforge.llm.providers._openai_compat import OpenAICompatProvider


class OpenRouterProvider(OpenAICompatProvider):
    name = "openrouter"
    base_url = "https://openrouter.ai"
    chat_path = "/api/v1/chat/completions"
    default_model = "meta-llama/llama-3.1-8b-instruct:free"
    supports_tools = True

    def __init__(
        self,
        *,
        api_key: str,
        default_model: str | None = None,
        site_url: str | None = None,
        site_title: str | None = None,
        client: httpx.Client | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(
            api_key=api_key,
            default_model=default_model,
            client=client,
            base_url=base_url,
            timeout=timeout,
        )
        self._site_url = site_url
        self._site_title = site_title

    def _auth_headers(self) -> dict[str, str]:
        headers = super()._auth_headers()
        if self._site_url:
            headers["HTTP-Referer"] = self._site_url
        if self._site_title:
            headers["X-Title"] = self._site_title
        return headers
