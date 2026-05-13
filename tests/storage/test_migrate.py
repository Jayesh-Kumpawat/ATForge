from __future__ import annotations

import sqlite3
from pathlib import Path

from atforge.storage.db import connect, init_db
from atforge.storage.migrate import apply_migrations

PHASE2A_TARGET_VERSION = 3

PHASE1_DDL = """
CREATE TABLE runs (
    run_id          TEXT PRIMARY KEY,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    universe_hash   TEXT,
    status          TEXT NOT NULL CHECK (status IN ('running','success','partial','failed')),
    notes           TEXT
);
CREATE TABLE strategies (
    strategy_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    family          TEXT NOT NULL,
    params_json     TEXT NOT NULL,
    description     TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE (name, params_json)
);
CREATE TABLE pattern_signals (
    signal_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    strategy_id     INTEGER NOT NULL REFERENCES strategies(strategy_id),
    symbol          TEXT NOT NULL,
    n_signals       INTEGER NOT NULL,
    first_date      TEXT,
    last_date       TEXT,
    created_at      TEXT NOT NULL
);
CREATE TABLE backtest_runs (
    backtest_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    signal_id       INTEGER REFERENCES pattern_signals(signal_id),
    strategy_id     INTEGER NOT NULL REFERENCES strategies(strategy_id),
    symbol          TEXT NOT NULL,
    success         INTEGER NOT NULL CHECK (success IN (0,1)),
    reason          TEXT,
    n_trades        INTEGER NOT NULL DEFAULT 0,
    total_return    TEXT,
    final_value     TEXT,
    max_drawdown    TEXT,
    sharpe          REAL,
    sortino         REAL,
    cagr            REAL,
    win_rate        REAL,
    hold_bars       INTEGER,
    fees            REAL,
    slippage        REAL,
    init_cash       TEXT,
    created_at      TEXT NOT NULL
);
CREATE TABLE experiments (
    experiment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id       INTEGER REFERENCES experiments(experiment_id),
    strategy_id     INTEGER REFERENCES strategies(strategy_id),
    mutation_json   TEXT,
    accepted        INTEGER CHECK (accepted IN (0,1)),
    delta_sharpe    REAL,
    reasoning       TEXT,
    created_at      TEXT NOT NULL
);
PRAGMA user_version = 0;
"""


def _user_version(db: Path) -> int:
    with connect(db) as conn:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _columns(db: Path, table: str) -> set[str]:
    with connect(db) as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"] for r in rows}


def test_fresh_db_lands_at_target_version(tmp_db_path: Path) -> None:
    init_db(tmp_db_path)
    assert _user_version(tmp_db_path) == PHASE2A_TARGET_VERSION


def test_fresh_db_has_phase2a_columns(tmp_db_path: Path) -> None:
    init_db(tmp_db_path)
    exp_cols = _columns(tmp_db_path, "experiments")
    expected = {
        "run_id",
        "generation",
        "parent_strategy_id",
        "child_strategy_id",
        "composite_score",
        "mutator",
    }
    assert expected.issubset(exp_cols), f"missing in experiments: {expected - exp_cols}"
    assert "generation" in _columns(tmp_db_path, "pattern_signals")
    assert "generation" in _columns(tmp_db_path, "backtest_runs")


def test_init_db_idempotent(tmp_db_path: Path) -> None:
    init_db(tmp_db_path)
    init_db(tmp_db_path)
    init_db(tmp_db_path)
    assert _user_version(tmp_db_path) == PHASE2A_TARGET_VERSION


def test_phase1_db_upgrades_via_migration(tmp_db_path: Path) -> None:
    conn = sqlite3.connect(tmp_db_path)
    conn.executescript(PHASE1_DDL)
    conn.commit()
    conn.close()
    assert _user_version(tmp_db_path) == 0

    init_db(tmp_db_path)

    assert _user_version(tmp_db_path) == PHASE2A_TARGET_VERSION
    exp_cols = _columns(tmp_db_path, "experiments")
    assert "generation" in exp_cols
    assert "composite_score" in exp_cols
    assert "mutator" in exp_cols
    assert "generation" in _columns(tmp_db_path, "pattern_signals")
    assert "generation" in _columns(tmp_db_path, "backtest_runs")


def test_apply_migrations_noop_when_current(tmp_db_path: Path) -> None:
    init_db(tmp_db_path)
    with connect(tmp_db_path) as conn:
        before = int(conn.execute("PRAGMA user_version").fetchone()[0])
        final = apply_migrations(conn)
    assert before == final == PHASE2A_TARGET_VERSION
