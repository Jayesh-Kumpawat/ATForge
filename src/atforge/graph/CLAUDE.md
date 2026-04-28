# LangGraph Pipeline — `src/atforge/graph/`

## What this module does

Orchestrates the full Phase 1 pipeline using LangGraph's `StateGraph`. Wires pure node functions into a directed graph and compiles it into an invokable pipeline.

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
    run_id: str                        # uuid4().hex[:12]
    universe: list[str]                # ["RELIANCE", "TCS", ...]
    start_iso: str                     # "2015-01-01"
    end_iso: str                       # "2025-01-01"
    data_refs: dict[str, str]          # {symbol: "/path/to/RELIANCE_abc123.parquet"}
    signal_refs: list[SignalRef]       # one per (symbol, detector)
    backtest_ids: list[int]            # rowids in backtest_runs table
    failures: list[dict]               # {node, symbol, reason} — never raise
```

`SignalRef` is a TypedDict with both the OHLCV and signal parquet paths + strategy/signal DB IDs.

`total=False` means all keys are optional — nodes only return the keys they set, LangGraph merges.

## `PipelineDeps` (`deps.py`)

Frozen dataclass injected at construction time. Contains all I/O dependencies:

```python
@dataclass(frozen=True)
class PipelineDeps:
    data_provider: DataProvider         # CachedProvider(FallbackDataProvider([...]))
    detectors: tuple[PatternDetector, ...]
    ohlcv_cache_dir: Path              # data/cache/ohlcv/
    signal_cache_dir: Path             # data/cache/signals/
    db_path: Path                      # data/atforge.db
    hold_bars: int = 10
    init_cash: Decimal = Decimal("100000")
    fees: float = 0.0003
    slippage: float = 0.0005
```

## Node factory pattern (`nodes.py`)

Nodes are closures created by factory functions:

```python
def make_fetch_data(deps: PipelineDeps) -> NodeFn:
    def fetch_data(state: PipelineState) -> dict:
        # uses deps.data_provider, deps.ohlcv_cache_dir
        ...
    return fetch_data
```

Why factories instead of classes: keeps nodes as pure functions (easy to test), lets `deps` be injected without global state. Tests inject a `_SyntheticProvider` — the node code is untouched.

## Pipeline graph (`pipeline.py`)

Phase 1 linear graph:

```
START → load_universe → fetch_data → detect_patterns → run_backtest → rank → END
```

```python
graph = build_pipeline(deps)
result = graph.invoke({
    "run_id": "abc123",
    "universe": ["RELIANCE", "TCS"],
    "start_iso": "2024-01-01",
    "end_iso": "2025-01-01",
})
```

## Error handling strategy

Worker nodes (`fetch_data`, `detect_patterns`, `run_backtest`) **never raise**. On failure:
```python
failures.append({"node": "fetch_data", "symbol": symbol, "reason": str(exc)})
```
The `failures` list accumulates across all nodes and is available in the final state for inspection.

## Phase 2+ evolution path (no refactor needed)

- **Send API fan-out**: `detect_patterns → Send("run_backtest", {"signal_ref": ref})` per signal. `make_run_backtest` already operates on one signal_ref at a time.
- **HITL interrupt**: `build_pipeline(deps, interrupt_before=["rank"])` — operator reviews before ranking.
- **Conditional routing**: add edge with condition after `run_backtest` to loop to `detect_patterns` with mutated detectors (Phase 2 evolution).
- **LLM nodes**: new nodes calling `llm/client.py` plug into the graph between `rank` and `END`.

## Tests

```
tests/graph/test_pipeline.py  — E2E with _SyntheticProvider (offline), partial provider failure
```
