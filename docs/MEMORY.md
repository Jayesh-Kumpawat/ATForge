# ATForge — Memory Architecture & Production Reliability

> **Portfolio note:** This document answers the most common interview question about agentic AI systems: *"How is memory handled? How do you ensure agents don't re-propose the same things? What happens when an LLM fails in production?"*
>
> Every claim here is backed by actual code in `src/atforge/`. Links to specific files and functions are included.

---

## Contents

1. [The five memory tiers](#1-the-five-memory-tiers)
2. [Tier 1 — Working memory: LangGraph PipelineState](#2-tier-1--working-memory-langgraph-pipelinestate)
3. [Tier 2 — Agent short-term memory: ReAct message history](#3-tier-2--agent-short-term-memory-react-message-history)
4. [Tier 3 — Long-term memory: SQLite knowledge base](#4-tier-3--long-term-memory-sqlite-knowledge-base)
5. [Tier 4 — Memory retrieval: 5 read-only DB tools](#5-tier-4--memory-retrieval-5-read-only-db-tools)
6. [Tier 5 — Observability memory: Langfuse traces](#6-tier-5--observability-memory-langfuse-traces)
7. [How memory tiers interact per generation](#7-how-memory-tiers-interact-per-generation)
8. [Production reliability: what prevents failures](#8-production-reliability-what-prevents-failures)
9. [Common interview questions answered](#9-common-interview-questions-answered)

---

## 1. The five memory tiers

```
┌─────────────────────────────────────────────────────────────────┐
│                    ATForge Memory Architecture                   │
├──────────────┬──────────────────────────────────────────────────┤
│ Tier         │ What it stores            │ Lifetime             │
├──────────────┼──────────────────────────────────────────────────┤
│ 1. Working   │ Pipeline run state        │ One pipeline invoke  │
│ 2. Agent ST  │ ReAct message history     │ One agent call       │
│ 3. Long-term │ All strategies + results  │ Permanent (SQLite)   │
│ 4. Retrieval │ Tool-queried DB slices    │ Per tool call        │
│ 5. Observ.   │ Every LLM call + score    │ Permanent (Langfuse) │
└──────────────┴──────────────────────────────────────────────────┘
```

These are intentionally separate. Mixing them is the most common mistake in agentic AI systems — it leads to stale agent context, state corruption, and OOM on large runs.

---

## 2. Tier 1 — Working memory: LangGraph PipelineState

**File:** `src/atforge/graph/state.py`

`PipelineState` is a `TypedDict` that flows through the LangGraph DAG. It is the *working memory* of a single pipeline run — ephemeral, never persisted to disk.

```python
class PipelineState(TypedDict, total=False):
    # Run identity — set once, never change
    run_id: str           # e.g. "a3f9d2c1b4e7"
    universe: list[str]   # ["RELIANCE", "TCS", ...]
    start_iso: str        # "2015-01-01"
    end_iso: str          # "2025-01-01"

    # Generation tracking
    generation: int        # 0-based, incremented by advance_generation
    max_generations: int   # CLI --max-generations

    # Last-writer-wins (single producer per pass)
    data_refs: dict[str, str]         # {symbol: path_to_parquet_cache}
    detector_configs: list[dict]       # active detectors for next backtest pass

    # Reducer fields — each node appends its OWN delta only
    signal_refs:        Annotated[list[SignalRef], operator.add]
    backtest_ids:       Annotated[list[int], operator.add]
    failures:           Annotated[list[dict], operator.add]
    mutations:          Annotated[list[dict], operator.add]

    # A2 multi-agent accumulators
    proposed_mutations: Annotated[list[dict], operator.add]  # explorer + exploiter
    vetoed_mutations:   Annotated[list[dict], operator.add]  # critic rejections
```

### Why TypedDict, not a class with methods?

LangGraph checkpoints state between every node for HITL interrupt support (Phase 3). TypedDict serializes to JSON trivially. A custom class would need `__getstate__`/`__setstate__` and could silently fail to checkpoint.

### The reducer pattern — why it matters for parallel workers

`run_backtest_one` runs in parallel via the `Send()` API — up to 50 workers simultaneously. Each returns a **delta**, not the full accumulated list:

```python
# WRONG — each worker sending the full list
return {"backtest_ids": state["backtest_ids"] + [new_id]}

# CORRECT — each worker sends only what IT produced
return {"backtest_ids": [new_id]}
```

LangGraph applies `operator.add(existing, returned)` to merge. If a worker returned the full list, LangGraph would produce `[1,2,3] + [1,2,3,4] = [1,2,3,1,2,3,4]` — duplicate IDs, corrupted ratchet comparisons.

### What is NOT in state

**DataFrames, NumPy arrays, Portfolio objects, sqlite3.Connection objects — never in state.**

Why: LangGraph checkpoints state on every node transition. A single OHLCV DataFrame for one symbol is ~4 MB. With 50 symbols, that is 200 MB per checkpoint, potentially checkpointed dozens of times per generation. Instead:
- OHLCV data → written to Parquet cache files, only the **path** goes in state (`data_refs`)
- Pattern signals → written to Parquet cache, only the **path** goes in state (`signal_refs`)
- Backtest results → written to SQLite, only the **row ID** goes in state (`backtest_ids`)

The working memory stays under 50 KB throughout an entire multi-generation run.

---

## 3. Tier 2 — Agent short-term memory: ReAct message history

**File:** `src/atforge/evolution/agent_runner.py` → `run_react_loop()`

Each A2 agent call (explorer, exploiter, or critic) runs a **bounded ReAct loop**. The loop maintains a `messages: tuple[Message, ...]` — this is the agent's short-term memory. It is local to one function call and discarded when the call returns.

```python
def run_react_loop(
    llm_router: Callable,
    tools: list[ToolDefinition],
    system_prompt: str,
    initial_message: str,
    conn: sqlite3.Connection,
    *,
    max_iterations: int = 6,   # hard bound — no infinite loops
    ...
) -> str | None:

    # Short-term memory — starts with the user's task
    messages: tuple[Message, ...] = (
        Message(role="user", content=initial_message),
    )

    for iteration in range(max_iterations):
        # LLM call — full conversation history is sent every turn
        request = LlmRequest(messages=messages, tools=tool_specs, ...)
        response = llm_router(request)

        if not response.tool_calls:
            return response.text   # agent is done — discard messages, return answer

        # Accumulate: assistant reasoning + tool calls
        asst_msg = Message(role="assistant", content=response.text,
                           tool_calls=response.tool_calls)
        messages = (*messages, asst_msg)

        # Execute each tool and append results
        for tc in response.tool_calls:
            result = _dispatch_tool(tc, tools, conn)
            messages = (*messages, Message(role="tool",
                                           content=json.dumps(result),
                                           tool_call_id=tc.id))

    # Max iterations hit — force a final answer without tool access
    messages = (*messages, Message(role="user", content=RESEARCH_FINAL_TURN))
    request = LlmRequest(messages=messages, temperature=0.3, ...)  # lower temp for forced answer
    response = llm_router(request)
    return response.text
```

### What the message history looks like mid-loop

```
Turn 0:  user: "Propose a mutation for SMA_CROSS(10,25). Sharpe=0.82..."
Turn 1:  assistant: <reasoning text> + tool_call: query_top_strategies({limit: 5})
         tool: {"strategies": [{"name": "SMA_CROSS(8,22)", "sharpe": 0.91, ...}]}
Turn 2:  assistant: <reasoning> + tool_call: query_strategy_lineage({strategy_id: 14})
         tool: {"children": [{"child_id": 21, "accepted": 0, ...}]}
Turn 3:  assistant: {"fast": 6, "slow": 20, "reasoning": "8,22 already tried; 6,20 unexplored"}
         (no tool_calls → loop exits)
```

### Why full history is sent every turn (not just last message)

LLMs are stateless. Without the full conversation history, the model has no memory of what tools it already called or what results it received. Sending the full `messages` tuple gives the model its working context for the current task.

### Bounded loops — the production safety guarantee

`max_iterations` (default 6) is a hard ceiling. Without it, a misbehaving LLM that always emits tool calls would loop forever. At max_iterations, the loop sends `RESEARCH_FINAL_TURN` ("You have reached your research limit. Emit your final proposal now.") and drops to temperature=0.3 — this forces a more deterministic final answer.

---

## 4. Tier 3 — Long-term memory: SQLite knowledge base

**Files:** `src/atforge/storage/schema.sql`, `src/atforge/storage/repo.py`

Every strategy, backtest result, pattern signal, and ratchet/critic verdict is written to SQLite. This is the **institutional memory** of the system — it persists across pipeline runs, is queryable by agents, and powers the dashboard.

### Schema overview

```sql
-- All candidate detector configs ever registered
strategies (strategy_id, name, family, params_json UNIQUE, description)

-- Signal detection metadata (not the signals themselves — those are in Parquet)
pattern_signals (signal_id, run_id, strategy_id, symbol, n_signals, generation)

-- Full backtest metrics per (run, strategy, symbol, generation)
backtest_runs (run_id, strategy_id, signal_id, symbol, sharpe, sortino,
               n_trades, max_drawdown, cagr, win_rate, success, generation)

-- Every ratchet verdict AND every critic veto
experiments (run_id, generation, parent_strategy_id, child_strategy_id,
             mutator, accepted, delta_sharpe, composite_score JSON, reasoning)

-- FTS5 index on strategy names/descriptions
strategy_search USING fts5(name, description)
```

### How the UNIQUE constraint prevents duplicate strategy registration

`strategies` has `UNIQUE (name, params_json)`. When `aggregate_node` calls `upsert_strategy`:

```python
INSERT OR IGNORE INTO strategies (name, family, params_json, description)
VALUES (?, ?, ?, ?)
-- RETURNING strategy_id always works — existing row returns its ID
```

`params_json` uses `json.dumps(config, sort_keys=True)` — stable key order regardless of how the dict was constructed. Two code paths that create `{"fast": 10, "slow": 25}` from different dicts will always produce the same canonical string.

This deduplication is the system's memory of "what has been tried." Even across multiple pipeline runs, the same strategy config gets the same `strategy_id`.

### The two types of experiment rows

The `experiments` table records two distinct events:

| Event | `mutator` | `child_strategy_id` | `accepted` | When |
|---|---|---|---|---|
| Critic veto | `"critic_veto"` | `NULL` | `0` | Before backtest — proposal rejected by critic agent |
| Ratchet verdict | `"param_delta"` / `"composition"` | strategy_id | `0` or `1` | After backtest — statistical comparison |

`child_strategy_id=NULL` means the mutation was rejected before a backtest was run — the system never spent compute on it. This distinction matters for the Agent Activity dashboard and for lineage queries.

### WAL mode for concurrent writes

The pipeline runs up to 50 parallel `run_backtest_one` workers, all writing to the same SQLite file. WAL (Write-Ahead Log) mode handles this:

```python
conn.execute("PRAGMA journal_mode=WAL")       # multiple concurrent readers
conn.execute("PRAGMA synchronous=NORMAL")     # ~10k writes/sec on SSD
conn.execute("PRAGMA cache_size=-64000")      # 64 MB page cache
```

Workers acquire write locks briefly per INSERT, then release. The probability of two workers needing the same write lock simultaneously is low — each INSERT takes ~0.1ms. This is sufficient for Phase 1-3 scale.

---

## 5. Tier 4 — Memory retrieval: 5 read-only DB tools

**File:** `src/atforge/evolution/agent_tools.py`

Agents cannot query SQLite directly — they call structured tools. Each tool is a `ToolDefinition` (a `ToolSpec` + a handler that calls a repo function). The tools are the **retrieval layer** that makes long-term memory accessible to agents.

```
Agent (LLM) ──tool_call──▶ _dispatch_tool() ──▶ repo function ──▶ SQLite
            ◀──tool result─────────────────────────────────────────────
```

### The 5 tools

| Tool name | Underlying function | What the agent learns |
|---|---|---|
| `query_top_strategies` | `top_rankings(conn, limit, run_id)` | Best-performing params across all history — "what already works" |
| `query_strategy_details` | `get_strategy(conn, strategy_id)` | Full config + params of any strategy by ID |
| `query_strategy_lineage` | `get_mutation_tree(conn, id, max_depth)` | Recursive parent→child tree — "what has been tried from this parent" |
| `query_pattern_performance` | `get_pattern_symbol_breakdown(conn, id)` | Per-symbol Sharpe breakdown — "where does this pattern underperform" |
| `query_recent_experiments` | `get_experiments_for_run(conn, run_id)` | Ratchet + critic verdicts for a run — "what was rejected and why" |

### Why tools are read-only

All 5 tools are `SELECT`-only. Agents have no write access to the DB during their research loop. Writes happen only through the graph's controlled mutation path (`aggregate_node` → `upsert_strategy`). This prevents an agent from corrupting the DB mid-loop if it hallucinates a tool call.

### Tool dispatch is exception-safe

```python
try:
    result = _dispatch_tool(tc, tools, conn)
except Exception as exc:
    result = {"error": str(exc)[:200]}  # agent sees the error, loop continues
```

If a tool fails (e.g. strategy_id not found), the agent receives `{"error": "..."}` and can continue reasoning or try a different tool. The loop does not crash.

### How lineage prevents re-proposing dead ends

The critic uses `query_strategy_lineage` to check whether a proposed mutation direction has been tried before and failed:

```
Proposal: SMA(8,22) from parent SMA(10,25)
Critic calls: query_strategy_lineage(strategy_id=parent_id)
  → returns: [{child_id: 14, params: {"fast":8,"slow":22}, accepted: 0, 
                reasoning: "sharpe_delta=-0.03<0.05"}]
Critic concludes: this direction was tried and rejected → VETO
insert_experiment(mutator="critic_veto", child_strategy_id=NULL, accepted=0)
```

This is how the system uses long-term memory (Tier 3) to avoid wasting compute in future runs — the rejected lineage is recorded and retrievable.

---

## 6. Tier 5 — Observability memory: Langfuse traces

**File:** `src/atforge/llm/tracing.py`

Every LLM call and every pipeline node execution is traced to Langfuse Cloud. This is immutable append-only observability memory — you can always go back and see exactly what prompt produced what output, on what provider, with what latency.

### What gets traced

**LLM completion traces** (`trace_completion`):
```python
with trace_completion("param_delta_sma", enabled=deps.tracing_enabled) as recorder:
    response = provider.complete(request)
    recorder.record_response(response)
    # → Langfuse span: input=prompt, output=response.text,
    #   usage_details={input_tokens, output_tokens}, latency_ms, provider
```

**Node-level traces** (`trace_node`, Phase 9):
```python
with trace_node("critic_node", enabled=deps.tracing_enabled,
                tags=["critic", "a2"],
                metadata={"gen": state["generation"]}):
    ...critic logic...
    # → Langfuse span wrapping the entire node execution
```

**Numeric scores** (`score_current_observation`, Phase 9):
```python
score_current_observation(
    "veto_rate", vetoed / total,
    enabled=deps.tracing_enabled,
    comment=f"{vetoed}/{total} proposals vetoed this generation",
)
# → Attached to the active critic_node Langfuse span as a numeric score
```

### What you can see in the Langfuse UI

- Per-generation veto rate trend (is the critic becoming too aggressive?)
- Which provider served each request (useful when Gemini is rate-limited)
- Token usage per agent role (are explorer agents burning tokens on useless tool calls?)
- ReAct loop iteration counts (is the critic resolving in 1 turn or 3?)
- Full prompt + response for any specific decision (audit any veto reasoning)

---

## 7. How memory tiers interact per generation

This is the end-to-end flow showing all five tiers working together:

```
Generation 0:
  load_universe   → Tier 1: detector_configs seeded from deps.detectors
  fetch_data      → Tier 3: OHLCV Parquet files written; Tier 1: data_refs updated
  detect_patterns → Tier 3: pattern_signals rows inserted; Tier 1: signal_refs (paths) added
  run_backtest_one × N → Tier 3: backtest_runs rows inserted; Tier 1: backtest_ids added
  ratchet_node    → no-op gen=0
  rank            → Tier 3: top_rankings() read
  
  explorer_node:
    → Tier 2: ReAct loop starts, messages = [(user, initial_message)]
    → Tier 4: query_top_strategies() → Tier 3 read
    → Tier 4: query_strategy_lineage() → Tier 3 read
    → Tier 2: messages grows with tool results
    → Tier 5: each LlmRequest traced to Langfuse
    → Tier 1: proposed_mutations += [proposals]
    → Tier 2: messages discarded (out of scope)
  
  exploiter_node: [same pattern as explorer]
  
  critic_node:
    → Tier 2: ReAct loop per proposal
    → Tier 4: query_recent_experiments() → checks if direction was tried
    → Tier 3: insert_experiment(critic_veto, child_strategy_id=NULL)
    → Tier 5: score_current_observation("veto_rate", ...)
    → Tier 1: vetoed_mutations += [vetoed_configs]
  
  aggregate_node:
    → survivors = proposed_mutations - vetoed_mutations
    → Tier 3: upsert_strategy() for each survivor (UNIQUE dedup)
    → Tier 1: mutations += [accepted_records]
  
  advance_generation → Tier 1: generation=1, detector_configs=survived_configs

Generation 1:
  detect_patterns → uses Tier 1 detector_configs from advance_generation
  run_backtest_one → Tier 3: new backtest_runs rows, generation=1
  ratchet_node → Tier 3: build_evaluation_result() for parent (gen=0) and child (gen=1)
               → Tier 3: insert_experiment(param_delta, accepted=T/F)
               → Tier 5: verdict traced
  [... A2 nodes repeat ...]
```

---

## 8. Production reliability: what prevents failures

### LLM provider failures

**5-provider fallback chain with per-error routing:**

```
complete_with_fallback() tries each provider in priority order:
  RateLimitError  → exponential backoff, then next provider
  TransientError  → exponential backoff (3 retries), then next provider
  AuthError       → skip immediately, try next (no retry — key is wrong)
  FatalError      → skip immediately, try next
  LlmExhausted    → all providers failed → raised to caller → node returns success=False
```

The router also filters providers by `supports_tools=True` when `LlmRequest.tools` is set — so if the only tool-capable provider (Gemini) is down, `LlmExhausted` is raised immediately rather than trying providers that cannot handle the request.

### LLM output hallucination / malformed JSON

Three independent parse layers in every mutator:

```
Layer 1: _strip_fences()  → removes ```json ... ``` if LLM wrapped in markdown
Layer 2: _brace_match()   → extracts outermost {...} (handles preamble text)
Layer 3: Pydantic          → validates types, ranges, cross-field constraints
                              (e.g. fast < slow for SMA)
```

If all three fail, the mutation is **silently dropped** — logged with `structlog` at WARNING level, but the pipeline continues. Evolution is statistical: one bad LLM response does not abort the run.

### Infinite agent loops

`max_iterations` hard-bounds every ReAct loop. At the limit, the runner sends `RESEARCH_FINAL_TURN` with `tools=None` and `temperature=0.3` — forcing a deterministic answer without tool access. The pipeline cannot loop forever.

### Parallel worker failures

`run_backtest_one` (the Send worker) never raises:

```python
try:
    result = run_backtest(signals, prices, hold_bars=deps.hold_bars, ...)
except Exception as exc:
    return {
        "backtest_ids": [],
        "failures": [{"node": "run_backtest", "symbol": symbol, "reason": str(exc)}]
    }
```

A failed worker returns empty `backtest_ids` — its siblings continue running and their results merge normally. The `failures` list is visible in `uv run python main.py inspect <run_id>`. The run completes with partial results rather than aborting.

### Duplicate strategy registration

`upsert_strategy` uses `INSERT OR IGNORE` with a `UNIQUE (name, params_json)` constraint. `params_json` is always serialized with `json.dumps(..., sort_keys=True)`. Two code paths proposing the same config will produce the same canonical string and the same `strategy_id` — the second call is a no-op. This prevents:
- Duplicate backtests for the same strategy
- Ratchet comparisons against wrong baseline
- Strategy lineage corruption

### Critic proposing mutations it already vetoed

Each proposal is deduplicated by fingerprint **before** entering the critic:

```python
def _make_fingerprint(parent_id: int, child_config: dict) -> str:
    return f"{parent_id}:{json.dumps(child_config, sort_keys=True)}"
```

Explorer and exploiter proposals are deduplicated against each other in `aggregate_node`. Even if both propose `SMA(8,22)` from the same parent, only one copy enters the critic review. Historical vetoes from previous runs are retrievable via `query_strategy_lineage` — the critic checks this before vetoing.

### SQLite concurrent write conflicts

WAL mode allows unlimited concurrent readers and serializes writers. Each worker holds the write lock for a single INSERT (~0.1ms). Conflicts are resolved by SQLite internally — no application-level locking needed. The `txn()` context manager handles `BEGIN / COMMIT / ROLLBACK` cleanly:

```python
with txn(conn):
    insert_backtest_result(conn, ...)
# COMMIT on exit, ROLLBACK on any exception
```

### State type errors

`PipelineState` is a `TypedDict`. LangGraph validates that node return values match the annotated types. Returning `{"backtest_ids": "oops"}` instead of `list[int]` raises a `TypeError` at the merge step — caught and logged before it corrupts the accumulated state.

---

## 9. Common interview questions answered

**Q: How do agents avoid re-proposing the same mutations across runs?**

Two mechanisms. First, fingerprint deduplication within a single generation (explorer + exploiter proposals are de-duped before the critic sees them). Second, the critic uses `query_strategy_lineage` to check historical `experiments` rows — if the direction was tried and rejected in any previous run, the critic has evidence to veto it. The lineage data lives in SQLite (Tier 3) and is permanent across runs.

---

**Q: What happens if the LLM is rate-limited during an overnight run?**

The router retries with exponential backoff, then falls through to the next provider. With 5 providers configured, Gemini hitting its 1,500 RPD limit causes automatic failover to Groq, then OpenRouter, etc. If all providers are exhausted for a single agent call, the ReAct loop returns `None` — the mutation is silently dropped and the pipeline continues with whatever proposals succeeded.

---

**Q: How do you prevent the agent from hallucinating strategy parameters outside valid ranges?**

Pydantic validates every LLM response before it is used. `SmaParamsDelta` enforces `fast ∈ [2,50]`, `slow ∈ [10,200]`, and `fast < slow`. `RsiParamsDelta` enforces `oversold ∈ [10,45]`. A proposal that fails validation is silently dropped and logged — it never reaches the DB. The cross-field validator (`fast < slow`) specifically guards against the most common LLM mistake when nudging parameters.

---

**Q: How does the system "learn" over time?**

Learning happens at two levels. Within a run: the ratchet accepts only statistically improved children (all 5 gates must pass), so `detector_configs` for generation N+1 contains only configs that measurably outperformed their parents. Across runs: the SQLite `experiments` table accumulates every accepted and rejected verdict permanently. Agents can query this history via tools to avoid repeating failed directions.

---

**Q: Can an agent corrupt the database?**

No. The 5 agent tools are all `SELECT`-only — the agent cannot write to the DB during its research loop. Writes happen only through `aggregate_node` (calling `upsert_strategy`) and `critic_node` (calling `insert_experiment`), which are plain Python code paths outside the agent's control. The agent influences *which* mutations proceed, but cannot directly mutate the schema or insert arbitrary rows.

---

**Q: What is the memory footprint of a 10-generation run?**

| Component | Size |
|---|---|
| LangGraph state (Tier 1) | < 50 KB — IDs and paths only, no data |
| ReAct message history (Tier 2) | < 100 KB per agent call — discarded after call |
| SQLite DB (Tier 3) | ~5 MB for 10 generations, 50 symbols, 3 mutators |
| Parquet cache (disk) | ~500 MB — OHLCV data, not in memory during pipeline |
| Langfuse (Tier 5) | Unlimited — cloud, zero local footprint |

The pipeline can run on a machine with 512 MB RAM. The constraint is CPU (backtest compute) and network (LLM API calls), not memory.

---

**Q: How is this different from a naive LangChain agent that just calls an LLM in a loop?**

| | Naive LangChain agent | ATForge A2 agents |
|---|---|---|
| Memory between calls | None — each call is stateless | SQLite knowledge base + tool retrieval |
| Loop bound | Often unbounded | Hard `max_iterations` ceiling |
| Provider failure | Crashes or returns None | 5-provider fallback chain with per-error routing |
| Output validation | String parsing | 3-layer parse + Pydantic cross-field validators |
| Duplicate prevention | None | Fingerprint dedup + UNIQUE DB constraint |
| Observability | print statements | Langfuse traces, numeric scores per span |
| Pre-filter | None — everything goes to backtest | Critic hard-vetoes before expensive backtest |
| State isolation | Shared mutable state | Immutable `deps`, reducer-merged `state`, tools are read-only |

---

*This document is maintained by the `update-docs` skill. Update it when: agent loop bounds change, new DB tools are added, new memory tiers are introduced, or provider fallback logic changes.*

*Tags for update-docs: memory, react, tools, production, reliability*
