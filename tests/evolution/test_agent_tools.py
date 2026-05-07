from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from atforge.backtest.engine import BacktestResult
from atforge.evolution.agent_tools import ToolDefinition, build_research_tools
from atforge.storage.db import connect, init_db, txn
from atforge.storage.repo import (
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


@pytest.fixture
def tools() -> list[ToolDefinition]:
    return build_research_tools()


# ── structural tests ──────────────────────────────────────────────────────────


def test_build_returns_5_tools(tools: list[ToolDefinition]) -> None:
    assert len(tools) == 5


def test_each_tool_has_unique_name(tools: list[ToolDefinition]) -> None:
    names = [t.spec.name for t in tools]
    assert len(names) == len(set(names))


def test_expected_tool_names_present(tools: list[ToolDefinition]) -> None:
    names = {t.spec.name for t in tools}
    expected = {
        "query_top_strategies",
        "query_strategy_details",
        "query_strategy_lineage",
        "query_pattern_performance",
        "query_recent_experiments",
    }
    assert names == expected


def test_each_tool_spec_has_valid_json_schema(tools: list[ToolDefinition]) -> None:
    for td in tools:
        Draft7Validator.check_schema(td.spec.parameters_schema)


# ── handler tests (real DB) ───────────────────────────────────────────────────


def _handler_for(tools: list[ToolDefinition], name: str):
    return next(t.handler for t in tools if t.spec.name == name)


def _seed_db(db: Path) -> tuple[str, int]:
    """Insert a run + strategy + backtest, return (run_id, strategy_id)."""
    run_id = "r-agent-1"
    with connect(db) as conn, txn(conn):
        insert_run(conn, run_id)
        sid = upsert_strategy(conn, "sma_test", "indicator", {"fast": 10, "slow": 30})
        sig_id = insert_pattern_signal(
            conn,
            run_id=run_id,
            strategy_id=sid,
            symbol="RELIANCE",
            n_signals=5,
            first_date="2024-01-01",
            last_date="2024-12-31",
        )
        insert_backtest_result(
            conn,
            run_id=run_id,
            signal_id=sig_id,
            strategy_id=sid,
            result=BacktestResult(
                success=True,
                pattern_name="sma_test",
                symbol="RELIANCE",
                metrics={
                    "total_return": Decimal("0.12"),
                    "final_value": Decimal("112000"),
                    "max_drawdown": Decimal("-0.05"),
                    "sharpe": 1.8,
                    "sortino": 2.1,
                    "cagr": 0.15,
                    "win_rate": 0.6,
                },
                n_trades=10,
            ),
            hold_bars=10,
            fees=0.0,
            slippage=0.0,
            init_cash=Decimal("100000"),
        )
    return run_id, sid


def test_query_top_strategies_handler(tools, db: Path) -> None:
    _run_id, _ = _seed_db(db)
    handler = _handler_for(tools, "query_top_strategies")
    with connect(db) as conn:
        result = handler({"limit": 5}, conn)
    assert "strategies" in result
    assert len(result["strategies"]) == 1
    assert result["strategies"][0]["strategy_name"] == "sma_test"


def test_query_strategy_details_handler(tools, db: Path) -> None:
    _, sid = _seed_db(db)
    handler = _handler_for(tools, "query_strategy_details")
    with connect(db) as conn:
        result = handler({"strategy_id": sid}, conn)
    assert result["strategy"] is not None
    assert result["strategy"]["name"] == "sma_test"


def test_query_recent_experiments_handler(tools, db: Path) -> None:
    run_id, sid = _seed_db(db)
    child_id = None
    with connect(db) as conn, txn(conn):
        child_id = upsert_strategy(conn, "sma_child", "indicator", {"fast": 12, "slow": 30})
        insert_experiment(
            conn,
            run_id=run_id,
            generation=1,
            parent_strategy_id=sid,
            child_strategy_id=child_id,
            mutator="param_delta",
            mutation_json="{}",
            accepted=1,
            delta_sharpe=0.3,
            composite_score_json="{}",
            reasoning="better",
        )
    handler = _handler_for(tools, "query_recent_experiments")
    with connect(db) as conn:
        result = handler({"run_id": run_id}, conn)
    assert len(result["experiments"]) == 1
    assert result["experiments"][0]["accepted"] == 1


def test_query_recent_experiments_accepted_only_filter(tools, db: Path) -> None:
    run_id, sid = _seed_db(db)
    with connect(db) as conn, txn(conn):
        child_id = upsert_strategy(conn, "sma_bad", "indicator", {"fast": 8, "slow": 30})
        insert_experiment(
            conn,
            run_id=run_id,
            generation=1,
            parent_strategy_id=sid,
            child_strategy_id=child_id,
            mutator="param_delta",
            mutation_json="{}",
            accepted=0,
            delta_sharpe=-0.1,
            composite_score_json="{}",
            reasoning="worse",
        )
    handler = _handler_for(tools, "query_recent_experiments")
    with connect(db) as conn:
        all_result = handler({"run_id": run_id, "accepted_only": False}, conn)
        accepted_result = handler({"run_id": run_id, "accepted_only": True}, conn)
    assert len(all_result["experiments"]) == 1
    assert len(accepted_result["experiments"]) == 0


def test_handler_extra_args_ignored_gracefully(tools, db: Path) -> None:
    _seed_db(db)
    handler = _handler_for(tools, "query_top_strategies")
    with connect(db) as conn:
        result = handler({"limit": 3, "unexpected_arg": "ignored"}, conn)
    assert "strategies" in result


def test_all_handlers_return_json_serializable(tools, db: Path) -> None:
    run_id, sid = _seed_db(db)
    calls = [
        ("query_top_strategies", {"limit": 5}),
        ("query_strategy_details", {"strategy_id": sid}),
        ("query_strategy_lineage", {"strategy_id": sid, "max_depth": 2}),
        ("query_pattern_performance", {"strategy_id": sid}),
        ("query_recent_experiments", {"run_id": run_id}),
    ]
    with connect(db) as conn:
        for name, args in calls:
            handler = _handler_for(tools, name)
            result = handler(args, conn)
            json.dumps(result)  # must not raise
