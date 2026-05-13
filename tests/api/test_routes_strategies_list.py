"""/strategies list + /strategies/{id} integration tests."""
from __future__ import annotations

import json
import sqlite3


def _seed_strategy(
    conn: sqlite3.Connection, name: str, family: str, params: dict, sid: int | None = None
) -> int:
    cur = conn.execute(
        "INSERT INTO strategies (strategy_id, name, family, params_json, description, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (sid, name, family, json.dumps(params, sort_keys=True), f"{name} desc", "2026-05-12T10:00:00"),
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_backtest(
    conn: sqlite3.Connection,
    run_id: str,
    strategy_id: int,
    symbol: str,
    generation: int,
    sharpe: float,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO runs (run_id, started_at, status) VALUES (?, '2026-05-12T10:00:00', 'running')",
        (run_id,),
    )
    conn.execute(
        """
        INSERT INTO backtest_runs (run_id, strategy_id, signal_id, symbol, sharpe, sortino,
                                   n_trades, max_drawdown, cagr, win_rate, success, generation, created_at)
        VALUES (?, ?, NULL, ?, ?, 0.5, 5, '-0.05', 0.1, 0.6, 1, ?, '2026-05-12T10:00:00')
        """,
        (run_id, strategy_id, symbol, sharpe, generation),
    )
    conn.commit()


def test_strategies_list_empty(client) -> None:
    r = client.get("/strategies")
    assert r.status_code == 200
    body = r.json()
    assert body["strategies"] == []
    assert body["total"] == 0


def test_strategies_list_returns_seeded(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    sid = _seed_strategy(conn, "SMA_10x25", "sma", {"fast": 10, "slow": 25})
    _seed_backtest(conn, "run-1", sid, "RELIANCE", 0, 1.5)
    conn.close()

    r = client.get("/strategies")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["strategies"][0]
    assert item["name"] == "SMA_10x25"
    assert item["family"] == "sma"


def test_strategy_detail_404(client) -> None:
    r = client.get("/strategies/9999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "STRATEGY_NOT_FOUND"


def test_strategy_detail_returns_full(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    sid = _seed_strategy(
        conn, "CDLENGULFING_bullish", "candle",
        {"pattern": "CDLENGULFING", "direction": "bullish"},
    )
    _seed_backtest(conn, "run-1", sid, "RELIANCE", 0, 1.71)
    conn.close()

    r = client.get(f"/strategies/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["strategy_id"] == sid
    assert body["family"] == "candle"
    assert body["params"]["pattern"] == "CDLENGULFING"
    assert body["metrics_summary"]["best_sharpe"] == 1.71
