from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from atforge.backtest.engine import BacktestResult
from atforge.storage.db import connect, init_db, txn
from atforge.storage.repo import (
    get_mutation_tree,
    get_pattern_symbol_breakdown,
    get_strategy_children,
    insert_backtest_result,
    insert_experiment,
    insert_pattern_signal,
    insert_run,
    upsert_strategy,
)


@pytest.fixture
def db(tmp_db_path: Path) -> Path:
    init_db(tmp_db_path)
    return tmp_db_path


def _make_backtest(symbol: str = "RELIANCE", sharpe: float = 1.5) -> BacktestResult:
    return BacktestResult(
        success=True,
        pattern_name="sma_x",
        symbol=symbol,
        metrics={
            "total_return": Decimal("0.10"),
            "final_value": Decimal("110000"),
            "max_drawdown": Decimal("-0.05"),
            "sharpe": sharpe,
            "sortino": 1.8,
            "cagr": 0.15,
            "win_rate": 0.6,
        },
        n_trades=10,
    )


def _seed(conn, run_id: str = "r-1") -> tuple[int, int, int]:
    """Insert run + parent + child strategies, return (parent_id, child_id, signal_id)."""
    insert_run(conn, run_id)
    parent_id = upsert_strategy(conn, "sma_parent", "indicator", {"fast": 10, "slow": 30})
    child_id = upsert_strategy(conn, "sma_child", "indicator", {"fast": 12, "slow": 30})
    signal_id = insert_pattern_signal(
        conn,
        run_id=run_id,
        strategy_id=parent_id,
        symbol="RELIANCE",
        n_signals=3,
        first_date="2024-01-01",
        last_date="2024-12-31",
    )
    return parent_id, child_id, signal_id


# ── get_strategy_children ─────────────────────────────────────────────────────


def test_children_empty_when_no_experiments(db: Path) -> None:
    with connect(db) as conn, txn(conn):
        parent_id = upsert_strategy(conn, "lone", "indicator", {})
    with connect(db) as conn:
        assert get_strategy_children(conn, parent_id) == []


def test_children_returns_accepted_child(db: Path) -> None:
    with connect(db) as conn, txn(conn):
        parent_id, child_id, _ = _seed(conn)
        insert_experiment(
            conn,
            run_id="r-1",
            generation=1,
            parent_strategy_id=parent_id,
            child_strategy_id=child_id,
            mutator="param_delta",
            mutation_json="{}",
            accepted=1,
            delta_sharpe=0.3,
            composite_score_json="{}",
            reasoning="better",
        )
    with connect(db) as conn:
        rows = get_strategy_children(conn, parent_id, accepted_only=True)
    assert len(rows) == 1
    assert rows[0]["strategy_id"] == child_id
    assert rows[0]["accepted"] == 1


def test_children_accepted_only_filter_excludes_rejected(db: Path) -> None:
    with connect(db) as conn, txn(conn):
        parent_id, child_id, _ = _seed(conn)
        insert_experiment(
            conn,
            run_id="r-1",
            generation=1,
            parent_strategy_id=parent_id,
            child_strategy_id=child_id,
            mutator="param_delta",
            mutation_json="{}",
            accepted=0,
            delta_sharpe=-0.1,
            composite_score_json="{}",
            reasoning="worse",
        )
    with connect(db) as conn:
        assert get_strategy_children(conn, parent_id, accepted_only=True) == []
        rows = get_strategy_children(conn, parent_id, accepted_only=False)
        assert len(rows) == 1
        assert rows[0]["accepted"] == 0


def test_children_nonexistent_parent_returns_empty(db: Path) -> None:
    with connect(db) as conn:
        assert get_strategy_children(conn, 99999) == []


# ── get_pattern_symbol_breakdown ─────────────────────────────────────────────


def test_symbol_breakdown_empty_without_backtests(db: Path) -> None:
    with connect(db) as conn, txn(conn):
        sid = upsert_strategy(conn, "s", "indicator", {})
    with connect(db) as conn:
        assert get_pattern_symbol_breakdown(conn, sid) == []


def test_symbol_breakdown_aggregates_per_symbol(db: Path) -> None:
    with connect(db) as conn, txn(conn):
        insert_run(conn, "r-1")
        sid = upsert_strategy(conn, "sma_x", "indicator", {"fast": 10, "slow": 30})
        for symbol, sharpe in [("RELIANCE", 1.2), ("TCS", 2.1)]:
            sig_id = insert_pattern_signal(
                conn,
                run_id="r-1",
                strategy_id=sid,
                symbol=symbol,
                n_signals=5,
                first_date="2024-01-01",
                last_date="2024-12-31",
            )
            insert_backtest_result(
                conn,
                run_id="r-1",
                signal_id=sig_id,
                strategy_id=sid,
                result=_make_backtest(symbol, sharpe),
                hold_bars=10,
                fees=0.0,
                slippage=0.0,
                init_cash=Decimal("100000"),
            )
    with connect(db) as conn:
        rows = get_pattern_symbol_breakdown(conn, sid)
    assert len(rows) == 2
    symbols = {r["symbol"] for r in rows}
    assert symbols == {"RELIANCE", "TCS"}
    tcs_row = next(r for r in rows if r["symbol"] == "TCS")
    assert tcs_row["avg_sharpe"] == pytest.approx(2.1)
    assert tcs_row["n_backtests"] == 1


# ── get_mutation_tree ─────────────────────────────────────────────────────────


def test_mutation_tree_empty_for_no_children(db: Path) -> None:
    with connect(db) as conn, txn(conn):
        sid = upsert_strategy(conn, "root", "indicator", {})
    with connect(db) as conn:
        assert get_mutation_tree(conn, sid) == []


def test_mutation_tree_depth_limit_respected(db: Path) -> None:
    """Chain: root → A → B → C. depth=1 should only return depth-0 edge (root→A)."""
    with connect(db) as conn, txn(conn):
        insert_run(conn, "r-1")
        root = upsert_strategy(conn, "root", "indicator", {"v": 0})
        a = upsert_strategy(conn, "a", "indicator", {"v": 1})
        b = upsert_strategy(conn, "b", "indicator", {"v": 2})
        c = upsert_strategy(conn, "c", "indicator", {"v": 3})

        def _exp(parent: int, child: int) -> None:
            insert_experiment(
                conn,
                run_id="r-1",
                generation=1,
                parent_strategy_id=parent,
                child_strategy_id=child,
                mutator="param_delta",
                mutation_json="{}",
                accepted=1,
                delta_sharpe=0.1,
                composite_score_json="{}",
                reasoning="ok",
            )

        _exp(root, a)
        _exp(a, b)
        _exp(b, c)

    with connect(db) as conn:
        rows_depth1 = get_mutation_tree(conn, root, max_depth=1)
        rows_full = get_mutation_tree(conn, root, max_depth=5)

    assert len(rows_depth1) == 1
    assert rows_depth1[0]["child_strategy_id"] == a
    assert rows_depth1[0]["depth"] == 0

    assert len(rows_full) == 3
    depths = [r["depth"] for r in rows_full]
    assert depths == [0, 1, 2]
