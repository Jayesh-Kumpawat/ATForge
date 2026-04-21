# ATForge — Agentic Trading Forge

Automated trading research system for NSE Indian equities that discovers, evaluates, and refines chart-pattern-based strategies using LLM-powered evolution.

## Language and tooling
- Python 3.12 only
- Always use `uv run` to execute Python. Never bare `python` or `pip`.
- Add deps: `uv add <package>`. Dev deps: `uv add --group dev <package>`.
- Tests: `uv run pytest`
- Lint: `uv run ruff check --fix && uv run ruff format`

## Hard rules — violating these causes real bugs
- NEVER commit .env or files containing API keys
- NEVER use float for financial values — use decimal.Decimal
- NEVER put large data (DataFrames, OHLCV arrays, Portfolio objects) in LangGraph state — use references/IDs
- ALL LLM calls must go through a centralized wrapper for Langfuse tracing
- Shift entry signals by 1 bar in backtests — vectorbt has no lookahead guard
- On backtest failure, return result with success=False — never raise from worker nodes
ture reference
See @CONTEXT.md for full project context, vision, tool choices, and phase plan.
