# Top-level package — `src/atforge/`

## What lives here

`config.py` — all settings. `cli.py` — CLI entry point (Typer). Everything else in submodules.

## Phase status

| Phase | Status | Notes |
|---|---|---|
| **Phase 1 — Foundation** | ✅ Complete | Data + patterns + backtest + storage + ranking |
| **Phase 2a — Evolution Loop** | ✅ Complete | LLM wrapper + parallel backtest + mutators + ratchet (175 tests) |
| Phase 2b — Evolution Depth | 🔄 Deferred | OpenEvolve population, Qdrant dedup, bootstrap significance |
| Phase 3 — HITL & Execution | 🔄 Deferred | Telegram approval, paper trading, Kite broker |

---

## `config.py` — Settings

Loaded from `.env` at repo root via pydantic-settings. All fields can be overridden with env vars.

```python
from atforge.config import settings

# Paths
settings.db_path          # Path to SQLite DB (default: data/atforge.db)
settings.cache_dir        # Path to parquet cache root (default: data/cache)

# LLM providers (set API keys in .env)
settings.google_api_key       # Gemini 2.5 Flash (primary)
settings.groq_api_key         # Groq (burst fallback)
settings.openrouter_api_key   # OpenRouter (diversity fallback)
settings.ollama_base_url      # Local Ollama (default: http://localhost:11434)
settings.enable_ollama        # bool, default False — Ollama is heavy, opt-in
settings.llm_default_model    # default: "gemini-2.5-flash"
settings.llm_provider_priority  # list[str], default: ["gemini", "groq", "openrouter"]

# Observability
settings.langfuse_public_key  # Langfuse Cloud
settings.langfuse_secret_key
settings.langfuse_host        # default: https://cloud.langfuse.com

# Vector search (Phase 2b)
settings.qdrant_url
settings.qdrant_api_key

# Ratchet thresholds — all overrideable via env (e.g. RATCHET_MIN_DELTA_SHARPE=0.1)
settings.ratchet_min_delta_sharpe     # default: 0.05
settings.ratchet_min_delta_sortino    # default: 0.02
settings.ratchet_max_drawdown_tol     # default: 0.10 (child_dd ≤ parent_dd × 1.10)
settings.ratchet_min_n_trades         # default: 5
settings.ratchet_max_symbol_regression  # default: 0.5 (max per-symbol Sharpe drop)
```

Override example:
```bash
RATCHET_MIN_DELTA_SHARPE=0.10 uv run python main.py pipeline --symbols RELIANCE --lookback 1y
ATFORGE_DB_PATH=/tmp/test.db uv run python main.py rank
```

`settings.ensure_dirs()` — creates `db_path.parent` and `cache_dir`. Called at startup.

---

## `cli.py` — CLI (Typer)

```
Commands:
  pipeline     Run the full Phase 2a pipeline (single-pass or multi-generation evolution)
  experiments  Show ratchet verdicts for a run (accepted/rejected mutations + reasons)
  rank         Show top-N backtest rankings from the DB
  inspect      Print run metadata + failure summary for a given run_id
```

### `pipeline` command — full option reference

```bash
uv run python main.py pipeline \
  --symbols RELIANCE,TCS \        # comma-separated; omit for full Nifty50
  --lookback 1y \                 # 10y / 6m / 30d — relative from today
  --universe nifty50 \            # alternative to --symbols
  --max-generations 3 \           # default 1 (no evolution loop)
  --mutators param_delta,composition \  # default "param_delta,composition"
  --top-n-parents 5 \             # top strategies to mutate each generation
  --llm-priority gemini,groq,openrouter \  # provider fallback chain
  --enable-ollama false \         # add Ollama as last-resort fallback
  --dry-run                       # ratchet runs but skips experiments table writes
```

### `pipeline` flow

```
1. Parse --symbols or load Nifty50
2. init_db(settings.db_path) — create tables, apply migrations
3. Build RatchetThresholds from settings (all thresholds config-driven)
4. Build PipelineDeps (providers, detectors, mutators, ratchet)
5. build_pipeline(deps) → graph
6. graph.invoke({run_id, universe, start_iso, end_iso, max_generations})
7. Print rich rankings table
```

### Key helper functions

| Function | What it builds |
|---|---|
| `_build_default_provider()` | `CachedProvider(FallbackDataProvider([openchart, jugaad, yfinance]))` |
| `_default_detectors()` | 13 detectors: 10 CDL + 2 SMA crossovers + 1 RSI reclaim |
| `_build_mutators(names, priority, enable_ollama)` | `[ParamDeltaMutator, CompositionMutator]` from LLM router |
| `_apply_lookback(end, lookback)` | Parses `"10y"`, `"6m"`, `"30d"` → `date` |

### Ratchet wiring

```python
# cli.py wires config into RatchetThresholds — all values config-driven, no hardcodes
ratchet_thresholds=RatchetThresholds(
    min_delta_sharpe=settings.ratchet_min_delta_sharpe,
    min_delta_sortino=settings.ratchet_min_delta_sortino,
    max_drawdown_tol=settings.ratchet_max_drawdown_tol,
    min_n_trades=settings.ratchet_min_n_trades,
    max_symbol_regression=settings.ratchet_max_symbol_regression,
)
```

---

## Submodule map

| Module | CLAUDE.md | What it does |
|---|---|---|
| `data/` | `data/CLAUDE.md` | OHLCV fetching, caching, 3-provider fallback |
| `patterns/` | `patterns/CLAUDE.md` | PatternDetector protocol + detectors + composition |
| `backtest/` | `backtest/CLAUDE.md` | vectorbt wrapper, BacktestResult, Decimal money |
| `storage/` | `storage/CLAUDE.md` | SQLite schema, repo functions, migrations |
| `graph/` | `graph/CLAUDE.md` | LangGraph pipeline, state, deps, nodes |
| `evolution/` | `evolution/CLAUDE.md` | Mutators, ratchet (incl. per-symbol), registry |
| `llm/` | `llm/CLAUDE.md` | Provider registry, router, Langfuse tracing |

## Useful shortcuts

```bash
uv run pytest -q                          # all 183 tests
uv run ruff check --fix && uv run ruff format
uvx datasette data/atforge.db             # browse DB in browser
uv run streamlit run dashboard.py         # 5-tab dashboard
uv run python main.py pipeline --symbols RELIANCE --lookback 6m
uv run python main.py pipeline --symbols RELIANCE --lookback 1y --max-generations 2
uv run python main.py experiments --run <run_id>
```
