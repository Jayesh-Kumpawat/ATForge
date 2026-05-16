"""Tests for GET /runs/{run_id}/rankings."""
from __future__ import annotations

import sqlite3


def _seed(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status) VALUES ('r1', '2026-05-16T10:00:00', 'success')"
    )
    conn.execute(
        "INSERT INTO strategies (name, family, params_json, created_at) "
        "VALUES ('SMA_10x25', 'sma', '{}', '2026-05-16T10:00:00')"
    )
    conn.execute(
        "INSERT INTO backtest_runs "
        "(run_id, strategy_id, symbol, success, n_trades, sharpe, sortino, cagr, win_rate, "
        " max_drawdown, total_return, generation, created_at) "
        "VALUES ('r1', 1, 'RELIANCE', 1, 37, 2.41, 2.9, 0.31, 0.61, '-0.082', '0.45', 1, "
        "'2026-05-16T10:00:00')"
    )
    conn.commit()
    conn.close()


def test_rankings_unknown_run_404(client) -> None:
    resp = client.get("/runs/nope/rankings")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_rankings_empty_run(client, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status) VALUES ('r1', '2026-05-16T10:00:00', 'success')"
    )
    conn.commit()
    conn.close()
    resp = client.get("/runs/r1/rankings")
    assert resp.status_code == 200
    assert resp.json() == {"run_id": "r1", "rankings": []}


def test_rankings_returns_row(client, db_path: str) -> None:
    _seed(db_path)
    resp = client.get("/runs/r1/rankings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "r1"
    assert len(body["rankings"]) == 1
    row = body["rankings"][0]
    assert row["symbol"] == "RELIANCE"
    assert row["strategy_id"] == 1
    assert row["strategy_name"] == "SMA_10x25"
    assert row["sharpe"] == 2.41
