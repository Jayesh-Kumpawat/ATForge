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

**Phase 2a is complete:** 185 tests passing, full evolution loop runs end-to-end — LLM mutation, parallel backtests via `Send()` fan-out, AutoResearch ratchet, multi-generation cycling.

---

## Architecture

```
CLI (Typer)
    └── LangGraph Pipeline (Phase 2a — evolution loop)
            ├── load_universe       — Nifty 50 or --symbols arg
            ├── fetch_data          — CachedProvider → FallbackDataProvider → [openchart|jugaad|yfinance]
            ├── detect_patterns     — 13 PatternDetectors (TA-Lib CDL, SMA cross, RSI reclaim)
            ├── [Send×N] run_backtest_one  — parallel per signal via LangGraph Send API
            ├── rank                — top_rankings() from SQLite, rich table output
            ├── mutate_strategies   — LLM proposes param_delta / composition mutations
            ├── ratchet_node        — judge_mutation(): accept if Δsharpe≥0.05 ∧ Δsortino≥0.02
            └── loop_decision ──────→ "continue" → advance_generation → detect_patterns (loop)
                                    → "stop"    → END

Storage: SQLite (WAL + JSON1 + FTS5) — 5 tables + experiments table (ratchet verdicts)
LLMs:    Gemini 2.5 Flash (primary) → Groq (burst) → OpenRouter → Ollama Qwen2.5-Coder (fallback)
Traces:  Langfuse Cloud — every LLM call traced with prompt, response, provider, latency
Dashboard: Streamlit 5-tab — Rankings | OHLCV+Signals | Run History | DB Stats | Evolution
```

Full architecture with Mermaid diagrams → [`ARCHITECTURE.md`](ARCHITECTURE.md)

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
| Vector search | Qdrant Cloud (Phase 2b) | Strategy embeddings, similarity dedup |
| Runtime LLMs | Gemini 2.5 Flash + Groq + OpenRouter + Ollama | 5,000+ free requests/day, provider fallback chain |
| Observability | Langfuse Cloud | LLM call tracing, every prompt/response logged |
| Evolution engine | AutoResearch ratchet (Phase 2a) | Δsharpe/Δsortino/drawdown acceptance criterion |
| Dashboard | Streamlit | 5 tabs, Plotly candlestick charts + evolution charts |
| CLI | Typer | `pipeline`, `rank`, `inspect` commands |

---

## Quickstart

```bash
# Install (requires uv)
git clone https://github.com/Jayesh-Kumpawat/ATForge
cd ATForge
uv sync

# Copy and fill API keys (Gemini/Groq for LLM evolution; data providers are free)
cp .env.example .env

# Single-pass run — baseline, no evolution (identical to Phase 1)
uv run python main.py pipeline --symbols RELIANCE,TCS,INFY --lookback 1y

# Evolution run — 3 LLM-driven generations, param_delta + composition mutators
uv run python main.py pipeline --symbols RELIANCE,TCS --lookback 1y \
  --max-generations 3 \
  --mutators param_delta,composition \
  --top-n-parents 5

# Inspect what the ratchet accepted/rejected (use run_id printed above)
uv run python main.py experiments --run <run_id>

# View rankings across all runs
uv run python main.py rank --top 20

# Dashboard (Rankings | OHLCV+Signals | Run History | DB Stats | Evolution)
uv run streamlit run dashboard.py

# Browse raw DB — all tables, full experiment log
uvx datasette data/atforge.db
```

---

## Project structure

```
ATForge/
├── main.py                     Entry point
├── dashboard.py                Streamlit 5-tab dashboard
├── src/atforge/
│   ├── config.py               pydantic-settings, .env loading
│   ├── cli.py                  Typer CLI (pipeline, rank, inspect)
│   ├── data/                   DataProvider protocol + 3 providers + cache
│   ├── patterns/               PatternDetector protocol + 3 detector types
│   ├── backtest/               vectorbt engine, BacktestResult, Decimal money
│   ├── storage/                SQLite schema, repo functions, WAL config
│   ├── graph/                  LangGraph state, deps, nodes (Phase 1), nodes_phase2 (evolution loop)
│   ├── llm/                    Provider registry, router, Langfuse tracing
│   └── evolution/              Mutators (param_delta, composition), ratchet, detector registry
├── tests/                      182 tests — E2E, unit, integration
├── ARCHITECTURE.md             6 Mermaid diagrams covering every component
└── CONTEXT.md                  Full vision, tool choices, phase plan
```

