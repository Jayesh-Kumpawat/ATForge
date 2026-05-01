# Evolution Submodule — `src/atforge/evolution/`

## What this module does

Drives the self-improvement loop: proposes mutations to strategies, scores their backtests against parents via a ratchet, and records verdicts. No LLM calls happen directly in this module — all LLM I/O is done via `llm/router.py` callables injected at construction time.

## `types.py` — shared type definitions

Key types used across the submodule:

```python
DetectorConfig = dict[str, Any]   # {"type": "sma_crossover", "fast": 5, "slow": 20}
                                   # nested for composition: {"type": "and", "left": ..., "right": ...}

StrategyRow = TypedDict(...)       # DB row from get_top_strategies_for_generation()
                                   # keys: strategy_id, name, family, params_json,
                                   #       mean_sharpe, mean_sortino, total_n_trades,
                                   #       max_drawdown, generation

ProposedMutation = dataclass(...)  # output from Mutator.propose()
                                   # keys: parent_strategy_id, child_config, mutator, reasoning

EvaluationResult = dataclass(...)  # aggregated backtest metrics per strategy+run+generation
                                   # keys: strategy_id, run_id, generation, mean_sharpe,
                                   #       mean_sortino, total_n_trades, max_drawdown, n_symbols

RatchetThresholds = dataclass(...)  # defaults: min_delta_sharpe=0.05, min_delta_sortino=0.02,
                                    #           max_dd_ratio=1.10, min_n_trades=5

RatchetVerdict = dataclass(...)     # accepted: bool, delta_sharpe, delta_sortino, dd_ratio,
                                    # reasoning: str, composite_score: dict

Mutator = Protocol  # propose(parents: list[StrategyRow], k: int) -> list[ProposedMutation]
```

## `registry.py` — DetectorConfig round-trip

Converts between live `PatternDetector` objects and serializable `DetectorConfig` dicts.

```python
from atforge.evolution.registry import build_detector_from_config, detector_params_json

# dict → detector (used in detect_patterns node)
cfg = {"type": "sma_crossover", "fast": 10, "slow": 25}
det = build_detector_from_config(cfg)   # SmaCrossover(fast=10, slow=25)

# detector → params_json (used in upsert_strategy)
json_str = detector_params_json(SmaCrossover(5, 20))
# '{"fast": 5, "slow": 20, "type": "sma_crossover"}'  ← sort_keys=True always
```

**Why `sort_keys=True` matters**: `upsert_strategy` has a `UNIQUE (name, params_json)` constraint. Key ordering must be deterministic or the same strategy registers as two separate rows. Every `json.dumps` on a DetectorConfig must use `sort_keys=True`.

Supported types: `sma_crossover` → `SmaCrossover`, `rsi_oversold` → `RsiOversoldReclaim`, `talib_cdl` → `TalibCdlDetector`, `and` → `AndDetector`, `or` → `OrDetector`. Composition configs are recursive.

## `ratchet.py` — DB aggregation + pure scoring

Two functions, intentionally separated:

```python
# Aggregates DB rows — has I/O (reads backtest_runs)
build_evaluation_result(
    conn, strategy_id: int, run_id: str, generation: int
) -> EvaluationResult | None

# Pure function — no I/O
judge_mutation(
    parent: EvaluationResult,
    child: EvaluationResult,
    thresholds: RatchetThresholds
) -> RatchetVerdict
```

`build_evaluation_result` AVG(sharpe), AVG(sortino), SUM(n_trades), MAX(max_drawdown) across all symbols for a given strategy+run+generation. Returns `None` if no rows found (used to skip orphaned mutations).

`judge_mutation` acceptance criterion:
1. `child.mean_sharpe - parent.mean_sharpe >= thresholds.min_delta_sharpe` (default 0.05)
2. `child.mean_sortino - parent.mean_sortino >= thresholds.min_delta_sortino` (default 0.02)
3. `child.max_drawdown / parent.max_drawdown <= thresholds.max_dd_ratio` (default 1.10) — if parent dd=0, dd_ratio=1.0
4. `child.total_n_trades >= thresholds.min_n_trades` (default 5)

All four must pass. `composite_score` dict keys: `delta_sharpe`, `delta_sortino`, `dd_ratio`, `child_n_trades`.

## `prompts.py` — LLM response schemas

Pydantic models for LLM JSON responses:

```python
class SmaParamsDelta(BaseModel):
    fast: int    # >= 2
    slow: int    # >= fast + 1  ← validator enforced
    reasoning: str

class RsiParamsDelta(BaseModel):
    period: int   # >= 2
    oversold: int # 1-49
    reasoning: str

class CompositionChoice(BaseModel):
    op: Literal["AND", "OR"]
    reasoning: str
```

`SmaParamsDelta` has a Pydantic field validator that rejects `fast >= slow` — this prevents a common LLM mistake from propagating into the DB.

## `mutators/param_delta.py` — ParamDeltaMutator

Handles SMA crossover and RSI oversold families only. CDL and composite configs are silently skipped (no handler registered).

```python
ParamDeltaMutator(llm_router: Callable[[LlmRequest], LlmResponse])
```

LLM robustness — two fallback layers for malformed responses:
1. Markdown fence stripping: removes ` ```json ` / ` ``` ` wrappers
2. Brace-match extraction: finds the outermost `{...}` if LLM adds preamble text

If both fail, the mutation is silently dropped (no exception, no partial data).

`propose(parents, k)` returns at most `k` mutations, one per parent (iterates parents in order).

## `mutators/composition.py` — CompositionMutator

Combines top-2 parents with AND or OR logic. LLM picks the operator.

```python
CompositionMutator(
    llm_router: Callable[[LlmRequest], LlmResponse],
    max_nesting_depth: int = 2  # guard against exponential signal explosion
)
```

`_nesting_depth(cfg)` returns 0 for leaf configs, N for N levels of AND/OR nesting. Any parent at `max_nesting_depth` is skipped — it can't be nested further.

Child config format: `{"type": "and", "left": <parent_cfg>, "right": <other_cfg>}`. Parent strategy ID = the parent with higher `mean_sharpe`.

## Tests

```
tests/evolution/test_registry_roundtrip.py   — parametrized round-trips, stable params_json
tests/evolution/test_param_delta.py          — happy paths, validation, fence-strip, brace-match
tests/evolution/test_composition_mutator.py  — AND/OR paths, depth guard, malformed response
tests/evolution/test_ratchet.py              — acceptance/rejection by each criterion, DB aggregation
```
