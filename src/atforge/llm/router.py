"""Router — single public LLM entrypoint with retry + fallback over a provider chain.

Classifies provider exceptions:
  RateLimitError, TransientError -> retry with exponential backoff (same provider)
  AuthError, FatalError          -> fall through to next provider (no retry)

If all providers exhaust, raises `LlmExhausted`.

The `sleep` parameter is injectable so tests don't actually sleep.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from atforge.llm.registry import ProviderRegistry
from atforge.llm.tracing import trace_completion
from atforge.llm.types import (
    AuthError,
    FatalError,
    LlmError,
    LlmExhausted,
    LlmRequest,
    LlmResponse,
    RateLimitError,
    TransientError,
)


def complete_with_fallback(
    request: LlmRequest,
    *,
    registry: ProviderRegistry,
    priority: list[str],
    max_retries: int = 3,
    base_delay: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    tracing_enabled: bool = False,
) -> LlmResponse:
    chain = registry.chain(priority)
    if not chain:
        raise LlmExhausted("provider chain is empty (no registered providers match priority)")

    last_error: LlmError | None = None

    for provider in chain:
        retryable = True
        attempt = 0
        while retryable and attempt < max_retries:
            try:
                with trace_completion(request, provider.name, enabled=tracing_enabled) as recorder:
                    response = provider.complete(request)
                    recorder.record_response(response)
                    return response
            except (RateLimitError, TransientError) as e:
                last_error = e
                attempt += 1
                if attempt < max_retries:
                    sleep(base_delay * (2 ** (attempt - 1)))
            except (AuthError, FatalError) as e:
                last_error = e
                retryable = False  # break out of retry loop, try next provider

    raise LlmExhausted(f"all providers failed; last={last_error!r}") from last_error
