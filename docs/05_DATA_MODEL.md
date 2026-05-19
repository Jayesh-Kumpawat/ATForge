# 05 — Data Model Reference

Pure reference. Look things up here; do not read straight through. Every structure below is transcribed from the code as of 2026-05-18.

Sections: [PipelineState](#pipelinestate) · [SignalRef](#signalref) · [PipelineDeps](#pipelinedeps) · [AgentRoleConfig](#agentroleconfig) · [Evolution types](#evolution-types) · [LLM types](#llm-types) · [SQLite schema](#sqlite-schema) · [repo.py functions](#repository-functions-repopy) · [Settings](#settings-configpy) · [Events](#events-grapheventspy)

---

## PipelineState

`graph/state.py`. A `TypedDict(total=False)` — the object LangGraph threads through every node.

| Field | Type | Merge mode | Producer(s) | Notes |
|---|---|---|---|---|
| `run_id` | `str` | last-writer | `cli.invoke` | 12-char hex (`uuid4().hex[:12]`) |
| `universe` | `list[str]` | last-writer | `load_universe` | the symbols |
| `start_iso` / `end_iso` | `str` | last-writer | `cli.invoke` | ISO dates of the data window |
| `generation` | `int` | last-writer | `advance_generation` | absent → read as `0` |
| `max_generations` | `int` | last-writer | `cli.invoke` | loop bound; `1` = no loop |
| `data_refs` | `dict[str, str]` | last-writer | `fetch_data` | `{symbol: ohlcv_parquet_path}` |
| `detector_configs` | `list[dict]` | last-writer | `load_universe` (gen 0), `advance_generation` (gen ≥ 1) | **not** a reducer — replaced each pass |
| `signal_refs` | `list[SignalRef]` | **reducer** (`operator.add`) | `detect_patterns` | one per (symbol × detector) |
| `backtest_ids` | `list[int]` | **reducer** | `run_backtest_one` | parallel workers each append one |
| `failures` | `list[dict]` | **reducer** | every worker node | accumulates across all generations |
| `mutations` | `list[dict]` | **reducer** | `aggregate_node` | accepted child records; read by `ratchet` + `advance_generation` |
| `proposed_mutations` | `list[dict]` | **reducer** | `explorer_node`, `exploiter_node` | carries a `generation` field for loop filtering |
| `vetoed_mutations` | `list[dict]` | **reducer** | `critic_node` | carries `generation` + `fingerprint` |

**Reducer rule:** for a reducer field a node returns *only its new items*; LangGraph concatenates. For last-writer fields a node returns the full replacement value.

`mutations` record shape (written by `aggregate_node`): `{generation, parent_strategy_id, child_strategy_id, mutator, mutation_json, reasoning}`.
`proposed_mutations` record shape: `{generation, parent_strategy_id, child_config, reasoning, role, fingerprint}`.
`vetoed_mutations` record shape: `{generation, parent_strategy_id, child_config, fingerprint, veto_reason, role}`.

---

## SignalRef

`graph/state.py`. A `TypedDict` — the unit of work passed from `detect_patterns` to a backtest worker.

| Field | Type | Notes |
|---|---|---|
| `symbol` | `str` | |
| `strategy_name` | `str` | the detector's `.name` |
| `strategy_id` | `int` | `strategies` row id |
| `signal_id` | `int` | `pattern_signals` row id |
| `signal_parquet` | `str` | path to the boolean signal Series |
| `ohlcv_parquet` | `str` | path to the symbol's OHLCV |
| `generation` | `int` | which generation produced it |
| `parent_strategy_id` | `int \| None` | set for mutated children |

---

## PipelineDeps

`graph/deps.py`. A frozen dataclass — the dependency bundle every node closure captures.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `data_provider` | `DataProvider` | — | the cached fallback chain |
| `detectors` | `tuple[PatternDetector, ...]` | — | the 13 generation-0 detectors; read **only** by `load_universe` |
| `ohlcv_cache_dir` | `Path` | — | where `fetch_data` writes OHLCV parquet |
| `signal_cache_dir` | `Path` | — | where `detect_patterns` writes signal parquet |
| `db_path` | `Path` | — | the SQLite file |
| `hold_bars` | `int` | `10` | backtest holding period |
| `init_cash` | `Decimal` | `100000` | backtest starting capital |
| `fees` | `float` | `0.0003` | per-leg fee |
| `slippage` | `float` | `0.0005` | per-leg slippage |
| `mutators` | `tuple[Mutator, ...]` | `()` | the mutators the explorer runs |
| `ratchet_thresholds` | `RatchetThresholds` | defaults | the 5 ratchet gates |
| `top_n_parents` | `int` | `5` | how many top strategies to mutate |
| `tracing_enabled` | `bool` | `False` | Langfuse on/off |
| `event_bus` | `Any \| None` | `None` | the live-monitor `EventBus` |
| `role_configs` | `dict[str, AgentRoleConfig]` | `{}` | per-role agent config |
| `llm_router` | `Callable \| None` | `None` | the single LLM door; `None` → no evolution |

`ensure_dirs()` creates the two cache dirs and the DB parent.

---

## AgentRoleConfig

`graph/deps.py`. Frozen dataclass, one per agent role.

| Field | Type | Default | Notes |
|---|---|---|---|
| `role` | `str` | — | `"explorer"` / `"exploiter"` / `"critic"` |
| `temperature` | `float` | — | 0.9 / 0.4 / 0.3 by role |
| `max_iterations` | `int` | — | ReAct loop bound (4 / 4 / 3) |
| `system_prompt` | `str` | — | role prompt; YAML can override |
| `llm_priority` | `tuple[str, ...]` | `()` | `()` → use global priority |
| `model` | `str \| None` | `None` | `None` → router default |

Loaded by `graph/role_config.py:load_role_configs()` from `atforge.yaml`. Consumed only by `exploiter_node` and `critic_node` ([see 04](04_DESIGN_DECISIONS.md#appendix-doc-vs-code-drift-found-2026-05-18)).

---

## Evolution types

`evolution/types.py`.

### DetectorConfig
`TypedDict(total=False)` — the JSON-safe serialization of any detector. `type` is required; other keys depend on it.

```python
{"type": "sma_crossover", "fast": int, "slow": int}
{"type": "rsi_oversold",  "period": int, "oversold": int}
{"type": "talib_cdl",     "cdl_name": str, "direction": str}
{"type": "and"|"or",      "left": DetectorConfig, "right": DetectorConfig}   # recursive
```

### StrategyRow
`TypedDict` — one aggregated strategy passed to a mutator. Fields: `strategy_id:int`, `name:str`, `family:str`, `params_json:str` (raw JSON from DB), `mean_sharpe:float`, `mean_sortino:float`, `total_n_trades:int`, `max_drawdown:str` (`str(Decimal)`), `generation:int`.

### ProposedMutation
Frozen dataclass — a mutator's output. Fields: `parent_strategy_id:int`, `child_config:DetectorConfig`, `reasoning:str`, `mutator:str`.

### EvaluationResult
Frozen dataclass — a strategy's aggregated performance, the ratchet's input. Fields: `strategy_id:int`, `run_id:str`, `generation:int`, `mean_sharpe:float`, `mean_sortino:float`, `total_n_trades:int`, `max_drawdown:Decimal`, `n_symbols:int`, `per_symbol_sharpe:dict[str,float]`. Built by `ratchet.py:build_evaluation_result`; `None` if the strategy has no successful backtests.

### RatchetThresholds
Frozen dataclass — the 5 gates. `min_delta_sharpe=0.05`, `min_delta_sortino=0.02`, `max_drawdown_tol=0.10`, `min_n_trades=5`, `max_symbol_regression=0.5`. All overridable via `settings` / env.

### RatchetVerdict
Frozen dataclass — `judge_mutation`'s output. Fields: `accepted:bool`, `delta_sharpe:float`, `delta_sortino:float`, `dd_ratio:float`, `composite_score:dict[str,float]`, `reasoning:str` (`"accepted"` or a `;`-joined list of failed gates).

`composite_score` keys: `delta_sharpe`, `delta_sortino`, `dd_ratio`, `child_n_trades`, `sharpe_ok`, `sortino_ok`, `dd_ok`, `trades_ok`, `symbol_ok`, `worst_symbol_regression` — all `float` (booleans stored as `0.0`/`1.0`).

### The 5 ratchet gates (`judge_mutation`)
A child is `accepted` only if **all** pass:
1. `delta_sharpe ≥ min_delta_sharpe` (child − parent mean Sharpe).
2. `delta_sortino ≥ min_delta_sortino`.
3. `dd_ratio ≤ 1 + max_drawdown_tol`. `dd_ratio = child_dd / parent_dd`; if `parent_dd == 0`: `1.0` when `child_dd == 0` else `inf`.
4. `child.total_n_trades ≥ min_n_trades`.
5. Per-symbol guard: for every symbol in *both* `per_symbol_sharpe` maps, the child's Sharpe must not regress by more than `max_symbol_regression`. **Skipped entirely if either map is empty.**

### Mutator (Protocol)
`@runtime_checkable` — `name: str` and `propose(parents: list[StrategyRow], k: int) -> list[ProposedMutation]`. Satisfied structurally by all three mutators.

### MutationRecord
Frozen dataclass — `run_id`, `generation`, `parent_strategy_id`, `child_strategy_id`, `mutator`, `mutation_json`, `verdict:RatchetVerdict`. A typed mirror of an `experiments` row; defined but not central to the live flow (the nodes pass plain dicts).

### Pydantic response schemas (`evolution/prompts.py`)
LLM outputs are validated against these:
- `SmaParamsDelta` — `fast:int(2-50)`, `slow:int(10-200)`, `reasoning:str(≤256)`; validator enforces `fast < slow`.
- `RsiParamsDelta` — `period:int(2-50)`, `oversold:int(10-45)`, `reasoning:str(≤256)`.
- `CompositionChoice` — `op:Literal["AND","OR"]`, `reasoning:str(≤256)`.
- `ResearchProposal` — `proposal_type:Literal["sma_param_delta","rsi_param_delta"]`, optional `sma`/`rsi` blocks, `research_summary:str(≤512)`, `confidence:float(0-1)`; validator requires the matching block be present.
- `CriticVerdict` — `verdict:Literal["accept","veto"]`, `reason:str(≤256)`.

---

## LLM types

`llm/types.py`. All frozen, `slots=True`.

- **`ToolSpec`** — `name`, `description`, `parameters_schema:dict` (JSON Schema).
- **`ToolCall`** — `id`, `name`, `arguments:dict`.
- **`Message`** — `role:Literal["user","assistant","tool"]`, `content:str|None`, `tool_calls:tuple[ToolCall,...]|None`, `tool_call_id:str|None`.
- **`LlmRequest`** — `prompt:str`, `model:str|None`, `system:str|None`, `temperature:float=0.7`, `max_tokens:int=1024`, `trace_name:str|None`, `metadata:dict|None`, `response_schema:type|None`, `tools:tuple[ToolSpec,...]|None`, `messages:tuple[Message,...]|None`.
- **`LlmResponse`** — `text:str`, `model:str`, `provider:str`, `input_tokens:int`, `output_tokens:int`, `latency_ms:int`, `trace_id:str|None`, `tool_calls:tuple[ToolCall,...]|None`, `stop_reason:str|None` (`"end_turn"`/`"tool_use"`/`"max_tokens"`).
- **`LlmProvider`** (Protocol) — `name`, `default_model`, `supports_tools:bool`, `complete(request)→LlmResponse`, `supports(model)→bool`.
- **Error hierarchy** — `LlmError` ⊃ `RateLimitError`, `AuthError`, `TransientError`, `FatalError`, `LlmExhausted`. Routing behavior: [03](03_AGENTS_AND_TOOLS.md#error-classification-llmtypespy).

---

## SQLite schema

`storage/schema.sql`. WAL + JSON1 + FTS5. `PRAGMA user_version = 2`. Five tables + one FTS5 virtual table.

### `runs` — one row per `graph.invoke()`
`run_id` TEXT PK · `started_at` TEXT · `finished_at` TEXT · `universe_hash` TEXT · `status` TEXT `CHECK IN ('running','success','partial','failed')` · `notes` TEXT.

### `strategies` — deduped strategy registry
`strategy_id` INTEGER PK · `name` TEXT · `family` TEXT (`candlestick`/`indicator`/`structural`/`composite`) · `params_json` TEXT · `description` TEXT · `created_at` TEXT · **`UNIQUE(name, params_json)`**.

### `pattern_signals` — one row per (run × strategy × symbol × generation)
`signal_id` INTEGER PK · `run_id` FK→runs (ON DELETE CASCADE) · `strategy_id` FK→strategies · `symbol` TEXT · `n_signals` INTEGER · `first_date` TEXT · `last_date` TEXT · `generation` INTEGER DEFAULT 0 · `created_at` TEXT. Indexed on `run_id`, `symbol`.

### `backtest_runs` — one row per backtest
`backtest_id` INTEGER PK · `run_id` FK→runs · `signal_id` FK→pattern_signals · `strategy_id` FK→strategies · `symbol` TEXT · `success` INTEGER `CHECK IN (0,1)` · `reason` TEXT · `n_trades` INTEGER · **money as TEXT:** `total_return`, `final_value`, `max_drawdown`, `init_cash` · **ratios as REAL:** `sharpe`, `sortino`, `cagr`, `win_rate` · config snapshot: `hold_bars` INT, `fees` REAL, `slippage` REAL · `generation` INTEGER DEFAULT 0 · `created_at` TEXT. Indexed on `run_id`, `symbol`, `strategy_id`, `sharpe DESC WHERE success=1`, `(strategy_id, generation)`.

### `experiments` — the ratchet + mutation verdict log
`experiment_id` INTEGER PK · `run_id` TEXT · `generation` INTEGER DEFAULT 0 · `parent_strategy_id` FK→strategies · `child_strategy_id` FK→strategies (**nullable** — `NULL` for `critic_veto` rows) · `mutator` TEXT (`param_delta`/`composition`/`explorer`/`exploiter`/`critic_veto`) · `mutation_json` TEXT · `accepted` INTEGER `CHECK IN (0,1)` · `delta_sharpe` REAL · `composite_score` TEXT (JSON) · `reasoning` TEXT · `created_at` TEXT. Indexed on `(run_id, generation)`.

> **Legacy columns.** `experiments` also has `parent_id` (self-referential FK) and a bare `strategy_id` from the Phase-1 schema. The Phase-2a code does not use them — it writes the `run_id`/`generation`/`parent_strategy_id`/`child_strategy_id`/`composite_score`/`mutator` columns added by migration `0002_phase2a.sql`. Treat `parent_id` and `strategy_id` as dead columns.

### `strategy_search` — FTS5 virtual table
`fts5(name, description, reasoning, content='')` — full-text search over strategy text.

### Migrations
`storage/migrate.py` applies `migrations/NNNN_*.sql` files gated by `PRAGMA user_version`. A fresh DB is created directly at version 2 from `schema.sql`; a Phase-1 DB (version ≤ 1) is upgraded by `0002_phase2a.sql` (adds `generation` to `pattern_signals`/`backtest_runs` and the genealogy columns to `experiments`).

### ER summary
`runs 1─∞ pattern_signals`, `runs 1─∞ backtest_runs`, `runs 1─∞ experiments`. `strategies 1─∞ pattern_signals / backtest_runs`, and `1─∞ experiments` twice (as `parent_strategy_id` and `child_strategy_id`). `pattern_signals 1─∞ backtest_runs` via `signal_id`.

---

## Repository functions (`repo.py`)

**Writes:** `insert_run(conn, run_id, universe_hash=None)` · `finish_run(conn, run_id, status, notes=None)` · `upsert_strategy(conn, name, family, params, description=None) → int` · `insert_pattern_signal(conn, *, run_id, strategy_id, symbol, n_signals, first_date, last_date, generation=0) → int` · `insert_backtest_result(conn, *, run_id, signal_id, strategy_id, result, hold_bars, fees, slippage, init_cash, generation=0) → int` · `insert_experiment(conn, *, run_id, generation, parent_strategy_id, child_strategy_id, mutator, mutation_json, accepted, delta_sharpe, composite_score_json, reasoning) → int`.

**Reads:** `top_rankings(conn, *, limit=20, run_id=None)` (deduped — one row per `(symbol, strategy_id)`, highest Sharpe, via a `ROW_NUMBER()` window) · `get_strategy(conn, strategy_id)` · `get_top_strategies_for_generation(conn, *, run_id, generation, limit=10)` (the mutator parent set — `AVG` metrics grouped by strategy) · `get_experiments_for_run(conn, run_id)` · `get_best_sharpe_per_generation(conn, run_id)` · `get_strategy_children(conn, parent_strategy_id, *, accepted_only=True)` · `get_pattern_symbol_breakdown(conn, strategy_id)` · `get_mutation_tree(conn, root_strategy_id, max_depth=5)` (recursive CTE) · `get_agent_activity_summary(conn, run_id)` · `get_recent_critic_verdicts(conn, run_id, limit=20)`.

> These signatures are the code as of 2026-05-18 and supersede the table in `storage/CLAUDE.md`, which is stale on several (see [04 appendix](04_DESIGN_DECISIONS.md#appendix-doc-vs-code-drift-found-2026-05-18)).

**Connection pattern** (`storage/db.py`): `with connect(db_path) as conn:` (autocommit-off, `row_factory=sqlite3.Row`); wrap writes in `with txn(conn):` (`BEGIN`/`COMMIT`/`ROLLBACK`). Reads need no `txn`.

---

## Settings (`config.py`)

`Settings(BaseSettings)` — pydantic-settings, reads `.env` at the repo root. The `settings` singleton is created at import.

Paths: `db_path` (`ATFORGE_DB_PATH`, default `data/atforge.db`), `cache_dir` (`ATFORGE_CACHE_DIR`, default `data/cache`).
Langfuse: `langfuse_public_key`, `langfuse_secret_key`, `langfuse_host`.
LLM keys: `google_api_key`, `groq_api_key`, `openrouter_api_key`, `cerebras_api_key`, `nvidia_api_key`, `ollama_base_url`, `enable_ollama` (default `False`), `llm_default_model` (`gemini-2.5-flash`), `llm_provider_priority` (`["gemini","groq","openrouter","cerebras","nvidia"]`).
Qdrant (Phase 2b, unused today): `qdrant_url`, `qdrant_api_key`.
Ratchet: `ratchet_min_delta_sharpe` 0.05 · `ratchet_min_delta_sortino` 0.02 · `ratchet_max_drawdown_tol` 0.10 · `ratchet_min_n_trades` 5 · `ratchet_max_symbol_regression` 0.5 — each overridable via env (e.g. `RATCHET_MIN_DELTA_SHARPE=0.1`).

---

## Events (`graph/events.py`)

`EventBus` — a thread-safe `Queue` wrapper: `emit(event)`, `drain(timeout)`, `close()`. Drained by `monitor.py:PipelineMonitor`. The 11 frozen event dataclasses:

| Event | Emitted by | Key fields |
|---|---|---|
| `EvtPipelineStart` | `cli.py` | `run_id`, `n_symbols`, `max_generations` |
| `EvtPipelineDone` | `cli.py` | `run_id`, `n_backtests`, `n_failures` |
| `EvtNodeStart` / `EvtNodeDone` | ratchet, A2 nodes | `node_name`, `generation` (+ `elapsed_ms`) |
| `EvtBacktestDone` | `run_backtest_one` | `symbol`, `strategy`, `success`, `sharpe` |
| `EvtMutationProposed` | `_proposals_from_mutator(s)` | `mutator`, `n_proposals` |
| `EvtRatchetVerdict` | `ratchet` | `parent_name`, `child_name`, `accepted`, `delta_sharpe`, `reason` |
| `EvtGenerationDone` | `ratchet` | `generation`, `n_backtests`, `n_accepted` |
| `EvtAgentToolCall` | `run_react_loop` | `role`, `tool_name`, `iteration`, `args_summary` |
| `EvtAgentReasoning` | `run_react_loop` | `role`, `iteration`, `text` |
| `EvtCriticVerdict` | `critic_node` | `parent_strategy_id`, `fingerprint`, `verdict`, `reason` |

All optional — nodes guard every emit with `if deps.event_bus:`. The bus changes nothing about pipeline behavior; it only feeds the live display.
