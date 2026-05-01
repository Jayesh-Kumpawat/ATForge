"""Groq provider — OpenAI-compatible chat completions endpoint."""

from __future__ import annotations

import httpx

from atforge.llm.providers._openai_compat import build_chat_body, post_chat_completion
from atforge.llm.types import LlmRequest, LlmResponse

_DEFAULT_BASE_URL = "https://api.groq.com"
_DEFAULT_MODEL = "llama-3.1-8b-instant"


class GroqProvider:
    name = "groq"

    def __init__(
        self,
        *,
        api_key: str,
        default_model: str = _DEFAULT_MODEL,
        client: httpx.Client | None = None,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self.default_model = default_model
        self._base_url = base_url.rstrip("/")
        self._client = client if client is not None else httpx.Client(timeout=timeout)

    def supports(self, model: str) -> bool:
        # Groq accepts any model id it serves — we don't gate by prefix.
        return True

    def complete(self, request: LlmRequest) -> LlmResponse:
        model = request.model or self.default_model
        return post_chat_completion(
            client=self._client,
            url=f"{self._base_url}/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            body=build_chat_body(request, model=model),
            provider=self.name,
            model=model,
        )
