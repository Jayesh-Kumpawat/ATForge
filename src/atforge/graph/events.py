"""Pipeline event bus for live monitoring.

Nodes emit lightweight event dataclasses into an EventBus (threading.Queue).
A monitor thread drains the queue and renders a Rich live display.
EventBus is optional — nodes check `deps.event_bus is not None` before emitting.
"""

from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue


@dataclass(frozen=True)
class EvtPipelineStart:
    run_id: str
    n_symbols: int
    max_generations: int


@dataclass(frozen=True)
class EvtNodeStart:
    node_name: str
    generation: int


@dataclass(frozen=True)
class EvtNodeDone:
    node_name: str
    generation: int
    elapsed_ms: float


@dataclass(frozen=True)
class EvtBacktestDone:
    symbol: str
    strategy: str
    success: bool
    sharpe: float | None = None


@dataclass(frozen=True)
class EvtMutationProposed:
    mutator: str
    n_proposals: int


@dataclass(frozen=True)
class EvtRatchetVerdict:
    parent_name: str
    child_name: str
    accepted: bool
    delta_sharpe: float
    reason: str


@dataclass(frozen=True)
class EvtGenerationDone:
    generation: int
    n_backtests: int
    n_accepted: int


@dataclass(frozen=True)
class EvtPipelineDone:
    run_id: str
    n_backtests: int
    n_failures: int


@dataclass(frozen=True)
class EvtAgentToolCall:
    role: str                   # "research" | "explorer" | "exploiter" | "critic"
    tool_name: str
    iteration: int
    args_summary: str           # JSON, max 200 chars
    parent_strategy_id: int | None = None


@dataclass(frozen=True)
class EvtAgentReasoning:
    role: str
    iteration: int
    text: str                   # max 500 chars
    parent_strategy_id: int | None = None


PipelineEvent = (
    EvtPipelineStart
    | EvtNodeStart
    | EvtNodeDone
    | EvtBacktestDone
    | EvtMutationProposed
    | EvtRatchetVerdict
    | EvtGenerationDone
    | EvtPipelineDone
    | EvtAgentToolCall
    | EvtAgentReasoning
)

_SENTINEL = None


class EventBus:
    """Thread-safe queue bridging pipeline nodes to the monitor thread."""

    def __init__(self) -> None:
        self._q: Queue[PipelineEvent | None] = Queue()

    def emit(self, event: PipelineEvent) -> None:
        self._q.put(event)

    def drain(self, timeout: float = 0.05) -> list[PipelineEvent]:
        """Return all currently queued events without blocking longer than `timeout`."""
        events: list[PipelineEvent] = []
        while True:
            try:
                item = self._q.get(timeout=timeout)
                if item is _SENTINEL:
                    break
                events.append(item)  # type: ignore[arg-type]
                timeout = 0.0  # drain remaining without waiting
            except Empty:
                break
        return events

    def close(self) -> None:
        """Signal the monitor thread to stop."""
        self._q.put(_SENTINEL)
