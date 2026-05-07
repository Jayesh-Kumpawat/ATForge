"""Step 11 — mutate_strategies and ratchet_node unit tests.
Step 12 — full loop with max_generations=2 integration test.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from atforge.backtest.engine import BacktestResult
from atforge.data.protocol import OHLCV_COLUMNS
from atforge.evolution.mutators.param_delta import ParamDeltaMutator
from atforge.graph.deps import PipelineDeps
from atforge.graph.nodes_phase2 import (
    make_mutate_strategies,
    make_ratchet_node,
)
from atforge.graph.pipeline import build_pipeline
from atforge.llm.types import LlmRequest, LlmResponse
from atforge.patterns.pandas_ta import SmaCrossover
from atforge.storage.db import connect, init_db, txn
from atforge.storage.repo import (
    insert_backtest_result,
    insert_pattern_signal,
    insert_run,
    upsert_strategy,
)


class _SyntheticProvider:
    name = "synth"

    def fetch_ohlcv(self, symbol, start, end, interval="1d"):
        idx = pd.date_range(start=start, end=end, freq="B")
        n = len(idx)
        rng = np.random.default_rng(seed=hash(symbol) % (2**32))
        close = 100 + rng.normal(0, 1.5, n).cumsum()
        close = close - close.min() + 101
        df = pd.DataFrame(
            {
                "open": close + rng.normal(0, 0.5, n),
                "high": close + rng.uniform(0.1, 1.0, n),
                "low": close - rng.uniform(0.1, 1.0, n),
                "close": close,
                "volume": rng.integers(10_000, 100_000, n).astype(float),
            },
            index=idx,
        )
        df = df[list(OHLCV_COLUMNS)]
        df.index.name = "date"
        return df


def _mock_sma_llm(fast: int = 10, slow: int = 25):
    """Mock LLM that always proposes a specific SMA mutation."""
    resp = json.dumps({"fast": fast, "slow": slow, "reasoning": "test mutation"})

    def _router(req: LlmRequest) -> LlmResponse:
        return LlmResponse(
            text=resp, model="mock", provider="mock", input_tokens=5, output_tokens=10, latency_ms=1
        )

    return _router


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "db.sqlite"
    init_db(p)
    return p


@pytest.fixture
def deps(tmp_path: Path, db_path: Path) -> PipelineDeps:
    return PipelineDeps(
        data_provider=_SyntheticProvider(),
        detectors=(SmaCrossover(fast=5, slow=15),),
        ohlcv_cache_dir=tmp_path / "ohlcv",
        signal_cache_dir=tmp_path / "signals",
        db_path=db_path,
        hold_bars=5,
        init_cash=Decimal("100000"),
        mutators=(ParamDeltaMutator(_mock_sma_llm(fast=10, slow=25)),),
        top_n_parents=3,
    )


# ─── Unit tests for mutate_strategies ────────────────────────────────────────


def _seed_gen0(db_path, run_id, tmp_path):
    """Insert a gen=0 backtest row for SMA_5x15."""
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_id)
        sid = upsert_strategy(
            conn,
            name="SMA_5x15_bullish",
            family="indicator",
            params={"type": "sma_crossover", "fast": 5, "slow": 15},
        )
        ohlcv_path = tmp_path / "ohlcv" / "RELIANCE.parquet"
        ohlcv_path.parent.mkdir(parents=True, exist_ok=True)
        idx = pd.date_range("2024-01-01", periods=50, freq="B")
        pd.DataFrame(
            {
                "open": [100.0] * 50,
                "high": [101.0] * 50,
                "low": [99.0] * 50,
                "close": [100.0 + i * 0.1 for i in range(50)],
                "volume": [10_000.0] * 50,
            },
            index=idx,
        ).to_parquet(ohlcv_path)
        sig_id = insert_pattern_signal(
            conn,
            run_id=run_id,
            strategy_id=sid,
            symbol="RELIANCE",
            n_signals=5,
            first_date=None,
            last_date=None,
            generation=0,
        )
        bt = BacktestResult(
            symbol="RELIANCE",
            pattern_name="SMA_5x15_bullish",
            success=True,
            reason="ok",
            n_trades=8,
            metrics={
                "sharpe": 1.2,
                "sortino": 1.5,
                "total_return": Decimal("0.12"),
                "final_value": Decimal("112000"),
                "max_drawdown": Decimal("0.08"),
                "cagr": 0.12,
                "win_rate": 0.6,
            },
        )
        insert_backtest_result(
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
    return sid


def test_mutate_strategies_registers_child_in_db(deps, db_path, tmp_path):
    run_id = uuid4().hex[:12]
    parent_sid = _seed_gen0(db_path, run_id, tmp_path)

    node = make_mutate_strategies(deps)
    state = {
        "run_id": run_id,
        "generation": 0,
        "max_generations": 2,  # allows one loop
        "mutations": [],
        "detector_configs": [{"type": "sma_crossover", "fast": 5, "slow": 15}],
    }
    result = node(state)

    mutations = result.get("mutations", [])
    assert len(mutations) == 1, f"expected 1 mutation, got {mutations}"
    m = mutations[0]
    assert m["parent_strategy_id"] == parent_sid
    assert m["mutator"] == "param_delta"
    assert m["generation"] == 0

    # Child strategy should be registered in DB
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT strategy_id, name FROM strategies WHERE strategy_id=?",
            (m["child_strategy_id"],),
        ).fetchone()
    assert row is not None
    assert "SMA_10x25" in row["name"]


def test_mutate_strategies_skips_when_at_max_gen(deps, db_path, tmp_path):
    """At max_generations=1, mutate_strategies returns {} (no next generation)."""
    run_id = uuid4().hex[:12]
    _seed_gen0(db_path, run_id, tmp_path)

    node = make_mutate_strategies(deps)
    result = node(
        {
            "run_id": run_id,
            "generation": 0,
            "max_generations": 1,  # 0+1 >= 1 → skip
            "mutations": [],
            "detector_configs": [{"type": "sma_crossover", "fast": 5, "slow": 15}],
        }
    )
    assert result == {}


# ─── Unit tests for ratchet_node ─────────────────────────────────────────────


def _seed_child_gen1(db_path, run_id, child_sid, sharpe: float = 1.4):
    """Insert gen=1 backtests for a given child strategy."""
    with connect(db_path) as conn, txn(conn):
        sig_id = insert_pattern_signal(
            conn,
            run_id=run_id,
            strategy_id=child_sid,
            symbol="RELIANCE",
            n_signals=8,
            first_date=None,
            last_date=None,
            generation=1,
        )
        bt = BacktestResult(
            symbol="RELIANCE",
            pattern_name="SMA_10x25_bullish",
            success=True,
            reason="ok",
            n_trades=12,
            metrics={
                "sharpe": sharpe,
                "sortino": sharpe * 1.2,
                "total_return": Decimal("0.15"),
                "final_value": Decimal("115000"),
                "max_drawdown": Decimal("0.07"),
                "cagr": 0.15,
                "win_rate": 0.65,
            },
        )
        insert_backtest_result(
            conn,
            run_id=run_id,
            signal_id=sig_id,
            strategy_id=child_sid,
            result=bt,
            hold_bars=5,
            fees=0.0003,
            slippage=0.0005,
            init_cash=Decimal("100000"),
            generation=1,
        )


def test_ratchet_node_writes_experiment_rows(deps, db_path, tmp_path):
    run_id = uuid4().hex[:12]
    parent_sid = _seed_gen0(db_path, run_id, tmp_path)

    # Register a child strategy
    with connect(db_path) as conn, txn(conn):
        child_sid = upsert_strategy(
            conn,
            name="SMA_10x25_bullish",
            family="indicator",
            params={"type": "sma_crossover", "fast": 10, "slow": 25},
        )
    _seed_child_gen1(db_path, run_id, child_sid, sharpe=1.4)

    node = make_ratchet_node(deps)
    state = {
        "run_id": run_id,
        "generation": 1,
        "mutations": [
            {
                "generation": 0,
                "parent_strategy_id": parent_sid,
                "child_strategy_id": child_sid,
                "mutator": "param_delta",
                "mutation_json": '{"type":"sma_crossover","fast":10,"slow":25}',
            }
        ],
    }
    node(state)

    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT accepted, delta_sharpe FROM experiments WHERE run_id=?", (run_id,)
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["accepted"] in (0, 1)


def test_ratchet_accepts_improved_child(deps, db_path, tmp_path):
    run_id = uuid4().hex[:12]
    parent_sid = _seed_gen0(db_path, run_id, tmp_path)  # parent sharpe=1.2

    with connect(db_path) as conn, txn(conn):
        child_sid = upsert_strategy(
            conn,
            name="SMA_10x25_bullish",
            family="indicator",
            params={"type": "sma_crossover", "fast": 10, "slow": 25},
        )
    _seed_child_gen1(db_path, run_id, child_sid, sharpe=1.4)  # delta=+0.2 > threshold 0.05

    node = make_ratchet_node(deps)
    node(
        {
            "run_id": run_id,
            "generation": 1,
            "mutations": [
                {
                    "generation": 0,
                    "parent_strategy_id": parent_sid,
                    "child_strategy_id": child_sid,
                    "mutator": "param_delta",
                    "mutation_json": "{}",
                }
            ],
        }
    )

    with connect(db_path) as conn:
        row = conn.execute("SELECT accepted FROM experiments WHERE run_id=?", (run_id,)).fetchone()
    assert row["accepted"] == 1


def test_ratchet_noop_on_generation_zero(deps, db_path):
    run_id = uuid4().hex[:12]
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_id)

    node = make_ratchet_node(deps)
    result = node({"run_id": run_id, "generation": 0, "mutations": []})
    assert result == {}

    with connect(db_path) as conn:
        n = conn.execute("SELECT COUNT(*) c FROM experiments WHERE run_id=?", (run_id,)).fetchone()[
            "c"
        ]
    assert n == 0


# ─── Step 12: full loop integration test ─────────────────────────────────────


def test_full_pipeline_two_generations(tmp_path: Path):
    """max_generations=2 → gen=0 backtests + gen=1 backtests + experiments rows."""
    db_path = tmp_path / "db.sqlite"
    init_db(db_path)

    pipeline_deps = PipelineDeps(
        data_provider=_SyntheticProvider(),
        detectors=(SmaCrossover(fast=5, slow=15),),
        ohlcv_cache_dir=tmp_path / "ohlcv",
        signal_cache_dir=tmp_path / "signals",
        db_path=db_path,
        hold_bars=5,
        init_cash=Decimal("100000"),
        mutators=(ParamDeltaMutator(_mock_sma_llm(fast=8, slow=22)),),
        top_n_parents=3,
    )
    pipeline = build_pipeline(pipeline_deps)
    run_id = uuid4().hex[:12]
    pipeline.invoke(
        {
            "run_id": run_id,
            "universe": ["RELIANCE"],
            "start_iso": date(2024, 1, 1).isoformat(),
            "end_iso": date(2024, 12, 31).isoformat(),
            "max_generations": 2,
        }
    )

    with connect(db_path) as conn:
        gen0_rows = conn.execute(
            "SELECT COUNT(*) c FROM backtest_runs WHERE run_id=? AND generation=0", (run_id,)
        ).fetchone()["c"]
        gen1_rows = conn.execute(
            "SELECT COUNT(*) c FROM backtest_runs WHERE run_id=? AND generation=1", (run_id,)
        ).fetchone()["c"]
        exp_rows = conn.execute(
            "SELECT accepted FROM experiments WHERE run_id=?", (run_id,)
        ).fetchall()

    assert gen0_rows >= 1, "generation=0 backtests missing"
    assert gen1_rows >= 1, "generation=1 backtests missing — loop didn't fire"
    assert len(exp_rows) >= 1, "no experiment rows written — ratchet didn't fire"
    for row in exp_rows:
        assert row["accepted"] in (0, 1), f"accepted not 0/1: {row['accepted']}"
