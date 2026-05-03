"""Step 10 — ratchet pure-function and DB aggregation tests."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from atforge.backtest.engine import BacktestResult
from atforge.evolution.ratchet import build_evaluation_result, judge_mutation
from atforge.evolution.types import EvaluationResult, RatchetThresholds
from atforge.storage.db import connect, init_db, txn
from atforge.storage.repo import (
    insert_backtest_result,
    insert_pattern_signal,
    insert_run,
    upsert_strategy,
)


def _result(
    strategy_id: int = 1,
    mean_sharpe: float = 1.0,
    mean_sortino: float = 1.5,
    total_n_trades: int = 20,
    max_drawdown: str = "0.10",
) -> EvaluationResult:
    return EvaluationResult(
        strategy_id=strategy_id,
        run_id="test",
        generation=0,
        mean_sharpe=mean_sharpe,
        mean_sortino=mean_sortino,
        total_n_trades=total_n_trades,
        max_drawdown=Decimal(max_drawdown),
        n_symbols=2,
    )


def test_judge_accepts_clear_improvement():
    parent = _result(mean_sharpe=1.0, mean_sortino=1.0, total_n_trades=10, max_drawdown="0.10")
    child = _result(mean_sharpe=1.2, mean_sortino=1.3, total_n_trades=15, max_drawdown="0.09")
    thresholds = RatchetThresholds()
    verdict = judge_mutation(parent, child, thresholds)
    assert verdict.accepted is True
    assert verdict.delta_sharpe == pytest.approx(0.2)
    assert verdict.delta_sortino == pytest.approx(0.3)


def test_judge_rejects_insufficient_sharpe_improvement():
    parent = _result(mean_sharpe=1.0, mean_sortino=1.0, total_n_trades=10)
    child = _result(mean_sharpe=1.02, mean_sortino=1.1, total_n_trades=15)  # delta_sharpe=0.02 < 0.05
    verdict = judge_mutation(parent, child, RatchetThresholds())
    assert verdict.accepted is False
    assert "sharpe" in verdict.reasoning


def test_judge_rejects_drawdown_regression():
    parent = _result(max_drawdown="0.10")
    child = _result(mean_sharpe=1.2, mean_sortino=1.3, total_n_trades=20, max_drawdown="0.25")
    # child dd = 0.25 > parent * 1.10 = 0.11
    verdict = judge_mutation(parent, child, RatchetThresholds())
    assert verdict.accepted is False
    assert "dd_ratio" in verdict.reasoning


def test_judge_rejects_too_few_trades():
    parent = _result(mean_sharpe=1.0, mean_sortino=1.0, total_n_trades=10)
    child = _result(mean_sharpe=1.2, mean_sortino=1.2, total_n_trades=2)
    verdict = judge_mutation(parent, child, RatchetThresholds(min_n_trades=5))
    assert verdict.accepted is False
    assert "n_trades" in verdict.reasoning


def test_judge_composite_score_has_expected_keys():
    parent = _result()
    child = _result(mean_sharpe=1.5, mean_sortino=2.0, total_n_trades=25, max_drawdown="0.08")
    verdict = judge_mutation(parent, child, RatchetThresholds())
    assert "delta_sharpe" in verdict.composite_score
    assert "delta_sortino" in verdict.composite_score
    assert "dd_ratio" in verdict.composite_score
    assert "child_n_trades" in verdict.composite_score


def test_judge_zero_parent_drawdown():
    parent = _result(max_drawdown="0")
    child = _result(mean_sharpe=1.5, mean_sortino=1.5, total_n_trades=20, max_drawdown="0")
    verdict = judge_mutation(parent, child, RatchetThresholds())
    assert verdict.dd_ratio == pytest.approx(1.0)


@pytest.fixture
def db_with_backtests(tmp_path: Path):
    db_path = tmp_path / "db.sqlite"
    init_db(db_path)
    run_id = "run001"
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_id)
        sid = upsert_strategy(
            conn, name="SMA_5x20", family="indicator",
            params={"type": "sma_crossover", "fast": 5, "slow": 20},
        )
        for symbol, sharpe, sortino in [("RELIANCE", 1.2, 1.5), ("TCS", 0.9, 1.1)]:
            sig_id = insert_pattern_signal(
                conn, run_id=run_id, strategy_id=sid, symbol=symbol,
                n_signals=5, first_date=None, last_date=None,
            )
            bt = BacktestResult(
                symbol=symbol,
                pattern_name="SMA_5x20",
                success=True,
                reason="ok",
                n_trades=10,
                metrics={
                    "sharpe": sharpe,
                    "sortino": sortino,
                    "total_return": Decimal("0.15"),
                    "final_value": Decimal("115000"),
                    "max_drawdown": Decimal("0.08"),
                    "cagr": 0.15,
                    "win_rate": 0.6,
                },
            )
            insert_backtest_result(
                conn, run_id=run_id, signal_id=sig_id, strategy_id=sid,
                result=bt, hold_bars=5, fees=0.0003, slippage=0.0005,
                init_cash=Decimal("100000"),
            )
    return db_path, run_id, sid


def test_build_evaluation_result_aggregates_correctly(db_with_backtests):
    db_path, run_id, sid = db_with_backtests
    with connect(db_path) as conn:
        er = build_evaluation_result(conn, strategy_id=sid, run_id=run_id, generation=0)
    assert er is not None
    assert er.n_symbols == 2
    assert er.mean_sharpe == pytest.approx((1.2 + 0.9) / 2)
    assert er.mean_sortino == pytest.approx((1.5 + 1.1) / 2)
    assert er.total_n_trades == 20
    assert er.max_drawdown == Decimal("0.08")


def test_build_evaluation_result_populates_per_symbol_sharpe(db_with_backtests):
    db_path, run_id, sid = db_with_backtests
    with connect(db_path) as conn:
        er = build_evaluation_result(conn, strategy_id=sid, run_id=run_id, generation=0)
    assert er is not None
    assert "RELIANCE" in er.per_symbol_sharpe
    assert "TCS" in er.per_symbol_sharpe
    assert er.per_symbol_sharpe["RELIANCE"] == pytest.approx(1.2)
    assert er.per_symbol_sharpe["TCS"] == pytest.approx(0.9)


def test_build_evaluation_result_none_when_no_rows(db_with_backtests):
    db_path, run_id, _sid = db_with_backtests
    with connect(db_path) as conn:
        er = build_evaluation_result(conn, strategy_id=999, run_id=run_id, generation=0)
    assert er is None


# ── per-symbol regression tests ───────────────────────────────────────────────

def _result_with_symbols(
    mean_sharpe: float = 1.0,
    mean_sortino: float = 1.5,
    total_n_trades: int = 20,
    max_drawdown: str = "0.10",
    per_symbol_sharpe: dict | None = None,
) -> EvaluationResult:
    return EvaluationResult(
        strategy_id=1,
        run_id="test",
        generation=0,
        mean_sharpe=mean_sharpe,
        mean_sortino=mean_sortino,
        total_n_trades=total_n_trades,
        max_drawdown=Decimal(max_drawdown),
        n_symbols=2,
        per_symbol_sharpe=per_symbol_sharpe or {},
    )


def test_judge_accepts_when_no_symbol_data():
    """Backward compat: empty per_symbol_sharpe skips the regression check."""
    parent = _result_with_symbols(mean_sharpe=1.0, per_symbol_sharpe={})
    child = _result_with_symbols(mean_sharpe=1.1, mean_sortino=1.6, total_n_trades=20, per_symbol_sharpe={})
    verdict = judge_mutation(parent, child, RatchetThresholds())
    assert verdict.accepted is True


def test_judge_accepts_when_all_symbols_improve():
    parent = _result_with_symbols(
        per_symbol_sharpe={"RELIANCE": 1.2, "TCS": 0.9},
    )
    child = _result_with_symbols(
        mean_sharpe=1.15, mean_sortino=1.6, total_n_trades=20,
        per_symbol_sharpe={"RELIANCE": 1.4, "TCS": 0.9},
    )
    verdict = judge_mutation(parent, child, RatchetThresholds())
    assert verdict.accepted is True
    assert verdict.composite_score["symbol_ok"] == 1.0


def test_judge_rejects_when_one_symbol_regresses_severely():
    """Aggregate improves but TCS drops 0.8 — exceeds max_symbol_regression=0.5."""
    parent = _result_with_symbols(
        mean_sharpe=1.0,
        per_symbol_sharpe={"RELIANCE": 1.5, "TCS": 0.5},
    )
    child = _result_with_symbols(
        mean_sharpe=1.1,  # aggregate +0.1 (above min_delta_sharpe=0.05)
        mean_sortino=1.6,
        total_n_trades=20,
        per_symbol_sharpe={"RELIANCE": 2.0, "TCS": -0.3},  # TCS drop = -0.8
    )
    verdict = judge_mutation(parent, child, RatchetThresholds(max_symbol_regression=0.5))
    assert verdict.accepted is False
    assert "symbol_regression" in verdict.reasoning
    assert "TCS" in verdict.reasoning
    assert verdict.composite_score["symbol_ok"] == 0.0


def test_judge_accepts_when_regression_within_threshold():
    """TCS drops 0.3 — below max_symbol_regression=0.5, so accepted."""
    parent = _result_with_symbols(
        mean_sharpe=1.0,
        per_symbol_sharpe={"RELIANCE": 1.5, "TCS": 0.8},
    )
    child = _result_with_symbols(
        mean_sharpe=1.1, mean_sortino=1.6, total_n_trades=20,
        per_symbol_sharpe={"RELIANCE": 1.9, "TCS": 0.5},  # TCS drop = -0.3
    )
    verdict = judge_mutation(parent, child, RatchetThresholds(max_symbol_regression=0.5))
    assert verdict.accepted is True


def test_judge_symbol_regression_disabled_with_inf():
    """max_symbol_regression=inf disables per-symbol check entirely."""
    parent = _result_with_symbols(per_symbol_sharpe={"RELIANCE": 1.0, "TCS": 1.0})
    child = _result_with_symbols(
        mean_sharpe=1.1, mean_sortino=1.6, total_n_trades=20,
        per_symbol_sharpe={"RELIANCE": 2.0, "TCS": -5.0},  # catastrophic TCS drop
    )
    verdict = judge_mutation(parent, child, RatchetThresholds(max_symbol_regression=float("inf")))
    assert verdict.accepted is True  # no symbol check fired


def test_composite_score_has_symbol_fields():
    parent = _result_with_symbols(per_symbol_sharpe={"RELIANCE": 1.0})
    child = _result_with_symbols(
        mean_sharpe=1.1, mean_sortino=1.6, total_n_trades=20,
        per_symbol_sharpe={"RELIANCE": 1.1},
    )
    verdict = judge_mutation(parent, child, RatchetThresholds())
    assert "symbol_ok" in verdict.composite_score
    assert "worst_symbol_regression" in verdict.composite_score
