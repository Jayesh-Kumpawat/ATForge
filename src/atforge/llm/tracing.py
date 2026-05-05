"""Langfuse 4.x tracing wrapper for LLM completions.

Designed to be flag-gated. Tests run with `enabled=False` and never touch the
Langfuse SDK. Production CLI passes `enabled=True` once API keys are configured.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol, runtime_checkable

from atforge.llm.types import LlmRequest, LlmResponse


@runtime_checkable
class _Recorder(Protocol):
    def record_response(self, response: LlmResponse) -> None: ...


class _NoopRecorder:
    def record_response(self, response: LlmResponse) -> None:
        return


class _LangfuseRecorder:
    def __init__(self, observation: Any) -> None:
        self._obs = observation

    def record_response(self, response: LlmResponse) -> None:
        self._obs.update(
            output=response.text,
            usage_details={
                "input": response.input_tokens,
                "output": response.output_tokens,
                "total": response.input_tokens + response.output_tokens,
            },
        )


@contextmanager
def trace_completion(
    request: LlmRequest,
    provider_name: str,
    *,
    enabled: bool = False,
    client: Any | None = None,
) -> Iterator[_Recorder]:
    """Wrap an LLM call in a Langfuse generation observation if `enabled`.

    Yields a recorder. Call `recorder.record_response(resp)` after the LLM returns
    to attach output + token usage to the span.
    """
    if not enabled:
        yield _NoopRecorder()
        return

    if client is None:
        from langfuse import get_client  # lazy: don't import in disabled path

        client = get_client()

    obs_kwargs: dict[str, Any] = {
        "name": request.trace_name or "llm.complete",
        "as_type": "generation",
        "input": request.prompt,
        "metadata": {"provider": provider_name, **(request.metadata or {})},
    }
    if request.model is not None:
        obs_kwargs["model"] = request.model

    with client.start_as_current_observation(**obs_kwargs) as obs:
        yield _LangfuseRecorder(obs)


@contextmanager
def trace_node(
    node_name: str,
    *,
    enabled: bool = False,
    client: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[None]:
    """Wrap a pipeline node execution in a Langfuse span if `enabled`.

    Usage:
        with trace_node("fetch_data", enabled=deps.tracing_enabled, metadata={"gen": 0}):
            ...node logic...
    """
    if not enabled:
        yield
        return

    if client is None:
        from langfuse import get_client  # lazy import — never touched in disabled path

        client = get_client()

    t0 = time.monotonic()
    with client.start_as_current_observation(
        name=f"node.{node_name}",
        as_type="span",
        metadata=metadata or {},
    ) as obs:
        yield
        obs.update(
            metadata={**(metadata or {}), "elapsed_ms": round((time.monotonic() - t0) * 1000)}
        )
