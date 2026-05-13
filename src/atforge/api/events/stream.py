"""SSE generator for /runs/{run_id}/events."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from collections.abc import AsyncIterator


HEARTBEAT_INTERVAL_S = 15.0
POLL_INTERVAL_S = 0.25
STOP_AFTER_DONE_S = 5.0


async def event_stream(
    db_path: str,
    run_id: str,
    after_event_id: int,
    *,
    max_polls: int | None = None,
) -> AsyncIterator[str]:
    """Yield SSE-formatted events for one run.

    Backfills any events with event_id > after_event_id, then tails the table.
    Closes 5s after the last EvtPipelineDone event.

    Args:
        max_polls: stop after this many DB polls (used in tests to avoid infinite loop).
    """
    last_id = after_event_id
    last_heartbeat = time.monotonic()
    seen_done = False
    seen_done_at: float | None = None
    polls = 0

    while True:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT event_id, run_id, generation, ts_ms, event_type, payload
                FROM pipeline_events
                WHERE run_id = ? AND event_id > ?
                ORDER BY event_id ASC
                LIMIT 500
                """,
                (run_id, last_id),
            ).fetchall()
        finally:
            conn.close()

        for row in rows:
            last_id = int(row["event_id"])
            envelope = {
                "event_id": last_id,
                "run_id": row["run_id"],
                "ts_ms": int(row["ts_ms"]),
                "event_type": row["event_type"],
                "generation": row["generation"],
                "payload": json.loads(row["payload"]),
            }
            yield f"event: pipeline_event\ndata: {json.dumps(envelope)}\n\n"

            if row["event_type"] == "EvtPipelineDone":
                seen_done = True
                seen_done_at = time.monotonic()

        now = time.monotonic()

        if not rows and (now - last_heartbeat) >= HEARTBEAT_INTERVAL_S:
            last_heartbeat = now
            yield f"event: heartbeat\ndata: {json.dumps({'ts_ms': int(time.time() * 1000)})}\n\n"

        if seen_done and seen_done_at is not None and (now - seen_done_at) >= STOP_AFTER_DONE_S:
            return

        polls += 1
        if max_polls is not None and polls >= max_polls:
            return

        await asyncio.sleep(POLL_INTERVAL_S)
