# ATForge — Agentic Trading Forge

> Automated self-improving multi-agent trading strategy research system for NSE Nifty 50 equities.
> Discovers, backtests, and evolves chart-pattern strategies using LLM-powered mutation — with human approval before any trade executes.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/orchestration-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![vectorbt](https://img.shields.io/badge/backtesting-vectorbt%200.28-green.svg)](https://github.com/polakowo/vectorbt)
[![SQLite WAL](https://img.shields.io/badge/storage-SQLite%20WAL-lightgrey.svg)](https://www.sqlite.org/)

---

## What it does

1. Downloads daily OHLCV data for all 50 Nifty 50 stocks (3 provider fallback chain)
2. Detects 13 chart patterns per symbol — 10 TA-Lib CDL patterns + SMA crossovers + RSI reclaim
3. Backtests every `(symbol × pattern)` combination with proper lookahead prevention
4. Stores ranked results in SQLite with full metrics (Sharpe, Sortino, CAGR, win rate)
5. *(Phase 2)* Uses LLMs to mutate strategy parameters overnight via OpenEvolve + AutoResearch ratchet
6. *(Phase 3)* Human approves each strategy before paper/live trade executes

**Phase 1 is complete:** 45 tests passing, full pipeline runs end-to-end, Streamlit dashboard live.

---

## Architecture

```
CLI (Typer)
    └── LangGraph Pipeline (5 nodes, linear in Phase 1)
            ├── load_universe   — Nifty 50 or --symbols arg
            ├── fetch_data      — CachedProvider → FallbackDataProvider → [openchart|jugaad|yfinance]
            ├── detect_patterns — 13 PatternDetectors (TA-Lib CDL, SMA cross, RSI reclaim)
            ├── run_backtest    — vectorbt 0.28, +1 bar shift (no lookahead), Decimal money
            └── rank            — top_rankings() from SQLite, rich table output

Storage: SQLite (WAL + JSON1 + FTS5) — 5 tables, indexed on sharpe DESC WHERE success=1
Dashboard: Streamlit 4-tab — Rankings | OHLCV+Signals | Run History | DB Stats
```

Full architecture with 6 Mermaid diagrams → [`ARCHITECTURE.md`](ARCHITECTURE.md)

---

## Key engineering decisions

| Decision | Why |
|---|---|
| **LangGraph** over plain Python | Phase 2 needs `Send()` fan-out (parallel backtests), HITL interrupts, LLM nodes — add without rewriting |
| **IDs only in state** | LangGraph checkpoints state; 50 OHLCV DataFrames × 5 nodes = 375 MB vs 60 bytes of parquet paths |
| **+1 bar signal shift** | vectorbt enters on signal-day close — impossible in live trading. Shift forces T+1 entry |
| **`Decimal` for money** | Float accumulates ₹100+ error over thousands of trades on a ₹10L portfolio |
| **SQLite over Postgres** | Zero infrastructure, WAL handles 10k+ writes/sec, `datasette` gives instant web UI |
| **Protocol pattern for providers** | Swap brokers without touching pipeline — add an `AngelOneProvider` with one `.fetch()` method |
| **Factory functions for nodes** | Nodes are pure functions over TypedDict state, testable by injecting a `SyntheticProvider` |

---

## Tech stack

| Layer | Tool | Notes |
|---|---|---|
| Orchestration | LangGraph 1.1.x | StateGraph, Phase 2: Send API fan-out |
| Backtesting | vectorbt 0.28.4 OSS | ~1M simulations/20s, frozen stable API |
| Pattern detection | TA-Lib 0.6.x + pandas-ta-classic | ARM64 wheels, 61 CDL patterns |
| Data — primary | openchart | NSE charting backend (not scraping) |
| Data — fallback 1 | jugaad-data | Bhavcopy CSV, history from 1995 |
| Data — fallback 2 | yfinance | Split/dividend-adjusted prices |
| Storage | SQLite + WAL + JSON1 + FTS5 | Concurrent reads during writes |
| Vector search | Qdrant Cloud (Phase 2) | Strategy embeddings, free tier |
| Runtime LLMs | Gemini 2.5 Flash + Groq + Ollama | 5,000+ free requests/day combined |
| Observability | Langfuse Cloud (Phase 2) | LLM call tracing, free Hobby tier |
| Evolution engine | OpenEvolve + AutoResearch ratchet (Phase 2) | AlphaEvolve-style population mutation |
| Dashboard | Streamlit | 4 tabs, Plotly candlestick charts |
| CLI | Typer | `pipeline`, `rank`, `inspect` commands |

---

## Quickstart

```bash
# Install (requires uv)
git clone https://github.com/Jayesh-Kumpawat/ATForge
cd ATForge
uv sync

# Copy and fill API keys (optional for Phase 1 — data providers are free)
cp .env.example .env

# Run pipeline — downloads data, detects patterns, backtests, prints rankings
uv run python main.py pipeline --symbols RELIANCE,TCS,INFY --lookback 1y

# Or full Nifty 50 (takes ~10-20 min on first run, cached on subsequent)
uv run python main.py pipeline --lookback 2y

# View rankings
uv run python main.py rank --top 20

# Dashboard
uv run streamlit run dashboard.py

# Browse raw DB
uvx datasette data/atforge.db
```

---

## Project structure

```
ATForge/
├── main.py                     Entry point
├── dashboard.py                Streamlit 4-tab dashboard
├── src/atforge/
│   ├── config.py               pydantic-settings, .env loading
│   ├── cli.py                  Typer CLI (pipeline, rank, inspect)
│   ├── data/                   DataProvider protocol + 3 providers + cache
│   ├── patterns/               PatternDetector protocol + 3 detector types
│   ├── backtest/               vectorbt engine, BacktestResult, Decimal money
│   ├── storage/                SQLite schema, repo functions, WAL config
│   ├── graph/                  LangGraph state, deps, nodes, pipeline
│   └── llm/                    LLM client scaffold (Phase 2 — NotImplementedError now)
├── tests/                      45 tests — E2E, unit, integration
├── ARCHITECTURE.md             6 Mermaid diagrams covering every component
└── CONTEXT.md                  Full vision, tool choices, phase plan
```

---

## Build phases

| Phase | Status | Scope |
|---|---|---|
| **1 — Foundation** | **Complete** | Data pipeline → pattern detection → backtesting → SQLite → dashboard |
| 2 — Evolution | Planned | LLM mutation loop, OpenEvolve, Qdrant RAG, parallel fan-out |
| 3 — HITL & Execution | Planned | Telegram approval, paper trading, Zerodha Kite broker |
| 4 — Scale | Planned | Multi-strategy portfolio, regime detection, Langfuse dashboards |

---

## Development

```bash
uv run pytest -q                          # run all 45 tests
uv run pytest tests/graph/test_pipeline.py  # single test file
uv run ruff check --fix && uv run ruff format  # lint + format
uv run python main.py inspect <run_id>    # inspect a specific run
```

---

## Constraints

- NSE Nifty 50 universe, daily EOD data only (Phase 1)
- All runtime LLMs are free — no paid API spend beyond Claude Pro for development
- Human approval required before any trade executes (Phase 3 gate)
- Python 3.12+, macOS Apple Silicon (M-series) primary dev environment
