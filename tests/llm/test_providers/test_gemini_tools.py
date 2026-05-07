from __future__ import annotations

import json

import httpx

from atforge.llm.providers.gemini import GeminiProvider
from atforge.llm.types import LlmRequest, Message, ToolCall, ToolSpec


def _client(handler) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://generativelanguage.googleapis.com/v1beta",
    )


def _tool_call_body(fn_name: str = "query_top_strategies", args: dict | None = None) -> dict:
    return {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [{"functionCall": {"name": fn_name, "args": args or {"limit": 5}}}],
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }


def _text_body(text: str = "final answer") -> dict:
    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": text}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 8},
    }


_TOOL = ToolSpec(
    name="query_top_strategies",
    description="Best-performing strategies by Sharpe.",
    parameters_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
)


# ── body builder tests ────────────────────────────────────────────────────────


def test_tools_added_to_request_body() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json=_tool_call_body())

    p = GeminiProvider(api_key="K", client=_client(handler))
    p.complete(LlmRequest(prompt="mutate?", tools=(_TOOL,)))

    body = captured["body"]
    assert "tools" in body
    fn_decls = body["tools"][0]["functionDeclarations"]
    assert fn_decls[0]["name"] == "query_top_strategies"
    assert fn_decls[0]["description"] == "Best-performing strategies by Sharpe."
    assert fn_decls[0]["parameters"] == _TOOL.parameters_schema
    assert body["toolConfig"]["functionCallingConfig"]["mode"] == "AUTO"


def test_no_tools_body_unchanged() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json=_text_body())

    p = GeminiProvider(api_key="K", client=_client(handler))
    p.complete(LlmRequest(prompt="hello"))
    assert "tools" not in captured["body"]
    assert "toolConfig" not in captured["body"]


def test_messages_mapped_to_contents() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json=_text_body())

    messages = (
        Message(role="user", content="what to mutate?"),
        Message(
            role="assistant",
            tool_calls=(
                ToolCall(
                    id="query_top_strategies", name="query_top_strategies", arguments={"limit": 5}
                ),
            ),
        ),
        Message(role="tool", content='{"strategies": []}', tool_call_id="query_top_strategies"),
        Message(role="assistant", content="Based on results, try RSI 12."),
    )

    p = GeminiProvider(api_key="K", client=_client(handler))
    p.complete(LlmRequest(messages=messages))

    contents = captured["body"]["contents"]
    assert contents[0] == {"role": "user", "parts": [{"text": "what to mutate?"}]}
    assert contents[1]["role"] == "model"
    assert contents[1]["parts"][0]["functionCall"]["name"] == "query_top_strategies"
    assert contents[2]["role"] == "user"
    assert contents[2]["parts"][0]["functionResponse"]["name"] == "query_top_strategies"
    assert contents[2]["parts"][0]["functionResponse"]["response"] == {"strategies": []}
    assert contents[3] == {"role": "model", "parts": [{"text": "Based on results, try RSI 12."}]}


# ── response parser tests ────────────────────────────────────────────────────


def test_tool_call_extracted_from_response() -> None:
    p = GeminiProvider(
        api_key="K",
        client=_client(
            lambda r: httpx.Response(
                200, json=_tool_call_body("query_top_strategies", {"limit": 5})
            )
        ),
    )
    resp = p.complete(LlmRequest(prompt="go"))
    assert resp.tool_calls is not None
    assert len(resp.tool_calls) == 1
    tc = resp.tool_calls[0]
    assert tc.name == "query_top_strategies"
    assert tc.arguments == {"limit": 5}
    assert tc.id == "query_top_strategies"


def test_stop_reason_tool_use_when_function_call_present() -> None:
    p = GeminiProvider(
        api_key="K",
        client=_client(lambda r: httpx.Response(200, json=_tool_call_body())),
    )
    resp = p.complete(LlmRequest(prompt="go"))
    assert resp.stop_reason == "tool_use"
    assert resp.text == ""


def test_stop_reason_end_turn_for_text_response() -> None:
    p = GeminiProvider(
        api_key="K",
        client=_client(lambda r: httpx.Response(200, json=_text_body())),
    )
    resp = p.complete(LlmRequest(prompt="go"))
    assert resp.stop_reason == "end_turn"
    assert resp.tool_calls is None


def test_text_and_tool_call_in_same_response() -> None:
    body = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {"text": "Let me check strategies."},
                        {"functionCall": {"name": "query_top_strategies", "args": {}}},
                    ],
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 10},
    }
    p = GeminiProvider(api_key="K", client=_client(lambda r: httpx.Response(200, json=body)))
    resp = p.complete(LlmRequest(prompt="go"))
    assert resp.text == "Let me check strategies."
    assert resp.tool_calls is not None
    assert resp.tool_calls[0].name == "query_top_strategies"
    assert resp.stop_reason == "tool_use"
