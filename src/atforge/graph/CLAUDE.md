# LangGraph Pipeline — `src/atforge/graph/`

## What this module does

Orchestrates the full Phase 2a pipeline using LangGraph's `StateGraph`. Wires pure node functions into a directed graph with parallel fan-out, an evolution loop, and a conditional stopping criterion.

## Core design: IDs only in state

**Never put DataFrames, arrays, or Portfolio objects in `PipelineState`.**

State holds only:
- Primitive values (strings, ints, ISO dates)
- File paths to parquet files (not the data itself)
- Database row IDs (not the records themselves)

Why: LangGraph checkpoints state. Large objects = huge checkpoint overhead. Phase 3 adds `interrupt_before=["rank"]` for HITL — cheap checkpoints are a prerequisite.

## `PipelineState` (`state.py`)

```python
class PipelineState(TypedDict, total=False):
    run_id: str                                         # uuid4().hex[:12]
    universe: list[str]                                 # ["RELIANCE", "TCS", ...]
    start_iso: str                                      # "2015-01-01"
    end_iso: str                                        # "2025-01-01"
    generation: int                                     # current generation (0-based)
    max_generations: int                                # stop when generation >= this
    detector_configs: list[dict[str, Any]]              # LAST-WRITER-WINS (NOT reduced)
    data_refs: dict[str, str]                           # {symbol: path_to_parquet}
    signal_refs: Annotated[list[SignalRef], operator.add]   # reducer — delta-only
    backtest_ids: Annotated[list[int], operator.add]        # reducer — delta-only
    failures: Annotated[list[dict], operator.add]           # reducer — delta-only
    mutations: Annotated[list[dict], operator.add]          # reducer — delta-only
```

**Reducers vs last-writer-wins**: `signal_refs`, `backtest_ids`, `failures`, `mutations` use `operator.add` — each node returns only the NEW items it produced, not the full list. `detector_configs` is last-writer-wins — `advance_generation` overwrites it with accepted child configs each loop.

`SignalRef` is a TypedDict with: `ohlcv_parquet`, `signal_parquet`, `signal_id`, `strategy_id`, `strategy_name`, `symbol`, `generation`.

## `PipelineDeps` (`deps.py`)

Frozen dataclass injected at construction time — immutable across the entire run.

```python
@dataclass(frozen=True)
class PipelineDeps:
    data_provider: DataProvider
    detectors: tuple[PatternDetector, ...]   # initial generation-0 detectors
    ohlcv_cache_dir: Path
    signal_cache_dir: Path
    db_path: Path
    hold_bars: int = 5
    init_cash: Decimal = Decimal("100000")
    fees: float = 0.0003
    slippage: float = 0.0005
    mutators: tuple[Mutator, ...] = ()
    ratchet_thresholds: RatchetThresholds = field(default_factory=RatchetThresholds)
    top_n_parents: int = 5
```

`deps.detectors` is only used to seed `state["detector_configs"]` on generation 0. In subsequent generations, `advance_generation` overwrites `detector_configs` with accepted child configs. Do NOT read `deps.detectors` in nodes — read `state["detector_configs"]` instead.

## Pipeline topology (`pipeline.py`)

```
START
  → load_universe          # seeds detector_configs from deps.detectors
  → fetch_data
  → detect_patterns        # uses state["detector_configs"] via build_detector_from_config
  → [conditional dispatch] run_backtest_one  ← Send API fan-out (one Send per signal_ref)
  → rank
  → mutate_strategies      # skips if generation+1 >= max_generations
  → ratchet_node           # no-op on generation=0
  → loop_decision ──────── continue → advance_generation → detect_patterns
                  └─────── stop     → END
```

`run_backtest_one` is the Send target — LangGraph runs one per signal ref in parallel. Results merge back via `operator.add` reducers.

## Node factory pattern

All nodes are closures created by factory functions (one per module):

```python
# nodes.py — Phase 1 nodes
make_load_universe(deps) → Callable[[PipelineState], dict]
make_fetch_data(deps)    → Callable[[PipelineState], dict]
make_detect_patterns(deps) → Callable[[PipelineState], dict]
make_rank(deps)          → Callable[[PipelineState], dict]

# nodes_phase2.py — Phase 2a nodes
make_run_backtest_dispatcher() → Callable[[PipelineState], list[Send]]
make_run_backtest_one(deps)   → Callable[[dict], dict]   # Send worker — receives {ref, run_id}
make_mutate_strategies(deps)  → Callable[[PipelineState], dict]
make_ratchet_node(deps)       → Callable[[PipelineState], dict]
make_advance_generation(deps) → Callable[[PipelineState], dict]
make_loop_decision()          → Callable[[PipelineState], str]  # returns "continue" | "stop"
```

Why factories instead of classes: pure functions are easy to test, `deps` injection without globals. Tests inject a `_SyntheticProvider` — node code is untouched.

## Key node behaviors

### `detect_patterns`
- Reads `state["detector_configs"]` (NOT `deps.detectors`)
- Resolves each config to a live detector via `build_detector_from_config(cfg)`
- Passes `generation=state["generation"]` to `insert_pattern_signal`
- Stores full `DetectorConfig` dict as `params` in `upsert_strategy` (enables round-trip + UNIQUE dedup)

### `run_backtest_one` (Send worker)
- Receives `{"ref": SignalRef, "run_id": str}` — NOT `PipelineState`
- Returns delta-only: `{"backtest_ids": [new_id], "failures": [...]}` or empty lists
- Passes `generation=ref["generation"]` to `insert_backtest_result`
- Never raises — logs failures to `failures` list

### `mutate_strategies`
- Skips if `generation + 1 >= max_generations` (no next generation needed)
- Calls each `Mutator.propose(parents, k=top_n_parents)` from `deps.mutators`
- Registers proposed child strategies via `upsert_strategy` (UNIQUE dedup is idempotent)
- Returns `{"mutations": [new_mutation_records]}` — merged via reducer

### `ratchet_node`
- No-op on `generation=0` (no parent to compare against)
- On `generation=N≥1`: reads `state["mutations"]` for `generation=N-1`
- Calls `build_evaluation_result` for both parent (gen N-1) and child (gen N)
- Calls `judge_mutation` (pure function)
- Writes verdict to `experiments` table via `insert_experiment`

### `loop_decision`
- Returns `"continue"` if `generation + 1 < max_generations`, else `"stop"`
- `max_generations=1` (default) → always stops → identical behavior to Phase 1

### `advance_generation`
- Reads `experiments` table to find accepted child strategy IDs for current generation
- Falls back to all proposed children if none accepted (keeps evolution alive)
- Returns `{"generation": generation + 1, "detector_configs": new_configs}`

## Error handling

Worker nodes (`fetch_data`, `detect_patterns`, `run_backtest_one`) **never raise**. On failure:
```python
failures.append({"node": "run_backtest", "symbol": symbol, "reason": str(exc)})
```

## Tests

```
tests/graph/test_pipeline.py       — Phase 1 E2E with synthetic provider
tests/graph/test_send_fanout.py    — dispatcher returns N Sends, worker writes DB row
tests/graph/test_mutate_node.py    — mutate_strategies registers child in DB,
                                     ratchet writes experiment rows, full 2-gen loop
tests/integration/test_phase2_pipeline.py — 2-generation run with mocked LLM
```
