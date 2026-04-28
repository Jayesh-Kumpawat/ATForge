# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# ATForge — Agentic Trading Forge

Automated self-improving multi-agent trading strategy and research system for NSE Indian equities that discovers, evaluates, and refines chart-pattern-based strategies using LLM-powered evolution.

## Commands
```bash
uv run pytest                              # all tests
uv run pytest tests/path/test_foo.py::test_name  # single test
uv run ruff check --fix && uv run ruff format    # lint + format
uv run python main.py                      # run app
uv add <package>                           # add runtime dep
uv add --group dev <package>               # add dev dep
```

## Architecture
Pipeline: `Data` → `Pattern Detection` → `Backtest` → `Storage` → `LLM Evolution` → `Rankings`

Orchestrated by **LangGraph** (linear graph in Phase 1, fan-out via Send API in Phase 2). Each node is a pure function over `TypedDict` state — never put DataFrames/arrays in state, store IDs only.

**Data sources** (in priority order): openchart → jugaad-data → yfinance. nsepy/nsetools are dead, do not use.

**Pattern detection**: TA-Lib CDL* patterns + pandas-ta-classic (NOT pandas-ta — supply chain risk). Structural patterns (cup-and-handle, H&S, double tops) via scipy.signal + custom ~200 LOC.

**Backtesting**: vectorbt 0.28.4 OSS. Always `freq="1D"`, always shift signals +1 bar before passing to vectorbt (no lookahead guard built in). Return `success=False` on failure, never raise from worker nodes.

**Storage**: SQLite (WAL mode, JSON1, FTS5) for backtest results + experiment history. Qdrant Cloud (free tier) for strategy embeddings / similarity search.

**Runtime LLMs**: Gemini 2.5 Flash (primary, 1500 RPD free) + Groq (burst) + OpenRouter (diversity) + local Ollama Qwen2.5-Coder 14B (unlimited fallback). ALL calls go through centralized wrapper for Langfuse tracing. Claude Pro is the pair-programmer only — cannot be used programmatically (blocked April 4, 2026).

**Evolutionary search**: OpenEvolve (AlphaEvolve replica) + Karpathy AutoResearch ratchet (try → measure → commit/revert).

**Observability**: Langfuse Cloud (Hobby tier, free).

## Hard rules — violating these causes real bugs
- NEVER commit .env or files containing API keys
- NEVER use float for financial values — use `decimal.Decimal`
- NEVER put large data (DataFrames, OHLCV arrays, Portfolio objects) in LangGraph state — use IDs/references
- ALL LLM calls must go through centralized Langfuse wrapper
- Shift entry signals by 1 bar in vectorbt backtests — no lookahead guard
- On backtest failure, return `success=False` — never raise from worker nodes

See @CONTEXT.md for full project context, vision, tool choices, and phase plan.
