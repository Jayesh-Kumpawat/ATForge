"""/runs and /runs/{id} integration tests."""
from __future__ import annotations

import sqlite3


def _seed_run(conn: sqlite3.Connection, run_id: str, started_iso: str = "2026-05-12T10:00:00") -> None:
    conn.execute(
        "INSERT INTO runs (run_id, universe_hash, started_at, status) VALUES (?, ?, ?, ?)",
        (run_id, "h-abc", started_iso, "running"),
    )
    conn.commit()


def test_runs_list_empty(client) -> None:
    r = client.get("/runs")
    assert r.status_code == 200
    body = r.json()
    assert body["runs"] == []
    assert body["total"] == 0


def test_runs_list_with_seeded_runs(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    _seed_run(conn, "run-a")
    _seed_run(conn, "run-b", started_iso="2026-05-12T11:00:00")
    conn.close()

    r = client.get("/runs?limit=10&offset=0")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    ids = [run["run_id"] for run in body["runs"]]
    # Newest first
    assert ids[0] == "run-b"
    assert ids[1] == "run-a"


def test_run_detail_404(client) -> None:
    r = client.get("/runs/nonexistent")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_run_detail_returns_summary(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    _seed_run(conn, "run-x")
    conn.close()

    r = client.get("/runs/run-x")
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == "run-x"
    assert body["status"] in {"running", "done", "failed", "unknown"}
