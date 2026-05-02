"""Gemini provider — wraps Google Generative Language API (`generativelanguage.googleapis.com`).

Uses httpx. The client is injectable for tests via `httpx.MockTransport`.
HTTP status -> exception mapping:
  429              -> RateLimitError
  401, 403         -> AuthError
  5xx, timeout     -> TransientError
  other 4xx        -> FatalError
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from atforge.llm.types import (
    AuthError,
    FatalError,
    LlmRequest,
    LlmResponse,
    RateLimitError,
    TransientError,
)

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiProvider:
    name = "gemini"

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
        return model.startswith("gemini-")

    def complete(self, request: LlmRequest) -> LlmResponse:
        model = request.model or self.default_model
        url = f"{self._base_url}/models/{model}:generateContent"
        body = self._build_body(request)

        started = time.monotonic()
        try:
            r = self._client.post(url, params={"key": self._api_key}, json=body)
        except httpx.TimeoutException as e:
            raise TransientError(f"gemini timeout: {e}") from e
        except httpx.HTTPError as e:
            raise TransientError(f"gemini http error: {e}") from e
        latency_ms = int((time.monotonic() - started) * 1000)

        self._raise_for_status(r)
        data = r.json()

        return LlmResponse(
            text=self._extract_text(data),
            model=model,
            provider=self.name,
            input_tokens=int(data.get("usageMetadata", {}).get("promptTokenCount", 0)),
            output_tokens=int(data.get("usageMetadata", {}).get("candidatesTokenCount", 0)),
            latency_ms=latency_ms,
        )

    @staticmethod
    def _build_body(request: LlmRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "contents": [
                {"role": "user", "parts": [{"text": request.prompt}]},
            ],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        if request.system:
            body["systemInstruction"] = {"parts": [{"text": request.system}]}
        return body

    @staticmethod
    def _raise_for_status(r: httpx.Response) -> None:
        if r.is_success:
            return
        status = r.status_code
        text = r.text
        if status == 429:
            raise RateLimitError(text)
        if status in (401, 403):
            raise AuthError(text)
        if 500 <= status < 600:
            raise TransientError(text)
        raise FatalError(f"{status}: {text}")

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", []) or []
        return "".join(p.get("text", "") for p in parts)
