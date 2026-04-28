# Top-level package — `src/atforge/`

## What lives here

`config.py` — settings, `cli.py` — CLI entry point. Everything else is in submodules.

## `config.py` — Settings

```python
from atforge.config import settings

settings.db_path        # Path to SQLite DB (default: data/atforge.db)
settings.cache_dir      # Path to parquet cache root (default: data/cache)
settings.google_api_key
settings.groq_api_key
settings.langfuse_public_key
settings.qdrant_url
```

Loaded from `.env` at repo root via pydantic-settings. Override with env vars:
```bash
ATFORGE_DB_PATH=/tmp/test.db uv run python main.py rank
```

`settings.ensure_dirs()` — creates `db_path.parent` and `cache_dir` if missing. Call at startup.

`REPO_ROOT = Path(__file__).resolve().parents[2]` — two levels up from `src/atforge/` = repo root. Used to resolve default paths regardless of working directory.

## `cli.py` — CLI

Three commands via typer:

```bash
uv run python main.py pipeline --symbols RELIANCE,TCS --lookback 1y
uv run python main.py rank --top 20 --run <run_id>
uv run python main.py inspect <run_id>
```

`pipeline` command flow:
1. Parse `--symbols` or load Nifty 50 universe
2. `init_db(settings.db_path)` — create tables if missing
3. Build `PipelineDeps` with `_build_default_provider()` and `_default_detectors()`
4. `build_pipeline(deps)` → `graph.invoke({run_id, universe, start_iso, end_iso})`
5. Print rich rankings table

`_build_default_provider()` tries each provider constructor in try/except — if openchart fails to init (NSE network issue), it's skipped and jugaad + yfinance still work.

`_default_detectors()` — 13 detectors: 10 CDL patterns + 2 SMA crossovers + 1 RSI reclaim.

`_apply_lookback(end, lookback)` — parses `"10y"`, `"6m"`, `"30d"` suffixes.

## `main.py`

```python
from atforge.cli import app
if __name__ == "__main__":
    app()
```

Entry point for `uv run python main.py`. The `pyproject.toml` also registers `atforge` as a script alias so `uv run atforge pipeline` works.

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

# Quick single-symbol test
uv run python main.py pipeline --symbols RELIANCE --lookback 6m
```
