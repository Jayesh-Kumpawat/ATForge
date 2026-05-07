"""Phase 9b — repo queries for the Agent Activity dashboard tab.

Tests for:
  - get_agent_activity_summary(conn, run_id) → per-role proposal/veto counts
  - get_recent_critic_verdicts(conn, run_id, limit) → critic_veto experiment rows
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from atforge.backtest.engine import BacktestResult
from atforge.storage.db import connect, init_db, txn
from atforge.storage.repo import (
    get_agent_activity_summary,
    get_recent_critic_verdicts,
    insert_backtest_result,
    insert_experiment,
    insert_pattern_signal,
    insert_run,
    upsert_strategy,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "agent_activity.sqlite"
    init_db(p)
    return p


def _seed_strategy(conn, name: str = "SMA_5x15") -> int:
    return upsert_strategy(
        conn,
        name=name,
        family="indicator",
        params={"type": "sma_crossover", "fast": 5, "slow": 15},
    )


def _seed_backtest(conn, run_id: str, sid: int) -> int:
    sig_id = insert_pattern_signal(
        conn,
        run_id=run_id,
        strategy_id=sid,
        symbol="RELIANCE",
        n_signals=3,
        first_date=None,
        last_date=None,
        generation=0,
    )
    bt = BacktestResult(
        symbol="RELIANCE",
        pattern_name="SMA_5x15",
        success=True,
        reason="ok",
        n_trades=6,
        metrics={
            "sharpe": 1.0,
            "sortino": 1.2,
            "total_return": Decimal("0.10"),
            "final_value": Decimal("110000"),
            "max_drawdown": Decimal("0.05"),
            "cagr": 0.10,
            "win_rate": 0.6,
        },
    )
    return insert_backtest_result(
        conn,
        run_id=run_id,
        signal_id=sig_id,
        strategy_id=sid,
        result=bt,
        hold_bars=5,
        fees=0.0003,
        slippage=0.0005,
        init_cash=Decimal("100000"),
        generation=0,
    )


# ─── get_agent_activity_summary ──────────────────────────────────────────────


def test_get_agent_activity_summary_empty_run(db_path: Path) -> None:
    """No experiments → all counts zero, veto_rate is 0.0."""
    run_id = uuid4().hex[:12]
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_id)

    with connect(db_path) as conn:
        result = get_agent_activity_summary(conn, run_id)

    assert result["explorer_proposals"] == 0
    assert result["exploiter_proposals"] == 0
    assert result["critic_vetoes"] == 0
    assert result["veto_rate"] == 0.0


def test_get_agent_activity_summary_counts_by_mutator(db_path: Path) -> None:
    """Counts explorer/exploiter experiments and critic_veto rows correctly."""
    run_id = uuid4().hex[:12]
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_id)
        parent_sid = _seed_strategy(conn, "Parent")
        child_sid = _seed_strategy(conn, "Child1")
        child2_sid = _seed_strategy(conn, "Child2")
        child3_sid = _seed_strategy(conn, "Child3")

        # 2 explorer experiments (accepted=1)
        insert_experiment(
            conn,
            run_id=run_id,
            generation=1,
            parent_strategy_id=parent_sid,
            child_strategy_id=child_sid,
            mutator="explorer",
            mutation_json='{"type":"sma_crossover","fast":6,"slow":18}',
            accepted=1,
            delta_sharpe=0.1,
            composite_score_json='{"delta_sharpe":0.1}',
            reasoning="",
        )
        insert_experiment(
            conn,
            run_id=run_id,
            generation=1,
            parent_strategy_id=parent_sid,
            child_strategy_id=child2_sid,
            mutator="explorer",
            mutation_json='{"type":"sma_crossover","fast":7,"slow":20}',
            accepted=0,
            delta_sharpe=-0.05,
            composite_score_json='{"delta_sharpe":-0.05}',
            reasoning="",
        )
        # 1 exploiter experiment
        insert_experiment(
            conn,
            run_id=run_id,
            generation=1,
            parent_strategy_id=parent_sid,
            child_strategy_id=child3_sid,
            mutator="exploiter",
            mutation_json='{"type":"sma_crossover","fast":5,"slow":16}',
            accepted=1,
            delta_sharpe=0.08,
            composite_score_json='{"delta_sharpe":0.08}',
            reasoning="",
        )
        # 3 critic_veto experiments (child_strategy_id=None)
        for i in range(3):
            insert_experiment(
                conn,
                run_id=run_id,
                generation=1,
                parent_strategy_id=parent_sid,
                child_strategy_id=None,
                mutator="critic_veto",
                mutation_json=f'{{"type":"sma_crossover","fast":{8 + i},"slow":25}}',
                accepted=0,
                delta_sharpe=0.0,
                composite_score_json='{"critic_veto":1.0}',
                reasoning="vetoed",
            )

    with connect(db_path) as conn:
        result = get_agent_activity_summary(conn, run_id)

    assert result["explorer_proposals"] == 2
    assert result["exploiter_proposals"] == 1
    assert result["critic_vetoes"] == 3
    # total proposals going to critic = 2 + 1 + 3 vetoed = 5 total reviewed
    # veto_rate = 3 / (2 + 1 + 3) = 3/6 = 0.5
    assert abs(result["veto_rate"] - 0.5) < 0.001


def test_get_agent_activity_summary_scoped_to_run(db_path: Path) -> None:
    """Summary only counts experiments for the given run_id, not others."""
    run_a = uuid4().hex[:12]
    run_b = uuid4().hex[:12]
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_a)
        insert_run(conn, run_b)
        sid = _seed_strategy(conn)

        insert_experiment(
            conn,
            run_id=run_a,
            generation=1,
            parent_strategy_id=sid,
            child_strategy_id=None,
            mutator="critic_veto",
            mutation_json='{"type":"sma_crossover","fast":9,"slow":25}',
            accepted=0,
            delta_sharpe=0.0,
            composite_score_json='{"critic_veto":1.0}',
            reasoning="vetoed",
        )

    with connect(db_path) as conn:
        result_b = get_agent_activity_summary(conn, run_b)

    assert result_b["critic_vetoes"] == 0


# ─── get_recent_critic_verdicts ───────────────────────────────────────────────


def test_get_recent_critic_verdicts_empty_run(db_path: Path) -> None:
    """No critic_veto rows → empty list."""
    run_id = uuid4().hex[:12]
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_id)

    with connect(db_path) as conn:
        rows = get_recent_critic_verdicts(conn, run_id)

    assert rows == []


def test_get_recent_critic_verdicts_returns_veto_rows(db_path: Path) -> None:
    """Returns critic_veto rows with expected fields."""
    run_id = uuid4().hex[:12]
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_id)
        sid = _seed_strategy(conn)
        insert_experiment(
            conn,
            run_id=run_id,
            generation=1,
            parent_strategy_id=sid,
            child_strategy_id=None,
            mutator="critic_veto",
            mutation_json='{"type":"sma_crossover","fast":9,"slow":25}',
            accepted=0,
            delta_sharpe=0.0,
            composite_score_json='{"critic_veto":1.0}',
            reasoning="parent already tried similar direction",
        )

    with connect(db_path) as conn:
        rows = get_recent_critic_verdicts(conn, run_id)

    assert len(rows) == 1
    row = rows[0]
    assert row["mutator"] == "critic_veto"
    assert row["accepted"] == 0
    assert row["child_strategy_id"] is None
    assert "already tried" in row["reasoning"]
    assert "experiment_id" in row
    assert "generation" in row
    assert "created_at" in row


def test_get_recent_critic_verdicts_limit_honored(db_path: Path) -> None:
    """limit param caps returned rows."""
    run_id = uuid4().hex[:12]
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_id)
        sid = _seed_strategy(conn)
        for i in range(10):
            insert_experiment(
                conn,
                run_id=run_id,
                generation=1,
                parent_strategy_id=sid,
                child_strategy_id=None,
                mutator="critic_veto",
                mutation_json=f'{{"type":"sma_crossover","fast":{8 + i},"slow":25}}',
                accepted=0,
                delta_sharpe=0.0,
                composite_score_json='{"critic_veto":1.0}',
                reasoning="vetoed",
            )

    with connect(db_path) as conn:
        rows = get_recent_critic_verdicts(conn, run_id, limit=3)

    assert len(rows) == 3


def test_get_recent_critic_verdicts_excludes_non_veto_rows(db_path: Path) -> None:
    """Explorer/exploiter/param_delta rows not returned — only critic_veto."""
    run_id = uuid4().hex[:12]
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_id)
        sid = _seed_strategy(conn)
        child_sid = _seed_strategy(conn, "Child")

        # Add explorer experiment (not a critic_veto)
        insert_experiment(
            conn,
            run_id=run_id,
            generation=1,
            parent_strategy_id=sid,
            child_strategy_id=child_sid,
            mutator="explorer",
            mutation_json='{"type":"sma_crossover","fast":6,"slow":18}',
            accepted=1,
            delta_sharpe=0.1,
            composite_score_json='{"delta_sharpe":0.1}',
            reasoning="",
        )
        # Add one critic_veto
        insert_experiment(
            conn,
            run_id=run_id,
            generation=1,
            parent_strategy_id=sid,
            child_strategy_id=None,
            mutator="critic_veto",
            mutation_json='{"type":"sma_crossover","fast":9,"slow":25}',
            accepted=0,
            delta_sharpe=0.0,
            composite_score_json='{"critic_veto":1.0}',
            reasoning="vetoed",
        )

    with connect(db_path) as conn:
        rows = get_recent_critic_verdicts(conn, run_id)

    assert len(rows) == 1
    assert rows[0]["mutator"] == "critic_veto"
