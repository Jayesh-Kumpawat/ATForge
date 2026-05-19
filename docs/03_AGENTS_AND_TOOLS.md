# 03 — Agents, Tools & the LLM Stack

This doc answers: *what are the agents, how do they think, what tools can they call, and how does an LLM call actually leave the process?* It covers the whole evolution/agent layer plus the `llm/` module.

If you only skim, read [The big picture](#the-big-picture) and [Who can call tools](#who-can-call-tools-the-exposure-map) — those two sections correct the most common misconceptions.

---

## The big picture

ATForge has **two layers of LLM use**, and they are easy to confuse:

1. **Mutators** — `ParamDeltaMutator`, `CompositionMutator`. A mutator makes a *single, structured* LLM call: "here is a strategy, propose new parameters as JSON." No tools, no multi-turn conversation. One request, one validated response.

2. **Agents** — the **ReAct loop** (`run_react_loop`). An agent runs a *multi-turn* conversation: the LLM can call read-only DB tools, see the results, reason again, and only then produce a final answer. Two things use it: the `ResearchAgentMutator` and the `critic_node`.

The A2 multi-agent pipeline strings four nodes together — `explorer → exploiter → critic → aggregate` — but those nodes are *orchestration*, not the agents themselves. The actual "agent" is the ReAct loop that exploiter and critic invoke.

```
explorer_node ──▶ exploiter_node ──▶ critic_node ──▶ aggregate_node
     │                  │                 │                │
 deps.mutators    ResearchAgent-     ReAct loop        no LLM —
 (param_delta,    Mutator → ReAct    per proposal      pure filter
  composition)    loop + 5 tools     + 5 tools         + DB upsert
 single-shot      multi-turn         multi-turn
 LLM calls        agent              agent
```

---

## Who can call tools — the exposure map

A frequent misconception (and a stale claim in `graph/CLAUDE.md`) is that the explorer runs a high-temperature research agent. **It does not.** Here is the truth from the code:

| Node / component | LLM mechanism | Tools? | Which tools |
|---|---|---|---|
| `explorer_node` | `deps.mutators` — i.e. `ParamDeltaMutator` + `CompositionMutator` | **No** | — single-shot calls |
| `exploiter_node` | a fresh `ResearchAgentMutator` → `run_react_loop` | **Yes** | the 5 research tools |
| `critic_node` | `run_react_loop` directly, once per proposal | **Yes** | the 5 research tools |
| `ResearchAgentMutator` (also usable as the `research` mutator) | `run_react_loop` | **Yes** | the 5 research tools |
| `ParamDeltaMutator`, `CompositionMutator` | one `call_llm_with_schema` call | **No** | — |

So **tools are exposed to exactly two runtime agents: the exploiter's research mutator and the critic.** The explorer, as currently wired, runs plain single-shot mutators.

---

## Agent roles and configuration

### `AgentRoleConfig` (`graph/deps.py`)

A frozen dataclass, one per role:

```python
@dataclass(frozen=True)
class AgentRoleConfig:
    role: str               # "explorer" | "exploiter" | "critic"
    temperature: float
    max_iterations: int     # ReAct loop bound
    system_prompt: str
    llm_priority: tuple[str, ...] = ()   # () = use the global priority
    model: str | None = None             # None = router default
```

### `atforge.yaml` and `load_role_configs` (`graph/role_config.py`)

`load_role_configs()` auto-discovers `atforge.yaml` in the working directory. Absent file → hardcoded defaults (`_ROLE_DEFAULTS`). Present file → defaults overlaid with the YAML's `roles:` block, field by field (omitted YAML fields keep the default).

Defaults and the shipped `atforge.yaml` agree:

| Role | temperature | max_iterations | llm_priority (yaml) | Intent |
|---|---|---|---|---|
| explorer | 0.9 | 4 | gemini, groq, openrouter | high-temp, novelty-seeking |
| exploiter | 0.4 | 4 | gemini, groq | low-temp, refinement |
| critic | 0.3 | 3 | gemini | very low-temp, conservative |

> **Important caveat:** `explorer_node` **never reads `role_configs["explorer"]`.** The explorer's 0.9 temperature exists in config but is not applied anywhere — the explorer runs `deps.mutators`, whose temperatures are their own constructor defaults (`ParamDeltaMutator` 0.8, `CompositionMutator` 0.7). Only `exploiter_node` and `critic_node` actually consume their `AgentRoleConfig`. See [04 — doc/code drift](04_DESIGN_DECISIONS.md#appendix-doc-vs-code-drift-found-2026-05-18).

`role_configs` is carried on `PipelineDeps.role_configs` and injected into the nodes.

---

## The four A2 nodes in detail

All four are factories in `graph/nodes_a2.py`. Shared helpers at the top of that file:
- `_make_fingerprint(parent_id, child_config)` → `f"{parent_id}:{json.dumps(child_config, sort_keys=True)}"` — the stable dedup key that ties a proposal to its veto.
- `_proposals_from_mutators(deps, run_id, generation, role)` — query top parents, run *all* `deps.mutators`, wrap each result as a proposal dict.
- `_proposals_from_mutator(deps, run_id, generation, role, mutator)` — same but for one specific mutator.

A "proposal dict" has: `generation`, `parent_strategy_id`, `child_config`, `reasoning`, `role`, `fingerprint`.

### `explorer_node` (`make_explorer_node`)
- **Skips** (returns `{"proposed_mutations": []}`) when `generation + 1 >= max_generations` — i.e. there is no next generation to feed.
- Otherwise: `_proposals_from_mutators(deps, run_id, generation, role="explorer")` — queries the top-`top_n_parents` strategies of the current generation, runs every mutator in `deps.mutators` against them.
- Wrapped in a `trace_node("explorer_node", tags=["explorer"])` span.
- **Returns** `{"proposed_mutations": [...]}` — a reducer field.

### `exploiter_node` (`make_exploiter_node`)
- **Skips** when `generation + 1 >= max_generations` **or** `deps.llm_router is None`.
- Otherwise: reads `role_configs["exploiter"]`, constructs a **fresh `ResearchAgentMutator`** with that role's `temperature`, `max_iterations`, `model`, and `system_prompt`. Runs it via `_proposals_from_mutator`.
- Wrapped in `trace_node("exploiter_node", tags=["exploiter"])`.
- **Returns** `{"proposed_mutations": [...]}` — appended (reducer) to the explorer's list.

### `critic_node` (`make_critic_node`)
- **Skips** (returns `{"vetoed_mutations": []}`) when there are no current-generation proposals **or** `deps.llm_router is None`.
- Otherwise, reads `role_configs["critic"]`, builds the 5 tools with `build_research_tools()`, and **for each proposal**:
  1. `run_react_loop(llm_router, tools, critic_system_prompt, critic_initial_message(proposal), conn, max_iterations=3, temperature=0.3, role="critic", trace_name="critic_agent")`.
  2. `_parse_critic_verdict(raw)` — 3-layer parse → a `CriticVerdict` (`{verdict: "accept"|"veto", reason: str}`) or `None`.
  3. Emit `EvtCriticVerdict`.
  4. If the verdict is `"veto"`: add to `vetoed`, and `insert_experiment(..., mutator="critic_veto", child_strategy_id=None, accepted=0, ...)` — a veto leaves a permanent row in the `experiments` log even though no child strategy was ever created.
- After the loop: `score_current_observation("veto_rate", vetoed/total, ...)` — attaches the veto rate to the Langfuse span.
- **Safe default:** if the LLM fails or returns unparseable output, `_parse_critic_verdict` returns `None` and the proposal is **accepted** — the critic never blocks the pipeline on an LLM error.
- **Returns** `{"vetoed_mutations": [...]}`.

### `aggregate_node` (`make_aggregate_node`)
- No LLM. Pure filter + persist.
- Filters to the current generation, builds `vetoed_fps` (the set of vetoed fingerprints), computes `survivors = current_proposals − vetoed`.
- For each survivor: `build_detector_from_config(child_config)` then `upsert_strategy(...)` — the child strategy becomes a real `strategies` row with an id.
- **Returns** `{"mutations": [...]}` — records with `parent_strategy_id`, `child_strategy_id`, `mutator` (= the proposing role), `mutation_json`, `reasoning`. This is the bridge to `ratchet`/`advance_generation`, which both read `mutations`.

---

## The ReAct loop (`evolution/agent_runner.py:run_react_loop`)

This is the actual agent engine. ReAct = **Reason + Act**: the LLM alternates between thinking and calling tools until it produces a final answer.

```python
run_react_loop(llm_router, tools, system_prompt, initial_message, conn, *,
               max_iterations=6, event_bus=None, role="research",
               parent_strategy_id=None, model=None, temperature=0.7,
               trace_name="research_agent") -> str | None
```

Mechanics:

1. Seed the conversation with one `Message(role="user", content=initial_message)`.
2. **Loop up to `max_iterations` times.** Each iteration:
   - Build an `LlmRequest` carrying the full `messages` history **and** `tools` (the `ToolSpec` tuple).
   - `response = llm_router(request)`. On any exception → log + `return None` (the caller treats `None` as failure).
   - If `event_bus`, emit `EvtAgentReasoning` with the response text.
   - **If `response.tool_calls` is empty → this is the final answer. Return `response.text`.**
   - Otherwise: append the assistant message (with its tool calls) to history. For each `ToolCall`: emit `EvtAgentToolCall`, dispatch it via `_dispatch_tool` (match by name, call the handler with `arguments` + the open `sqlite3.Connection`), append the result as a `Message(role="tool", ...)`.
3. **If `max_iterations` is hit without a final answer:** send one last user turn (`RESEARCH_FINAL_TURN`, "emit your final JSON now") with **no tools** and `temperature=0.3`, and return whatever text comes back. This guarantees the loop always terminates with an attempt at a final answer.

`_dispatch_tool(tc, tools, conn)` is a linear name match over the tool list; an unknown tool name returns `{"error": "unknown tool ..."}` rather than raising.

The connection is passed *into* the loop and shared by every tool call — the agent reads a consistent DB snapshot for the duration of its reasoning.

---

## Tool calling — how it actually works

### The types (`llm/types.py`)

```python
@dataclass(frozen=True, slots=True)
class ToolSpec:          # what the LLM is told a tool can do
    name: str
    description: str
    parameters_schema: dict   # JSON Schema of the arguments

@dataclass(frozen=True, slots=True)
class ToolCall:          # what the LLM asks to invoke
    id: str
    name: str
    arguments: dict

@dataclass(frozen=True, slots=True)
class Message:           # one turn of a multi-turn conversation
    role: Literal["user", "assistant", "tool"]
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] | None = None
    tool_call_id: str | None = None     # set when role == "tool"
```

`LlmRequest` carries `tools: tuple[ToolSpec, ...] | None` and `messages: tuple[Message, ...] | None`. `LlmResponse` carries `tool_calls: tuple[ToolCall, ...] | None` and `stop_reason` (`"end_turn"` | `"tool_use"` | `"max_tokens"`).

### Per-provider translation

Each provider translates ATForge's neutral types into its own wire format:

- **OpenAI-compatible providers** (`_openai_compat.py`): `build_chat_body` emits an OpenAI `tools` array (`{"type": "function", "function": {...}}`) with `tool_choice: "auto"`. `parse_chat_response` reads `message.tool_calls` back into `ToolCall` objects. `_messages_to_openai` maps the `Message` history into the OpenAI `messages` array (including `role: "tool"` results).
- **Gemini** (`gemini.py`): `_build_body` emits `tools: [{"functionDeclarations": [...]}]` with `toolConfig.functionCallingConfig.mode = "AUTO"`. `_messages_to_contents` maps history into Gemini `contents[]` — tool results become a `functionResponse` part. `_parse_content` reads `functionCall` parts back into `ToolCall`s. Gemini has no per-call ID, so the function name is reused as the `id`.
- **Ollama** (`ollama.py`): `supports_tools = False` — no tool translation at all.

### The router's tool filter

`complete_with_fallback` (`llm/router.py`): when `request.tools is not None`, the provider chain is filtered to those with `supports_tools = True`. If that leaves nothing, it raises `LlmExhausted("no tool-capable providers in chain")`.

`supports_tools` by provider: **`gemini`, `groq`, `openrouter`, `cerebras`, `nvidia` → `True`; `ollama` → `False`.** (`OpenAICompatProvider` sets the class default `supports_tools = True`, which the four OpenAI-compat subclasses inherit.)

---

## The 5 research tools (`evolution/agent_tools.py`)

`build_research_tools()` returns a list of `ToolDefinition(spec: ToolSpec, handler: Callable)`. All five are **read-only** — they only `SELECT`. Each handler is a thin lambda over a `repo.py` function.

| Tool | Backing `repo.py` function | What the agent learns |
|---|---|---|
| `query_top_strategies` | `top_rankings(conn, limit, run_id)` | The best-performing strategies — "what already works" |
| `query_strategy_details` | `get_strategy(conn, strategy_id)` | Full config + family of one strategy |
| `query_strategy_lineage` | `get_mutation_tree(conn, strategy_id, max_depth)` | The mutation tree under a strategy — "has this direction been tried?" |
| `query_pattern_performance` | `get_pattern_symbol_breakdown(conn, strategy_id)` | Per-symbol Sharpe/Sortino — "which symbols does it struggle on?" |
| `query_recent_experiments` | `get_experiments_for_run(conn, run_id)` | Past ratchet verdicts — "what mutations already failed?" |

`get_mutation_tree` is a recursive SQL CTE walking `experiments.parent_strategy_id → child_strategy_id` chains.

**Adding a tool** is a one-place change: append a `ToolDefinition` to the list in `build_research_tools()`. The dispatcher matches by name; nothing else changes.

The tools all point read-only at the same DB the pipeline is writing — this is the system's institutional memory. An agent in generation 3 can see what generations 0–2 tried, and avoid re-proposing dead ends. (See [01 — vocabulary](01_OVERVIEW.md#key-vocabulary) and the lineage tool above.)

---

## The mutators (`evolution/mutators/`)

A mutator implements the `Mutator` Protocol (`evolution/types.py`): `name: str` and `propose(parents: list[StrategyRow], k: int) -> list[ProposedMutation]`.

### `ParamDeltaMutator` (`param_delta.py`)
- Handles `sma_crossover` (mutates `fast`/`slow`) and `rsi_oversold` (mutates `period`/`oversold`). Skips `talib_cdl` and composites.
- For each parent: builds a prompt (`prompts.py:sma_param_delta_prompt` / `rsi_param_delta_prompt` — current params + performance + few-shot examples + constraints), calls `call_llm_with_schema` with the Pydantic schema (`SmaParamsDelta` / `RsiParamsDelta`), turns the validated result into a `ProposedMutation`.
- Constructor `temperature` default `0.8`. No tools — one LLM call per parent.

### `CompositionMutator` (`composition.py`)
- Takes **pairs** of parents (`itertools.combinations`, capped at `k*2` pairs) and asks the LLM to pick `AND` or `OR`.
- Skips a pair if either config is already at `max_nesting_depth` (default 2) — prevents exponentially deep, never-firing signal trees.
- The child config is `{"type": "and"|"or", "left": <cfg>, "right": <cfg>}`. The higher-Sharpe parent is recorded as `parent_strategy_id`.
- Constructor `temperature` default `0.7`. No tools.

### `ResearchAgentMutator` (`research_agent.py`)
- The agentic mutator. For each parent (`sma_crossover` / `rsi_oversold` only): builds `research_initial_message(...)`, gets the 5 tools, opens a connection, runs `run_react_loop`.
- Parses the loop's final text with `_parse_json` → validates against the `ResearchProposal` Pydantic schema → converts to a `ProposedMutation` (reasoning prefixed `[research]` and suffixed with the model's `confidence`).
- Constructor takes `model`, `max_iterations` (default 6), `temperature` (default 0.7), `system_prompt_override`, `event_bus` — which is exactly how `exploiter_node` configures it from `role_configs["exploiter"]`.
- Enabled as a CLI mutator with `--mutators research` (then it is also used by the explorer).

