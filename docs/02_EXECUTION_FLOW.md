# 02 — Execution Flow

The complete trace of a pipeline run, from the process entry point to the last node. Follow it top to bottom. Every step names the file, function, and what it reads from / writes to `PipelineState` and SQLite.

Companion references: state shape and schema in [05_DATA_MODEL.md](05_DATA_MODEL.md); the agent internals in [03_AGENTS_AND_TOOLS.md](03_AGENTS_AND_TOOLS.md); the *why* in [04_DESIGN_DECISIONS.md](04_DESIGN_DECISIONS.md).

---

## Part 1 — Process entry

### `main.py` (repo root)

```python
from atforge.cli import app
if __name__ == "__main__":
    app()
```

Four lines. It exists only so `uv run python main.py ...` works. All real CLI logic is `src/atforge/cli.py`.

### `cli.py` — the Typer app

`cli.py:34` creates `app = typer.Typer(...)`. Four commands are registered with `@app.command()`:

| Command | Function | Purpose |
|---|---|---|
| `pipeline` | `cli.py:pipeline` (line 62) | Run the full pipeline — the only command that evolves strategies |
| `experiments` | `cli.py:experiments` (line 180) | Print the ratchet verdict log for a run |
| `rank` | `cli.py:rank` (line 222) | Print the top-N backtest leaderboard |
| `inspect` | `cli.py:inspect` (line 232) | Print run metadata + backtest success count |

