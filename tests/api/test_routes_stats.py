"""Tests for GET /stats."""
from __future__ import annotations

import sqlite3


def test_stats_empty_db(client) -> None:
    resp = client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_runs"] == 0
    assert body["n_strategies"] == 0
    assert body["n_backtests"] == 0
    assert body["n_experiments"] == 0
    assert body["best_sharpe"] is None
    assert body["families"] == []


def test_stats_counts_and_families(client, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status) VALUES ('r1', '2026-05-16T10:00:00', 'success')"
    )
    conn.execute(
        "INSERT INTO strategies (name, family, params_json, created_at) "
        "VALUES ('S1', 'sma', '{}', '2026-05-16T10:00:00')"
    )
    conn.execute(
        "INSERT INTO strategies (name, family, params_json, created_at) "
        "VALUES ('S2', 'sma', '{\"a\":1}', '2026-05-16T10:00:00')"
    )
    conn.execute(
        "INSERT INTO backtest_runs (run_id, strategy_id, symbol, success, sharpe, created_at) "
        "VALUES ('r1', 1, 'RELIANCE', 1, 2.4, '2026-05-16T10:00:00')"
    )
    conn.commit()
    conn.close()

    resp = client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_runs"] == 1
    assert body["n_strategies"] == 2
    assert body["n_backtests"] == 1
    assert body["best_sharpe"] == 2.4
    assert body["families"] == [{"family": "sma", "count": 2}]
