"""Gemini provider — wraps Google Generative Language API (`generativelanguage.googleapis.com`).

Uses httpx. The client is injectable for tests via `httpx.MockTransport`.
HTTP status -> exception mapping:
  429              -> RateLimitError
  401, 403         -> AuthError
  5xx, timeout     -> TransientError
  other 4xx        -> FatalError
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

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiProvider:
    name = "gemini"
    supports_tools = True

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

        text, tool_calls, stop_reason = GeminiProvider._parse_content(data)

        return LlmResponse(
            text=text,
            model=model,
            provider=self.name,
            input_tokens=int(data.get("usageMetadata", {}).get("promptTokenCount", 0)),
            output_tokens=int(data.get("usageMetadata", {}).get("candidatesTokenCount", 0)),
            latency_ms=latency_ms,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
        )

    @staticmethod
    def _build_body(request: LlmRequest) -> dict[str, Any]:
        if request.messages is not None:
            contents = GeminiProvider._messages_to_contents(request.messages)
        else:
            contents = [{"role": "user", "parts": [{"text": request.prompt}]}]

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }

        if request.system:
            body["systemInstruction"] = {"parts": [{"text": request.system}]}

        if request.tools:
            body["tools"] = [{
                "functionDeclarations": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters_schema,
                    }
                    for t in request.tools
                ]
            }]
            body["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}

        return body

    @staticmethod
    def _messages_to_contents(messages: tuple[Message, ...]) -> list[dict[str, Any]]:
        """Convert internal Message objects to Gemini contents[] format."""
        contents = []
        for msg in messages:
            if msg.role == "user":
                contents.append({"role": "user", "parts": [{"text": msg.content or ""}]})
            elif msg.role == "assistant":
                if msg.tool_calls:
                    parts: list[dict[str, Any]] = [
                        {"functionCall": {"name": tc.name, "args": tc.arguments}}
                        for tc in msg.tool_calls
                    ]
                    if msg.content:
                        parts = [{"text": msg.content}, *parts]
                    contents.append({"role": "model", "parts": parts})
                else:
                    contents.append({"role": "model", "parts": [{"text": msg.content or ""}]})
            elif msg.role == "tool":
                try:
                    response_data = json.loads(msg.content or "{}")
                except (json.JSONDecodeError, TypeError):
                    response_data = {"result": msg.content or ""}
                contents.append({
                    "role": "user",
                    "parts": [{
                        "functionResponse": {
                            "name": msg.tool_call_id or "unknown",
                            "response": response_data,
                        }
                    }],
                })
        return contents

    @staticmethod
    def _parse_content(
        data: dict[str, Any],
    ) -> tuple[str, tuple[ToolCall, ...] | None, str | None]:
        """Extract text, tool_calls, stop_reason from a Gemini generateContent response."""
        candidates = data.get("candidates") or []
        if not candidates:
            return "", None, None

        candidate = candidates[0]
        parts = candidate.get("content", {}).get("parts", []) or []
        finish_reason = candidate.get("finishReason", "")

        text_parts: list[str] = []
        fn_calls: list[ToolCall] = []

        for part in parts:
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                fn_calls.append(ToolCall(
                    id=fc["name"],  # Gemini has no separate call ID; function name is unique per turn
                    name=fc["name"],
                    arguments=fc.get("args", {}),
                ))

        tool_calls = tuple(fn_calls) if fn_calls else None

        if tool_calls:
            stop_reason: str | None = "tool_use"
        elif finish_reason == "STOP":
            stop_reason = "end_turn"
        elif finish_reason == "MAX_TOKENS":
            stop_reason = "max_tokens"
        else:
            stop_reason = None

        return "".join(text_parts), tool_calls, stop_reason

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
