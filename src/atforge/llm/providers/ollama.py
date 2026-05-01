"""Ollama provider — local model server.

Distinct request shape from OpenAI-compat:
  - body uses `options.temperature` + `options.num_predict`
  - response has `message.content`, token counts in `prompt_eval_count` / `eval_count`
  - no auth header (localhost)
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

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "qwen2.5-coder:14b"


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        *,
        default_model: str = _DEFAULT_MODEL,
        client: httpx.Client | None = None,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 120.0,
    ) -> None:
        self.default_model = default_model
        self._base_url = base_url.rstrip("/")
        self._client = client if client is not None else httpx.Client(timeout=timeout)

    def supports(self, model: str) -> bool:
        # Local server runs whatever the user has pulled — accept any id.
        return True

    def complete(self, request: LlmRequest) -> LlmResponse:
        model = request.model or self.default_model
        body: dict[str, Any] = {
            "model": model,
            "messages": self._messages(request),
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        started = time.monotonic()
        try:
            r = self._client.post(f"{self._base_url}/api/chat", json=body)
        except httpx.TimeoutException as e:
            raise TransientError(f"ollama timeout: {e}") from e
        except httpx.HTTPError as e:
            raise TransientError(f"ollama http error: {e}") from e
        latency_ms = int((time.monotonic() - started) * 1000)
        self._raise_for_status(r)
        data = r.json()
        return LlmResponse(
            text=(data.get("message") or {}).get("content", ""),
            model=model,
            provider=self.name,
            input_tokens=int(data.get("prompt_eval_count", 0)),
            output_tokens=int(data.get("eval_count", 0)),
            latency_ms=latency_ms,
        )

    @staticmethod
    def _messages(request: LlmRequest) -> list[dict[str, str]]:
        msgs: list[dict[str, str]] = []
        if request.system:
            msgs.append({"role": "system", "content": request.system})
        msgs.append({"role": "user", "content": request.prompt})
        return msgs

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
