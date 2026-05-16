"""Tests for GET /runs/{run_id}/evolution."""
from __future__ import annotations

import sqlite3


def test_evolution_unknown_run_404(client) -> None:
    resp = client.get("/runs/nope/evolution")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_evolution_empty_run(client, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status) VALUES ('r1', '2026-05-16T10:00:00', 'success')"
    )
    conn.commit()
    conn.close()
    resp = client.get("/runs/r1/evolution")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"run_id": "r1", "experiments": [], "sharpe_progression": []}


def test_evolution_returns_experiment_and_progression(client, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status) VALUES ('r1', '2026-05-16T10:00:00', 'success')"
    )
    conn.execute(
        "INSERT INTO strategies (name, family, params_json, created_at) "
        "VALUES ('P', 'sma', '{}', '2026-05-16T10:00:00')"
    )
    conn.execute(
        "INSERT INTO strategies (name, family, params_json, created_at) "
        "VALUES ('C', 'sma', '{\"a\":1}', '2026-05-16T10:00:00')"
    )
    conn.execute(
        "INSERT INTO experiments "
        "(run_id, generation, parent_strategy_id, child_strategy_id, mutator, mutation_json, "
        " accepted, delta_sharpe, composite_score, reasoning, created_at) "
        "VALUES ('r1', 1, 1, 2, 'param_delta', '{}', 1, 0.18, '{}', 'accepted', "
        "'2026-05-16T10:01:00')"
    )
    conn.execute(
        "INSERT INTO backtest_runs (run_id, strategy_id, symbol, success, sharpe, generation, created_at) "
        "VALUES ('r1', 1, 'RELIANCE', 1, 2.41, 1, '2026-05-16T10:00:00')"
    )
    conn.commit()
    conn.close()

    resp = client.get("/runs/r1/evolution")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["experiments"]) == 1
    exp = body["experiments"][0]
    assert exp["mutator"] == "param_delta"
    assert exp["accepted"] == 1
    assert exp["parent_name"] == "P"
    assert exp["child_name"] == "C"
    assert body["sharpe_progression"] == [
        {"generation": 1, "best_sharpe": 2.41, "n_backtests": 1}
    ]
