from __future__ import annotations

import json

import httpx
import pytest

from atforge.llm.providers.ollama import OllamaProvider
from atforge.llm.types import LlmRequest, TransientError


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://localhost:11434")


def test_provider_attributes() -> None:
    p = OllamaProvider(
        client=_client(lambda r: httpx.Response(200, json={"message": {"content": "x"}}))
    )
    assert p.name == "ollama"
    assert p.supports("qwen2.5-coder:14b")
    assert p.supports("anything")  # local user picks freely


def test_happy_path() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "answer"},
                "prompt_eval_count": 11,
                "eval_count": 22,
            },
        )

    p = OllamaProvider(client=_client(handler))
    resp = p.complete(
        LlmRequest(prompt="ping", model="qwen2.5-coder:14b", temperature=0.6, max_tokens=200)
    )
    assert resp.text == "answer"
    assert resp.input_tokens == 11
    assert resp.output_tokens == 22
    assert resp.provider == "ollama"
    assert "/api/chat" in captured["url"]
    assert captured["body"]["model"] == "qwen2.5-coder:14b"
    assert captured["body"]["stream"] is False
    assert captured["body"]["options"]["temperature"] == 0.6
    assert captured["body"]["options"]["num_predict"] == 200
    assert captured["body"]["messages"][-1] == {"role": "user", "content": "ping"}


def test_connection_error_raises_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    p = OllamaProvider(client=_client(handler))
    with pytest.raises(TransientError):
        p.complete(LlmRequest(prompt="x"))


def test_500_raises_transient() -> None:
    p = OllamaProvider(client=_client(lambda r: httpx.Response(500, text="boom")))
    with pytest.raises(TransientError):
        p.complete(LlmRequest(prompt="x"))
