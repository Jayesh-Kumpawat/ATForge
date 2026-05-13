"""Unit test for persist_event helper."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from atforge.api.events.persistence import persist_event
from atforge.graph.events import EvtBacktestDone, EvtPipelineStart
from atforge.storage.db import init_db


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return sqlite3.connect(db_path)


def test_persist_pipeline_start(conn: sqlite3.Connection) -> None:
    evt = EvtPipelineStart(run_id="run-xyz", n_symbols=3, max_generations=2)

    persist_event(conn, evt, generation=None)

    row = conn.execute(
        "SELECT run_id, event_type, payload, generation FROM pipeline_events"
    ).fetchone()
    assert row is not None
    assert row[0] == "run-xyz"
    assert row[1] == "EvtPipelineStart"
    payload = json.loads(row[2])
    assert payload == {"run_id": "run-xyz", "n_symbols": 3, "max_generations": 2}
    assert row[3] is None


def test_persist_backtest_done_with_generation(conn: sqlite3.Connection) -> None:
    evt = EvtBacktestDone(symbol="RELIANCE", strategy="SMA_10x25", success=True, sharpe=1.42)

    persist_event(conn, evt, generation=1, run_id="run-abc")

    row = conn.execute(
        "SELECT run_id, generation, event_type, payload FROM pipeline_events"
    ).fetchone()
    assert row[0] == "run-abc"
    assert row[1] == 1
    assert row[2] == "EvtBacktestDone"
    payload = json.loads(row[3])
    assert payload["symbol"] == "RELIANCE"
    assert payload["sharpe"] == 1.42


def test_persist_assigns_autoincrement_ids(conn: sqlite3.Connection) -> None:
    e1 = EvtPipelineStart(run_id="r1", n_symbols=1, max_generations=1)
    e2 = EvtPipelineStart(run_id="r2", n_symbols=2, max_generations=1)

    persist_event(conn, e1)
    persist_event(conn, e2)

    ids = [row[0] for row in conn.execute("SELECT event_id FROM pipeline_events ORDER BY event_id")]
    assert ids == sorted(ids) and len(ids) == 2 and ids[1] > ids[0]


def test_persist_ts_ms_is_recent(conn: sqlite3.Connection) -> None:
    import time
    before_ms = int(time.time() * 1000)
    persist_event(conn, EvtPipelineStart(run_id="t", n_symbols=1, max_generations=1))
    after_ms = int(time.time() * 1000)

    ts = conn.execute("SELECT ts_ms FROM pipeline_events").fetchone()[0]
    assert before_ms <= ts <= after_ms
