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
    signal_refs: Annotated[list[SignalRef], operator.add]         # reducer — delta-only
    backtest_ids: Annotated[list[int], operator.add]              # reducer — delta-only
    failures: Annotated[list[dict], operator.add]                 # reducer — delta-only
    mutations: Annotated[list[dict[str, Any]], operator.add]      # reducer — all generations
    # A2 multi-agent — accumulated within each generation pass
    proposed_mutations: Annotated[list[dict[str, Any]], operator.add]  # explorer+exploiter output
    vetoed_mutations: Annotated[list[dict[str, Any]], operator.add]    # critic output
```

**Reducers vs last-writer-wins**: `signal_refs`, `backtest_ids`, `failures`, `mutations`, `proposed_mutations`, `vetoed_mutations` use `operator.add` — each node returns only NEW items. `detector_configs` is last-writer-wins — `advance_generation` overwrites it with accepted child configs each loop.

`SignalRef` is a TypedDict with: `ohlcv_parquet`, `signal_parquet`, `signal_id`, `strategy_id`, `strategy_name`, `symbol`, `generation`, `parent_strategy_id`.

## `AgentRoleConfig` + `PipelineDeps` (`deps.py`)

```python
@dataclass(frozen=True)
class AgentRoleConfig:
    role: str           # "explorer" | "exploiter" | "critic"
    temperature: float  # 0.9 explorer, 0.4 exploiter, 0.3 critic
    max_iterations: int # ReAct loop bound
    system_prompt: str  # loaded from atforge.yaml or built-in default
    llm_priority: tuple[str, ...] = ()  # empty = use global priority
    model: str | None = None            # None = use router default
```

Loaded from `atforge.yaml` at startup via `load_role_configs(path)` in `role_config.py`. Falls back to `default_role_configs()` if file absent.

```python
@dataclass(frozen=True)
class PipelineDeps:
    data_provider: DataProvider
    detectors: tuple[PatternDetector, ...]   # initial generation-0 detectors
    ohlcv_cache_dir: Path
    signal_cache_dir: Path
    db_path: Path
    hold_bars: int = 10
    init_cash: Decimal = Decimal("100000")
    fees: float = 0.0003
    slippage: float = 0.0005
    mutators: tuple[Mutator, ...] = ()
    ratchet_thresholds: RatchetThresholds = field(default_factory=RatchetThresholds)
    top_n_parents: int = 5
    # Observability
    tracing_enabled: bool = False
    event_bus: Any | None = None
    # A2 multi-agent
    role_configs: dict[str, AgentRoleConfig] = field(default_factory=dict)
    llm_router: Callable | None = None  # injected by CLI; used by critic/exploiter directly
```

`deps.detectors` is only used to seed `state["detector_configs"]` on generation 0. In subsequent generations, `advance_generation` overwrites `detector_configs` with accepted child configs. Do NOT read `deps.detectors` in nodes — read `state["detector_configs"]` instead.

## Pipeline topology (`pipeline.py`)

```
START
  → load_universe          # seeds detector_configs from deps.detectors
  → fetch_data
  → detect_patterns        # uses state["detector_configs"] via build_detector_from_config
  → [Send×N] run_backtest_one  ← Send API fan-out (one Send per signal_ref)
  → ratchet_node           # no-op on generation=0; scores gen≥1 backtest results
  → rank                   # top_rankings() from SQLite
  → explorer_node          # propose novel mutations — ResearchAgentMutator, high-temp
  → exploiter_node         # refine top performers — ResearchAgentMutator, low-temp
  → critic_node            # hard-veto proposals via ReAct loop; logs critic_veto rows
  → aggregate_node         # filter vetoed, upsert survivors → mutations reducer
  → loop_decision ──────── continue → advance_generation → detect_patterns
                  └─────── stop     → END
```

`run_backtest_one` is the Send target — LangGraph runs one per signal ref in parallel. Results merge back via `operator.add` reducers. `loop_decision` now lives on `aggregate_node` (not `ratchet_node`).

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
make_ratchet_node(deps)       → Callable[[PipelineState], dict]
make_advance_generation(deps) → Callable[[PipelineState], dict]
make_loop_decision()          → Callable[[PipelineState], str]  # returns "continue" | "stop"

# nodes_a2.py — A2 multi-agent nodes
make_explorer_node(deps)   → Callable[[PipelineState], dict]   # propose novel mutations
make_exploiter_node(deps)  → Callable[[PipelineState], dict]   # refine top performers
make_critic_node(deps)     → Callable[[PipelineState], dict]   # hard-veto bad proposals
make_aggregate_node(deps)  → Callable[[PipelineState], dict]   # filter + upsert survivors
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

### `explorer_node` (A2)
- Runs `ResearchAgentMutator` at high temperature (from `deps.role_configs["explorer"]`)
- Uses `build_research_tools(deps)` — 5 read-only DB tools for historical lookups
- Deduplicates proposals by fingerprint (`parent_id + canonical JSON`) before emitting
- Returns `{"proposed_mutations": [proposals]}` — merged via reducer

### `exploiter_node` (A2)
- Runs `ResearchAgentMutator` at low temperature (from `deps.role_configs["exploiter"]`)
- Targets top-N strategies from current generation by Sharpe
- Returns `{"proposed_mutations": [proposals]}` — appended to explorer's proposals

### `critic_node` (A2)
- For each proposal in `state["proposed_mutations"]`, runs a bounded ReAct loop
- On veto: calls `insert_experiment` with `mutator="critic_veto"`, `child_strategy_id=NULL`, `accepted=0`
- Emits `EvtCriticVerdict` to `EventBus` for each verdict
- Scores `veto_rate` on active Langfuse span via `score_current_observation`
- Returns `{"vetoed_mutations": [vetoed_configs]}` — merged via reducer

### `aggregate_node` (A2)
- Filters `proposed_mutations` minus `vetoed_mutations` — survivors proceed to backtest
- Calls `upsert_strategy` for each survivor (UNIQUE dedup is idempotent)
- Returns `{"mutations": [accepted_records]}` — merged into the main mutations reducer
- `loop_decision` conditional edge runs on this node (not ratchet_node)

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
