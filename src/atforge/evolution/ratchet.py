"""Ratchet — pure scoring and DB aggregation for the acceptance criterion.

`judge_mutation` is a pure function (no I/O). `build_evaluation_result` reads DB.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from atforge.evolution.types import EvaluationResult, RatchetThresholds, RatchetVerdict


def build_evaluation_result(
    conn: sqlite3.Connection,
    *,
    strategy_id: int,
    run_id: str,
    generation: int,
) -> EvaluationResult | None:
    """Aggregate successful backtest_runs rows for one strategy into one EvaluationResult.

    Returns None if no successful backtests exist (strategy never ran or all failed).
    """
    rows = conn.execute(
        """
        SELECT sharpe, sortino, n_trades, max_drawdown
        FROM backtest_runs
        WHERE strategy_id=? AND run_id=? AND generation=? AND success=1
        """,
        (strategy_id, run_id, generation),
    ).fetchall()

    if not rows:
        return None

    sharpes = [r["sharpe"] for r in rows if r["sharpe"] is not None]
    sortinos = [r["sortino"] for r in rows if r["sortino"] is not None]
    n_trades = sum(r["n_trades"] for r in rows)
    drawdowns = [Decimal(r["max_drawdown"]) for r in rows if r["max_drawdown"] is not None]

    return EvaluationResult(
        strategy_id=strategy_id,
        run_id=run_id,
        generation=generation,
        mean_sharpe=sum(sharpes) / len(sharpes) if sharpes else 0.0,
        mean_sortino=sum(sortinos) / len(sortinos) if sortinos else 0.0,
        total_n_trades=n_trades,
        max_drawdown=max(drawdowns) if drawdowns else Decimal("0"),
        n_symbols=len(rows),
    )


def judge_mutation(
    parent: EvaluationResult,
    child: EvaluationResult,
    thresholds: RatchetThresholds,
) -> RatchetVerdict:
    """Score a parent/child pair against acceptance thresholds. Pure — no side effects."""
    delta_sharpe = child.mean_sharpe - parent.mean_sharpe
    delta_sortino = child.mean_sortino - parent.mean_sortino

    # float conversion only for ratio (analytical, not money)
    if parent.max_drawdown != Decimal("0"):
        dd_ratio = float(child.max_drawdown / parent.max_drawdown)
    else:
        dd_ratio = 1.0 if child.max_drawdown == Decimal("0") else float("inf")

    sharpe_ok = delta_sharpe >= thresholds.min_delta_sharpe
    sortino_ok = delta_sortino >= thresholds.min_delta_sortino
    dd_ok = dd_ratio <= (1.0 + thresholds.max_drawdown_tol)
    trades_ok = child.total_n_trades >= thresholds.min_n_trades

    accepted = sharpe_ok and sortino_ok and dd_ok and trades_ok

    composite_score = {
        "delta_sharpe": delta_sharpe,
        "delta_sortino": delta_sortino,
        "dd_ratio": dd_ratio,
        "child_n_trades": float(child.total_n_trades),
        "sharpe_ok": float(sharpe_ok),
        "sortino_ok": float(sortino_ok),
        "dd_ok": float(dd_ok),
        "trades_ok": float(trades_ok),
    }

    reasons: list[str] = []
    if not sharpe_ok:
        reasons.append(f"sharpe_delta={delta_sharpe:.3f}<{thresholds.min_delta_sharpe}")
    if not sortino_ok:
        reasons.append(f"sortino_delta={delta_sortino:.3f}<{thresholds.min_delta_sortino}")
    if not dd_ok:
        reasons.append(f"dd_ratio={dd_ratio:.2f}>{1+thresholds.max_drawdown_tol:.2f}")
    if not trades_ok:
        reasons.append(f"n_trades={child.total_n_trades}<{thresholds.min_n_trades}")

    return RatchetVerdict(
        accepted=accepted,
        delta_sharpe=delta_sharpe,
        delta_sortino=delta_sortino,
        dd_ratio=dd_ratio,
        composite_score=composite_score,
        reasoning="accepted" if accepted else "; ".join(reasons),
    )
