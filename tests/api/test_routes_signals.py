"""/strategies/{id}/signals route."""
from __future__ import annotations

import json
import sqlite3


def _seed_strategy(conn, name):
    cur = conn.execute(
        "INSERT INTO strategies (name, family, params_json, description, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, "sma", "{}", name, "2026-05-12T10:00:00"),
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_run(conn, run_id):
    conn.execute(
        "INSERT OR IGNORE INTO runs (run_id, started_at, status) VALUES (?, '2026-05-12T10:00:00', 'running')",
        (run_id,),
    )
    conn.commit()


def test_signals_404_for_unknown_strategy(client) -> None:
    r = client.get("/strategies/99999/signals?symbol=RELIANCE&run_id=r1")
    assert r.status_code == 404


def test_signals_404_when_no_signals_json(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    sid = _seed_strategy(conn, "S")
    conn.close()

    r = client.get(f"/strategies/{sid}/signals?symbol=RELIANCE&run_id=r1")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "SIGNAL_DATA_MISSING"


def test_signals_returns_markers_when_signals_json_present(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    sid = _seed_strategy(conn, "S2")
    _seed_run(conn, "r2")
    signals = json.dumps([
        {"t": 1700000000000, "type": "entry", "price": 2500.0},
        {"t": 1700432000000, "type": "exit", "price": 2560.0},
    ])
    conn.execute(
        """
        INSERT INTO backtest_runs (run_id, strategy_id, signal_id, symbol, sharpe, sortino,
                                   n_trades, max_drawdown, cagr, win_rate, success, generation,
                                   created_at, signals_json)
        VALUES ('r2', ?, NULL, 'RELIANCE', 1.5, 0.8, 2, '-0.04', 0.1, 0.6, 1, 0,
                '2026-05-12T10:00:00', ?)
        """,
        (sid, signals),
    )
    conn.commit()
    conn.close()

    r = client.get(f"/strategies/{sid}/signals?symbol=RELIANCE&run_id=r2")
    assert r.status_code == 200
    body = r.json()
    assert body["strategy_id"] == sid
    assert len(body["signals"]) == 2
    assert body["signals"][0]["type"] == "entry"
    assert body["signals"][1]["type"] == "exit"
    assert isinstance(body["bars"], list)
