from __future__ import annotations

import json

import httpx
import pytest

from atforge.llm.providers.openrouter import OpenRouterProvider
from atforge.llm.types import AuthError, LlmRequest, RateLimitError


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://openrouter.ai")


def _ok_body() -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": "hey"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2},
    }


def test_provider_attributes() -> None:
    p = OpenRouterProvider(
        api_key="K", client=_client(lambda r: httpx.Response(200, json=_ok_body()))
    )
    assert p.name == "openrouter"
    assert p.supports("anything/at-all")


def test_happy_path_sends_referer_and_title_headers() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=_ok_body())

    p = OpenRouterProvider(
        api_key="SECRET",
        site_url="https://atforge.local",
        site_title="ATForge",
        client=_client(handler),
    )
    p.complete(LlmRequest(prompt="hi", model="meta-llama/llama-3.1-8b-instruct:free"))
    assert "api/v1/chat/completions" in captured["url"]
    assert captured["headers"]["authorization"] == "Bearer SECRET"
    assert captured["headers"]["http-referer"] == "https://atforge.local"
    assert captured["headers"]["x-title"] == "ATForge"
    assert captured["body"]["model"] == "meta-llama/llama-3.1-8b-instruct:free"


def test_429() -> None:
    p = OpenRouterProvider(api_key="K", client=_client(lambda r: httpx.Response(429, text="quota")))
    with pytest.raises(RateLimitError):
        p.complete(LlmRequest(prompt="x"))


def test_401() -> None:
    p = OpenRouterProvider(api_key="K", client=_client(lambda r: httpx.Response(401, text="bad")))
    with pytest.raises(AuthError):
        p.complete(LlmRequest(prompt="x"))
