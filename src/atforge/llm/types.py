"""Shared LLM types — `LlmRequest`, `LlmResponse`, `LlmProvider` Protocol, error hierarchy.

All Phase 2a LLM code (router, registry, providers, mutators) imports from here.
The Phase 1 `client.py` re-exports the dataclasses for back-compat.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class LlmRequest:
    prompt: str
    model: str | None = None
    system: str | None = None
    temperature: float = 0.7
    max_tokens: int = 1024
    trace_name: str | None = None
    metadata: dict[str, Any] | None = None
    response_schema: type | None = None


@dataclass(frozen=True, slots=True)
class LlmResponse:
    text: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    trace_id: str | None = None


@runtime_checkable
class LlmProvider(Protocol):
    """Structural Protocol for LLM providers. Each concrete provider lives in `llm/providers/`."""

    name: str
    default_model: str

    def complete(self, request: LlmRequest) -> LlmResponse: ...

    def supports(self, model: str) -> bool: ...


class LlmError(Exception):
    """Base for all LLM errors raised through the router."""


class RateLimitError(LlmError):
    """HTTP 429 / quota exhaustion. Retry with exponential backoff."""


class AuthError(LlmError):
    """HTTP 401/403. Do not retry; fall through to the next provider."""


class TransientError(LlmError):
    """HTTP 5xx, network glitch, timeout. Retry with backoff."""


class FatalError(LlmError):
    """Non-retryable 4xx (other than 401/403/429). Fall through, do not retry."""


class LlmExhausted(LlmError):
    """All providers in the configured chain failed."""
