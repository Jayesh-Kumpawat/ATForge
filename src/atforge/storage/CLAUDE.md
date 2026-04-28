# Storage Layer — `src/atforge/storage/`

## What this module does

Persists all pipeline results to SQLite. Single source of truth for runs, strategies, pattern signals, backtest results, and (Phase 2) experiment history.

## Database setup

SQLite with:
- **WAL mode** — allows concurrent reads during writes (important for dashboard + pipeline running together)
- **JSON1** — query strategy `params_json` fields in SQL
- **FTS5** — full-text search over strategy names/descriptions/reasoning

Configured via PRAGMAs in `db.py::_configure_connection`:
```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA synchronous=NORMAL;
```

## Schema (`schema.sql`)

```
runs                  — one row per pipeline invocation (run_id, status, timestamps)
strategies            — deduped by (name, params_json) — same strategy across runs = 1 row
pattern_signals       — one row per (run, strategy, symbol) — signal metadata only
backtest_runs         — one row per backtest result — money as TEXT, ratios as REAL
experiments           — Phase 2 LLM mutation log (scaffolded, not used)
strategy_search       — FTS5 virtual table over strategy names/descriptions
```

**Money columns** (`total_return`, `final_value`, `max_drawdown`, `init_cash`): stored as `TEXT` holding `str(Decimal)`. Round-trip: `Decimal(row["total_return"])`. Never use REAL for money.

**Ratio columns** (`sharpe`, `sortino`, `cagr`, `win_rate`): stored as `REAL` (float). Purely analytical, not financial values.

Index on `backtest_runs(sharpe DESC) WHERE success = 1` — makes `top_rankings` query fast even at 10k+ rows.

Foreign keys with `ON DELETE CASCADE` — deleting a run cleans up all its signals and backtests.

## Connection (`db.py`)

```python
# Preferred pattern — explicit transaction boundary
with connect(db_path) as conn:
    with txn(conn):
        insert_run(conn, run_id)
        upsert_strategy(conn, ...)

# init_db: idempotent, creates all tables if missing
init_db(db_path)  # call once at startup
```

`connect()` uses `isolation_level=None` (autocommit). Transactions are explicit via `txn()` context manager which does `BEGIN / COMMIT / ROLLBACK`.

`conn.row_factory = sqlite3.Row` — rows are dict-like, access by column name.

## Repository (`repo.py`)

| Function | What it does |
|---|---|
| `insert_run(conn, run_id)` | Create run with status='running' |
| `finish_run(conn, run_id, status, notes)` | Update status + finished_at |
| `upsert_strategy(conn, name, family, params, ...)` | Insert or return existing strategy_id |
| `insert_pattern_signal(conn, ...)` | Record signal metadata |
| `insert_backtest_result(conn, ...)` | Write BacktestResult to DB |
| `top_rankings(conn, limit, run_id)` | SELECT top-N by Sharpe, success=1 only |

`upsert_strategy` deduplicates by `(name, params_json)`. Same CDL pattern across 50 symbols = 1 strategy row, many backtest_runs rows.

`_dec_to_text(x)` converts `Decimal | None → str | None` for TEXT columns.

## Key invariants

- **All money = TEXT** — `str(Decimal)` in, `Decimal(row_value)` out. No implicit float conversion.
- **Use `txn()` for writes** — never rely on autocommit.
- **`init_db` is idempotent** — safe to call every startup; uses `CREATE TABLE IF NOT EXISTS`.
- **FTS5 `strategy_search`** — content='', so you must manually insert into it when adding strategies with reasoning (Phase 2). Phase 1 leaves it empty.

## Querying the DB directly

```bash
uvx datasette data/atforge.db          # web UI
sqlite3 data/atforge.db               # raw SQL

# Useful queries
SELECT COUNT(*) FROM backtest_runs WHERE success=1;
SELECT symbol, name, sharpe FROM backtest_runs b JOIN strategies s USING(strategy_id)
  WHERE success=1 ORDER BY sharpe DESC LIMIT 10;
```

## Tests

```
tests/storage/test_repo.py  — init_db idempotent, WAL mode, upsert dedup, insert/fetch round-trip,
                               failure rows excluded from rankings, cascade delete
```
