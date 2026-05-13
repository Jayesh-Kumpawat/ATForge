"""Retention pruning for pipeline_events.

Run on FastAPI startup. Keeps table size bounded.
"""
from __future__ import annotations

import sqlite3
import time


def prune_old_events(
    conn: sqlite3.Connection,
    *,
    max_age_days: int = 30,
    max_runs: int = 100,
) -> int:
    """Delete rows older than max_age_days; keep only the last max_runs distinct runs.

    Returns the total number of rows deleted.
    """
    cutoff_ms = int((time.time() - max_age_days * 86400) * 1000)

    # Step 1: prune by age.
    cur = conn.execute("DELETE FROM pipeline_events WHERE ts_ms < ?", (cutoff_ms,))
    age_deleted = cur.rowcount

    # Step 2: prune by run count — keep newest max_runs distinct runs.
    runs_to_keep = conn.execute(
        """
        SELECT run_id FROM (
            SELECT run_id, MAX(event_id) as last_event
            FROM pipeline_events
            GROUP BY run_id
            ORDER BY last_event DESC
            LIMIT ?
        )
        """,
        (max_runs,),
    ).fetchall()
    keep_ids = {row[0] for row in runs_to_keep}

    if keep_ids:
        placeholders = ",".join("?" * len(keep_ids))
        cur = conn.execute(
            f"DELETE FROM pipeline_events WHERE run_id NOT IN ({placeholders})",
            tuple(keep_ids),
        )
        runs_deleted = cur.rowcount
    else:
        runs_deleted = 0

    conn.commit()
    return age_deleted + runs_deleted
