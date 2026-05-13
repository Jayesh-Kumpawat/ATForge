-- Migration 0003: Add pipeline_events table for Track C SSE bridge.
CREATE TABLE IF NOT EXISTS pipeline_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT NOT NULL,
    generation INTEGER,
    ts_ms      INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pipeline_events_run
    ON pipeline_events (run_id, event_id);

PRAGMA user_version = 3;
