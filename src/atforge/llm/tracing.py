"""Langfuse 4.x tracing wrapper for LLM completions.

Designed to be flag-gated. Tests run with `enabled=False` and never touch the
Langfuse SDK. Production CLI passes `enabled=True` once API keys are configured.
"""

from __future__ import annotations

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