`experiments`, `rank`, `inspect` are read-only SQL reports — covered briefly in [Part 9](#part-9--the-other-three-cli-commands). The rest of this document traces `pipeline`.

---

## Part 2 — Pipeline startup (`cli.py:pipeline`)

`pipeline()` runs *before* the graph and builds everything the graph needs. Step by step:

### 2.1 — Resolve the date window
`cli.py:91` — `end = date.today()`; `start = _apply_lookback(end, lookback)`.
`_apply_lookback` (`cli.py:331`) parses `"10y"`, `"6m"`, `"30d"` into a `date`. It raises `typer.BadParameter` if the suffix is not `y`/`m`/`d`.

### 2.2 — Resolve the symbol universe
`cli.py:94` — if `--symbols RELIANCE,TCS` was given, split and upper-case it. Else if `--universe nifty50`, call `load_nifty50()` (`data/universe.py`) which reads `data/nifty50.json` and asserts exactly 50 symbols. Otherwise raise.

### 2.3 — Filesystem + observability + DB
- `settings.ensure_dirs()` (`config.py:46`) — creates the DB parent dir and the cache dir.
- `_configure_langfuse_env()` (`cli.py:315`) — copies Langfuse keys from `settings` into `os.environ`. Required because the Langfuse SDK reads `os.environ` directly, but pydantic-settings only populates the `settings` object.
- `init_db(settings.db_path)` (`storage/db.py:20`) — creates the schema on a fresh DB, then applies pending migrations. Idempotent; safe every startup.

### 2.4 — Build the LLM stack (`cli.py:_build_mutators`, line 271)
This is where the LLM machinery is assembled:
1. `eff_settings = settings.model_copy(update={"enable_ollama": ...})` — apply the `--enable-ollama` flag.
2. `registry = build_default_registry(eff_settings)` — registers one provider per configured API key (see [03](03_AGENTS_AND_TOOLS.md#the-provider-registry)).
3. `priority = llm_priority + (["ollama"] if enable_ollama else [])` — the fallback order, from `--llm-priority`.
4. `chain = registry.chain(priority)` — resolve names to provider objects. **If empty, mutators are skipped** and `llm_router` is `None` — the run becomes a pure backtest with no evolution.
5. Define the `llm_router` closure: `llm_router(req) → complete_with_fallback(req, registry=registry, priority=priority, tracing_enabled=...)`. This single callable is the only LLM door for the whole run.
6. Build the mutator list from `--mutators`: `param_delta → ParamDeltaMutator`, `composition → CompositionMutator`, `research → ResearchAgentMutator`. Unknown names warn and skip.
7. Return `(mutators, llm_router)`.

### 2.5 — Load agent role configs
`cli.py:116` — `role_configs = load_role_configs()` (`graph/role_config.py:65`). Auto-discovers `atforge.yaml` in the working directory; if absent, returns hardcoded defaults. Produces three `AgentRoleConfig` objects (`explorer`, `exploiter`, `critic`) — temperature, max iterations, system prompt, LLM priority, model.

### 2.6 — Assemble `PipelineDeps`
`cli.py:118` — one frozen dataclass carrying everything the nodes need:
`data_provider` (the cached fallback chain from `_build_default_provider`, line 38), `detectors` (the 13 generation-0 detectors from `_default_detectors`, line 52), cache dirs, `db_path`, backtest params (`init_cash`, `hold_bars`, `fees`, `slippage`), `mutators`, `ratchet_thresholds` (built field-by-field from `settings`), `tracing_enabled`, `event_bus`, `llm_router`, `role_configs`. Full field list: [05_DATA_MODEL.md](05_DATA_MODEL.md#pipelinedeps).

### 2.7 — Compile the graph and mint the run
- `cli.py:139` — `graph = build_pipeline(deps)` (see Part 3).
- `cli.py:140` — `run_id = uuid4().hex[:12]`.
- `cli.py:142` — if `--live`, an `EventBus` and `PipelineMonitor` background thread are started; otherwise a one-line status is printed.
- `effective_max_gen = 1 if dry_run else max_generations` — `--dry-run` forces a single generation.

### 2.8 — Invoke
`cli.py:155` — the run begins:
```python
result = graph.invoke({
    "run_id": run_id,
    "universe": syms,
    "start_iso": start.isoformat(),
    "end_iso": end.isoformat(),
    "max_generations": effective_max_gen,
})
```
Five keys go in. `generation` is absent, so every node reads it as `state.get("generation", 0)` — generation 0.

### 2.9 — Teardown
After `invoke` returns, `cli.py:165` counts `backtest_ids` and `failures` from the final state, emits `EvtPipelineDone`, stops the monitor, and calls `_print_rankings` (`cli.py:246`) — a Rich table from `top_rankings()`.

---

## Part 3 — Graph compilation (`graph/pipeline.py:build_pipeline`)

`build_pipeline(deps)` is small and worth reading in full once. It:

1. Calls `deps.ensure_dirs()`.
2. Creates `g = StateGraph(PipelineState)` — the state schema drives reducer behavior (Part 5).
3. Registers 11 nodes with `g.add_node(name, factory(deps))`. Every node is a **closure** produced by a `make_*` factory — the factory captures `deps`, the returned function takes `PipelineState`. See [04 — node factory pattern](04_DESIGN_DECISIONS.md#node-factory-functions-not-classes).
4. Wires edges:
   - Plain edges: `START→load_universe→fetch_data→detect_patterns`, `run_backtest_one→ratchet→rank→explorer_node→exploiter_node→critic_node→aggregate_node`, `advance_generation→detect_patterns`.
   - Conditional edge after `detect_patterns`: `make_run_backtest_dispatcher()` (the fan-out).
   - Conditional edge after `aggregate_node`: `make_loop_decision()` mapping `{"continue": "advance_generation", "stop": END}`.
5. Returns `g.compile()` — a runnable graph.

The 11 registered nodes: `load_universe`, `fetch_data`, `detect_patterns`, `run_backtest_one`, `ratchet`, `rank`, `explorer_node`, `exploiter_node`, `critic_node`, `aggregate_node`, `advance_generation`.

> **Dead code:** `nodes.py:make_run_backtest` (a serial backtest node) and `nodes_phase2.py:make_mutate_strategies` (the pre-A2 single mutate node) still exist but are **never registered** in `build_pipeline`. They were superseded by `run_backtest_one` (Send worker) and the 4-node A2 layer. Ignore them when reasoning about a run.

---

## Part 4 — The node trace (generation 0)

Each node below: **reads** from `PipelineState`, **does** work, **writes** DB rows, **returns** a partial-state dict that LangGraph merges in.

### 4.1 — `load_universe` (`nodes.py:make_load_universe`)
- **Reads:** `universe`, `run_id`, `detector_configs`.
- **Does:** opens a DB connection, `insert_run(conn, run_id)` — a `runs` row with `status='running'`.
- **Seeds detectors:** if `detector_configs` is not already set, serializes `deps.detectors` (the 13 default detectors) via `registry._detector_to_config` and puts the list in state. This is the *only* place `deps.detectors` is read — every later generation gets `detector_configs` from `advance_generation` instead.
- **Returns:** `{"universe": ..., "detector_configs": [...]}`.
- **DB written:** 1 `runs` row.

### 4.2 — `fetch_data` (`nodes.py:make_fetch_data`)
- **Reads:** `start_iso`, `end_iso`, `universe`, `run_id`.
- **Does:** for each symbol, `deps.data_provider.fetch_ohlcv(symbol, start, end)` → a pandas DataFrame → written to a parquet file `ohlcv_cache_dir/{symbol}_{run_id}.parquet`. The path (not the data) goes into `data_refs`.
- **Error handling:** any exception per symbol is caught, logged (`structlog`), appended to `failures` — the run continues.
- **Returns:** `{"data_refs": {symbol: path}, "failures": [...]}`.
- **DB written:** none. **Files written:** N parquet files.

`deps.data_provider` is `CachedProvider(FallbackDataProvider([openchart, jugaad, yfinance]))` — see [Part 7](#part-7--the-data-provider-chain).

### 4.3 — `detect_patterns` (`nodes.py:make_detect_patterns`)
The fan-out producer. The most write-heavy node.
- **Reads:** `generation`, `detector_configs`, `data_refs`, `run_id`.
- **Does:** for every `(symbol, detector_config)` pair:
  1. `pd.read_parquet(ohlcv_path)` — load the symbol's OHLCV.
  2. `build_detector_from_config(cfg)` (`evolution/registry.py`) — turn the config dict into a live `PatternDetector`.
  3. `detector.detect(df)` → a `PatternSignal` (a boolean Series).
  4. `upsert_strategy(conn, name=det.name, family=det.family, params=cfg)` — register the strategy (idempotent — dedup on `(name, params_json)`), get a `strategy_id`.
  5. `insert_pattern_signal(conn, ..., generation=generation)` — record signal count + first/last date, get a `signal_id`.
  6. Write the signal Series to a parquet file `signal_cache_dir/{symbol}_{name}_g{gen}_{run_id}.parquet`.
  7. Append a `SignalRef` TypedDict (symbol, names, ids, both parquet paths, generation) to the result list.
- **Error handling:** per-pair `try/except` → `failures`.
- **Returns:** `{"signal_refs": [...], "failures": [...]}` — `signal_refs` is a **reducer** field.
- **DB written:** up to `symbols × detectors` rows in `strategies` (deduped) and the same count in `pattern_signals`.

### 4.4 — `run_backtest_dispatcher` (the conditional edge, `nodes_phase2.py:make_run_backtest_dispatcher`)
Not a node — the conditional-edge function attached after `detect_patterns`. It is the fan-out:
```python
def dispatcher(state):
    return [Send("run_backtest_one", {"ref": ref, "run_id": run_id})
            for ref in state.get("signal_refs", [])]
```
It returns a **list of `Send` objects**. LangGraph schedules one `run_backtest_one` invocation per `Send`, and they run in parallel. Each `Send` payload is `{"ref": SignalRef, "run_id": str}` — *not* the full `PipelineState`.

### 4.5 — `run_backtest_one` (`nodes_phase2.py:make_run_backtest_one`) — the Send worker
Runs once per pattern signal, in parallel.
- **Reads:** its `Send` payload — `state["ref"]` and `state["run_id"]`. (It receives a plain dict, not `PipelineState`.)
- **Does:** inside a `trace_node("run_backtest_one", ...)` Langfuse span:
  1. `pd.read_parquet` the OHLCV and signal parquets named in the ref.
  2. `run_backtest(ohlcv, sig, ...)` (`backtest/engine.py`) — the vectorbt backtest (see [Part 6](#part-6--inside-a-backtest)).
  3. `insert_backtest_result(conn, ..., result=result, generation=ref["generation"])` — one `backtest_runs` row.
  4. Emit `EvtBacktestDone` to the event bus.
- **Error handling:** read failure → log + `failures` + early return; `run_backtest` itself never raises (returns `success=False`).
- **Returns:** `{"backtest_ids": [new_id], "failures": [...]}` — both **reducer** fields, so parallel workers append without clobbering each other.
- **DB written:** 1 `backtest_runs` row.

### 4.6 — `ratchet` (`nodes_phase2.py:make_ratchet_node`)
- **Reads:** `generation`, `run_id`, `mutations`.
- **Generation 0:** `generation == 0` → returns `{}` immediately. **No-op.** There is no parent generation to compare against.
- **Generation N ≥ 1:** see [Part 8](#part-8--the-evolution-loop-generations-1) for the real behavior.
- **Returns:** `{}` always (it only writes the DB, never state).

### 4.7 — `rank` (`nodes.py:make_rank`)
- **Reads:** `run_id`, `failures`.
- **Does:** `top_rankings(conn, limit=20, run_id=run_id)` — the deduped leaderboard. Then `finish_run(conn, run_id, status=...)` — `status='success'` if any rows ranked, else `'partial'`.
- **Returns:** `{}`.
- **DB written:** updates the `runs` row (`finished_at`, `status`, `notes`).

> Note: `rank` calls `finish_run` *every* generation, so on a multi-generation run the `runs` row is "finished" repeatedly — the last write wins. This is harmless but worth knowing.

### 4.8 — The four A2 agent nodes
`explorer_node → exploiter_node → critic_node → aggregate_node` run in sequence after `rank`. Their full behavior is in [03_AGENTS_AND_TOOLS.md](03_AGENTS_AND_TOOLS.md). Summary of what they do to state:

| Node | Skips when | Reads | Writes to state | Writes to DB |
|---|---|---|---|---|
| `explorer_node` | `generation+1 >= max_generations` | top strategies of current gen | `proposed_mutations` (+) | — |
| `exploiter_node` | same, **or** `llm_router is None` | top strategies of current gen | `proposed_mutations` (+) | — |
| `critic_node` | no proposals, **or** `llm_router is None` | `proposed_mutations` | `vetoed_mutations` (+) | `experiments` rows for vetoes |
| `aggregate_node` | (never skips; may produce 0) | `proposed_mutations`, `vetoed_mutations` | `mutations` (+) | `strategies` rows for survivors |

With `max_generations=1` (default), explorer and exploiter short-circuit on the very first check (`0 + 1 >= 1`), critic sees no proposals, aggregate produces nothing. The run ends as a pure backtest.

### 4.9 — `loop_decision` (the conditional edge, `nodes_phase2.py:make_loop_decision`)
After `aggregate_node`:
```python
return "continue" if generation + 1 < max_generations else "stop"
```
`"stop"` → `END`. `"continue"` → `advance_generation`.

---

## Part 5 — How state merges: reducers and the fan-out

`PipelineState` (`graph/state.py`) is a `TypedDict`. Each node returns a *partial* dict; LangGraph merges it. Two merge modes:

- **Last-writer-wins** (no annotation): `run_id`, `universe`, `generation`, `data_refs`, `detector_configs`, ... A node's value replaces the old one.
- **Reducer** (`Annotated[list[...], operator.add]`): `signal_refs`, `backtest_ids`, `failures`, `mutations`, `proposed_mutations`, `vetoed_mutations`. A node returns only its **delta** (new items); LangGraph concatenates.

Why this matters for the fan-out: `run_backtest_dispatcher` launches N parallel `run_backtest_one` workers. Each returns `{"backtest_ids": [its_one_id]}`. Because `backtest_ids` is a reducer, the N partial returns concatenate deterministically into one list — no worker overwrites another. Without the reducer, the last worker to finish would clobber all the others.

`detector_configs` is deliberately **not** a reducer: it has a single producer per pass (`load_universe` at gen 0, `advance_generation` at gen ≥ 1) and must be *replaced*, not appended, each generation. Full field-by-field table: [05_DATA_MODEL.md](05_DATA_MODEL.md#pipelinestate).

---

## Part 6 — Inside a backtest (`backtest/engine.py:run_backtest`)

`run_backtest(ohlcv, signal, *, symbol, pattern_name, init_cash, hold_bars, fees, slippage)`:

1. Guard: empty OHLCV, or signal/OHLCV length mismatch → `BacktestResult(success=False, reason=...)`.
2. `_bool_to_entry_exit(signal, hold_bars)` — **the no-lookahead shift.** `entries = signal.shift(1)` (a pattern firing on bar T enters at T+1's open); `exits = entries.shift(hold_bars)` (exit `hold_bars` later). vectorbt has no built-in lookahead guard, so this shift is mandatory.
3. If no entries survive the shift → `success=False, reason="no entries after shift"`.
4. `vbt.Portfolio.from_signals(close, entries, exits, init_cash=float(...), fees, slippage, freq="1D")`. `freq="1D"` is mandatory for correct Sharpe/CAGR annualization.
5. `compute_metrics(portfolio)` (`backtest/metrics.py`) — extracts `sharpe`, `sortino`, `cagr`, `win_rate` (floats — analytical ratios) and `total_return`, `final_value`, `max_drawdown` (`Decimal` — money). `_safe_decimal` converts via `Decimal(str(x))` and maps `NaN`/`inf` → `Decimal(0)`.
6. Returns `BacktestResult(success=True, metrics=..., n_trades=...)`.

**`run_backtest` never raises** — any exception is caught and returned as `success=False`. This is a hard rule: worker nodes must not propagate exceptions (it would abort the whole fan-out).

---

## Part 7 — The data provider chain

`deps.data_provider` is built in `cli.py:_build_default_provider` as three nested layers:

```
CachedProvider( FallbackDataProvider([ OpenchartProvider, JugaadProvider, YFinanceProvider ]) )
```

- **`OpenchartProvider`** (`data/providers/openchart.py`) — NSE's charting backend. Primary.
- **`JugaadProvider`** (`data/providers/jugaad.py`) — NSE bhavcopy CSVs, history from 1995.
- **`YFinanceProvider`** (`data/providers/yfinance.py`) — Yahoo Finance, the only split-adjusted free source. Maps `RELIANCE → RELIANCE.NS`.
- **`FallbackDataProvider`** (`data/chain.py`) — tries each in order; first non-empty result wins; raises `DataUnavailableError` only if *all* fail.
- **`CachedProvider`** (`data/cache.py`) — parquet disk cache keyed on `{provider}/{symbol}/{interval}/{start}_{end}`. Exact-range match only.

Every provider calls `validate_ohlcv` (`data/protocol.py`) before returning — enforces the column contract, tz-naive `DatetimeIndex`, sorted, deduped. `DataProvider` is a structural `Protocol`; adding a provider needs no inheritance.

---

## Part 8 — The evolution loop (generations ≥ 1)

When `loop_decision` returns `"continue"`, control reaches `advance_generation`, then loops back to `detect_patterns`.

### 8.1 — `advance_generation` (`nodes_phase2.py:make_advance_generation`)
- **Reads:** `generation`, `run_id`, `mutations`.
- **Does:**
  1. `current_gen_mutations` = `mutations` rows whose `generation == generation`. If none → just `{"generation": generation + 1}`.
  2. Tries to find *accepted* children: queries `experiments WHERE child_strategy_id=? AND generation=generation+1 AND accepted=1`.
  3. `candidate_sids = accepted_sids or [all proposed child ids]` — **fallback to all proposed children if none were accepted.**
  4. Loads each candidate's `params_json` from `strategies`, JSON-decodes it into a `detector_config`.
  5. Returns `{"generation": generation + 1, "detector_configs": new_configs}`.

### 8.2 — The generation timeline (and a subtlety worth knowing)

Trace two generations with `max_generations=2`:

```
GEN 0:
  load_universe → fetch_data → detect_patterns (13 default detectors)
  → backtest → ratchet (NO-OP, gen 0) → rank
  → explorer/exploiter propose mutations → critic vetoes some
  → aggregate upserts survivors as child strategies, writes `mutations` (generation=0)
  → loop_decision: 0+1 < 2 → "continue"
  → advance_generation: generation→1, detector_configs ← child configs

GEN 1:
  detect_patterns (the CHILD detectors) → backtest the children
  → ratchet: generation=1, prev_gen=0 → finds `mutations` with generation==0,
     builds parent EvaluationResult (gen 0) + child EvaluationResult (gen 1),
     calls judge_mutation, writes an `experiments` row with generation=1
  → rank
  → explorer/exploiter SKIP (1+1 >= 2) → critic SKIP (no proposals)
  → aggregate produces nothing
  → loop_decision: 1+1 < 2 is false → "stop" → END
```

**The subtlety:** `advance_generation` runs at the *end* of generation 0 and looks for `experiments` rows at `generation = 0+1 = 1`. But the ratchet that *writes* those rows does not run until the *start* of generation 1 — after `advance_generation` has already finished. So `accepted_sids` is always empty at that moment, and `advance_generation` always takes the `or [all proposed children]` fallback.

Consequence as the code stands today: **the ratchet verdict is recorded for analysis (the `experiments` log, the dashboard) but does not gate which children advance to the next generation.** Every proposed-and-not-vetoed child advances. The gate that actually prunes proposals each generation is the **critic veto**, not the ratchet. This is a real architectural quirk — see [04 — the ratchet is advisory](04_DESIGN_DECISIONS.md#the-ratchet-is-advisory-not-gating).

### 8.3 — `ratchet` on generation N ≥ 1 (full behavior)
`nodes_phase2.py:make_ratchet_node`, for `generation = N ≥ 1`:
1. `prev_gen = N - 1`. `pending = mutations` rows with `generation == prev_gen`. If none → `{}`.
2. For each pending mutation:
   - `build_evaluation_result(conn, strategy_id=parent_id, run_id, generation=prev_gen)` — aggregates the parent's successful `backtest_runs` (mean Sharpe/Sortino, summed trades, max drawdown, per-symbol Sharpe map).
   - Same for the child at `generation=N`.
   - If either is `None` (no successful backtests) → skip.
   - `judge_mutation(parent_er, child_er, deps.ratchet_thresholds)` → a `RatchetVerdict` (pure function, 5 gates — see [03](03_AGENTS_AND_TOOLS.md#the-ratchet) and [05](05_DATA_MODEL.md#ratchetverdict)).
   - `insert_experiment(conn, ..., accepted=1|0, composite_score_json=..., reasoning=...)` — one `experiments` row, `generation=N`.
   - Emit `EvtRatchetVerdict`.
3. Emit `EvtGenerationDone`.

---

## Part 9 — The other three CLI commands

All three open a read-only connection and print a Rich table. No graph, no LLM.

- **`experiments --run <id>`** (`cli.py:180`) — `SELECT` from `experiments` JOINed to `strategies` twice (parent + child names). Shows generation, mutator, accepted, Δsharpe, reasoning.
- **`rank --top N --run <id>`** (`cli.py:222`) — calls `_print_rankings` → `top_rankings()`. The same leaderboard the pipeline prints at the end.
- **`inspect <run_id>`** (`cli.py:232`) — one `runs` row + a `COUNT(*)/SUM(success)` over `backtest_runs`.

---

## Part 10 — Cross-cutting: error handling

The pipeline is built to **degrade, not crash**:

| Failure | Handling |
|---|---|
| A data provider fails | `FallbackDataProvider` tries the next; only `DataUnavailableError` if *all* fail |
| `fetch_data` can't get a symbol | caught → `failures` list → run continues without that symbol |
| `detect_patterns` detector throws | caught per pair → `failures` → other detectors continue |
| `run_backtest` hits any error | returns `BacktestResult(success=False, reason=...)` — never raises |
| `run_backtest_one` can't read a parquet | caught → `failures` → returns early, fan-out unaffected |
| An LLM call fails | the router retries / falls through providers; exhaustion raises `LlmExhausted`, caught by the mutator → proposal dropped |
| A mutator throws | caught in `_proposals_from_mutator(s)` → that mutator yields no proposals |
| The critic LLM fails or returns garbage | parse returns `None` → **safe default: accept** (never block on an LLM error) |

The rule (stated in `CLAUDE.md`): **worker nodes never raise.** A failure becomes a `failures` entry or a `success=False` result, never an exception that aborts the run. The `failures` list is a reducer — it accumulates across every node and generation, and the final count is printed at teardown.

---

## Part 11 — Cross-cutting: observability

Two independent, optional channels, both off by default:

- **EventBus → PipelineMonitor** (`graph/events.py`, `monitor.py`): enabled by `--live`. Nodes emit lightweight event dataclasses (`EvtBacktestDone`, `EvtRatchetVerdict`, `EvtAgentToolCall`, ...) into a thread-safe `Queue`; a background `PipelineMonitor` thread drains it and renders a Rich live terminal display. Nodes guard every emit with `if deps.event_bus:`.
- **Langfuse tracing** (`llm/tracing.py`): enabled when `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` are set. `trace_completion` wraps every LLM call as a generation observation; `trace_node` wraps agent nodes as spans with role tags (`["explorer"]`, `["critic"]`, ...); `score_current_observation` attaches scores (e.g. the critic's `veto_rate`). All three are no-ops when `enabled=False` — tests never touch the Langfuse SDK.

Neither channel changes pipeline behavior — they only observe.
