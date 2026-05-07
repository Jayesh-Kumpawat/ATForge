"""Shared helpers + base class for OpenAI-compatible chat-completion providers.

Centralizes:
  - request body construction (`build_chat_body`) — single-turn, multi-turn, tool calling
  - HTTP status → LlmError classification (`raise_for_status`)
  - response parsing (`parse_chat_response`) — extracts tool_calls and stop_reason
  - `OpenAICompatProvider` base class — new providers are a 6-line subclass

Adding a new OpenAI-compatible provider:
    class MyProvider(OpenAICompatProvider):
        name = "myprovider"
        base_url = "https://api.myprovider.com"   # no trailing slash
        default_model = "my-model-id"
        # chat_path defaults to "/v1/chat/completions" — override only if non-standard
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from atforge.llm.types import (
    AuthError,
    FatalError,
    LlmRequest,
    LlmResponse,
    Message,
    RateLimitError,
    ToolCall,
    TransientError,
)


def _messages_to_openai(messages: tuple[Message, ...]) -> list[dict[str, Any]]:
    """Convert internal Message objects to OpenAI messages array format."""
    result: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "tool":
            result.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id or "",
                    "content": msg.content or "",
                }
            )
        elif msg.role == "assistant" and msg.tool_calls:
            result.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
        else:
            result.append({"role": msg.role, "content": msg.content or ""})
    return result


def build_chat_body(request: LlmRequest, *, model: str) -> dict[str, Any]:
    if request.messages is not None:
        messages = _messages_to_openai(request.messages)
    else:
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
    }

    if request.tools:
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters_schema,
                },
            }
            for t in request.tools
        ]
        body["tool_choice"] = "auto"

    return body


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
    tool_calls: tuple[ToolCall, ...] | None = None
    stop_reason: str | None = None

    if choices:
        choice = choices[0]
        message = choice.get("message", {})
        text = message.get("content", "") or ""
        finish_reason = choice.get("finish_reason", "")

        raw_tcs = message.get("tool_calls")
        if raw_tcs:
            tool_calls = tuple(
                ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=json.loads(tc["function"]["arguments"]),
                )
                for tc in raw_tcs
            )
            stop_reason = "tool_use"
        elif finish_reason == "stop":
            stop_reason = "end_turn"
        elif finish_reason in ("length", "max_tokens"):
            stop_reason = "max_tokens"

    usage = data.get("usage") or {}
    return LlmResponse(
        text=text,
        model=model,
        provider=provider,
        input_tokens=int(usage.get("prompt_tokens", 0)),
        output_tokens=int(usage.get("completion_tokens", 0)),
        latency_ms=latency_ms,
        tool_calls=tool_calls,
        stop_reason=stop_reason,
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


class OpenAICompatProvider:
    """Base for all OpenAI-compatible providers. Subclass by setting class-level attrs.

    Subclasses get tool calling, multi-turn messages, error mapping, and retry-safe HTTP
    for free. Only need to declare name/base_url/default_model.

    Override `_auth_headers()` for providers that need extra headers (e.g. HTTP-Referer).
    Override `chat_path` for non-standard completion paths.
    """

    name: str
    base_url: str
    chat_path: str = "/v1/chat/completions"
    default_model: str
    supports_tools: bool = True

    def __init__(
        self,
        *,
        api_key: str,
        default_model: str | None = None,
        client: httpx.Client | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        if default_model is not None:
            self.default_model = default_model
        if base_url is not None:
            self.base_url = base_url.rstrip("/")
        self._client = client if client is not None else httpx.Client(timeout=timeout)

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def supports(self, model: str) -> bool:
        return True

    def complete(self, request: LlmRequest) -> LlmResponse:
        model = request.model or self.default_model
        return post_chat_completion(
            client=self._client,
            url=f"{self.base_url.rstrip('/')}{self.chat_path}",
            headers=self._auth_headers(),
            body=build_chat_body(request, model=model),
            provider=self.name,
            model=model,
        )
