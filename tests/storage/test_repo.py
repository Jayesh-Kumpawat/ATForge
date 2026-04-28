from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from atforge.backtest.engine import BacktestResult
from atforge.storage.db import connect, init_db, txn
from atforge.storage.repo import (
    finish_run,
    insert_backtest_result,
    insert_pattern_signal,
    insert_run,
    top_rankings,
    upsert_strategy,
)


@pytest.fixture
def db(tmp_db_path: Path) -> Path:
    init_db(tmp_db_path)
    return tmp_db_path


def test_init_db_creates_tables(db: Path) -> None:
    with connect(db) as conn:
        tables = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    for t in ["runs", "strategies", "pattern_signals", "backtest_runs", "experiments"]:
        assert t in tables


def test_wal_mode_enabled(db: Path) -> None:
    with connect(db) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_upsert_strategy_is_idempotent(db: Path) -> None:
    with connect(db) as conn:
        a = upsert_strategy(conn, "sma_x", "indicator", {"fast": 10, "slow": 30})
        b = upsert_strategy(conn, "sma_x", "indicator", {"fast": 10, "slow": 30})
        c = upsert_strategy(conn, "sma_x", "indicator", {"fast": 5, "slow": 20})
    assert a == b
    assert a != c


def test_insert_and_fetch_backtest(db: Path) -> None:
    with connect(db) as conn, txn(conn):
        insert_run(conn, "r-1")
        sid = upsert_strategy(conn, "sma_x", "indicator", {"fast": 10, "slow": 30})
        signal_id = insert_pattern_signal(
            conn,
            run_id="r-1",
            strategy_id=sid,
            symbol="RELIANCE",
            n_signals=3,
            first_date="2025-01-01",
            last_date="2025-01-20",
        )
        res = BacktestResult(
            success=True,
            pattern_name="sma_x",
            symbol="RELIANCE",
            metrics={
                "total_return": Decimal("0.1234"),
                "final_value": Decimal("112340.5"),
                "max_drawdown": Decimal("0.05"),
                "sharpe": 1.42,
                "sortino": 1.9,
                "cagr": 0.25,
                "win_rate": 0.6,
            },
            n_trades=5,
        )
        insert_backtest_result(
            conn,
            run_id="r-1",
            signal_id=signal_id,
            strategy_id=sid,
            result=res,
            hold_bars=10,
            fees=0.0003,
            slippage=0.0005,
            init_cash=Decimal("100000"),
        )
        finish_run(conn, "r-1", status="success")

    with connect(db) as conn:
        rows = top_rankings(conn, limit=10)
    assert len(rows) == 1
    r = rows[0]
    assert r["symbol"] == "RELIANCE"
    assert r["strategy_name"] == "sma_x"
    # Decimal round-trips via TEXT
    assert Decimal(r["total_return"]) == Decimal("0.1234")
    assert Decimal(r["max_drawdown"]) == Decimal("0.05")


def test_failure_results_are_excluded_from_rankings(db: Path) -> None:
    with connect(db) as conn, txn(conn):
        insert_run(conn, "r-2")
        sid = upsert_strategy(conn, "bad", "indicator", {})
        bad = BacktestResult(success=False, pattern_name="bad", symbol="X", reason="no trades")
        insert_backtest_result(
            conn,
            run_id="r-2",
            signal_id=None,
            strategy_id=sid,
            result=bad,
            hold_bars=10,
            fees=0.0,
            slippage=0.0,
            init_cash=Decimal("100000"),
        )
    with connect(db) as conn:
        assert top_rankings(conn) == []


def test_foreign_key_cascade_on_run_delete(db: Path) -> None:
    with connect(db) as conn, txn(conn):
        insert_run(conn, "r-3")
        sid = upsert_strategy(conn, "s", "indicator", {})
        insert_pattern_signal(
            conn,
            run_id="r-3",
            strategy_id=sid,
            symbol="X",
            n_signals=1,
            first_date=None,
            last_date=None,
        )
    with connect(db) as conn, txn(conn):
        conn.execute("DELETE FROM runs WHERE run_id=?", ("r-3",))
    with connect(db) as conn:
        rows = conn.execute("SELECT COUNT(*) c FROM pattern_signals").fetchone()
        assert rows["c"] == 0
