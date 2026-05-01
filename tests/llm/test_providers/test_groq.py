from __future__ import annotations

import json

import httpx
import pytest

from atforge.llm.providers.groq import GroqProvider
from atforge.llm.types import AuthError, LlmRequest, RateLimitError, TransientError


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.groq.com")


def _ok_body(text: str = "ok", prompt_tokens: int = 4, completion_tokens: int = 6) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


def test_provider_attributes() -> None:
    p = GroqProvider(api_key="K", client=_client(lambda r: httpx.Response(200, json=_ok_body())))
    assert p.name == "groq"
    assert p.default_model
    assert p.supports(p.default_model)


def test_happy_path() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=_ok_body(text="hello"))

    p = GroqProvider(api_key="SECRET", client=_client(handler))
    resp = p.complete(LlmRequest(prompt="hi", temperature=0.3, max_tokens=50, system="be terse"))
    assert resp.text == "hello"
    assert resp.provider == "groq"
    assert resp.input_tokens == 4
    assert resp.output_tokens == 6
    assert "openai/v1/chat/completions" in captured["url"]
    assert captured["auth"] == "Bearer SECRET"
    assert captured["body"]["temperature"] == 0.3
    assert captured["body"]["max_tokens"] == 50
    # System message is the first message; user prompt second.
    msgs = captured["body"]["messages"]
    assert msgs[0] == {"role": "system", "content": "be terse"}
    assert msgs[-1] == {"role": "user", "content": "hi"}


def test_explicit_model_overrides_default() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_body())

    p = GroqProvider(api_key="K", client=_client(handler))
    p.complete(LlmRequest(prompt="x", model="llama-3.1-70b"))
    assert captured["body"]["model"] == "llama-3.1-70b"


def test_429_rate_limit() -> None:
    p = GroqProvider(api_key="K", client=_client(lambda r: httpx.Response(429, text="quota")))
    with pytest.raises(RateLimitError):
        p.complete(LlmRequest(prompt="x"))


def test_401_auth_error() -> None:
    p = GroqProvider(api_key="K", client=_client(lambda r: httpx.Response(401, text="bad key")))
    with pytest.raises(AuthError):
        p.complete(LlmRequest(prompt="x"))


def test_503_transient() -> None:
    p = GroqProvider(api_key="K", client=_client(lambda r: httpx.Response(503, text="down")))
    with pytest.raises(TransientError):
        p.complete(LlmRequest(prompt="x"))
