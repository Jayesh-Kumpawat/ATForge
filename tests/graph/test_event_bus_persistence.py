"""EventBus optionally persists events to pipeline_events table."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from atforge.graph.events import EventBus, EvtPipelineStart
from atforge.storage.db import init_db


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    p = tmp_path / "test.db"
    init_db(p)
    return str(p)


def test_event_bus_without_db_path_does_not_persist(tmp_path: Path) -> None:
    bus = EventBus()
    bus.emit(EvtPipelineStart(run_id="r1", n_symbols=1, max_generations=1))
    drained = bus.drain()
    assert len(drained) == 1


def test_event_bus_with_db_path_persists_event(db_path: str) -> None:
    bus = EventBus(db_path=db_path)
    bus.emit(EvtPipelineStart(run_id="r2", n_symbols=1, max_generations=1))

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT run_id, event_type FROM pipeline_events").fetchall()
    assert len(rows) == 1
    assert rows[0] == ("r2", "EvtPipelineStart")


def test_event_bus_with_db_path_still_queues_for_in_process_monitor(db_path: str) -> None:
    bus = EventBus(db_path=db_path)
    bus.emit(EvtPipelineStart(run_id="r3", n_symbols=2, max_generations=1))

    drained = bus.drain()
    assert len(drained) == 1
    assert drained[0].run_id == "r3"
