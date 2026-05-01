# Storage Layer — `src/atforge/storage/`

## What this module does

Persists all pipeline results to SQLite. Single source of truth for runs, strategies, pattern signals, backtest results, and experiment history (ratchet verdicts).

## Database setup

SQLite with:
- **WAL mode** — allows concurrent reads during writes (dashboard + pipeline running together)
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
pattern_signals       — one row per (run, strategy, symbol, generation)
backtest_runs         — one row per backtest result — money as TEXT, ratios as REAL
experiments           — ratchet verdict log: accepted, delta_sharpe, composite_score JSON
strategy_search       — FTS5 virtual table over strategy names/descriptions
```

**`pattern_signals` and `backtest_runs` both have a `generation INTEGER NOT NULL DEFAULT 0` column.** This enables generation-scoped queries for the ratchet.

**`experiments` columns** (fully active in Phase 2a):
- `run_id` — which pipeline run
- `generation` — the child's generation (ratchet fires on gen N, comparing gen N child to gen N-1 parent)
- `parent_strategy_id` / `child_strategy_id` — FK to strategies
- `mutator` — which mutator proposed this child (`"param_delta"` / `"composition"`)
- `mutation_json` — the full child DetectorConfig as JSON
- `accepted` — 0 or 1 (set by ratchet)
- `delta_sharpe` — child.mean_sharpe - parent.mean_sharpe
- `composite_score` — JSON blob with all four ratchet component scores
- `reasoning` — human-readable verdict string from judge_mutation

**Money columns** (`total_return`, `final_value`, `max_drawdown`, `init_cash`): stored as `TEXT` holding `str(Decimal)`. Round-trip: `Decimal(row["total_return"])`. Never use REAL for money.

**Ratio columns** (`sharpe`, `sortino`, `cagr`, `win_rate`): stored as `REAL`. Analytical, not financial.

## Migrations (`migrate.py`)

`apply_migrations(conn)` is called automatically by `init_db`. Uses `PRAGMA user_version` as the version counter.

- `user_version=0` → fresh DB, `schema.sql` applied directly, user_version set to 2
- `user_version=1` → Phase 1 schema, `0002_phase2a.sql` applied to add generation columns + experiments columns
- `user_version=2` → Phase 2a schema, no-op

Migration SQL (`migrations/0002_phase2a.sql`) guards each `ALTER TABLE` with a `PRAGMA table_info` column-exists check — safe to run on an already-migrated DB.

## Connection (`db.py`)

```python
# Preferred pattern — explicit transaction boundary
with connect(db_path) as conn:
    with txn(conn):
        insert_run(conn, run_id)
        upsert_strategy(conn, ...)

# init_db: idempotent, creates tables + runs migrations
init_db(db_path)  # call once at startup
```

`connect()` uses `isolation_level=None` (autocommit). Transactions are explicit via `txn()` context manager: `BEGIN / COMMIT / ROLLBACK`.

`conn.row_factory = sqlite3.Row` — rows are dict-like, access by column name.

## Repository (`repo.py`)

| Function | Signature | What it does |
|---|---|---|
| `insert_run` | `(conn, run_id)` | Create run with status='running' |
| `finish_run` | `(conn, run_id, status, notes)` | Update status + finished_at |
| `upsert_strategy` | `(conn, name, family, params, ...)` | Insert or return existing strategy_id |
| `insert_pattern_signal` | `(conn, ..., generation=0)` | Record signal metadata with generation |
| `insert_backtest_result` | `(conn, ..., generation=0)` | Write BacktestResult to DB with generation |
| `insert_experiment` | `(conn, run_id, generation, parent_strategy_id, child_strategy_id, ...)` | Write ratchet verdict |
| `get_top_strategies_for_generation` | `(conn, run_id, generation, limit)` | Top-N by Sharpe for given generation |
| `top_rankings` | `(conn, limit, run_id)` | All-generation top-N by Sharpe |
| `get_strategy` | `(conn, strategy_id)` | Fetch single strategy row |

`upsert_strategy` deduplicates by `(name, params_json)`. Same strategy config across runs/generations = 1 row. **`params_json` must be `json.dumps(..., sort_keys=True)`** — UNIQUE constraint depends on stable key ordering.

`_dec_to_text(x)` converts `Decimal | None → str | None` for TEXT money columns.

## Key invariants

- **All money = TEXT** — `str(Decimal)` in, `Decimal(row_value)` out. No implicit float conversion.
- **Use `txn()` for writes** — never rely on autocommit.
- **`init_db` is idempotent** — calls `apply_migrations` automatically; safe to call every startup.
- **`generation` flows through the whole chain** — `detect_patterns` → `insert_pattern_signal(generation=)` → `insert_backtest_result(generation=)` → `build_evaluation_result(generation=)` → ratchet.
- **`experiments.accepted`** — always 0 or 1 after ratchet runs; NULL means ratchet didn't fire yet.

## Querying the DB directly

```bash
uvx datasette data/atforge.db          # web UI
sqlite3 data/atforge.db               # raw SQL

# Useful queries
SELECT COUNT(*) FROM backtest_runs WHERE success=1;
SELECT symbol, name, sharpe FROM backtest_runs b JOIN strategies s USING(strategy_id)
  WHERE success=1 ORDER BY sharpe DESC LIMIT 10;
SELECT * FROM experiments WHERE accepted=1 ORDER BY delta_sharpe DESC;
SELECT generation, COUNT(*) FROM backtest_runs WHERE run_id=? GROUP BY generation;
```

## Tests

```
tests/storage/test_repo.py    — init_db idempotent, WAL mode, upsert dedup, insert/fetch round-trip,
                                 failure rows excluded from rankings, cascade delete
tests/storage/test_migrate.py — fresh DB lands at user_version=2, existing Phase 1 DB migrates cleanly
```
