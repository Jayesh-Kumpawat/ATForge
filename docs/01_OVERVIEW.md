# 01 — System Overview

## What ATForge is

ATForge is an automated, self-improving multi-agent system that **discovers, backtests, and refines chart-pattern trading strategies** for NSE (Indian) equities. It downloads daily price data, detects patterns, backtests them, ranks the results, then uses LLM-driven agents to propose mutations to the best strategies — and loops, generation after generation, keeping a full audit trail of every experiment in a SQLite knowledge base.

It is two things at once: a portfolio project demonstrating agentic AI engineering, and the seed of a real overnight trading-research assistant. Phase 3 (human approval + broker execution) is deferred; today the system stops at "ranked strategies with reasoning."

## The one-sentence mental model

> A LangGraph state machine runs a fan-out backtest, then three LLM agents (explore → exploit → critique) propose and filter strategy mutations, a ratchet scores parent-vs-child, and the loop repeats — every step writing to SQLite, every LLM call routed through a fallback chain and traced to Langfuse.

## The pipeline at a glance

The whole system is one compiled LangGraph graph. Eleven nodes, two conditional edges, one loop:

```
START
  │
  ▼
load_universe ──▶ fetch_data ──▶ detect_patterns
                                      │
                                      │  conditional edge: run_backtest_dispatcher
                                      │  emits one Send per pattern signal
                                      ▼
                              [ run_backtest_one ] × N   ← parallel fan-out (Send API)
                                      │
                                      ▼
                                  ratchet ──▶ rank ──▶ explorer_node ──▶ exploiter_node
                                                                              │
                                                                              ▼
                                                                         critic_node
                                                                              │
                                                                              ▼
                                                                        aggregate_node
                                                                              │
                                              conditional edge: loop_decision │
                                  ┌───────────────────────────────────────────┤
                                  │ "continue"                       "stop"    │
                                  ▼                                            ▼
                          advance_generation                                  END
                                  │
                                  └──────────▶ detect_patterns   (loop back)
```

Defined in `graph/pipeline.py:build_pipeline`. The two conditional edges are the only branching:
- **`run_backtest_dispatcher`** (after `detect_patterns`) — fans out: returns a list of `Send` objects, one per pattern signal, each routed to `run_backtest_one`. This is the parallelism.
- **`loop_decision`** (after `aggregate_node`) — returns `"continue"` or `"stop"`, deciding whether to evolve another generation.

## How one run lives and dies

A run is one call to `graph.invoke(...)`. Its lifecycle:

1. **Startup** (`cli.py:pipeline`) — parse CLI args, create the DB, build all dependencies (`PipelineDeps`), compile the graph, mint a 12-char `run_id`.
2. **Generation 0 — baseline.** `load_universe` → `fetch_data` → `detect_patterns` produces pattern signals for every (symbol × detector). The dispatcher fans them out; `run_backtest_one` backtests each in parallel. `ratchet` is a no-op (no parent to compare). `rank` reads the leaderboard.
3. **Generation 0 — propose.** `explorer_node` and `exploiter_node` ask LLMs to propose mutations of the top strategies. `critic_node` reviews each proposal and may veto it. `aggregate_node` upserts the survivors as new child strategies.
4. **`loop_decision`** — if `generation + 1 < max_generations`, go to step 5; else END.
5. **Generation N — advance.** `advance_generation` increments the counter and swaps `detector_configs` to the proposed child configs, then loops back to `detect_patterns`. The children get detected, backtested, and *now* `ratchet` fires — scoring generation-N children against generation-(N−1) parents.
6. Repeat until `loop_decision` says stop. Then `rank` of the final generation is the last leaderboard; the CLI prints it.

With the default `max_generations=1`, steps 3–6 are skipped entirely (explorer/exploiter/critic all short-circuit) — the run is a pure single-pass backtest, identical to the pre-evolution "Phase 1" behavior.

See [02_EXECUTION_FLOW.md](02_EXECUTION_FLOW.md) for the function-by-function trace.

## The four runtime concerns, and where each lives

| Concern | Module | One-liner |
|---|---|---|
| **Orchestration** | `graph/` | LangGraph `StateGraph`, the 11 nodes, `PipelineState`, `PipelineDeps`, the event bus |
| **Evolution / agents** | `evolution/` | Mutators, the ReAct research agent, the 5 DB tools, the ratchet acceptance criterion |
| **LLM access** | `llm/` | Provider registry, fallback router, 6 providers, Langfuse tracing, tool-calling types |
| **Domain work** | `data/`, `patterns/`, `backtest/`, `storage/` | Fetch OHLCV, detect patterns, run vectorbt, persist everything to SQLite |

## Module map

