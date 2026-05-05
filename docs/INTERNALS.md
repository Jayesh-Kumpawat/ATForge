# ATForge — Pipeline Internals

How the system actually runs. Read this to understand execution, not intent.
For the *why* behind design choices, see [DESIGN.md](DESIGN.md).

> **Verified against code:** 2026-05-05. If a section tag below appears in a git diff, re-verify that section.
> Section tags: `<!-- section:trace -->`, `<!-- section:state -->`, `<!-- section:fanout -->`, `<!-- section:evolution -->`, `<!-- section:ratchet -->`

---

## Contents

1. [Complete annotated execution trace](#1-complete-annotated-execution-trace) — follow one real run step by step
2. [PipelineState mechanics](#2-pipelinestate-mechanics) — reducer vs last-writer-wins, field evolution table
3. [Send API fan-out](#3-send-api-fan-out) — how parallel backtests work and merge
4. [Multi-generation evolution lifecycle](#4-multi-generation-evolution-lifecycle) — 3 concrete generations
5. [Ratchet walkthrough](#5-ratchet-walkthrough) — accept, reject (Sharpe), reject (symbol regression)

---

## 1. Complete annotated execution trace

<!-- section:trace -->

**Command being traced:**
```bash
uv run python main.py pipeline --symbols RELIANCE,TCS --lookback 1y --max-generations 2
```

**What `main.py pipeline` does before touching LangGraph:**
1. Parses `--symbols RELIANCE,TCS` → `universe = ["RELIANCE", "TCS"]`
2. Applies `--lookback 1y` → `end = date.today()`, `start = end - 365 days`
3. Calls `init_db(settings.db_path)` — creates tables if missing, runs migrations
4. Builds `RatchetThresholds` from `config.py` settings (all env-overrideable)
5. Builds `PipelineDeps` — immutable frozen dataclass injected into every node closure
6. Calls `build_pipeline(deps)` — wires the LangGraph `StateGraph`
7. Calls `graph.invoke({...initial state...})`

**Initial state passed to `graph.invoke()`:**
```json
{
  "run_id": "a3f9d2c1",
  "universe": ["RELIANCE", "TCS"],
  "start_iso": "2024-05-05",
  "end_iso": "2025-05-05",
  "generation": 0,
  "max_generations": 2
}
```

Note: `detector_configs`, `signal_refs`, `backtest_ids`, `failures`, `mutations` are absent — `total=False` on `PipelineState` means absent keys are valid.

---

### Node 1: `load_universe`

**Source:** `graph/nodes.py:make_load_universe`

**Reads from state:** `universe`, `detector_configs` (checks if absent)

**What it does:**
- Confirms `universe` is set (uses CLI-provided list, or loads Nifty 50 if missing)
- Calls `insert_run(conn, run_id)` — writes one row to the `runs` table in SQLite
- If `detector_configs` is absent (always true on gen=0), converts `deps.detectors` → list of `DetectorConfig` dicts via `_detector_to_config()`

**`deps.detectors` default contents** (13 detectors from `_default_detectors()` in `cli.py`):
```
10 TA-Lib CDL patterns:  CDL_HAMMER, CDL_ENGULFING, CDL_DOJI, CDL_MORNINGSTAR,
                          CDL_SHOOTINGSTAR, CDL_HANGINGMAN, CDL_EVENINGSTAR,
                          CDL_HARAMI, CDL_DARKCLOUD, CDL_PIERCING
2 SMA crossovers:        SMA(fast=10, slow=25),  SMA(fast=5, slow=20)
1 RSI reclaim:           RSI(period=14, oversold=30)
```

**Returns:**
```json
{
  "universe": ["RELIANCE", "TCS"],
  "detector_configs": [
    {"type": "talib_cdl", "cdl_name": "CDL_HAMMER", "direction": "bullish"},
    {"type": "talib_cdl", "cdl_name": "CDL_ENGULFING", "direction": "bullish"},
    {"type": "talib_cdl", "cdl_name": "CDL_DOJI", "direction": "bullish"},
    {"type": "talib_cdl", "cdl_name": "CDL_MORNINGSTAR", "direction": "bullish"},
    {"type": "talib_cdl", "cdl_name": "CDL_SHOOTINGSTAR", "direction": "bearish"},
    {"type": "talib_cdl", "cdl_name": "CDL_HANGINGMAN", "direction": "bearish"},
    {"type": "talib_cdl", "cdl_name": "CDL_EVENINGSTAR", "direction": "bearish"},
    {"type": "talib_cdl", "cdl_name": "CDL_HARAMI", "direction": "bullish"},
    {"type": "talib_cdl", "cdl_name": "CDL_DARKCLOUD", "direction": "bearish"},
    {"type": "talib_cdl", "cdl_name": "CDL_PIERCING", "direction": "bullish"},
    {"type": "sma_crossover", "fast": 10, "slow": 25},
    {"type": "sma_crossover", "fast": 5, "slow": 20},
    {"type": "rsi_oversold", "period": 14, "oversold": 30}
  ]
}
```

**LangGraph merges this return into state.** `detector_configs` is last-writer-wins — the 13 configs now live in state.

---

### Node 2: `fetch_data`

**Source:** `graph/nodes.py:make_fetch_data`

**Reads from state:** `universe`, `start_iso`, `end_iso`, `run_id`

**What it does:**  
For each symbol — calls `deps.data_provider.fetch_ohlcv(symbol, start, end)`.  
The provider is `CachedProvider(FallbackDataProvider([openchart, jugaad_data, yfinance]))` — tries sources in order until one succeeds.  
Result is a DataFrame with columns: `open, high, low, close, volume` (DatetimeIndex, daily freq).  
Saves as parquet: `data/cache/ohlcv/{SYMBOL}_{run_id}.parquet`  
On any exception: appends to `failures`, continues to next symbol — never raises.

**Returns:**
```json
{
  "data_refs": {
    "RELIANCE": "data/cache/ohlcv/RELIANCE_a3f9d2c1.parquet",
    "TCS":      "data/cache/ohlcv/TCS_a3f9d2c1.parquet"
  },
  "failures": []
}
```

**`data_refs` is last-writer-wins** — not a reducer. One producer, overwrites entirely.

**Files written to disk:**
```
data/cache/ohlcv/
  RELIANCE_a3f9d2c1.parquet   ← ~252 rows (trading days in 1 year)
  TCS_a3f9d2c1.parquet        ← ~252 rows
```

---

### Node 3: `detect_patterns`

**Source:** `graph/nodes.py:make_detect_patterns`

**Reads from state:** `detector_configs`, `data_refs`, `run_id`, `generation`

**What it does:**  
Outer loop: each symbol in `data_refs`.  
Inner loop: each config in `detector_configs`.  
Per (symbol, config) pair:
1. Reads OHLCV parquet from disk
2. `build_detector_from_config(cfg)` → instantiates live detector object
3. `det.detect(df)` → `DetectionResult` with `.signal` bool Series
4. `upsert_strategy(conn, name, family, params=cfg)` → gets or creates a `strategy_id`
   - UNIQUE on `(name, params_json)` with `sort_keys=True` — idempotent
5. `insert_pattern_signal(conn, run_id, strategy_id, symbol, n_signals, generation)` → `signal_id`
6. Saves signal Series as parquet: `data/cache/signals/{symbol}_{strategy_id}_{run_id}.parquet`
7. Builds a `SignalRef` dict and appends to `new_refs`

**Returns delta only** (reducer merges):
```json
{
  "signal_refs": [
    {
      "symbol": "RELIANCE",
      "strategy_name": "CDL_HAMMER_bullish",
      "strategy_id": 1,
      "signal_id": 1,
      "ohlcv_parquet": "data/cache/ohlcv/RELIANCE_a3f9d2c1.parquet",
      "signal_parquet": "data/cache/signals/RELIANCE_1_a3f9d2c1.parquet",
      "generation": 0,
      "parent_strategy_id": null
    },
    ... (25 more, one per symbol×detector combination)
  ],
  "failures": []
}
```

**DB rows written (per combination):**
- `strategies` table: upsert (may already exist from a prior run)
- `pattern_signals` table: new row per (symbol, strategy, generation, run_id)

**Files written to disk:**
```
data/cache/signals/
  RELIANCE_1_a3f9d2c1.parquet   ← CDL_HAMMER signals on RELIANCE
  RELIANCE_2_a3f9d2c1.parquet   ← CDL_ENGULFING signals on RELIANCE
  ...
  TCS_13_a3f9d2c1.parquet       ← RSI_OVERSOLD signals on TCS
```

**State `signal_refs` after this node:** 26 items (2 symbols × 13 detectors).

---

### Node 4: dispatcher → `run_backtest_one` fan-out

**Source:** `graph/nodes_phase2.py:make_run_backtest_dispatcher` + `make_run_backtest_one`

This is NOT a regular node — it is the conditional edge function that LangGraph calls after `detect_patterns`. It returns a list of `Send` objects, not a state delta.

```python
def dispatcher(state: PipelineState) -> list[Send]:
    return [
        Send("run_backtest_one", {"ref": ref, "run_id": run_id})
        for ref in state.get("signal_refs", [])
    ]
```

LangGraph receives 26 `Send` objects and launches 26 parallel workers.

**Each `run_backtest_one` worker receives** (NOT `PipelineState` — a plain dict):
```json
{
  "ref": {<one SignalRef>},
  "run_id": "a3f9d2c1"
}
```

**What each worker does:**
1. Reads OHLCV parquet and signal parquet from disk
2. `run_backtest(ohlcv, sig, symbol, pattern_name, init_cash, hold_bars, fees, slippage)`
   - Shifts signal Series by +1 bar before passing to vectorbt (lookahead prevention)
   - Returns `BacktestResult` with `.success`, `.metrics` (Sharpe, Sortino, n_trades, max_drawdown)
3. `insert_backtest_result(conn, run_id, signal_id, strategy_id, result, generation=0)` → `backtest_id`
4. Returns `{"backtest_ids": [bid], "failures": []}` on success
5. Returns `{"backtest_ids": [], "failures": [{...}]}` on any exception — never raises

**LangGraph merges all 26 returns via `operator.add`:**
```
Worker 1  returns {"backtest_ids": [1], "failures": []}
Worker 2  returns {"backtest_ids": [2], "failures": []}
...
Worker 25 returns {"backtest_ids": [], "failures": [{"node": "run_backtest", "symbol": "RELIANCE", "strategy": "CDL_DARKCLOUD", "reason": "n_trades=0"}]}
Worker 26 returns {"backtest_ids": [26], "failures": []}
                                            ↓ operator.add merge
state["backtest_ids"] = [1, 2, 3, ..., 25]   ← 25 succeeded
state["failures"]     = [...existing..., {"node": "run_backtest", ...}]
```

**DB rows written:**
- `backtest_runs` table: one row per worker, with `generation=0`
- Stores: `run_id`, `strategy_id`, `signal_id`, `sharpe`, `sortino`, `n_trades`, `max_drawdown`, `hold_bars`, `fees`, `slippage`, `init_cash`, `success`

---

### Node 5: `rank`

**Source:** `graph/nodes.py:make_rank`

Reads `backtest_runs` from DB for this `run_id`, orders by Sharpe descending, prints a rich table to terminal. Returns `{}` (no state changes). Does not write to DB.

---

### Node 6: `mutate_strategies`

**Source:** `graph/nodes_phase2.py:make_mutate_strategies`

**Guard check first:**
```python
if generation + 1 >= max_gen:   # 0+1=1 < 2 → NOT skipped
    return {}
```

**What it does:**
1. `get_top_strategies_for_generation(conn, run_id, generation=0, limit=5)` → top 5 `StrategyRow` dicts by Sharpe
2. For each mutator in `deps.mutators`:

**`ParamDeltaMutator.propose(parents, k=5)`:**
- Checks each parent's `DetectorConfig` type
- `sma_crossover` and `rsi_oversold` → eligible; `talib_cdl`, `and`, `or` → skipped
- Sends LLM prompt with current params and recent performance metrics
- LLM returns new params in JSON
- Three-layer parse: strip fences → brace-match → Pydantic validate
- On success → `ProposedMutation(parent_id, child_config, reasoning, "param_delta")`

**`CompositionMutator.propose(parents, k=5)`:**
- Forms pairs from `itertools.combinations(parents, 2)`
- Skips any parent whose config nesting depth ≥ 2
- For each pair, asks LLM: "AND or OR for these two detectors?"
- Returns AND/OR composite `DetectorConfig`

**For each `ProposedMutation`:**
```python
det = build_detector_from_config(proposal.child_config)   # validates config is constructible
child_sid = upsert_strategy(conn, name=det.name, family=det.family, params=proposal.child_config)
```

**Returns delta:**
```json
{
  "mutations": [
    {
      "generation": 0,
      "parent_strategy_id": 11,
      "child_strategy_id": 14,
      "mutator": "param_delta",
      "mutation_json": "{\"fast\":8,\"slow\":22,\"type\":\"sma_crossover\"}",
      "reasoning": "Tighter fast window captures momentum earlier in trending markets."
    },
    {
      "generation": 0,
      "parent_strategy_id": 12,
      "child_strategy_id": 15,
      "mutator": "param_delta",
      "mutation_json": "{\"fast\":6,\"slow\":18,\"type\":\"sma_crossover\"}",
      "reasoning": "Shorter periods reduce lag on NSE's intraday-driven daily bars."
    },
    {
      "generation": 0,
      "parent_strategy_id": 13,
      "child_strategy_id": 16,
      "mutator": "param_delta",
      "mutation_json": "{\"oversold\":25,\"period\":10,\"type\":\"rsi_oversold\"}",
      "reasoning": "Lower period and higher oversold threshold reduces whipsaw in trending regimes."
    },
    {
      "generation": 0,
      "parent_strategy_id": 11,
      "child_strategy_id": 17,
      "mutator": "composition",
      "mutation_json": "{\"left\":{\"fast\":10,\"slow\":25,\"type\":\"sma_crossover\"},\"op\":\"and\",\"right\":{\"oversold\":30,\"period\":14,\"type\":\"rsi_oversold\"},\"type\":\"and\"}",
      "reasoning": "AND combination filters SMA crossovers to only those with RSI confirmation, reducing false entries."
    },
    {
      "generation": 0,
      "parent_strategy_id": 1,
      "child_strategy_id": 18,
      "mutator": "composition",
      "mutation_json": "{\"left\":{\"cdl_name\":\"CDL_HAMMER\",\"direction\":\"bullish\",\"type\":\"talib_cdl\"},\"op\":\"or\",\"right\":{\"fast\":5,\"slow\":20,\"type\":\"sma_crossover\"},\"type\":\"or\"}",
      "reasoning": "OR combination increases signal frequency by capturing either candlestick reversal or trend-following entry."
    }
  ]
}
```

---

### Node 7: `ratchet_node` (generation 0 — no-op)

```python
generation = state.get("generation", 0)   # = 0
if generation == 0:
    return {}   # ← exits immediately, no DB reads, no comparisons
```

No experiments written. State unchanged.

---

### Node 8: `loop_decision`

```python
return "continue" if generation + 1 < max_gen else "stop"
# 0 + 1 = 1 < 2 → "continue"
```

LangGraph routes to `advance_generation`.

---

### Node 9: `advance_generation`

**Source:** `graph/nodes_phase2.py:make_advance_generation`

```python
current_gen_mutations = [m for m in state["mutations"] if m["generation"] == 0]
# → all 5 mutations

# Check experiments table for accepted children at generation=1
# (ratchet_node was a no-op at gen=0, so experiments table has NO rows yet)
accepted_sids = []   # empty — fall back to all proposed
candidate_sids = [14, 15, 16, 17, 18]   # all 5 child strategy IDs

# Build detector configs from each child's params_json in strategies table
new_configs = [child_config_14, child_config_15, ..., child_config_18]
```

**Returns:**
```json
{
  "generation": 1,
  "detector_configs": [
    {"type": "sma_crossover", "fast": 8, "slow": 22},
    {"type": "sma_crossover", "fast": 6, "slow": 18},
    {"type": "rsi_oversold", "period": 10, "oversold": 25},
    {"type": "and", "left": {"fast": 10, "slow": 25, "type": "sma_crossover"}, "right": {"oversold": 30, "period": 14, "type": "rsi_oversold"}},
    {"type": "or",  "left": {"cdl_name": "CDL_HAMMER", "direction": "bullish", "type": "talib_cdl"}, "right": {"fast": 5, "slow": 20, "type": "sma_crossover"}}
  ]
}
```

**`detector_configs` is OVERWRITTEN** (last-writer-wins). The 13 gen=0 configs are gone. Gen=1 runs with only these 5 child configs.

LangGraph routes back to `detect_patterns`.

---

### Generation 1 loop (abbreviated)

**`detect_patterns` (gen=1):**
- 2 symbols × 5 configs = 10 new (symbol, detector) pairs
- `generation=1` passed to `insert_pattern_signal` — stored in `pattern_signals.generation`
- `signal_refs` reducer appends 10 new refs: total grows from 26 → 36

**`run_backtest_one` (10 parallel workers, gen=1):**
- Same flow as gen=0
- `generation=1` stored in `backtest_runs.generation`
- `backtest_ids` grows from 25 → 34 (if 9 succeed, 1 fails)

**`mutate_strategies` (gen=1):**
```python
if generation + 1 >= max_gen:   # 1+1=2 >= 2 → SKIPPED
    return {}
```

**`ratchet_node` (gen=1 — active):**

Now gen=1 ≥ 1, so ratchet runs. See [§5 Ratchet walkthrough](#5-ratchet-walkthrough) for detail.

Writes 5 rows to `experiments` table (one per gen=0 mutation).

**`loop_decision` (gen=1):**
```python
# 1 + 1 = 2 >= 2 → "stop"
```

Pipeline ends. `rank` node runs one final time, prints results.

---

### Final state snapshot (end of run)

```
run_id:          "a3f9d2c1"
universe:        ["RELIANCE", "TCS"]
generation:      1
max_generations: 2
detector_configs: [5 gen-1 configs]   ← last value written by advance_generation
data_refs:       {RELIANCE: ..., TCS: ...}
signal_refs:     [36 items]           ← 26 gen-0 + 10 gen-1, all preserved by reducer
backtest_ids:    [34 items]           ← 25 gen-0 + 9 gen-1
failures:        [2 items]            ← all accumulated failures across both gens
mutations:       [5 items]            ← gen-0 proposals, reducer-preserved
```

---

## 2. PipelineState mechanics

<!-- section:state -->

### Reducer vs last-writer-wins

Two fundamentally different merge behaviors in `PipelineState`:

| Field | Behavior | Annotation | Why |
|---|---|---|---|
| `run_id` | last-writer-wins | none | Set once, never changes |
| `universe` | last-writer-wins | none | Set once |
| `start_iso`, `end_iso` | last-writer-wins | none | Set once |
| `generation` | last-writer-wins | none | `advance_generation` is sole writer each loop |
| `max_generations` | last-writer-wins | none | Set once from CLI |
| `data_refs` | last-writer-wins | none | `fetch_data` is sole writer |
| `detector_configs` | last-writer-wins | none | `load_universe` OR `advance_generation` writes — never both in same pass |
| `signal_refs` | **reducer** | `Annotated[list, operator.add]` | Multiple workers each return their own delta |
| `backtest_ids` | **reducer** | `Annotated[list, operator.add]` | 26 parallel workers each return `[bid]` |
| `failures` | **reducer** | `Annotated[list, operator.add]` | Any node can append failures |
| `mutations` | **reducer** | `Annotated[list, operator.add]` | Accumulates across generations |

### Critical rule for reducer fields

**Nodes must return only their NEW delta, not the full list.**

```python
# WRONG — would double-count on every merge
return {"backtest_ids": state["backtest_ids"] + [new_bid]}

# CORRECT — return only what this node produced
return {"backtest_ids": [new_bid]}
```

LangGraph calls `operator.add(existing, returned)` to merge. If you return the full list, LangGraph extends the existing list with it — duplicating everything.

### State evolution across 2 generations

| After node | `generation` | `detector_configs` | `signal_refs` | `backtest_ids` | `mutations` |
|---|---|---|---|---|---|
| *invoke()* | 0 | absent | absent | absent | absent |
| `load_universe` | 0 | 13 configs | absent | absent | absent |
| `fetch_data` | 0 | 13 | absent | absent | absent |
| `detect_patterns` (gen=0) | 0 | 13 | **26** | absent | absent |
| `run_backtest_one` ×26 | 0 | 13 | 26 | **25** | absent |
| `rank` | 0 | 13 | 26 | 25 | absent |
| `mutate_strategies` | 0 | 13 | 26 | 25 | **5** |
| `ratchet_node` (no-op) | 0 | 13 | 26 | 25 | 5 |
| `loop_decision` → continue | 0 | 13 | 26 | 25 | 5 |
| `advance_generation` | **1** | **5** ← overwritten | 26 | 25 | 5 |
| `detect_patterns` (gen=1) | 1 | 5 | **36** | 25 | 5 |
| `run_backtest_one` ×10 | 1 | 5 | 36 | **34** | 5 |
| `rank` | 1 | 5 | 36 | 34 | 5 |
| `mutate_strategies` (skipped) | 1 | 5 | 36 | 34 | 5 |
| `ratchet_node` (active) | 1 | 5 | 36 | 34 | 5 |
| `loop_decision` → stop | 1 | 5 | 36 | 34 | 5 |

Note: `signal_refs` grows from 26 → 36 across generations. `backtest_ids` grows from 25 → 34. These are cumulative — all generations' data stays in state via reducers.

`detector_configs` at gen=1 is ONLY the 5 child configs — not the union of gen=0 and gen=1. It was overwritten by `advance_generation`.

---

## 3. Send API fan-out

<!-- section:fanout -->

### Sequence diagram

```
pipeline.py
  detect_patterns completes
        │
        ▼
  dispatcher(state) ──── returns list[Send] ─────────────────────────────────┐
        │                                                                     │
        │  Send("run_backtest_one", {"ref": ref_0, "run_id": "a3f9d2c1"})   │
        │  Send("run_backtest_one", {"ref": ref_1, "run_id": "a3f9d2c1"})   │
        │  ...                                                                │
        │  Send("run_backtest_one", {"ref": ref_25, "run_id": "a3f9d2c1"})  │
        │                                                                     │
        ▼                                                                     │
  LangGraph spawns 26 workers simultaneously ◄──────────────────────────────┘
        │
        ├─ worker_0  → reads parquets → run_backtest() → insert DB → {"backtest_ids": [1],  "failures": []}
        ├─ worker_1  → reads parquets → run_backtest() → insert DB → {"backtest_ids": [2],  "failures": []}
        ├─ ...
        ├─ worker_24 → reads parquets → run_backtest() → fails     → {"backtest_ids": [],   "failures": [{...}]}
        └─ worker_25 → reads parquets → run_backtest() → insert DB → {"backtest_ids": [25], "failures": []}
        │
        ▼
  LangGraph merges all 26 returns via operator.add
        backtest_ids = [] + [1] + [2] + ... + [] + [25] = [1, 2, ..., 25]
        failures     = [] + [] + ... + [{...}] + []      = [{...}]
        │
        ▼
  rank node receives updated state
```

### Why the worker receives a plain dict, not PipelineState

```python
# dispatcher sends:
Send("run_backtest_one", {"ref": ref, "run_id": run_id})

# worker receives: plain dict, NOT PipelineState
def run_backtest_one(state: dict[str, Any]) -> dict[str, Any]:
    ref = state["ref"]    # ← access the ref directly
```

LangGraph's `Send` API passes the second argument as the worker's "state". It is a freeform dict — the worker only needs its specific inputs, not the entire pipeline state. This prevents workers from accidentally reading (or writing) state they don't own.

### Why large objects must not go in state

LangGraph checkpoints state between every node. If `signal_refs` contained actual DataFrames:
- Each checkpoint would serialize potentially hundreds of MB
- With 26 parallel workers all merging via reducer, LangGraph would serialize+deserialize the accumulating list 26 times
- Phase 3 adds `interrupt_before=["rank"]` for HITL — checkpoint must be loadable instantly

Instead, state holds only file paths. Workers read directly from disk. Checkpoints are tiny (a few KB of JSON).

### Parallel DB writes — why they don't conflict

Each worker opens its own connection via `connect(deps.db_path)`. SQLite in WAL mode allows multiple concurrent readers and one writer at a time. Workers that write `backtest_runs` acquire a write lock briefly, then release. The likelihood of two workers writing simultaneously is low since each write is a single fast INSERT.

---

## 4. Multi-generation evolution lifecycle

<!-- section:evolution -->

### Generation 0 — baseline

**What runs:** All 13 default detectors on RELIANCE + TCS. 26 backtests.

**Top 5 by Sharpe (realistic values):**

| Rank | Strategy | Symbol | Sharpe | Sortino | n_trades | Max DD |
|---|---|---|---|---|---|---|
| 1 | SMA_CROSS(10,25) | RELIANCE | 0.82 | 0.61 | 18 | 7.4% |
| 2 | SMA_CROSS(5,20) | TCS | 0.71 | 0.53 | 24 | 9.1% |
| 3 | RSI_OVERSOLD(14,30) | RELIANCE | 0.64 | 0.48 | 12 | 6.8% |
| 4 | SMA_CROSS(10,25) | TCS | 0.58 | 0.42 | 16 | 8.3% |
| 5 | CDL_HAMMER_bullish | RELIANCE | 0.44 | 0.31 | 9 | 5.2% |

**What `build_evaluation_result` aggregates per strategy across symbols:**

For `SMA_CROSS(10,25)` (strategy_id=11), which ran on both RELIANCE and TCS:
```python
EvaluationResult(
    strategy_id=11,
    mean_sharpe=0.70,       # avg(0.82, 0.58)
    mean_sortino=0.515,     # avg(0.61, 0.42)
    total_n_trades=34,      # 18 + 16
    max_drawdown=Decimal("0.083"),  # max(0.074, 0.083)
    n_symbols=2,
    per_symbol_sharpe={"RELIANCE": 0.82, "TCS": 0.58}
)
```

**`mutate_strategies` LLM calls for gen=0:**

```
ParamDeltaMutator processes SMA_CROSS(10,25):
  Prompt includes: current fast=10, slow=25, Sharpe=0.70, n_trades=34
  LLM response:    {"fast": 8, "slow": 22, "reasoning": "Tighter window captures ..."}
  → child_config: {"type": "sma_crossover", "fast": 8, "slow": 22}
  → upsert_strategy → strategy_id=14

ParamDeltaMutator processes SMA_CROSS(5,20):
  Prompt: fast=5, slow=20, Sharpe=0.71
  LLM response: {"fast": 6, "slow": 18, "reasoning": "Shorter periods reduce lag ..."}
  → strategy_id=15

ParamDeltaMutator processes RSI_OVERSOLD(14,30):
  Prompt: period=14, oversold=30, Sharpe=0.64
  LLM response: {"period": 10, "oversold": 25, "reasoning": "Lower period ..."}
  → strategy_id=16

CompositionMutator processes pair (SMA_CROSS(10,25), RSI_OVERSOLD(14,30)):
  LLM response: {"op": "AND", "reasoning": "AND filters SMA crossovers with RSI confirmation ..."}
  → child_config: {"type": "and", "left": {sma_10_25}, "right": {rsi_14_30}}
  → strategy_id=17

CompositionMutator processes pair (CDL_HAMMER, SMA_CROSS(5,20)):
  LLM response: {"op": "OR", "reasoning": "OR captures either candlestick reversal or trend ..."}
  → child_config: {"type": "or", "left": {cdl_hammer}, "right": {sma_5_20}}
  → strategy_id=18
```

---

### Generation 1 — mutations backtested

`advance_generation` updates `detector_configs` to the 5 child configs.  
`detect_patterns` runs with those 5 configs → 10 signal_refs (2 symbols × 5).  
10 backtest workers run → results stored with `generation=1`.

**Gen=1 backtest results (realistic values):**

| Strategy | Symbol | Sharpe (gen=1) | vs parent Sharpe | Δ Sharpe |
|---|---|---|---|---|
| SMA_CROSS(8,22) | RELIANCE | 0.91 | 0.82 (parent SMA_10_25 on RELIANCE) | **+0.09** |
| SMA_CROSS(8,22) | TCS | 0.61 | 0.58 (parent SMA_10_25 on TCS) | **+0.03** |
| SMA_CROSS(6,18) | RELIANCE | 0.74 | 0.82 | **-0.08** |
| SMA_CROSS(6,18) | TCS | 0.66 | 0.71 | -0.05 |
| RSI(10,25) | RELIANCE | 0.67 | 0.64 | +0.03 |
| RSI(10,25) | TCS | 0.55 | — | — |
| AND(SMA_10_25, RSI_14_30) | RELIANCE | 0.78 | 0.70 (mean across symbols) | +0.08 |
| AND(SMA_10_25, RSI_14_30) | TCS | 0.65 | 0.70 | — |
| OR(CDL_HAMMER, SMA_5_20) | RELIANCE | 0.51 | 0.44 | +0.07 |
| OR(CDL_HAMMER, SMA_5_20) | TCS | 0.69 | 0.71 | -0.02 |

Now `ratchet_node` compares each child to its parent. See §5 for examples.

---

## 5. Ratchet walkthrough

<!-- section:ratchet -->

The ratchet runs in `ratchet_node` at gen=1. For each of the 5 mutations proposed at gen=0:

1. `build_evaluation_result(conn, strategy_id=parent_sid, run_id, generation=0)` → parent `EvaluationResult`
2. `build_evaluation_result(conn, strategy_id=child_sid, run_id, generation=1)` → child `EvaluationResult`
3. `judge_mutation(parent, child, thresholds)` → `RatchetVerdict`

`judge_mutation` is pure — no DB reads, no side effects.

### Example A — ACCEPTED (SMA_CROSS 10,25 → 8,22)

```
Parent EvaluationResult (strategy_id=11, gen=0):
  mean_sharpe:    0.70   (avg of RELIANCE=0.82, TCS=0.58)
  mean_sortino:   0.515
  total_n_trades: 34
  max_drawdown:   Decimal("0.083")
  per_symbol_sharpe: {"RELIANCE": 0.82, "TCS": 0.58}

Child EvaluationResult (strategy_id=14, gen=1):
  mean_sharpe:    0.76   (avg of RELIANCE=0.91, TCS=0.61)
  mean_sortino:   0.57
  total_n_trades: 30
  max_drawdown:   Decimal("0.079")
  per_symbol_sharpe: {"RELIANCE": 0.91, "TCS": 0.61}

Gate checks:
  Gate 1 (Sharpe):    delta=0.76-0.70=0.06  >= 0.05  ✓
  Gate 2 (Sortino):   delta=0.57-0.515=0.055 >= 0.02  ✓
  Gate 3 (Drawdown):  ratio=0.079/0.083=0.95 <= 1.10  ✓
  Gate 4 (Trades):    child n_trades=30      >= 5     ✓
  Gate 5 (Per-symbol):
    RELIANCE: 0.91-0.82=+0.09 >= -0.50  ✓
    TCS:      0.61-0.58=+0.03 >= -0.50  ✓

Result: accepted=True, reasoning="accepted"

composite_score written to experiments table:
  {"delta_sharpe": 0.06, "delta_sortino": 0.055, "dd_ratio": 0.95,
   "child_n_trades": 30.0, "sharpe_ok": 1.0, "sortino_ok": 1.0,
   "dd_ok": 1.0, "trades_ok": 1.0, "symbol_ok": 1.0, "worst_symbol_regression": 0.0}
```

---

### Example B — REJECTED (Gate 1: Sharpe delta too small)

```
Mutation: SMA_CROSS(5,20) → SMA_CROSS(6,18) via param_delta

Parent EvaluationResult (strategy_id=12, gen=0):
  mean_sharpe:    0.71   (avg RELIANCE=0.82 wait... this was SMA_CROSS(5,20))
  Actually: TCS=0.71, RELIANCE=0.69
  mean_sharpe:    0.70
  mean_sortino:   0.53
  total_n_trades: 39
  max_drawdown:   Decimal("0.091")

Child EvaluationResult (strategy_id=15, gen=1):
  mean_sharpe:    0.70   (RELIANCE=0.74, TCS=0.66) → avg=0.70
  mean_sortino:   0.51
  total_n_trades: 35
  max_drawdown:   Decimal("0.096")

Gate checks:
  Gate 1 (Sharpe):  delta=0.70-0.70=0.00  >= 0.05  ✗  ← FAIL

Result: accepted=False
reasoning: "sharpe_delta=0.000<0.05"

composite_score:
  {"delta_sharpe": 0.0, "delta_sortino": -0.02, "dd_ratio": 1.055,
   "child_n_trades": 35.0, "sharpe_ok": 0.0, "sortino_ok": 0.0,
   "dd_ok": 1.0, "trades_ok": 1.0, "symbol_ok": 1.0, "worst_symbol_regression": 0.0}
```

---

### Example C — REJECTED (Gate 5: per-symbol regression)

```
Mutation: AND(SMA_10_25, RSI_14_30) via composition

This child has higher MEAN Sharpe than parent — Gates 1-4 all pass.
But one symbol degrades badly.

Parent EvaluationResult (strategy_id=11, gen=0):
  mean_sharpe:    0.70
  per_symbol_sharpe: {"RELIANCE": 0.82, "TCS": 0.58}

Child EvaluationResult (strategy_id=17, gen=1):
  mean_sharpe:    0.715  (avg RELIANCE=0.78, TCS=0.65)
  mean_sortino:   0.54
  total_n_trades: 22      ← AND combination reduces signal count
  max_drawdown:   Decimal("0.072")
  per_symbol_sharpe: {"RELIANCE": 0.16, "TCS": 1.27}

Gate checks:
  Gate 1 (Sharpe):    delta=0.715-0.70=0.015 >= 0.05  ✗  ← ALSO fails

Actually let me use a cleaner example where Gate 5 is the sole failure:

Parent: mean_sharpe=0.70, per_symbol_sharpe={"RELIANCE": 0.82, "TCS": 0.58}
Child:  mean_sharpe=0.77, per_symbol_sharpe={"RELIANCE": 0.18, "TCS": 1.36}
  mean across symbols: (0.18+1.36)/2 = 0.77

Gate 1:  delta=0.77-0.70=0.07  >= 0.05  ✓
Gate 2:  delta sortino passes  ✓
Gate 3:  drawdown passes        ✓
Gate 4:  n_trades=19 >= 5      ✓
Gate 5:
  RELIANCE: 0.18-0.82 = -0.64  < -0.50  ✗  ← FAIL
  TCS:      1.36-0.58 = +0.78  >= -0.50  ✓

Result: accepted=False
reasoning: "symbol_regression=RELIANCE:-0.640<-0.5"

Interpretation: The AND combination is too restrictive on RELIANCE — it only fires 3 times
in the year (insufficient RSI confirmation on RELIANCE's trending behavior). TCS benefits
because RSI dips more frequently there. The mean looks good but it's masking per-symbol
collapse. Gate 5 catches this.
```

---

### Where experiments rows go

After `ratchet_node` completes, the `experiments` table has 5 rows:

```sql
SELECT mutator, accepted, delta_sharpe, reasoning FROM experiments WHERE run_id='a3f9d2c1';

mutator       accepted  delta_sharpe  reasoning
param_delta   1         0.06          accepted
param_delta   0         0.00          sharpe_delta=0.000<0.05
param_delta   0         0.03          sharpe_delta=0.030<0.05
composition   0         0.07          symbol_regression=RELIANCE:-0.640<-0.5
composition   1         0.09          accepted
```

View these with: `uv run python main.py experiments --run a3f9d2c1`

---

*Tags for update-docs skill: trace, state, fanout, evolution, ratchet*
