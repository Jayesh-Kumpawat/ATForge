"""/strategies/{id}/backtests, /lineage, /reasoning tests."""
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


def _seed_backtest(conn, run_id, strategy_id, symbol, generation, sharpe):
    _seed_run(conn, run_id)
    conn.execute(
        """
        INSERT INTO backtest_runs (run_id, strategy_id, signal_id, symbol, sharpe, sortino,
                                   n_trades, max_drawdown, cagr, win_rate, success, generation, created_at)
        VALUES (?, ?, NULL, ?, ?, 0.5, 5, '-0.05', 0.2, 0.6, 1, ?, '2026-05-12T10:00:00')
        """,
        (run_id, strategy_id, symbol, sharpe, generation),
    )
    conn.commit()


def _seed_experiment(conn, run_id, gen, parent_id, child_id, mutator, accepted, delta_sharpe, reasoning):
    _seed_run(conn, run_id)
    conn.execute(
        """
        INSERT INTO experiments (run_id, generation, parent_strategy_id, child_strategy_id,
                                 mutator, accepted, delta_sharpe, composite_score, reasoning, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?, '2026-05-12T10:00:00')
        """,
        (run_id, gen, parent_id, child_id, mutator, accepted, delta_sharpe, reasoning),
    )
    conn.commit()


def test_backtests_returns_rows(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    sid = _seed_strategy(conn, "S1", "sma", {})
    _seed_backtest(conn, "r1", sid, "RELIANCE", 0, 1.2)
    _seed_backtest(conn, "r1", sid, "TCS", 0, 1.4)
    conn.close()

    r = client.get(f"/strategies/{sid}/backtests")
    assert r.status_code == 200
    body = r.json()
    assert body["strategy_id"] == sid
    assert len(body["backtests"]) == 2


def test_lineage_returns_ancestors_and_descendants(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    parent = _seed_strategy(conn, "P", "sma", {"fast": 10, "slow": 25})
    me = _seed_strategy(conn, "M", "sma", {"fast": 8, "slow": 22})
    child = _seed_strategy(conn, "C", "sma", {"fast": 6, "slow": 20})

    _seed_experiment(conn, "r1", 1, parent, me, "param_delta", 1, 0.10, "ok")
    _seed_experiment(conn, "r1", 2, me, child, "param_delta", 1, 0.05, "ok")
    conn.close()

    r = client.get(f"/strategies/{me}/lineage")
    assert r.status_code == 200
    body = r.json()
    ancestor_ids = [n["strategy_id"] for n in body["ancestors"]]
    descendant_ids = [n["strategy_id"] for n in body["descendants"]]
    assert parent in ancestor_ids
    assert child in descendant_ids


def test_reasoning_returns_entries(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    parent = _seed_strategy(conn, "P", "sma", {})
    me = _seed_strategy(conn, "M", "sma", {})
    _seed_experiment(conn, "r1", 1, parent, me, "param_delta", 1, 0.12,
                     "Tried smaller fast period because parent under-traded.")
    conn.close()

    r = client.get(f"/strategies/{me}/reasoning")
    assert r.status_code == 200
    body = r.json()
    assert len(body["entries"]) == 1
    assert "smaller fast" in body["entries"][0]["reasoning"]
