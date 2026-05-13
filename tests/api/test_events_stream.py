"""SSE stream generator tests.

Tested directly (async) using max_polls=1 to collect one backfill batch
and stop, avoiding the infinite polling loop in test environments.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from atforge.api.events.stream import event_stream
from atforge.storage.db import init_db


def _insert_event(
    db_path: str, run_id: str, event_type: str, ts_ms: int = 1_700_000_000_000
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO pipeline_events (run_id, generation, ts_ms, event_type, payload) "
        "VALUES (?, NULL, ?, ?, ?)",
        (run_id, ts_ms, event_type, json.dumps({"run_id": run_id})),
    )
    conn.commit()
    conn.close()


async def test_sse_backfill_yields_seeded_events(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test.db")
    init_db(tmp_path / "test.db")
    _insert_event(db_path, "run-1", "EvtPipelineStart")
    _insert_event(db_path, "run-1", "EvtNodeStart")
    _insert_event(db_path, "run-1", "EvtPipelineDone")

    chunks: list[str] = []
    async for chunk in event_stream(db_path, "run-1", 0, max_polls=1):
        chunks.append(chunk)

    joined = "".join(chunks)
    assert "EvtPipelineStart" in joined
    assert "EvtNodeStart" in joined
    assert "EvtPipelineDone" in joined


async def test_sse_filters_by_run_id(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test.db")
    init_db(tmp_path / "test.db")
    _insert_event(db_path, "run-A", "EvtPipelineStart")
    _insert_event(db_path, "run-B", "EvtPipelineStart")

    chunks: list[str] = []
    async for chunk in event_stream(db_path, "run-A", 0, max_polls=1):
        chunks.append(chunk)

    joined = "".join(chunks)
    assert "run-A" in joined
    assert "run-B" not in joined
