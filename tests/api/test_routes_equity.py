"""/strategies/{id}/equity route tests."""
from __future__ import annotations

import json
import sqlite3


def _seed_strategy(conn, name, family, params):
    cur = conn.execute(
        "INSERT INTO strategies (name, family, params_json, description, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, family, json.dumps(params, sort_keys=True), name, "2026-05-12T10:00:00"),
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_run(conn, run_id):
    conn.execute(
        "INSERT OR IGNORE INTO runs (run_id, started_at, status) VALUES (?, '2026-05-12T10:00:00', 'running')",
        (run_id,),
    )
    conn.commit()


def _seed_backtest_with_equity(conn, run_id, strategy_id, symbol, equity_json, signals_json):
    _seed_run(conn, run_id)
    conn.execute(
        """
        INSERT INTO backtest_runs (run_id, strategy_id, signal_id, symbol, sharpe, sortino,
                                   n_trades, max_drawdown, cagr, win_rate, success, generation,
                                   created_at, equity_json, signals_json)
        VALUES (?, ?, NULL, ?, 1.5, 0.8, 5, '-0.05', 0.1, 0.6, 1, 0,
                '2026-05-12T10:00:00', ?, ?)
        """,
        (run_id, strategy_id, symbol, equity_json, signals_json),
    )
    conn.commit()


def test_equity_404_for_unknown_strategy(client) -> None:
    r = client.get("/strategies/99999/equity?symbol=RELIANCE&run_id=r1")
    assert r.status_code == 404


def test_equity_404_when_no_equity_json(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    sid = _seed_strategy(conn, "S1", "sma", {})
    _seed_run(conn, "r1")
    conn.execute(
        """
        INSERT INTO backtest_runs (run_id, strategy_id, signal_id, symbol, sharpe, sortino,
                                   n_trades, max_drawdown, cagr, win_rate, success, generation,
                                   created_at)
        VALUES ('r1', ?, NULL, 'RELIANCE', 1.0, 0.5, 3, '-0.03', 0.08, 0.55, 1, 0,
                '2026-05-12T10:00:00')
        """,
        (sid,),
    )
    conn.commit()
    conn.close()

    r = client.get(f"/strategies/{sid}/equity?symbol=RELIANCE&run_id=r1")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "SIGNAL_DATA_MISSING"


def test_equity_returns_points_when_equity_json_present(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    sid = _seed_strategy(conn, "S2", "sma", {})
    equity = json.dumps([
        {"t": 1700000000000, "equity": 100000.0, "drawdown": 0.0},
        {"t": 1700086400000, "equity": 101200.0, "drawdown": -0.005},
    ])
    signals = json.dumps([{"t": 1700000000000, "type": "entry", "price": 2500.0}])
    _seed_backtest_with_equity(conn, "r2", sid, "RELIANCE", equity, signals)
    conn.close()

    r = client.get(f"/strategies/{sid}/equity?symbol=RELIANCE&run_id=r2")
    assert r.status_code == 200
    body = r.json()
    assert body["strategy_id"] == sid
    assert body["symbol"] == "RELIANCE"
    assert len(body["points"]) == 2
    assert body["points"][0]["t"] == 1700000000000
    assert body["points"][0]["equity"] == 100000.0
