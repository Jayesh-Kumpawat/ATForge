# LLM Client — `src/atforge/llm/`

## Status: A1 + A2 Complete

This module implements the full LLM provider stack for strategy evolution. All calls
go through `complete_with_fallback` which chains providers, retries transiently, and
wraps each call in a Langfuse trace.

## Architecture

```
llm/
  types.py       — LlmRequest, LlmResponse, LlmProvider Protocol, error hierarchy
  registry.py    — ProviderRegistry, build_default_registry(settings)
  router.py      — complete_with_fallback (single public entrypoint)
  tracing.py     — Langfuse 4.x trace_completion context manager
  providers/
    gemini.py    — Google Gemini via openai-compat shim
    groq.py      — Groq cloud
    openrouter.py — OpenRouter (20+ free models)
    ollama.py    — Local Ollama (gated by settings.enable_ollama)
```

## Calling the LLM

```python
from atforge.llm.registry import build_default_registry
from atforge.llm.router import complete_with_fallback
from atforge.llm.types import LlmRequest
from atforge.config import settings

registry = build_default_registry(settings)
priority = settings.llm_provider_priority  # e.g. ["gemini", "groq", "openrouter"]

response = complete_with_fallback(
    LlmRequest(
        prompt="Suggest new SMA fast/slow windows...",
        system="You are a quant analyst. Reply with JSON only.",
        temperature=0.8,
        trace_name="param_delta_sma",
    ),
    registry=registry,
    priority=priority,
    tracing_enabled=True,   # flip on when LANGFUSE_PUBLIC_KEY is set
)
print(response.text)
```

## Tool calling (A1 addition)

Multi-turn tool calling is supported for providers with `supports_tools=True` (currently Gemini only).

```python
# New types in types.py
@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters_schema: dict[str, Any]  # JSON Schema of tool arguments

@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

@dataclass(frozen=True, slots=True)
class Message:
    role: Literal["user", "assistant", "tool"]
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] | None = None
    tool_call_id: str | None = None  # set when role=="tool"
```

Router filter: when `LlmRequest.tools` is set, `complete_with_fallback` skips providers where `supports_tools=False`. All non-Gemini providers have `supports_tools=False`.

Used by: `ResearchAgentMutator` / `run_react_loop` in `evolution/agent_runner.py`.

## LlmRequest fields

```python
@dataclass(frozen=True, slots=True)
class LlmRequest:
    prompt: str = ""
    model: str | None = None          # None = provider's default_model
    system: str | None = None
    temperature: float = 0.7
    max_tokens: int = 1024
    trace_name: str | None = None     # Langfuse span name
    metadata: dict | None = None
    response_schema: type | None = None  # reserved for JSON-mode (provider-specific)
    tools: tuple[ToolSpec, ...] | None = None     # multi-turn tool calling (A1)
    messages: tuple[Message, ...] | None = None   # multi-turn conversation history (A1)
```

LlmResponse additions (A1):
```python
tool_calls: tuple[ToolCall, ...] | None = None  # present when stop_reason=="tool_use"
stop_reason: str | None = None  # "end_turn" | "tool_use" | "max_tokens"
```

LlmProvider Protocol (A1 addition):
```python
supports_tools: bool  # True only for providers wired with function-calling support
```

## Error handling

| Exception | Meaning | Router action |
|---|---|---|
| `RateLimitError` | HTTP 429, quota | retry with exponential backoff, then next provider |
| `TransientError` | HTTP 5xx, timeout | retry with exponential backoff, then next provider |
| `AuthError` | HTTP 401/403 | skip provider immediately, try next |
| `FatalError` | non-retryable 4xx | skip provider immediately, try next |
| `LlmExhausted` | all providers failed | raised to caller |

## Langfuse tracing (4.x API)

**Do NOT use the v2 `Langfuse(public_key=..., secret_key=...)` constructor** — that's the old API.

Langfuse 4.x (installed as `langfuse>=4.5.0`) uses the OTEL-compatible API:

```python
from langfuse import get_client

client = get_client()   # reads LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST from env

with client.start_as_current_observation(name="span_name", as_type="generation", input="...") as obs:
    result = do_llm_call()
    obs.update(output=result, usage_details={"input": 10, "output": 20, "total": 30})
```

Keys are set in `.env` as `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`.
The `tracing.py::trace_completion` context manager handles this exactly. Pass
`tracing_enabled=True` to `complete_with_fallback` to activate.

### `trace_node` (A2 Phase 9 addition)

Wraps a full pipeline node in a Langfuse span. Accepts `tags` for per-role filtering in the Langfuse UI:

```python
with trace_node("critic_node", enabled=deps.tracing_enabled,
                metadata={"gen": state["generation"]},
                tags=["critic", "a2"]):
    ...node logic...
```

Signature: `trace_node(node_name, *, enabled=False, client=None, metadata=None, tags=None)`

### `score_current_observation` (A2 Phase 9 addition)

Score the currently active Langfuse observation. No-op when `enabled=False`. Must be called inside an active `trace_node` or `trace_completion` context:

```python
score_current_observation(
    "veto_rate",
    vetoed / total,
    enabled=deps.tracing_enabled,
    comment=f"{vetoed}/{total} proposals vetoed",
)
```

Signature: `score_current_observation(name, value, *, enabled=False, client=None, comment=None)`

## Adding a new provider

1. Create `llm/providers/myprovider.py` with a class exposing `name`, `default_model`, `complete(request)`, `supports(model)`.
2. Add a registration block in `registry.py::build_default_registry` (gated on an API key check).
3. Done — no other changes needed in router, mutators, or ratchet.

## Critical constraint

**Claude Pro cannot be used programmatically** — blocked April 4, 2026 for API/automated use.
Claude Code (interactive session) is the pair-programmer only. Do not add Anthropic SDK to runtime deps.

## Provider defaults

| Provider | Default model | Free tier |
|---|---|---|
| Gemini | gemini-2.5-flash | 1,500 RPD |
| Groq | llama-3.3-70b-versatile | ~14,400 RPD (burst) |
| OpenRouter | auto | 20+ free models |
| Ollama | qwen2.5-coder:14b | unlimited (local) |
