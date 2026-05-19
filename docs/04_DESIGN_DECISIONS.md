# 04 — Design Decisions

*Why* ATForge is built the way it is. This doc never re-explains mechanics (that is [02](02_EXECUTION_FLOW.md) and [03](03_AGENTS_AND_TOOLS.md)) — only the motivation, the trade-off accepted, and the alternative rejected.

Each entry: **Decision → Why → Trade-off / what was rejected.**

---

## Orchestration

### LangGraph as the orchestrator
**Decision.** The pipeline is a LangGraph `StateGraph`, not a hand-written loop or a generic task queue.
**Why.** Three features are used directly: the **Send API** for parallel fan-out, **conditional edges** for the evolution loop, and a typed state object with **reducers**. LangGraph also makes Phase 3's human-in-the-loop interrupts (`interrupt_before`) a near-free addition later. And it is the most in-demand agentic framework — this is partly a portfolio project.
**Trade-off.** A framework dependency and its idioms (factories, reducers, `Send`) instead of plain Python. Accepted because the fan-out + loop + future-HITL combination is exactly LangGraph's sweet spot.

### Node factory functions, not classes
**Decision.** Every node is a closure built by a `make_*(deps)` factory (`make_load_universe`, `make_critic_node`, ...), not a method on a class.
**Why.** A node is a pure function `PipelineState -> dict`. Factories inject `deps` by closure with no globals and no `self`. Tests construct `deps` with a synthetic provider and a mock LLM and call the returned function directly — node code is untouched.
**Trade-off.** A little boilerplate (`make_x` wrapping `x`). Rejected: node classes (more ceremony, mutable `self`, harder to keep pure) and module-level `deps` globals (untestable).

### IDs and paths in state — never data
**Decision.** `PipelineState` holds only primitives, **file paths** to parquet files, and **DB row IDs**. Never DataFrames, signal arrays, or vectorbt `Portfolio` objects.
**Why.** LangGraph checkpoints state. A checkpoint containing 50 OHLCV DataFrames would be enormous and slow. Cheap checkpoints are also a prerequisite for Phase 3's HITL pause/resume.
**Trade-off.** Nodes re-read parquet from disk instead of passing data in memory. Accepted — disk I/O is negligible next to backtests and LLM calls, and the decoupling is worth it. This is a hard rule (see `CLAUDE.md`).

