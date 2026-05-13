"""Retention pruning: drop events older than N days OR beyond last M runs."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from atforge.api.events.persistence import persist_event
from atforge.api.events.retention import prune_old_events
from atforge.graph.events import EvtPipelineStart
from atforge.storage.db import init_db


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return sqlite3.connect(db_path)


def _insert_old_event(conn: sqlite3.Connection, run_id: str, days_ago: int) -> None:
    ts = int((time.time() - days_ago * 86400) * 1000)
    conn.execute(
        "INSERT INTO pipeline_events (run_id, generation, ts_ms, event_type, payload) VALUES (?, NULL, ?, 'EvtPipelineStart', '{}')",
        (run_id, ts),
    )
    conn.commit()


def test_prune_removes_events_older_than_30_days(conn: sqlite3.Connection) -> None:
    _insert_old_event(conn, "old-run", days_ago=40)
    _insert_old_event(conn, "fresh-run", days_ago=1)

    pruned = prune_old_events(conn, max_age_days=30, max_runs=100)

    assert pruned == 1
    rows = conn.execute("SELECT run_id FROM pipeline_events").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "fresh-run"


def test_prune_keeps_last_100_runs_only(conn: sqlite3.Connection) -> None:
    # 105 runs, all fresh
    for i in range(105):
        persist_event(conn, EvtPipelineStart(run_id=f"r{i:03d}", n_symbols=1, max_generations=1))

    pruned = prune_old_events(conn, max_age_days=30, max_runs=100)

    # 5 oldest runs (r000..r004) should be pruned
    assert pruned == 5
    remaining_runs = {row[0] for row in conn.execute("SELECT DISTINCT run_id FROM pipeline_events")}
    assert "r000" not in remaining_runs
    assert "r004" not in remaining_runs
    assert "r005" in remaining_runs
    assert "r104" in remaining_runs


def test_prune_is_idempotent(conn: sqlite3.Connection) -> None:
    _insert_old_event(conn, "old-run", days_ago=40)

    first = prune_old_events(conn, max_age_days=30, max_runs=100)
    second = prune_old_events(conn, max_age_days=30, max_runs=100)

    assert first == 1
    assert second == 0
