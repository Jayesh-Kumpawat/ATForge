# Top-level package — `src/atforge/`

## What lives here

`config.py` — settings, `cli.py` — CLI entry point. Everything else is in submodules.

## `config.py` — Settings

```python
from atforge.config import settings

settings.db_path                # Path to SQLite DB (default: data/atforge.db)
settings.cache_dir              # Path to parquet cache root (default: data/cache)
settings.google_api_key         # Gemini API key
settings.groq_api_key           # Groq API key
settings.openrouter_api_key     # OpenRouter API key
settings.langfuse_public_key    # Langfuse Cloud public key
settings.langfuse_secret_key    # Langfuse Cloud secret key
settings.qdrant_url             # Qdrant Cloud URL
settings.llm_provider_priority  # default: "gemini,groq,openrouter"
settings.enable_ollama          # default: False
settings.ratchet_min_delta_sharpe   # default: 0.05
settings.ratchet_min_delta_sortino  # default: 0.02
settings.ratchet_max_dd_ratio       # default: 1.10
settings.ratchet_min_n_trades       # default: 5
```

Loaded from `.env` at repo root via pydantic-settings. Override with env vars:
```bash
ATFORGE_DB_PATH=/tmp/test.db uv run python main.py rank
```

`settings.ensure_dirs()` — creates `db_path.parent` and `cache_dir` if missing. Called at startup.

`REPO_ROOT = Path(__file__).resolve().parents[2]` — two levels up from `src/atforge/` = repo root. Used to resolve default paths regardless of working directory.

## `cli.py` — CLI

Commands via typer:

```bash
# Run the full pipeline (single or multi-generation evolution)
uv run python main.py pipeline \
  --symbols RELIANCE,TCS \       # or omit for full Nifty 50
  --lookback 1y \                # 10y, 6m, 30d — relative lookback
  --max-generations 3 \          # default 1 (no loop)
  --mutators param_delta,composition \   # default "param_delta,composition"
  --top-n-parents 5 \            # top strategies to mutate each gen
  --llm-priority gemini,groq,openrouter \  # provider chain
  --enable-ollama false \        # add Ollama as last-resort fallback
  --dry-run                      # run ratchet but skip experiments writes

# Show top-N rankings
uv run python main.py rank --top 20 --run <run_id>

# Inspect a run's backtest results
uv run python main.py inspect <run_id>

# Show experiment (ratchet) results for a run
uv run python main.py experiments --run <run_id>
```

`pipeline` command flow:
1. Parse `--symbols` or load Nifty 50 universe
2. `init_db(settings.db_path)` — creates tables + applies migrations
3. Build `PipelineDeps` with providers, detectors, mutators, ratchet thresholds from settings
4. `build_pipeline(deps)` → `graph.invoke({run_id, universe, start_iso, end_iso, max_generations})`
5. Print rich rankings table

`_build_default_provider()` tries each provider in try/except — if openchart fails (NSE network issue), jugaad + yfinance still work.

`_default_detectors()` — 13 detectors: 10 CDL patterns + 2 SMA crossovers + 1 RSI reclaim.

`_build_mutators(llm_router)` — builds `(ParamDeltaMutator, CompositionMutator)` from the configured LLM router. Router is built from `settings.llm_provider_priority` + API keys.

`_apply_lookback(end, lookback)` — parses `"10y"`, `"6m"`, `"30d"` suffixes.

## Submodules

| Module | Contents |
|---|---|
| `data/` | `DataProvider` Protocol, `OpenChartProvider`, `JugaadProvider`, `YFinanceProvider`, `CachedProvider`, `FallbackDataProvider` |
| `patterns/` | `PatternDetector` Protocol, `TalibCdlDetector`, `SmaCrossover`, `RsiOversoldReclaim`, `DoubleBottomDetector`, `AndDetector`, `OrDetector` |
| `backtest/` | `run_backtest()`, `BacktestResult` |
| `storage/` | `db.py` (connect, init_db, txn), `repo.py` (all repository functions), `migrate.py`, `schema.sql` |
| `graph/` | `PipelineState`, `PipelineDeps`, node factories, `build_pipeline()` |
| `evolution/` | `Mutator` Protocol, `ParamDeltaMutator`, `CompositionMutator`, `judge_mutation`, `build_evaluation_result`, `build_detector_from_config` |
| `llm/` | `LlmProvider` Protocol, `ProviderRegistry`, `complete_with_fallback`, provider implementations |

## Phase status

- **Phase 1** ✅ — data + patterns + backtest + storage + ranking (45 tests)
- **Phase 2a** ✅ — LLM wrapper + parallel backtest + evolution loop + mutators + ratchet (175 tests)
- **Phase 2b** deferred — OpenEvolve population, Qdrant dedup, per-symbol ratchet, bootstrap significance
- **Phase 3** deferred — HITL approval, paper trading, Kite broker integration

## Useful shortcuts

```bash
# Run tests
uv run pytest -q

# Lint + format
uv run ruff check --fix && uv run ruff format

# Browse DB
uvx datasette data/atforge.db

# Visualize pipeline results
uv run streamlit run dashboard.py

# Inspect a run
uv run python main.py inspect <run_id>

# Quick single-symbol single-gen test
uv run python main.py pipeline --symbols RELIANCE --lookback 6m

# Two-generation evolution test
uv run python main.py pipeline --symbols RELIANCE --lookback 1y --max-generations 2
```