### Reducers vs last-writer-wins
**Decision.** `signal_refs`, `backtest_ids`, `failures`, `mutations`, `proposed_mutations`, `vetoed_mutations` use the `operator.add` reducer; everything else (incl. `detector_configs`) is last-writer-wins.
**Why.** The reducer fields have **multiple concurrent producers** — the fan-out runs N `run_backtest_one` workers in parallel, each returning one `backtest_id`. A reducer concatenates the deltas deterministically; last-writer-wins would have the last worker clobber the rest. `detector_configs` is the opposite: one producer per pass, and it must be *replaced* each generation, so a reducer there would wrongly accumulate stale configs.
**Trade-off.** You must remember which field is which when writing a node — a node returns *only its delta* for reducer fields. Documented in [05](05_DATA_MODEL.md#pipelinestate).

### Send API for parallelism
**Decision.** `run_backtest_dispatcher` returns a list of `Send` objects — one backtest worker per signal — instead of a serial loop over signals.
**Why.** Backtests are independent and the dominant cost. Fan-out gives near-linear speedup. The serial version (`nodes.py:make_run_backtest`) still exists but is **dead code**, kept only as a reference.
**Trade-off.** Workers receive a bare `{"ref", "run_id"}` dict, not the full state, and must merge back via reducers — a little mental overhead for a large speedup.

---

## The ratchet

### A pure scoring function, separated from DB I/O
**Decision.** `judge_mutation(parent, child, thresholds)` is a pure function — no I/O, fully deterministic. DB aggregation lives separately in `build_evaluation_result`.
**Why.** Scoring logic is the part most likely to be wrong and most worth testing. A pure function is trivially unit-tested with hand-built `EvaluationResult`s — every one of the 5 gates can be checked in isolation.
**Trade-off.** Two functions instead of one. Worth it — the seam between "get the data" and "judge the data" is exactly where bugs hide.

### Five gates, all must pass
**Decision.** A child is accepted only if **all** of: Δsharpe ≥ 0.05, Δsortino ≥ 0.02, drawdown ratio ≤ 1.10, ≥ 5 trades, and no per-symbol Sharpe regression worse than 0.5.
**Why.** This is Karpathy's AutoResearch "ratchet" — only commit a change if it strictly improves. The trade gate kills statistical noise (a 2-trade strategy with Sharpe 4 is luck). The per-symbol gate kills strategies that win on average by overfitting one symbol while quietly degrading others.
**Trade-off.** Conservative — a child that improves Sharpe but adds drawdown is rejected. Intentional: the system should compound only real gains. Thresholds are all config-driven (`RatchetThresholds` ← `settings` ← env), so they can be tuned without code changes.

### The ratchet is advisory, not gating
**Observation, not an intended design — a known quirk.** As the code stands, the ratchet verdict does **not** decide which children advance to the next generation.
**Why it happens.** `ratchet` writes an `experiments` row at `generation = N` (the child's generation). `advance_generation` runs at the *end* of generation `N−1` and queries for accepted children at `generation = N` — but that ratchet has not run yet (it fires at the *start* of generation `N`). So `advance_generation` always finds zero accepted rows and takes its `or [all proposed children]` fallback.
**Consequence.** Every proposed-and-not-vetoed child advances. The real per-generation pruning gate is the **critic veto**, not the ratchet. The ratchet still earns its place — it produces the `experiments` verdict log, the `composite_score` breakdown, and the data the dashboard and the agents' `query_recent_experiments` tool rely on.
**If you want the ratchet to gate advancement**, the fix is to align the timing — either ratchet children before `advance_generation` chooses, or have `advance_generation` query the verdicts from the generation that already ran. Flagged here so the next person does not assume the ratchet prunes when it does not.

---

## Numbers and correctness

### Decimal for money, float for ratios
**Decision.** `total_return`, `final_value`, `max_drawdown`, `init_cash` are `Decimal`; `sharpe`, `sortino`, `cagr`, `win_rate` are `float`.
**Why.** Money must not accumulate binary-float drift — over thousands of trades on a ₹10-lakh portfolio that becomes real rupees of error. Ratios are analytical quantities where float is exact enough and what every library expects. `_safe_decimal` converts via `Decimal(str(x))` (not `Decimal(float)`) precisely to avoid importing the float's binary error.
**Trade-off.** Conversions at boundaries and `Decimal` stored as `TEXT` in SQLite. A hard project rule (`CLAUDE.md`): never use `float` for money.

### The +1 bar signal shift
**Decision.** `backtest/engine.py:_bool_to_entry_exit` shifts every entry signal forward one bar before handing it to vectorbt.
**Why.** A pattern is only *known* at the close of bar T. Entering at bar T's price would be lookahead bias — trading on information you did not have. The realistic fill is bar T+1's open. vectorbt has **no built-in lookahead guard**, so the shift is mandatory and explicit.
**Trade-off.** None, really — it is simply correct. Stated as a hard rule so no one "optimizes" it away.

### Worker nodes never raise
**Decision.** `fetch_data`, `detect_patterns`, `run_backtest_one`, `run_backtest` catch every exception and convert it to a `failures` entry or `BacktestResult(success=False)`.
**Why.** One bad symbol or one vectorbt edge case must not abort a 50-symbol, multi-generation run. Partial results are valuable; a crash is not.
**Trade-off.** Failures are silent unless you read the `failures` list or the logs. Accepted — the alternative (fail fast) is wrong for a long unattended batch job.

---

## Storage

### SQLite (WAL + JSON1 + FTS5), not Postgres
**Decision.** One SQLite file, `data/atforge.db`.
**Why.** Zero infrastructure — no server, no container. WAL mode lets the dashboard read while the pipeline writes. JSON1 stores `DetectorConfig` and `composite_score` blobs without extra tables. FTS5 gives free-text search over strategy names/reasoning. SQLite handles far more write throughput than this workload needs.
**Trade-off.** Single-machine, single-writer. Fine for a personal research system; revisit only if it ever becomes multi-user.

### `params_json` with `sort_keys=True`
**Decision.** Every `DetectorConfig` is serialized with `json.dumps(..., sort_keys=True)` before it touches the DB.
**Why.** `strategies` has `UNIQUE (name, params_json)` for dedup. SQLite compares the JSON as a byte string. Without stable key order, `{"fast":5,"slow":20}` and `{"slow":20,"fast":5}` are the *same strategy* stored as *two rows* — and the dedup silently fails.
**Trade-off.** None — it is just a flag. Stated as a hard rule because it is invisible until it breaks.

### `DetectorConfig` round-trip serialization
**Decision.** `evolution/registry.py` converts every `PatternDetector` to/from a plain JSON-safe `DetectorConfig` dict, with a guaranteed round-trip.
**Why.** Detectors must survive three boundaries: LangGraph state (`detector_configs`), the DB (`params_json`), and LLM proposals (the JSON an agent emits). A live object can cross none of them; a dict crosses all three. The round-trip guarantee means a config that survives a DB round-trip rebuilds an identical detector.
**Trade-off.** A serialization layer to maintain (one `if isinstance` arm per detector type). Worth it — it is the linchpin that lets agents propose strategies as JSON.

---

## Abstractions

### Structural `Protocol`s everywhere — no ABCs
**Decision.** `DataProvider`, `PatternDetector`, `Mutator`, `LlmProvider` are all PEP 544 `Protocol`s. No class inherits from them.
**Why.** Structural typing means a class is a valid provider/detector/mutator simply by having the right methods. Tests inject fakes with zero ceremony. New implementations need no import of a base class.
**Trade-off.** Less discoverability (no "find all subclasses"). Mitigated by `@runtime_checkable` and the registries that list concrete implementations.

### Plug-and-play provider registry + OpenAI-compat base
**Decision.** `build_default_registry` registers a provider per API key; adding one is a single gated block. `OpenAICompatProvider` is a base that turns a new OpenAI-compatible provider into a ~10-line subclass.
**Why.** The free-tier LLM landscape changes constantly — providers appear, quotas change. Onboarding a new one must be trivial and must touch nothing else (router, mutators, ratchet all unchanged). This was an explicit requirement: drop-in providers, config-driven routing.
**Trade-off.** Two abstraction layers (registry + compat base). Justified by how often providers actually change.

### The LLM is injected as a `Callable`
**Decision.** Mutators, the ReAct loop, and the agent nodes never import the router. They receive `llm_router: Callable[[LlmRequest], LlmResponse]`, built once in `cli.py`.
**Why.** The entire evolution layer becomes unit-testable with a mock callable — no network, no API keys, no Langfuse. `evolution/` has zero direct LLM I/O by design.
**Trade-off.** The callable is threaded through many constructors. Accepted — dependency injection is exactly what makes the agent layer testable.

### The router fallback chain + typed errors
**Decision.** One entrypoint, `complete_with_fallback`; providers raise a 4-type error hierarchy; the router retries transient errors and falls through fatal ones.
**Why.** Free-tier providers rate-limit and flake constantly. A multi-generation overnight run must survive that. Classifying the error (`RateLimitError`/`TransientError` → retry; `AuthError`/`FatalError` → skip) means the router does the right thing automatically.
**Trade-off.** Every provider must map its HTTP statuses into the hierarchy. A small, well-contained cost.

---

## The agent layer

### Three roles: explore, exploit, critique
**Decision.** Evolution is split into an explorer (novelty), an exploiter (refinement), and a critic (veto) — separate nodes with separate `AgentRoleConfig`s.
**Why.** Explore-vs-exploit is the core tension of any search. Separating them makes the balance explicit and tunable (temperatures, prompts, even different models per role). The critic adds a third idea: **kill bad proposals before spending a backtest on them** — compute is the scarce resource.
**Trade-off.** More nodes, more LLM calls per generation. Accepted — the critic's veto saves more backtest compute than it costs in critic tokens, and the separation is good engineering.

### The critic is a hard veto, before backtest
**Decision.** A vetoed proposal is dropped by `aggregate_node` and never becomes a strategy or a backtest. The veto is logged to `experiments` (`mutator="critic_veto"`, `child_strategy_id=NULL`).
**Why.** The critic uses the lineage tool to spot already-tried, already-failed directions. Catching them *before* the backtest is the whole point — a soft "warning" would save nothing.
**Trade-off.** A wrong veto permanently loses a potentially good strategy. Mitigated two ways: the critic's prompt says *"veto sparingly, only with strong evidence"*, and any LLM/parse failure defaults to **accept** — the system errs toward spending a backtest rather than wrongly discarding.

### `AgentRoleConfig` in YAML
**Decision.** Role temperature, iterations, prompt, model, and provider priority live in `atforge.yaml`, loaded at startup; code holds only defaults.
**Why.** Prompt and temperature tuning is the daily work of an agent system. Doing it in YAML means no code change, no redeploy, and the config is diffable and version-controlled.
**Trade-off.** Config can drift from code intent — and it has: the explorer's YAML temperature `0.9` is never applied (the explorer runs plain mutators, not a role-configured agent). See the appendix.

---

## Cross-cutting

### Observability is flag-gated and optional
**Decision.** Langfuse tracing and the EventBus monitor are both off by default; every trace/emit is guarded.
**Why.** Tests must run with zero external dependencies and zero overhead — they pass `enabled=False` / no `event_bus` and never touch the Langfuse SDK or spawn a monitor thread. Production flips the flags.
**Trade-off.** A guard at every call site (`if deps.event_bus:`, `if not enabled: return`). Cheap, and it keeps the test suite hermetic.

### Free-tier-only LLM stack; Claude is not a provider
**Decision.** Six free providers (Gemini primary, Groq/OpenRouter/Cerebras/NVIDIA fallbacks, Ollama local). Claude is deliberately absent from the runtime.
**Why.** A hard project constraint — free tools only. And Claude Pro cannot be used programmatically (blocked 2026-04-04); Claude Code is the *pair-programmer*, not a runtime dependency. The combined free quota (~5k requests/day) is enough for hundreds of generations.
**Trade-off.** Free models are weaker and flakier than frontier models — which is exactly why the fallback router and the 3-layer parse exist. The discipline they impose is a feature.

### `pandas-ta-classic`, not `pandas-ta`
**Decision.** The RSI detector imports `pandas_ta_classic`.
**Why.** The original `pandas-ta` package carries a supply-chain compromise risk. `pandas-ta-classic` is the maintained, safe fork.
**Trade-off.** None — same API, safe provenance.

### vectorbt OSS 0.28.4
**Decision.** The backtest engine is vectorbt's open-source 0.28.4, pinned.
**Why.** Free, MIT, and extremely fast vectorized backtests — the right fit for running hundreds of automated backtests per generation. The OSS branch is in maintenance mode but its API is frozen and stable, so a pin is safe.
**Trade-off.** No new vectorbt features. Irrelevant — the frozen API is exactly what a reproducible research pipeline wants.

---

## Appendix — doc/code drift found 2026-05-18

These were found while writing this doc set, by reading every source file. They are **stale documentation**, not code bugs. Listed so they can be fixed (in the `CLAUDE.md` files) and so readers trust the code over the old docs.

| Stale claim | Where | Reality in code |
|---|---|---|
| "explorer_node runs a `ResearchAgentMutator` at temperature 0.9" | `graph/CLAUDE.md` | `explorer_node` calls `_proposals_from_mutators` → iterates `deps.mutators` (`ParamDeltaMutator`, `CompositionMutator`). It never builds a `ResearchAgentMutator` and never reads `role_configs["explorer"]`. |
| The explorer's `temperature: 0.9` (in `atforge.yaml` and `role_config.py` defaults) is applied | implied by `atforge.yaml` | Never consumed. Only `exploiter_node` and `critic_node` read their `AgentRoleConfig`. The explorer's mutators use their own constructor defaults (0.8 / 0.7). |
| "Tool calling supported for providers with `supports_tools=True` (currently Gemini only)" | `llm/CLAUDE.md` | All five cloud providers support tools (`OpenAICompatProvider.supports_tools = True`, inherited by Groq/OpenRouter/Cerebras/NVIDIA; `GeminiProvider` sets it too). Only `ollama` is `False`. |
| Groq default model `llama-3.3-70b-versatile` | `llm/CLAUDE.md` | `groq.py` sets `default_model = "llama-3.1-8b-instant"`. |
| Several `repo.py` read-function signatures (e.g. `get_mutation_tree(conn, run_id)`, `get_pattern_symbol_breakdown(conn, run_id, limit)`) | `storage/CLAUDE.md` | Actual: `get_mutation_tree(conn, root_strategy_id, max_depth=5)`, `get_pattern_symbol_breakdown(conn, strategy_id)`, `get_strategy_children(conn, parent_strategy_id, *, accepted_only=True)`. See [05](05_DATA_MODEL.md#repository-functions-repopy). |
| The ratchet gates which children advance each generation | implied across docs | It does not — see [the ratchet is advisory](#the-ratchet-is-advisory-not-gating). The critic veto is the real per-generation gate. |

None of these change what the system *does* — they change what the old docs *say* it does. This doc set follows the code.
