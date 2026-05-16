"""Tests for GET /runs/{run_id}/timeline."""
from __future__ import annotations

import sqlite3


def test_timeline_unknown_run_404(client) -> None:
    resp = client.get("/runs/nope/timeline")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_timeline_empty_run(client, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status) VALUES ('r1', '2026-05-16T10:00:00', 'success')"
    )
    conn.commit()
    conn.close()
    resp = client.get("/runs/r1/timeline")
    assert resp.status_code == 200
    assert resp.json() == {"run_id": "r1", "events": []}


def test_timeline_returns_ordered_events(client, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status) VALUES ('r1', '2026-05-16T10:00:00', 'success')"
    )
    conn.execute(
        "INSERT INTO pipeline_events (run_id, generation, ts_ms, event_type, payload) "
        "VALUES ('r1', 0, 1000, 'EvtPipelineStart', '{\"n_symbols\": 2}')"
    )
    conn.execute(
        "INSERT INTO pipeline_events (run_id, generation, ts_ms, event_type, payload) "
        "VALUES ('r1', 1, 2000, 'EvtAgentReasoning', '{\"role\": \"explorer\"}')"
    )
    conn.commit()
    conn.close()

    resp = client.get("/runs/r1/timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "r1"
    assert [e["event_type"] for e in body["events"]] == [
        "EvtPipelineStart",
        "EvtAgentReasoning",
    ]
    assert body["events"][0]["payload"] == {"n_symbols": 2}
    assert body["events"][1]["generation"] == 1
