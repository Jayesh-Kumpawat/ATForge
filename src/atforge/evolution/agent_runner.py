"""ReAct (Reason + Act) loop for research agents.

Runs a multi-turn LLM conversation with tool access. Terminates when LLM
emits a response with no tool calls (final answer) or when max_iterations
is reached (forced final turn sent without tools, lower temperature).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable

import structlog

from atforge.evolution.agent_tools import ToolDefinition
from atforge.evolution.research_prompts import RESEARCH_FINAL_TURN
from atforge.graph.events import EventBus, EvtAgentReasoning, EvtAgentToolCall
from atforge.llm.types import LlmRequest, LlmResponse, Message, ToolCall

log = structlog.get_logger(__name__)


def _dispatch_tool(
    tc: ToolCall,
    tools: list[ToolDefinition],
    conn: sqlite3.Connection,
) -> dict:
    for td in tools:
        if td.spec.name == tc.name:
            return td.handler(tc.arguments, conn)
    return {"error": f"unknown tool {tc.name!r}"}


def run_react_loop(
    llm_router: Callable[[LlmRequest], LlmResponse],
    tools: list[ToolDefinition],
    system_prompt: str,
    initial_message: str,
    conn: sqlite3.Connection,
    *,
    max_iterations: int = 6,
    event_bus: EventBus | None = None,
    role: str = "research",
    parent_strategy_id: int | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    trace_name: str = "research_agent",
) -> str | None:
    """Run ReAct loop. Returns final text response or None on LLM failure."""
    tool_specs = tuple(td.spec for td in tools)
    messages: tuple[Message, ...] = (Message(role="user", content=initial_message),)

    for iteration in range(max_iterations):
        request = LlmRequest(
            messages=messages,
            tools=tool_specs if tool_specs else None,
            system=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=2048,
            trace_name=f"{trace_name}_iter{iteration}",
        )
        try:
            response = llm_router(request)
        except Exception as exc:
            log.warning("react_loop_llm_failed", iteration=iteration, error=str(exc))
            return None

        iter_trace = f"{trace_name}_iter{iteration}"
        if event_bus and response.text:
            event_bus.emit(
                EvtAgentReasoning(
                    role=role,
                    iteration=iteration,
                    text=response.text[:500],
                    parent_strategy_id=parent_strategy_id,
                    trace_name=iter_trace,
                )
            )

        if not response.tool_calls:
            return response.text

        asst_msg = Message(role="assistant", content=response.text, tool_calls=response.tool_calls)
        messages = (*messages, asst_msg)

        for tc in response.tool_calls:
            if event_bus:
                event_bus.emit(
                    EvtAgentToolCall(
                        role=role,
                        tool_name=tc.name,
                        iteration=iteration,
                        args_summary=json.dumps(tc.arguments)[:200],
                        parent_strategy_id=parent_strategy_id,
                        trace_name=iter_trace,
                    )
                )
            try:
                result = _dispatch_tool(tc, tools, conn)
            except Exception as exc:
                result = {"error": str(exc)[:200]}
            messages = (
                *messages,
                Message(role="tool", content=json.dumps(result), tool_call_id=tc.id),
            )

    # Max iterations reached — force a final answer without tool access
    messages = (*messages, Message(role="user", content=RESEARCH_FINAL_TURN))
    request = LlmRequest(
        messages=messages,
        system=system_prompt,
        model=model,
        temperature=0.3,
        max_tokens=1024,
        trace_name=f"{trace_name}_final",
    )
    try:
        response = llm_router(request)
        return response.text
    except Exception as exc:
        log.warning("react_loop_final_failed", error=str(exc))
        return None
