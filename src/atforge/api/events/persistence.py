"""Persist pipeline EventBus events to the pipeline_events SQLite table.

Called from inside EventBus.publish() when an optional db_path is configured.
The pipeline still works without this when db_path=None — the in-process Rich
monitor uses the same EventBus queue.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, is_dataclass
from typing import Any


def persist_event(
    conn: sqlite3.Connection,
    evt: Any,
    *,
    generation: int | None = None,
    run_id: str | None = None,
) -> None:
    """Insert one event row into pipeline_events.

    Args:
        conn: open SQLite connection (caller manages lifecycle/commit).
        evt: a frozen dataclass instance from atforge.graph.events.
        generation: optional generation number to tag the event row.
        run_id: optional run_id override. If None, attempts to read evt.run_id;
            if neither present, raises ValueError.
    """
    if not is_dataclass(evt):
        raise TypeError(f"persist_event expects a dataclass instance, got {type(evt).__name__}")

    payload: dict[str, Any] = asdict(evt)

    resolved_run_id = run_id or payload.get("run_id")
    if resolved_run_id is None:
        raise ValueError(
            f"persist_event needs run_id (got {type(evt).__name__} without run_id field "
            f"and no run_id kwarg)"
        )

    conn.execute(
        """
        INSERT INTO pipeline_events (run_id, generation, ts_ms, event_type, payload)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            resolved_run_id,
            generation,
            int(time.time() * 1000),
            type(evt).__name__,
            json.dumps(payload, sort_keys=True, default=str),
        ),
    )
    conn.commit()
