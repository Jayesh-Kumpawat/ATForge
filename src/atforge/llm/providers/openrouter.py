"""OpenRouter provider — OpenAI-compatible chat completions across 20+ free + paid models."""

from __future__ import annotations

import httpx

from atforge.llm.providers._openai_compat import build_chat_body, post_chat_completion
from atforge.llm.types import LlmRequest, LlmResponse

_DEFAULT_BASE_URL = "https://openrouter.ai"
_DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct:free"


class OpenRouterProvider:
    name = "openrouter"

    def __init__(
        self,
        *,
        api_key: str,
        default_model: str = _DEFAULT_MODEL,
        site_url: str | None = None,
        site_title: str | None = None,
        client: httpx.Client | None = None,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self.default_model = default_model
        self._site_url = site_url
        self._site_title = site_title
        self._base_url = base_url.rstrip("/")
        self._client = client if client is not None else httpx.Client(timeout=timeout)

    def supports(self, model: str) -> bool:
        # OpenRouter routes any model id it knows about — no prefix gating.
        return True

    def complete(self, request: LlmRequest) -> LlmResponse:
        model = request.model or self.default_model
        headers: dict[str, str] = {"Authorization": f"Bearer {self._api_key}"}
        if self._site_url:
            headers["HTTP-Referer"] = self._site_url
        if self._site_title:
            headers["X-Title"] = self._site_title
        return post_chat_completion(
            client=self._client,
            url=f"{self._base_url}/api/v1/chat/completions",
            headers=headers,
            body=build_chat_body(request, model=model),
            provider=self.name,
            model=model,
        )
