"""Centralized LLM client with Langfuse tracing.

Phase 1 SCAFFOLD: this module only defines the shape. Any attempt to call
the LLM raises NotImplementedError — Phase 2 will plug in Gemini Flash / Groq /
OpenRouter / Ollama behind this same interface.

CLAUDE.md hard rule: ALL LLM calls must go through this wrapper (Langfuse trace).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LlmRequest:
    model: str
    prompt: str
    temperature: float = 0.7
    max_tokens: int = 1024
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class LlmResponse:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    trace_id: str | None = None


def complete(request: LlmRequest) -> LlmResponse:
    """Run an LLM completion with Langfuse tracing. Phase 2 implements."""
    raise NotImplementedError(
        "LLM client not implemented in Phase 1. Phase 2 adds Gemini/Groq/OpenRouter/Ollama."
    )