---

## Build phases

| Phase | Status | Scope |
|---|---|---|
| **1 — Foundation** | **Complete** | Data pipeline → pattern detection → backtesting → SQLite → dashboard |
| **2a — Evolution Loop** | **Complete** | LLM mutation, `Send()` parallel backtests, AutoResearch ratchet, multi-generation cycling |
| 2b — Evolution Depth | Deferred | OpenEvolve population dynamics, Qdrant similarity dedup, per-symbol ratchet, bootstrap significance |
| 3 — HITL & Execution | Deferred | Telegram approval, paper trading, Zerodha Kite broker |
| 4 — Scale | Deferred | Multi-strategy portfolio, regime detection, Langfuse dashboards |

---

## Dashboard tabs

| Tab | What it shows |
|-----|--------------|
| **🏆 Rankings** | Top backtests across all runs — symbol, strategy, gen, Sharpe, CAGR, max drawdown, win rate |
| **📊 OHLCV + Signals** | Candlestick chart for any symbol/run with pattern signal bars highlighted in orange |
| **🔄 Run History** | All pipeline runs — status, duration, backtest counts, failures |
| **🗄️ DB Stats** | Row counts per table, strategy families breakdown |
| **🧬 Evolution** | Sharpe-by-generation bar chart, accept/reject pie, full mutations table with Δsharpe and ratchet reasoning |

---

## Testing & verification

### 1 — Automated test suite
```bash
uv run pytest -q
# Expect: 182 passed
```

### 2 — Run a 2-generation evolution (end-to-end smoke test)
```bash
uv run python main.py pipeline \
  --symbols RELIANCE,TCS \
  --lookback 6m \
  --max-generations 2 \
  --mutators param_delta,composition \
  --top-n-parents 3
# Note the run_id printed at start (e.g. "run abc123def456")
```

### 3 — Verify CLI outputs
```bash
uv run python main.py rank --top 20         # gen column appears next to symbol
uv run python main.py experiments --run <run_id>  # ratchet verdicts: ✓ accepted / ✗ rejected
uv run python main.py inspect <run_id>      # run metadata + failure count
```

### 4 — Dashboard verification
```bash
uv run streamlit run dashboard.py
```
- **Rankings tab**: "gen" column visible (gen=0 = baseline, gen≥1 = evolved)
- **OHLCV tab**: candlestick loads, orange signal overlays appear on signal days
- **Evolution tab**: select the run from step 2 → Sharpe bar chart shows gen 0 and gen 1, pie shows accepted/rejected count, mutations table shows full ratchet reasoning
- **Edge case**: select a single-pass run (no `--max-generations`) → "No evolution data" message appears

### 5 — Browse raw DB
```bash
uvx datasette data/atforge.db
# All 5 tables browsable in browser: runs, strategies, pattern_signals, backtest_runs, experiments
```

---

## Development

```bash
uv run pytest -q                                   # run all 182 tests
uv run pytest tests/graph/test_pipeline.py         # single test file
uv run ruff check --fix && uv run ruff format      # lint + format
uv run python main.py inspect <run_id>             # run metadata + failure summary
uv run python main.py experiments --run <run_id>   # ratchet verdicts for a run
```

---

## Constraints

- NSE Nifty 50 universe, daily EOD data only (Phase 1)
- All runtime LLMs are free — no paid API spend beyond Claude Pro for development
- Human approval required before any trade executes (Phase 3 gate)
- Python 3.12+, macOS Apple Silicon (M-series) primary dev environment