---

## The structured-output discipline (the 3-layer parse)

LLMs return messy text. ATForge defends in three layers — see `evolution/mutators/_utils.py` and `prompts.py`:

1. **Prompt discipline.** Every system prompt ends with *"Reply ONLY with a valid JSON object — no markdown fences, no extra text."* Prompts include the exact JSON schema and few-shot examples.
2. **Tolerant parsing** (`_utils.py`): `_strip_fences` removes ` ```json ` fences; `_brace_match` extracts the outermost `{...}` block, discarding any preamble the model added; `_parse_json` chains both.
3. **Pydantic validation.** The parsed dict is validated against a schema in `prompts.py` — `SmaParamsDelta` (with a `fast < slow` cross-field validator), `RsiParamsDelta`, `CompositionChoice`, `ResearchProposal`, `CriticVerdict`. Field constraints (`ge`/`le`, `Literal`, `max_length`) reject out-of-range values.

`call_llm_with_schema(llm, request, schema, max_retries=3)` ties it together: call → parse → validate; on failure, retry with a correction appended to the prompt ("previous response was invalid: <error>"). After 3 failures it returns `None` — and the mutation is **silently dropped** (never raised). The critic uses the same parse stack via `_parse_critic_verdict`.

> Historical note: an early bug — Gemini 2.5 Flash's *thinking tokens* eating the `max_tokens` budget and truncating JSON — was fixed by raising `max_tokens` to 1024 and setting `thinkingConfig.thinkingBudget = 0` in `GeminiProvider._build_body`. Both are still in the code.

---

## The LLM stack (`llm/`)

### The provider registry
`build_default_registry(settings)` (`llm/registry.py`) registers one provider per **configured API key**:

| Provider | Class | Wire protocol | `supports_tools` | Default model |
|---|---|---|---|---|
| `gemini` | `GeminiProvider` | native Gemini API | ✅ | `gemini-2.5-flash` |
| `groq` | `GroqProvider` | OpenAI-compat | ✅ | `llama-3.1-8b-instant` |
| `openrouter` | `OpenRouterProvider` | OpenAI-compat | ✅ | `meta-llama/llama-3.1-8b-instruct:free` |
| `cerebras` | `CerebrasProvider` | OpenAI-compat | ✅ | `llama-3.3-70b` |
| `nvidia` | `NvidiaProvider` | OpenAI-compat | ✅ | `meta/llama-3.3-70b-instruct` |
| `ollama` | `OllamaProvider` | local Ollama API | ❌ | `qwen2.5-coder:14b` |

Ollama is gated by `settings.enable_ollama` (off by default). The four OpenAI-compat providers are each a ~10-line subclass of `OpenAICompatProvider` — only `name`, `base_url`, `default_model` differ.

### The router — `complete_with_fallback` (`llm/router.py`)
**The single LLM entrypoint.** Every LLM call in the system goes through it (via the `llm_router` closure built in `cli.py`).

```python
complete_with_fallback(request, *, registry, priority, max_retries=3,
                       base_delay=1.0, sleep=time.sleep, tracing_enabled=False)
