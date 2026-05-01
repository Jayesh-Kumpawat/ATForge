"""Centralized LLM client with Langfuse tracing.

Public types and the `complete()` entry point. The actual routing / provider
fallback / retry logic lives in `llm.router` (wired in Step 4 of Phase 2a).
"""

from __future__ import annotations

from atforge.llm.types import (
    AuthError,
    FatalError,
    LlmError,
    LlmExhausted,
    LlmProvider,
    LlmRequest,
    LlmResponse,
    RateLimitError,
    TransientError,
)

__all__ = [
    "AuthError",
    "FatalError",
    "LlmError",
    "LlmExhausted",
    "LlmProvider",
    "LlmRequest",
    "LlmResponse",
    "RateLimitError",
    "TransientError",
    "complete",
]


def complete(request: LlmRequest) -> LlmResponse:
    """Run an LLM completion. Step 4 wires this to `router.complete_with_fallback`."""
    raise NotImplementedError(
        "LLM router not yet wired. Phase 2a Step 4 implements provider fallback."
    )
