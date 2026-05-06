"""Tests for run_react_loop in agent_runner.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from atforge.evolution.agent_runner import run_react_loop
from atforge.evolution.agent_tools import build_research_tools
from atforge.graph.events import EventBus, EvtAgentReasoning, EvtAgentToolCall
from atforge.llm.types import LlmRequest, LlmResponse, ToolCall
from atforge.storage.db import connect, init_db, txn
from atforge.storage.repo import insert_run, upsert_strategy

SYSTEM = "You are a test research agent."


def _resp(
    text: str = "",
    tool_calls: tuple[ToolCall, ...] | None = None,
) -> LlmResponse:
    return LlmResponse(
        text=text,
        model="test-model",
        provider="test",
        input_tokens=10,
        output_tokens=10,
        latency_ms=5,
        tool_calls=tool_calls,
        stop_reason="tool_use" if tool_calls else "end_turn",
    )


class MockSequentialLLM:
    """Returns pre-configured responses in sequence; repeats last on exhaustion."""

    def __init__(self, responses: list[LlmResponse]) -> None:
        self._responses = list(responses)
        self._idx = 0

    def __call__(self, request: LlmRequest) -> LlmResponse:
        resp = self._responses[min(self._idx, len(self._responses) - 1)]
        self._idx += 1
        return resp


@pytest.fixture
def seeded_db(tmp_db_path: Path) -> Path:
    init_db(tmp_db_path)
    with connect(tmp_db_path) as conn, txn(conn):
        insert_run(conn, "run-agent-test")
        upsert_strategy(conn, "sma_10x30", "indicator", {"fast": 10, "slow": 30})
    return tmp_db_path


# ── no-tool-call path ─────────────────────────────────────────────────────────


def test_no_tool_calls_returns_immediately(seeded_db: Path) -> None:
    llm = MockSequentialLLM([_resp("final answer")])
    with connect(seeded_db) as conn:
        result = run_react_loop(llm, [], SYSTEM, "user msg", conn)
    assert result == "final answer"


# ── single tool call then final ───────────────────────────────────────────────


def test_one_tool_call_then_final(seeded_db: Path) -> None:
    tc = ToolCall(id="call_1", name="query_top_strategies", arguments={"limit": 5})
    tools = build_research_tools()
    responses = [
        _resp("thinking...", tool_calls=(tc,)),
        _resp('{"proposal_type": "done"}'),
    ]
    llm = MockSequentialLLM(responses)
    with connect(seeded_db) as conn:
        result = run_react_loop(llm, tools, SYSTEM, "user msg", conn)
    assert result is not None


# ── max_iterations forces final turn ─────────────────────────────────────────


def test_max_iterations_triggers_forced_final(seeded_db: Path) -> None:
    tc = ToolCall(id="call_1", name="query_top_strategies", arguments={})
    tools = build_research_tools()
    responses = [_resp("thinking", tool_calls=(tc,))] * 3 + [_resp("forced final answer")]
    llm = MockSequentialLLM(responses)
    with connect(seeded_db) as conn:
        result = run_react_loop(llm, tools, SYSTEM, "user msg", conn, max_iterations=3)
    assert result == "forced final answer"


def test_forced_final_request_has_no_tools(seeded_db: Path) -> None:
    """Verify forced final turn sends request without tools so LLM can't loop further."""
    tc = ToolCall(id="c1", name="query_top_strategies", arguments={})
    tools = build_research_tools()
    captured_requests: list[LlmRequest] = []

    def capturing_llm(req: LlmRequest) -> LlmResponse:
        captured_requests.append(req)
        if req.tools:
            return _resp("thinking", tool_calls=(tc,))
        return _resp("no tools final")

    with connect(seeded_db) as conn:
        result = run_react_loop(capturing_llm, tools, SYSTEM, "user msg", conn, max_iterations=2)

    final_req = captured_requests[-1]
    assert final_req.tools is None
    assert result == "no tools final"


# ── unknown tool ──────────────────────────────────────────────────────────────


def test_unknown_tool_returns_error_in_message(seeded_db: Path) -> None:
    """Unknown tool name → error dict appended to messages, loop continues."""
    tc = ToolCall(id="x", name="nonexistent_tool", arguments={})
    responses = [
        _resp("thinking", tool_calls=(tc,)),
        _resp("final answer"),
    ]
    llm = MockSequentialLLM(responses)
    with connect(seeded_db) as conn:
        # No tools registered — all names unknown
        result = run_react_loop(llm, [], SYSTEM, "user msg", conn)
    assert result == "final answer"


# ── LLM failure ───────────────────────────────────────────────────────────────


def test_llm_exception_returns_none(seeded_db: Path) -> None:
    def failing_llm(req: LlmRequest) -> LlmResponse:
        raise RuntimeError("provider down")

    with connect(seeded_db) as conn:
        result = run_react_loop(failing_llm, [], SYSTEM, "user msg", conn)
    assert result is None


# ── event bus ─────────────────────────────────────────────────────────────────


def test_event_bus_emits_reasoning_and_tool_call(seeded_db: Path) -> None:
    tc = ToolCall(id="c1", name="query_top_strategies", arguments={"limit": 3})
    tools = build_research_tools()
    responses = [
        _resp("reasoning text", tool_calls=(tc,)),
        _resp("final answer"),
    ]
    llm = MockSequentialLLM(responses)
    bus = EventBus()
    with connect(seeded_db) as conn:
        run_react_loop(llm, tools, SYSTEM, "user msg", conn, event_bus=bus)

    events = bus.drain()
    assert any(isinstance(e, EvtAgentReasoning) for e in events)
    assert any(
        isinstance(e, EvtAgentToolCall) and e.tool_name == "query_top_strategies" for e in events
    )


def test_event_bus_includes_parent_strategy_id(seeded_db: Path) -> None:
    tc = ToolCall(id="c1", name="query_top_strategies", arguments={})
    tools = build_research_tools()
    responses = [_resp("thinking", tool_calls=(tc,)), _resp("final")]
    llm = MockSequentialLLM(responses)
    bus = EventBus()
    with connect(seeded_db) as conn:
        run_react_loop(
            llm,
            tools,
            SYSTEM,
            "user msg",
            conn,
            event_bus=bus,
            parent_strategy_id=42,
        )

    events = bus.drain()
    tool_events = [e for e in events if isinstance(e, EvtAgentToolCall)]
    assert all(e.parent_strategy_id == 42 for e in tool_events)


# ── multiple tool calls per turn ─────────────────────────────────────────────


def test_multiple_tool_calls_per_turn(seeded_db: Path) -> None:
    tc1 = ToolCall(id="c1", name="query_top_strategies", arguments={"limit": 5})
    tc2 = ToolCall(id="c2", name="query_strategy_details", arguments={"strategy_id": 1})
    tools = build_research_tools()
    responses = [
        _resp("thinking", tool_calls=(tc1, tc2)),
        _resp("final answer"),
    ]
    llm = MockSequentialLLM(responses)
    with connect(seeded_db) as conn:
        result = run_react_loop(llm, tools, SYSTEM, "user msg", conn)
    assert result == "final answer"
