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

    # Dedup: one row per (symbol, strategy) — keep the highest-Sharpe result.
    # Without this, multi-generation runs show the same baseline strategy once per
    # generation it was tested in, cluttering the rankings with identical rows.
    sql = f"""
        SELECT backtest_id, run_id, symbol, strategy_name, family,
               generation, n_trades, total_return, final_value, max_drawdown,
               sharpe, sortino, cagr, win_rate
        FROM (
            SELECT
                b.backtest_id, b.run_id, b.symbol,
                s.name AS strategy_name, s.family,
                b.generation,
                b.n_trades, b.total_return, b.final_value, b.max_drawdown,
                b.sharpe, b.sortino, b.cagr, b.win_rate,
                ROW_NUMBER() OVER (
                    PARTITION BY b.symbol, b.strategy_id
                    ORDER BY b.sharpe DESC
                ) AS rn
            FROM backtest_runs b
            JOIN strategies s ON s.strategy_id = b.strategy_id
            WHERE {" AND ".join(where)}
        )
        WHERE rn = 1
        ORDER BY sharpe DESC
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
    child_strategy_id: int | None,
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
            run_id,
            generation,
            parent_strategy_id,
            child_strategy_id,
            mutator,
            mutation_json,
            accepted,
            delta_sharpe,
            composite_score_json,
            reasoning,
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


def get_experiments_for_run(
    conn: sqlite3.Connection,
    run_id: str,
) -> list[dict[str, Any]]:
    """Return all ratchet verdicts for a run, joined with strategy names."""
    rows = conn.execute(
        """
        SELECT
            e.experiment_id, e.generation, e.mutator,
            e.accepted, e.delta_sharpe, e.reasoning, e.composite_score,
            e.mutation_json, e.created_at,
            p.name AS parent_name,
            c.name AS child_name,
            e.parent_strategy_id, e.child_strategy_id
        FROM experiments e
        LEFT JOIN strategies p ON p.strategy_id = e.parent_strategy_id
        LEFT JOIN strategies c ON c.strategy_id = e.child_strategy_id
        WHERE e.run_id = ?
        ORDER BY e.generation, e.experiment_id
        """,
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_best_sharpe_per_generation(
    conn: sqlite3.Connection,
    run_id: str,
) -> list[dict[str, Any]]:
    """Return best Sharpe achieved per generation — used for the progression chart."""
    rows = conn.execute(
        """
        SELECT generation, MAX(sharpe) AS best_sharpe, COUNT(*) AS n_backtests
        FROM backtest_runs
        WHERE run_id = ? AND success = 1
        GROUP BY generation
        ORDER BY generation
        """,
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_strategy_children(
    conn: sqlite3.Connection,
    parent_strategy_id: int,
    *,
    accepted_only: bool = True,
) -> list[dict[str, Any]]:
    """All experiments where this strategy was the parent."""
    where = "WHERE e.parent_strategy_id = ?"
    params: list[Any] = [parent_strategy_id]
    if accepted_only:
        where += " AND e.accepted = 1"
    query = f"""
        SELECT s.strategy_id, s.name, s.family, s.params_json,
               e.experiment_id, e.delta_sharpe, e.composite_score,
               e.mutator, e.accepted, e.created_at
        FROM experiments e
        JOIN strategies s ON e.child_strategy_id = s.strategy_id
        {where}
        ORDER BY e.created_at DESC
    """
    return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_pattern_symbol_breakdown(
    conn: sqlite3.Connection,
    strategy_id: int,
) -> list[dict[str, Any]]:
    """Per-symbol AVG sharpe/sortino/n_trades for a strategy across all backtests."""
    query = """
        SELECT b.symbol,
               AVG(b.sharpe)   AS avg_sharpe,
               AVG(b.sortino)  AS avg_sortino,
               AVG(b.n_trades) AS avg_n_trades,
               COUNT(*)        AS n_backtests,
               MAX(b.sharpe)   AS best_sharpe
        FROM backtest_runs b
        WHERE b.strategy_id = ? AND b.success = 1
        GROUP BY b.symbol
        ORDER BY avg_sharpe DESC
    """
    return [dict(r) for r in conn.execute(query, (strategy_id,)).fetchall()]


def get_mutation_tree(
    conn: sqlite3.Connection,
    root_strategy_id: int,
    max_depth: int = 5,
) -> list[dict[str, Any]]:
    """Recursive CTE walking parent→child mutation chains from a root strategy."""
    query = """
        WITH RECURSIVE tree AS (
            SELECT e.experiment_id, e.parent_strategy_id, e.child_strategy_id,
                   e.accepted, e.delta_sharpe, e.mutator, 0 AS depth
            FROM experiments e
            WHERE e.parent_strategy_id = ?
            UNION ALL
            SELECT e.experiment_id, e.parent_strategy_id, e.child_strategy_id,
                   e.accepted, e.delta_sharpe, e.mutator, t.depth + 1
            FROM experiments e
            JOIN tree t ON e.parent_strategy_id = t.child_strategy_id
            WHERE t.depth + 1 < ?
        )
        SELECT * FROM tree ORDER BY depth, experiment_id
    """
    return [dict(r) for r in conn.execute(query, (root_strategy_id, max_depth)).fetchall()]


def get_agent_activity_summary(
    conn: sqlite3.Connection,
    run_id: str,
) -> dict[str, Any]:
    """Per-role proposal/veto counts for the Agent Activity dashboard tab.

    Returns:
        explorer_proposals  — count of explorer experiments (any accepted value)
        exploiter_proposals — count of exploiter experiments
        critic_vetoes       — count of critic_veto experiments
        veto_rate           — critic_vetoes / (explorer + exploiter + critic_vetoes)
                              0.0 when no multi-agent experiments exist
    """
    rows = conn.execute(
        """
        SELECT mutator, COUNT(*) AS n
        FROM experiments
        WHERE run_id = ? AND mutator IN ('explorer', 'exploiter', 'critic_veto')
        GROUP BY mutator
        """,
        (run_id,),
    ).fetchall()

    counts: dict[str, int] = {r["mutator"]: r["n"] for r in rows}
    explorer = counts.get("explorer", 0)
    exploiter = counts.get("exploiter", 0)
    vetoes = counts.get("critic_veto", 0)
    total = explorer + exploiter + vetoes
    veto_rate = vetoes / total if total > 0 else 0.0

    return {
        "explorer_proposals": explorer,
        "exploiter_proposals": exploiter,
        "critic_vetoes": vetoes,
        "veto_rate": veto_rate,
    }


def get_recent_critic_verdicts(
    conn: sqlite3.Connection,
    run_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Most recent critic_veto experiment rows for a run, newest first."""
    rows = conn.execute(
        """
        SELECT e.experiment_id, e.generation, e.parent_strategy_id,
               e.child_strategy_id, e.mutator, e.mutation_json,
               e.accepted, e.reasoning, e.created_at,
               s.name AS parent_name
        FROM experiments e
        LEFT JOIN strategies s ON e.parent_strategy_id = s.strategy_id
        WHERE e.run_id = ? AND e.mutator = 'critic_veto'
        ORDER BY e.created_at DESC
        LIMIT ?
        """,
        (run_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]