```

1. Resolve the provider chain from `priority`. Empty → `LlmExhausted`.
2. If `request.tools` is set, drop providers with `supports_tools=False`.
3. For each provider in order, retry up to `max_retries`:
   - Wrap the call in `trace_completion(...)`, `provider.complete(request)`, record the response, return.
   - `RateLimitError` / `TransientError` → retry **the same provider** with exponential backoff (`base_delay * 2^(attempt-1)`).
   - `AuthError` / `FatalError` → stop retrying this provider, **fall through to the next**.
4. All providers exhausted → raise `LlmExhausted`.

The `sleep` parameter is injectable so tests don't actually wait.

### Error classification (`llm/types.py`)
Providers map HTTP status to a typed exception, and the router routes on the type:

| Exception | Cause | Router action |
|---|---|---|
| `RateLimitError` | HTTP 429 / quota | retry with backoff, then next provider |
| `TransientError` | 5xx, timeout, network | retry with backoff, then next provider |
| `AuthError` | 401 / 403 | skip provider immediately |
| `FatalError` | other non-retryable 4xx | skip provider immediately |
| `LlmExhausted` | whole chain failed | raised to the caller |

### Langfuse tracing (`llm/tracing.py`)
Langfuse **4.x** API (`from langfuse import get_client` — *not* the v2 constructor). Three flag-gated helpers, all no-ops when `enabled=False`:
- `trace_completion(request, provider_name, enabled=...)` — wraps one LLM call as a *generation* observation; records output + token usage.
- `trace_node(node_name, enabled=..., metadata=..., tags=...)` — wraps a pipeline node as a *span*; `tags` (`["explorer"]`, `["critic"]`, ...) enable per-role filtering in the Langfuse UI.
- `score_current_observation(name, value, enabled=...)` — attaches a numeric score to the active observation (the critic's `veto_rate` uses this).

> **Constraint:** Claude (Anthropic) is deliberately **not** a provider. Claude Pro cannot be used programmatically (blocked 2026-04-04); it is the pair-programming assistant only. Do not add the Anthropic SDK to runtime deps.

---

## End-to-end: one critic decision

To make it concrete, here is a single critic verdict, fully traced:

1. `aggregate`'s upstream — `explorer`/`exploiter` — produced a proposal: parent strategy 42, child config `{"type":"sma_crossover","fast":8,"slow":30}`, fingerprint `"42:{...}"`.
2. `critic_node` builds `critic_initial_message(proposal)` — it tells the LLM the parent id, the child config, who proposed it, and *suggests* it call `query_strategy_lineage(42)` and `query_pattern_performance(42)`.
3. `run_react_loop` starts. Iteration 0: the LLM (Gemini, temp 0.3) responds with a `tool_call` for `query_strategy_lineage`. The loop dispatches it → `get_mutation_tree(conn, 42, 3)` → the mutation subtree → appended as a `tool` message.
4. Iteration 1: the LLM sees the lineage, reasons that `fast=8,slow=30` was already tried and rejected, and responds with **no tool calls** — final text `{"verdict": "veto", "reason": "fast=8/slow=30 already tried at gen 1, ratchet-rejected"}`.
5. `_parse_critic_verdict` → `CriticVerdict(verdict="veto", reason=...)`.
6. `critic_node` records it: `vetoed_mutations += [veto_record]`, and `insert_experiment(mutator="critic_veto", child_strategy_id=None, accepted=0, reasoning=...)`.
7. `aggregate_node` sees fingerprint `"42:{...}"` in `vetoed_fps` → the proposal is **not** upserted, **not** backtested. Compute saved.

If the LLM had failed at any step, `run_react_loop` returns `None`, `_parse_critic_verdict` returns `None`, and the proposal is **accepted** — failures never block.