```
src/atforge/
├── cli.py            CLI entry (Typer). 4 commands: pipeline, experiments, rank, inspect.
├── config.py         Settings (pydantic-settings). Reads .env. The `settings` singleton.
├── monitor.py         PipelineMonitor — Rich live terminal display, background thread.
│
├── graph/            ── ORCHESTRATION ──
│   ├── pipeline.py    build_pipeline(deps) — compiles the StateGraph.
│   ├── state.py       PipelineState (TypedDict) + SignalRef. Reducer annotations.
│   ├── deps.py        PipelineDeps + AgentRoleConfig — the dependency bundle.
│   ├── role_config.py load_role_configs() — reads atforge.yaml for agent roles.
│   ├── nodes.py        Phase 1 node factories: load_universe, fetch_data, detect_patterns, rank.
│   ├── nodes_phase2.py Phase 2a: backtest dispatcher + worker, ratchet, advance_generation, loop_decision.
│   ├── nodes_a2.py     A2 multi-agent: explorer, exploiter, critic, aggregate.
│   └── events.py       EventBus + 11 event dataclasses for live monitoring.
│
├── evolution/        ── EVOLUTION / AGENTS ──
│   ├── types.py        DetectorConfig, StrategyRow, ProposedMutation, EvaluationResult,
│   │                   RatchetThresholds, RatchetVerdict, the Mutator Protocol.
│   ├── ratchet.py      build_evaluation_result (DB I/O) + judge_mutation (pure scoring).
│   ├── registry.py     DetectorConfig ↔ PatternDetector round-trip serialization.
│   ├── prompts.py      Pydantic response schemas + prompt templates for mutators.
│   ├── research_prompts.py  System prompts + initial messages for the 4 agent roles.
│   ├── agent_runner.py run_react_loop() — the multi-turn ReAct loop.
│   ├── agent_tools.py  build_research_tools() — the 5 read-only DB tools.
│   └── mutators/
│       ├── _utils.py        call_llm_with_schema() — parse + validate + retry.
│       ├── param_delta.py   ParamDeltaMutator — LLM tweaks SMA/RSI params.
│       ├── composition.py   CompositionMutator — LLM picks AND/OR of two detectors.
│       └── research_agent.py ResearchAgentMutator — ReAct loop + tools before proposing.
│
├── llm/              ── LLM ACCESS ──
│   ├── types.py        LlmRequest, LlmResponse, ToolSpec, ToolCall, Message, error hierarchy.
│   ├── client.py       Back-compat re-exports (the `complete()` stub is unused).
│   ├── registry.py     ProviderRegistry + build_default_registry(settings).
│   ├── router.py       complete_with_fallback() — THE LLM entrypoint.
│   ├── tracing.py      Langfuse 4.x wrappers: trace_completion, trace_node, score_*.
│   └── providers/
│       ├── _openai_compat.py  OpenAICompatProvider base + body/parse/error helpers.
│       ├── gemini.py          GeminiProvider (native Gemini API, not OpenAI-compat).
│       ├── groq.py, openrouter.py, cerebras.py, nvidia.py  6-line OpenAI-compat subclasses.
│       └── ollama.py          OllamaProvider (local, distinct request shape).
│
├── data/             ── DATA ──
│   ├── protocol.py     DataProvider Protocol + validate_ohlcv contract enforcement.
│   ├── chain.py        FallbackDataProvider — tries providers in order.
│   ├── cache.py        CachedProvider — parquet disk cache.
│   ├── universe.py     load_nifty50() — reads the 50-symbol snapshot.
│   └── providers/      openchart.py, jugaad.py, yfinance.py.
│
├── patterns/         ── PATTERNS ──
│   ├── base.py         PatternDetector Protocol + PatternSignal dataclass.
│   ├── talib_cdl.py    TalibCdlDetector — wraps TA-Lib CDL* candlestick functions.
│   ├── pandas_ta.py    SmaCrossover + RsiOversoldReclaim — indicator detectors.
│   ├── composition.py  AndDetector / OrDetector — combine two detectors.
│   └── structural.py   DoubleBottomDetector — scipy find_peaks stub.
│
├── backtest/         ── BACKTEST ──
│   ├── engine.py       run_backtest() — vectorbt wrapper. BacktestResult. +1 bar shift.
│   └── metrics.py      compute_metrics() — extracts Sharpe/Sortino/drawdown/etc.
│
└── storage/          ── STORAGE ──
    ├── schema.sql      The 5 tables + FTS5 virtual table. PRAGMA user_version = 2.
    ├── db.py           connect(), txn(), init_db() — SQLite, WAL mode.
    ├── migrate.py      apply_migrations() — version-gated .sql migrations.
    └── repo.py         All SQL — insert_* writes, get_*/top_rankings reads.
```

## Phase status

| Phase | State | What it added |
|---|---|---|
| Phase 1 — Foundation | ✅ | Data fetch, pattern detection, backtest, storage, ranking, linear graph |
| Phase 2a — Evolution loop | ✅ | LLM mutators, parallel backtest (Send API), ratchet, the generation loop |
| A1 — Research agent | ✅ | ReAct loop, tool calling on all OpenAI-compat providers + Gemini, `ResearchAgentMutator` |
| A2 (Phases 6–9) — Multi-agent | ✅ | The 4-node explorer/exploiter/critic/aggregate topology, `AgentRoleConfig`, critic hard-veto, Langfuse trace tags + veto scoring |
| Phase 2b — Evolution depth | ⏳ deferred | OpenEvolve population dynamics, Qdrant similarity dedup, bootstrap significance |
| Phase 3 — HITL & execution | ⏳ deferred | Telegram/web approval, paper trading, Zerodha Kite broker integration |

Everything documented here is the **A2-complete** backend. 289 tests pass as of the last doc-sync commit.

## Key vocabulary

| Term | Meaning |
|---|---|
| **run** | One `graph.invoke()`. Identified by a 12-char hex `run_id`. |
| **generation** | One loop iteration. Generation 0 = baseline detectors; generation N = mutated children. |
| **detector** | An object that turns OHLCV into a boolean entry signal (`SmaCrossover`, `TalibCdlDetector`, ...). |
| **strategy** | A detector persisted to the `strategies` table — deduped by `(name, params_json)`. |
| **mutation / proposal** | A candidate child `DetectorConfig` an LLM proposes from a parent strategy. |
| **mutator** | A class that generates proposals (`ParamDeltaMutator`, `CompositionMutator`, `ResearchAgentMutator`). |
| **agent** | An LLM running a ReAct loop with tools — used by the research mutator and the critic node. |
| **ratchet** | The pure acceptance test: is a child strategy good enough to beat its parent? |
| **node** | One step in the LangGraph graph — a pure function `PipelineState -> dict`. |
