"""Schema test: pipeline_events table exists with expected columns + index."""
from __future__ import annotations

from pathlib import Path

from atforge.storage.db import connect, init_db


def test_pipeline_events_table_exists(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_events'"
        )
        assert cur.fetchone() is not None, "pipeline_events table missing"


def test_pipeline_events_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(pipeline_events)")}
    expected = {"event_id", "run_id", "generation", "ts_ms", "event_type", "payload"}
    assert expected.issubset(cols), f"missing columns: {expected - cols}"


def test_pipeline_events_index_exists(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with connect(db_path) as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pipeline_events_run'"
        )
        assert cur.fetchone() is not None, "idx_pipeline_events_run index missing"
