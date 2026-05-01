"""Shared helpers for OpenAI-compatible chat-completion providers (Groq, OpenRouter, ...).

Centralizes:
  - request body construction (`build_chat_body`)
  - HTTP status -> LlmError classification (`raise_for_status`)
  - response parsing (`parse_chat_response`)

A new OpenAI-compatible provider is a thin class that fills in URL + headers + name
+ default_model + supports() and delegates to these helpers.
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


def build_chat_body(request: LlmRequest, *, model: str) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if request.system:
        messages.append({"role": "system", "content": request.system})
    messages.append({"role": "user", "content": request.prompt})
    return {
        "model": model,
        "messages": messages,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
    }


def raise_for_status(r: httpx.Response) -> None:
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


def parse_chat_response(
    data: dict[str, Any],
    *,
    model: str,
    provider: str,
    latency_ms: int,
) -> LlmResponse:
    choices = data.get("choices") or []
    text = ""
    if choices:
        text = choices[0].get("message", {}).get("content", "") or ""
    usage = data.get("usage") or {}
    return LlmResponse(
        text=text,
        model=model,
        provider=provider,
        input_tokens=int(usage.get("prompt_tokens", 0)),
        output_tokens=int(usage.get("completion_tokens", 0)),
        latency_ms=latency_ms,
    )


def post_chat_completion(
    *,
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    provider: str,
    model: str,
) -> LlmResponse:
    """Single round-trip + classification + parse. Raises classified LlmError on failure."""
    started = time.monotonic()
    try:
        r = client.post(url, headers=headers, json=body)
    except httpx.TimeoutException as e:
        raise TransientError(f"{provider} timeout: {e}") from e
    except httpx.HTTPError as e:
        raise TransientError(f"{provider} http error: {e}") from e
    latency_ms = int((time.monotonic() - started) * 1000)
    raise_for_status(r)
    return parse_chat_response(r.json(), model=model, provider=provider, latency_ms=latency_ms)
