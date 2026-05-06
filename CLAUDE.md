# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# ATForge — Agentic Trading Forge

Automated self-improving multi-agent trading strategy and research system for NSE Indian equities that discovers, evaluates, and refines chart-pattern-based strategies using LLM-powered evolution.

## Commands
```bash
uv run pytest                                      # all tests
uv run pytest tests/path/test_foo.py::test_name    # single test
uv run ruff check --fix && uv run ruff format      # lint + format
uv run python main.py                              # run app
uv add <package>                                   # add runtime dep
uv add --group dev <package>                       # add dev dep
```

### Pipeline CLI flags (Phase 2a)
```bash
# Basic run
uv run python main.py pipeline --symbols RELIANCE,TCS --lookback 1y

# Evolution run — 3 generations with param-delta mutations
uv run python main.py pipeline --symbols RELIANCE,TCS --lookback 1y \
  --max-generations 3 \
  --mutators param_delta,composition \
  --top-n-parents 5

# Dry-run — runs ratchet scoring but skips experiments table writes
uv run python main.py pipeline --symbols RELIANCE,TCS \
  --max-generations 2 --dry-run

# Inspect experiments from a run
uv run python main.py experiments --run <run_id>

# LLM provider control
uv run python main.py pipeline --symbols RELIANCE \
  --llm-priority gemini,groq,openrouter \
  --enable-ollama false
```

## Architecture

**Phase 2a pipeline** (fan-out loop via LangGraph Send API):
```
START → load_universe → fetch_data → detect_patterns
  → [Send×N] run_backtest_one   ← parallel per signal
  → rank → mutate_strategies → ratchet_node
  → loop_decision
      continue → advance_generation → detect_patterns  (loop)
      stop     → END
```

`max_generations=1` (default) = no loop, single-pass backtest identical to Phase 1.
`max_generations=N` = N generations of evolution with LLM-proposed mutations.

**Data sources** (priority order): openchart → jugaad-data → yfinance. nsepy/nsetools are dead.

**Pattern detection**: TA-Lib CDL* patterns + pandas-ta-classic (NOT pandas-ta — supply chain risk). Composition: `AndDetector(left, right)` / `OrDetector(left, right)` in `patterns/composition.py`. Structural patterns (cup-and-handle, H&S, double tops) deferred to Phase 2b.

**Backtesting**: vectorbt 0.28.4 OSS. Always `freq="1D"`, always shift signals +1 bar before passing to vectorbt. Return `success=False` on failure, never raise from worker nodes.

**Storage**: SQLite (WAL mode, JSON1, FTS5). `backtest_runs` and `pattern_signals` have `generation` column. `experiments` table records every ratchet verdict with `composite_score` JSON.

**LLM**: Gemini 2.5 Flash (primary, 1500 RPD free) + Groq (burst) + OpenRouter (diversity) + Ollama Qwen2.5-Coder 14B (unlimited fallback). ALL calls through `llm/router.py:complete_with_fallback` with Langfuse tracing. Claude Pro = pair-programmer only, cannot be used programmatically.

**Ratchet**: `judge_mutation(parent, child, thresholds)` — pure function. Accepts child if: `delta_sharpe ≥ 0.05 ∧ delta_sortino ≥ 0.02 ∧ child_dd ≤ parent_dd × 1.10 ∧ child_n_trades ≥ 5`. Verdict stored as JSON in `experiments.composite_score`.

**Observability**: Langfuse Cloud (Hobby tier, free). Langfuse 4.x API — use `from langfuse import get_client` NOT the v2 `Langfuse(public_key=...)` constructor.

## Submodule map

| Module | CLAUDE.md | What it does |
|---|---|---|
| `data/` | `data/CLAUDE.md` | OHLCV fetching, caching, provider fallback |
| `patterns/` | `patterns/CLAUDE.md` | Pattern detectors incl. composition |
| `backtest/` | `backtest/CLAUDE.md` | vectorbt wrapper, BacktestResult |
| `storage/` | `storage/CLAUDE.md` | SQLite schema, repo functions |
| `graph/` | `graph/CLAUDE.md` | LangGraph pipeline, state, deps, nodes |
| `evolution/` | `evolution/CLAUDE.md` | Mutators, ratchet, detector registry |
| `llm/` | `llm/CLAUDE.md` | Provider registry, router, tracing |

## Hard rules — violating these causes real bugs
- NEVER commit `.env` or files containing API keys
- NEVER use `float` for financial values — use `decimal.Decimal`
- NEVER put large data (DataFrames, OHLCV arrays, Portfolio objects) in LangGraph state — IDs/paths only
- ALL LLM calls must go through `llm/router.py:complete_with_fallback` with Langfuse tracing
- Shift entry signals by 1 bar in vectorbt backtests — no lookahead guard built in
- On backtest failure, return `success=False` — never raise from worker nodes
- `params_json` in `strategies` table must use `json.dumps(..., sort_keys=True)` — UNIQUE dedup depends on stable key ordering
- `detector_configs` in state is last-writer-wins (NOT a reducer). `mutations` IS a reducer (`operator.add`)

## Phase status
- **Phase 1** ✅ complete — data + patterns + backtest + storage + ranking
- **Phase 2a** ✅ complete — LLM wrapper + parallel backtest + mutators + ratchet + evolution loop (234 tests)
- **A1** ✅ complete — ReAct research agent, tool calling (all 5 providers), ResearchAgentMutator
- **Phase 2b** deferred — OpenEvolve population dynamics, Qdrant similarity dedup, per-symbol ratchet, bootstrap significance
- **Phase 3** deferred — HITL Telegram approval, paper trading, Kite broker integration

See @CONTEXT.md for full project context, vision, and phase plan.
