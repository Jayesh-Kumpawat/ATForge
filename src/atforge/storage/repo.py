from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from atforge.backtest.engine import BacktestResult


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _dec_to_text(x: Decimal | None) -> str | None:
    return None if x is None else str(x)


def insert_run(conn: sqlite3.Connection, run_id: str, universe_hash: str | None = None) -> None:
    conn.execute(
        "INSERT INTO runs(run_id, started_at, universe_hash, status) VALUES (?, ?, ?, 'running')",
        (run_id, _now_iso(), universe_hash),
    )


def finish_run(
    conn: sqlite3.Connection, run_id: str, status: str, notes: str | None = None
) -> None:
    conn.execute(
        "UPDATE runs SET finished_at=?, status=?, notes=? WHERE run_id=?",
        (_now_iso(), status, notes, run_id),
    )


def upsert_strategy(
    conn: sqlite3.Connection,
    name: str,
    family: str,
    params: dict[str, Any],
    description: str | None = None,
) -> int:
    params_json = json.dumps(params, sort_keys=True, separators=(",", ":"))
    cur = conn.execute(
        "SELECT strategy_id FROM strategies WHERE name=? AND params_json=?",
        (name, params_json),
    )
    row = cur.fetchone()
    if row:
        return int(row["strategy_id"])

    cur = conn.execute(
        "INSERT INTO strategies(name, family, params_json, description, created_at) VALUES (?,?,?,?,?)",
        (name, family, params_json, description, _now_iso()),
    )
    return int(cur.lastrowid)


def insert_pattern_signal(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    strategy_id: int,
    symbol: str,
    n_signals: int,
    first_date: str | None,
    last_date: str | None,
    generation: int = 0,
) -> int:
    cur = conn.execute(
        "INSERT INTO pattern_signals(run_id, strategy_id, symbol, n_signals, first_date, last_date, generation, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (run_id, strategy_id, symbol, n_signals, first_date, last_date, generation, _now_iso()),
    )
    return int(cur.lastrowid)


def insert_backtest_result(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    signal_id: int | None,
    strategy_id: int,
    result: BacktestResult,
    hold_bars: int,
    fees: float,
    slippage: float,
    init_cash: Decimal,
    generation: int = 0,
) -> int:
    m = result.metrics
    cur = conn.execute(
        """
        INSERT INTO backtest_runs(
            run_id, signal_id, strategy_id, symbol, success, reason, n_trades,
            total_return, final_value, max_drawdown,
            sharpe, sortino, cagr, win_rate,
            hold_bars, fees, slippage, init_cash,
            generation, created_at
        ) VALUES (?,?,?,?,?,?,?, ?,?,?, ?,?,?,?, ?,?,?,?, ?,?)
        """,
        (
            run_id,
            signal_id,
            strategy_id,
            result.symbol,
            1 if result.success else 0,
            result.reason,
            result.n_trades,
            _dec_to_text(m.get("total_return") if result.success else None),
            _dec_to_text(m.get("final_value") if result.success else None),
            _dec_to_text(m.get("max_drawdown") if result.success else None),
            float(m.get("sharpe", 0.0)) if result.success else None,
            float(m.get("sortino", 0.0)) if result.success else None,
            float(m.get("cagr", 0.0)) if result.success else None,
            float(m.get("win_rate", 0.0)) if result.success else None,
            hold_bars,
            fees,
            slippage,
            str(init_cash),
            generation,
            _now_iso(),
        ),
    )
    return int(cur.lastrowid)


def top_rankings(
    conn: sqlite3.Connection,
    *,
    limit: int = 20,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    where = ["success = 1"]
    params: list[Any] = []
    if run_id is not None:
        where.append("run_id = ?")
        params.append(run_id)

    sql = f"""
        SELECT
            b.backtest_id, b.run_id, b.symbol,
            s.name AS strategy_name, s.family,
            b.n_trades, b.total_return, b.final_value, b.max_drawdown,
            b.sharpe, b.sortino, b.cagr, b.win_rate
        FROM backtest_runs b
        JOIN strategies s ON s.strategy_id = b.strategy_id
        WHERE {" AND ".join(where)}
        ORDER BY b.sharpe DESC
        LIMIT ?
    """
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_strategy(conn: sqlite3.Connection, strategy_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT strategy_id, name, family, params_json FROM strategies WHERE strategy_id=?",
        (strategy_id,),
    ).fetchone()
    return dict(row) if row else None


def insert_experiment(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    generation: int,
    parent_strategy_id: int,
    child_strategy_id: int,
    mutator: str,
    mutation_json: str,
    accepted: int,
    delta_sharpe: float,
    composite_score_json: str,
    reasoning: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO experiments(
            run_id, generation,
            parent_strategy_id, child_strategy_id,
            mutator, mutation_json,
            accepted, delta_sharpe,
            composite_score, reasoning,
            created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            run_id, generation,
            parent_strategy_id, child_strategy_id,
            mutator, mutation_json,
            accepted, delta_sharpe,
            composite_score_json, reasoning,
            _now_iso(),
        ),
    )
    return int(cur.lastrowid)


def get_top_strategies_for_generation(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    generation: int,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return aggregated per-strategy metrics for a generation — used by mutators."""
    rows = conn.execute(
        """
        SELECT
            b.strategy_id,
            s.name,
            s.family,
            s.params_json,
            AVG(b.sharpe)   AS mean_sharpe,
            AVG(b.sortino)  AS mean_sortino,
            SUM(b.n_trades) AS total_n_trades,
            MAX(b.max_drawdown) AS max_drawdown,
            b.generation
        FROM backtest_runs b
        JOIN strategies s ON s.strategy_id = b.strategy_id
        WHERE b.run_id=? AND b.generation=? AND b.success=1
        GROUP BY b.strategy_id
        ORDER BY mean_sharpe DESC
        LIMIT ?
        """,
        (run_id, generation, limit),
    ).fetchall()
    return [dict(r) for r in rows]
