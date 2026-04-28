# LLM Client — `src/atforge/llm/`

## Phase 1 status: SCAFFOLD ONLY

This module exists but makes no LLM calls in Phase 1. `complete()` raises `NotImplementedError`.

The scaffold is here so:
1. Import paths are stable — Phase 2 fills in the body without changing callers.
2. The `LlmRequest` / `LlmResponse` dataclasses define the interface contract upfront.

## Interface

```python
@dataclass
class LlmRequest:
    prompt: str
    system: str | None = None
    model: str | None = None         # None = use default from settings
    temperature: float = 0.7
    max_tokens: int = 4096
    trace_name: str | None = None    # Langfuse span name

@dataclass
class LlmResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int

def complete(request: LlmRequest) -> LlmResponse:
    raise NotImplementedError("LLM client is Phase 2")
```

## Phase 2 implementation plan

Priority order (all free):
1. **Gemini 2.5 Flash** — 1,500 requests/day free, primary workhorse
2. **Groq** — fast inference for burst/latency-sensitive tasks
3. **OpenRouter** — 20+ free models for diversity / ensemble
4. **Ollama (Qwen2.5-Coder 14B)** — unlimited local fallback for overnight batch

All calls route through this single `complete()` function with:
- **Langfuse tracing** — every call creates a trace with `trace_name`, input tokens, output tokens, latency
- **Automatic fallback** — if Gemini hits rate limit, fall through to Groq, then OpenRouter, then Ollama
- **Model selection** — `request.model = None` → use current primary; explicit model overrides for experiments

## Critical constraint

**Claude Pro cannot be used programmatically** — blocked April 4, 2026 for API/automated use. Claude Code (interactive session) is the pair-programmer only. Do not add Anthropic SDK to runtime deps.

## Langfuse setup (Phase 2)

```python
from langfuse import Langfuse
client = Langfuse(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    host=settings.langfuse_host,
)
```

Keys already read from `.env` via `config.py::Settings`. Langfuse Cloud Hobby tier = 50k observations/month free.
