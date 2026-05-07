"""Phase 7 — critic_node logic tests.

Covers:
  - insert_experiment accepts null child_strategy_id (critic_veto rows)
  - EvtCriticVerdict exists in PipelineEvent union
  - CriticVerdict Pydantic model validates accept/veto
  - critic_node vetoes proposals when mock LLM returns veto verdict
  - vetoed proposals logged to experiments table with mutator='critic_veto'
  - EvtCriticVerdict emitted per proposal
  - LLM failure → proposal passes through (safe default)
  - empty proposals → noop (no DB writes, no events)
  - PipelineDeps.llm_router field exists with None default
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from atforge.backtest.engine import BacktestResult
from atforge.data.protocol import OHLCV_COLUMNS
from atforge.graph.deps import PipelineDeps
from atforge.graph.events import EventBus
from atforge.graph.nodes_a2 import make_critic_node
from atforge.llm.types import LlmRequest, LlmResponse
from atforge.patterns.pandas_ta import SmaCrossover
from atforge.storage.db import connect, init_db, txn
from atforge.storage.repo import (
    insert_backtest_result,
    insert_experiment,
    insert_pattern_signal,
    insert_run,
    upsert_strategy,
)

# ─── Helpers ─────────────────────────────────────────────────────────────────


class _SyntheticProvider:
    name = "synth"

    def fetch_ohlcv(self, symbol, start, end, interval="1d"):
        idx = pd.date_range(start=start, end=end, freq="B")
        n = len(idx)
        rng = np.random.default_rng(seed=42)
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


def _seed_parent(db_path: Path, run_id: str) -> int:
    """Seed a parent strategy + backtest for the critic to query."""
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_id)
        sid = upsert_strategy(
            conn,
            name="SMA_5x15_bullish",
            family="indicator",
            params={"type": "sma_crossover", "fast": 5, "slow": 15},
        )
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


def _make_proposal(parent_sid: int, child_config: dict, generation: int = 0) -> dict:
    fp = f"{parent_sid}:{json.dumps(child_config, sort_keys=True)}"
    return {
        "generation": generation,
        "parent_strategy_id": parent_sid,
        "child_config": child_config,
        "reasoning": "test proposal",
        "role": "explorer",
        "fingerprint": fp,
    }


def _veto_llm(reason: str = "parent already tried this direction"):
    """LLM that always returns a veto verdict."""
    payload = json.dumps({"verdict": "veto", "reason": reason})

    def _router(req: LlmRequest) -> LlmResponse:
        return LlmResponse(
            text=payload,
            model="mock",
            provider="mock",
            input_tokens=5,
            output_tokens=10,
            latency_ms=1,
        )

    return _router


def _accept_llm():
    """LLM that always returns an accept verdict."""
    payload = json.dumps({"verdict": "accept", "reason": "looks promising"})

    def _router(req: LlmRequest) -> LlmResponse:
        return LlmResponse(
            text=payload,
            model="mock",
            provider="mock",
            input_tokens=5,
            output_tokens=10,
            latency_ms=1,
        )

    return _router


def _failing_llm():
    """LLM that always raises an exception."""

    def _router(req: LlmRequest) -> LlmResponse:
        raise RuntimeError("LLM unavailable")

    return _router


# ─── Fixtures ────────────────────────────────────────────────────────────────


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
    )


# ─── Storage: insert_experiment with null child_strategy_id ──────────────────


def test_insert_experiment_accepts_null_child_strategy_id(db_path: Path):
    """Critic veto rows have child_strategy_id=None — experiments table allows NULL FK."""
    run_id = uuid4().hex[:12]
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_id)
        parent_sid = upsert_strategy(
            conn,
            name="SMA_5x15_bullish",
            family="indicator",
            params={"type": "sma_crossover", "fast": 5, "slow": 15},
        )

    with connect(db_path) as conn, txn(conn):
        exp_id = insert_experiment(
            conn,
            run_id=run_id,
            generation=0,
            parent_strategy_id=parent_sid,
            child_strategy_id=None,  # critic veto — no child strategy created
            mutator="critic_veto",
            mutation_json='{"type":"sma_crossover","fast":8,"slow":22}',
            accepted=0,
            delta_sharpe=0.0,
            composite_score_json='{"critic_veto":1.0}',
            reasoning="parent already tried similar direction",
        )

    assert isinstance(exp_id, int)
    assert exp_id > 0

    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT child_strategy_id, mutator, accepted FROM experiments WHERE experiment_id=?",
            (exp_id,),
        ).fetchone()

    assert row is not None
    assert row["child_strategy_id"] is None
    assert row["mutator"] == "critic_veto"
    assert row["accepted"] == 0


# ─── Events: EvtCriticVerdict ─────────────────────────────────────────────────


def test_evt_critic_verdict_exists_in_pipeline_event_union():
    """EvtCriticVerdict must be importable and in the PipelineEvent union."""
    from atforge.graph.events import EvtCriticVerdict, PipelineEvent

    evt = EvtCriticVerdict(
        parent_strategy_id=1,
        fingerprint="1:{...}",
        verdict="veto",
        reason="already tried",
    )
    assert evt.verdict == "veto"
    assert evt.reason == "already tried"

    # Must be part of the PipelineEvent union (used for type checking in bus)
    import typing

    args = typing.get_args(PipelineEvent)
    assert EvtCriticVerdict in args, "EvtCriticVerdict not in PipelineEvent union"


# ─── Pydantic model: CriticVerdict ───────────────────────────────────────────


def test_critic_verdict_model_accept():
    """CriticVerdict validates accept verdict."""
    from atforge.evolution.prompts import CriticVerdict

    v = CriticVerdict(verdict="accept", reason="looks promising")
    assert v.verdict == "accept"
    assert v.reason == "looks promising"


def test_critic_verdict_model_veto():
    """CriticVerdict validates veto verdict."""
    from atforge.evolution.prompts import CriticVerdict

    v = CriticVerdict(verdict="veto", reason="parent's children already failed this direction")
    assert v.verdict == "veto"


def test_critic_verdict_model_rejects_invalid():
    """CriticVerdict rejects unknown verdict values."""
    from pydantic import ValidationError

    from atforge.evolution.prompts import CriticVerdict

    with pytest.raises(ValidationError):
        CriticVerdict(verdict="maybe", reason="unsure")


# ─── PipelineDeps.llm_router ─────────────────────────────────────────────────


def test_pipeline_deps_has_llm_router_field_with_none_default():
    """PipelineDeps.llm_router defaults to None — backward compat for existing tests."""
    import dataclasses

    field_map = {f.name: f for f in dataclasses.fields(PipelineDeps)}
    assert "llm_router" in field_map, "llm_router field missing from PipelineDeps"
    assert field_map["llm_router"].default is None, "llm_router default must be None"


# ─── critic_node: veto path ──────────────────────────────────────────────────


def test_critic_node_vetoes_proposal_with_veto_llm(db_path: Path, tmp_path: Path):
    """critic_node returns vetoed_mutations when LLM returns veto verdict."""
    run_id = uuid4().hex[:12]
    parent_sid = _seed_parent(db_path, run_id)

    proposal = _make_proposal(parent_sid, {"type": "sma_crossover", "fast": 8, "slow": 22})

    test_deps = PipelineDeps(
        data_provider=_SyntheticProvider(),
        detectors=(SmaCrossover(fast=5, slow=15),),
        ohlcv_cache_dir=tmp_path / "ohlcv",
        signal_cache_dir=tmp_path / "signals",
        db_path=db_path,
        llm_router=_veto_llm(),
    )

    node = make_critic_node(test_deps)
    result = node(
        {
            "run_id": run_id,
            "generation": 0,
            "proposed_mutations": [proposal],
            "vetoed_mutations": [],
        }
    )

    vetoed = result.get("vetoed_mutations", [])
    assert len(vetoed) == 1
    assert vetoed[0]["fingerprint"] == proposal["fingerprint"]
    assert vetoed[0]["generation"] == 0


def test_critic_veto_logged_to_experiments_table(db_path: Path, tmp_path: Path):
    """Vetoed proposals are logged to experiments with mutator='critic_veto', accepted=0."""
    run_id = uuid4().hex[:12]
    parent_sid = _seed_parent(db_path, run_id)

    proposal = _make_proposal(parent_sid, {"type": "sma_crossover", "fast": 8, "slow": 22})

    test_deps = PipelineDeps(
        data_provider=_SyntheticProvider(),
        detectors=(SmaCrossover(fast=5, slow=15),),
        ohlcv_cache_dir=tmp_path / "ohlcv",
        signal_cache_dir=tmp_path / "signals",
        db_path=db_path,
        llm_router=_veto_llm("parent already tried this"),
    )

    node = make_critic_node(test_deps)
    node(
        {
            "run_id": run_id,
            "generation": 0,
            "proposed_mutations": [proposal],
            "vetoed_mutations": [],
        }
    )

    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT mutator, accepted, child_strategy_id, reasoning FROM experiments WHERE run_id=?",
            (run_id,),
        ).fetchall()

    assert len(rows) == 1
    r = rows[0]
    assert r["mutator"] == "critic_veto"
    assert r["accepted"] == 0
    assert r["child_strategy_id"] is None
    assert "already tried" in r["reasoning"]


def test_critic_node_accept_does_not_log_to_experiments(db_path: Path, tmp_path: Path):
    """Accepted proposals are NOT logged to experiments — only vetoes are logged."""
    run_id = uuid4().hex[:12]
    parent_sid = _seed_parent(db_path, run_id)

    proposal = _make_proposal(parent_sid, {"type": "sma_crossover", "fast": 8, "slow": 22})

    test_deps = PipelineDeps(
        data_provider=_SyntheticProvider(),
        detectors=(SmaCrossover(fast=5, slow=15),),
        ohlcv_cache_dir=tmp_path / "ohlcv",
        signal_cache_dir=tmp_path / "signals",
        db_path=db_path,
        llm_router=_accept_llm(),
    )

    node = make_critic_node(test_deps)
    result = node(
        {
            "run_id": run_id,
            "generation": 0,
            "proposed_mutations": [proposal],
            "vetoed_mutations": [],
        }
    )

    # No vetoes returned
    assert result.get("vetoed_mutations", []) == []

    # No experiments logged for accepts
    with connect(db_path) as conn:
        n = conn.execute("SELECT COUNT(*) c FROM experiments WHERE run_id=?", (run_id,)).fetchone()[
            "c"
        ]
    assert n == 0


def test_critic_node_emits_evt_critic_verdict(db_path: Path, tmp_path: Path):
    """EvtCriticVerdict emitted per proposal regardless of verdict."""
    from atforge.graph.events import EvtCriticVerdict

    run_id = uuid4().hex[:12]
    parent_sid = _seed_parent(db_path, run_id)

    proposals = [
        _make_proposal(parent_sid, {"type": "sma_crossover", "fast": 8, "slow": 22}),
        _make_proposal(parent_sid, {"type": "sma_crossover", "fast": 10, "slow": 30}),
    ]

    bus = EventBus()
    test_deps = PipelineDeps(
        data_provider=_SyntheticProvider(),
        detectors=(SmaCrossover(fast=5, slow=15),),
        ohlcv_cache_dir=tmp_path / "ohlcv",
        signal_cache_dir=tmp_path / "signals",
        db_path=db_path,
        llm_router=_veto_llm(),
        event_bus=bus,
    )

    node = make_critic_node(test_deps)
    node(
        {
            "run_id": run_id,
            "generation": 0,
            "proposed_mutations": proposals,
            "vetoed_mutations": [],
        }
    )

    events = bus.drain(timeout=0.1)
    critic_events = [e for e in events if isinstance(e, EvtCriticVerdict)]
    assert len(critic_events) == 2, f"expected 2 EvtCriticVerdict, got {len(critic_events)}"
    assert all(e.verdict == "veto" for e in critic_events)


def test_critic_node_llm_failure_passes_proposal_through(db_path: Path, tmp_path: Path):
    """If LLM fails, proposal is NOT vetoed — safe default: let aggregate_node decide."""
    run_id = uuid4().hex[:12]
    parent_sid = _seed_parent(db_path, run_id)

    proposal = _make_proposal(parent_sid, {"type": "sma_crossover", "fast": 8, "slow": 22})

    test_deps = PipelineDeps(
        data_provider=_SyntheticProvider(),
        detectors=(SmaCrossover(fast=5, slow=15),),
        ohlcv_cache_dir=tmp_path / "ohlcv",
        signal_cache_dir=tmp_path / "signals",
        db_path=db_path,
        llm_router=_failing_llm(),
    )

    node = make_critic_node(test_deps)
    result = node(
        {
            "run_id": run_id,
            "generation": 0,
            "proposed_mutations": [proposal],
            "vetoed_mutations": [],
        }
    )

    # LLM failed → no veto
    assert result.get("vetoed_mutations", []) == []

    # No experiments logged
    with connect(db_path) as conn:
        n = conn.execute("SELECT COUNT(*) c FROM experiments WHERE run_id=?", (run_id,)).fetchone()[
            "c"
        ]
    assert n == 0


def test_critic_node_no_llm_router_accepts_all(db_path: Path, tmp_path: Path):
    """critic_node with llm_router=None falls back to Phase 6 stub — accept all."""
    run_id = uuid4().hex[:12]
    parent_sid = _seed_parent(db_path, run_id)

    proposal = _make_proposal(parent_sid, {"type": "sma_crossover", "fast": 8, "slow": 22})

    # deps without llm_router (default None)
    test_deps = PipelineDeps(
        data_provider=_SyntheticProvider(),
        detectors=(SmaCrossover(fast=5, slow=15),),
        ohlcv_cache_dir=tmp_path / "ohlcv",
        signal_cache_dir=tmp_path / "signals",
        db_path=db_path,
    )

    node = make_critic_node(test_deps)
    result = node(
        {
            "run_id": run_id,
            "generation": 0,
            "proposed_mutations": [proposal],
            "vetoed_mutations": [],
        }
    )

    assert result.get("vetoed_mutations", []) == []


def test_critic_node_empty_proposals_is_noop(db_path: Path, tmp_path: Path):
    """No proposals → no LLM calls, no DB writes, empty vetoed_mutations."""
    run_id = uuid4().hex[:12]
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_id)

    test_deps = PipelineDeps(
        data_provider=_SyntheticProvider(),
        detectors=(SmaCrossover(fast=5, slow=15),),
        ohlcv_cache_dir=tmp_path / "ohlcv",
        signal_cache_dir=tmp_path / "signals",
        db_path=db_path,
        llm_router=_veto_llm(),
    )

    node = make_critic_node(test_deps)
    result = node(
        {
            "run_id": run_id,
            "generation": 0,
            "proposed_mutations": [],
            "vetoed_mutations": [],
        }
    )

    assert result.get("vetoed_mutations", []) == []

    with connect(db_path) as conn:
        n = conn.execute("SELECT COUNT(*) c FROM experiments").fetchone()["c"]
    assert n == 0
