"""Phase 6 — A2 multi-agent node topology tests.

Tests for the 4-node multi-agent pipeline that replaces `mutate_strategies`:
  explorer_node → exploiter_node → critic_node → aggregate_node

Design contract:
- explorer_node  : calls deps.mutators, returns proposed_mutations tagged with role="explorer"
- exploiter_node : Phase 6 stub, returns empty proposed_mutations (wired in Phase 8)
- critic_node    : Phase 6 stub, returns empty vetoed_mutations (wired in Phase 7)
- aggregate_node : filters vetoed proposals, upserts survivors to DB, writes to mutations reducer

All proposed_mutation dicts carry a `fingerprint` key used for veto matching.
All nodes tag proposals with `generation` for multi-loop correctness.
aggregate_node output is compatible with ratchet_node's existing mutations reader.
"""

from __future__ import annotations

import json
import operator
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from atforge.backtest.engine import BacktestResult
from atforge.data.protocol import OHLCV_COLUMNS
from atforge.evolution.mutators.param_delta import ParamDeltaMutator
from atforge.graph.deps import AgentRoleConfig, PipelineDeps
from atforge.graph.nodes_a2 import (
    make_aggregate_node,
    make_critic_node,
    make_exploiter_node,
    make_explorer_node,
)
from atforge.llm.types import LlmRequest, LlmResponse
from atforge.patterns.pandas_ta import SmaCrossover
from atforge.storage.db import connect, init_db, txn
from atforge.storage.repo import (
    insert_backtest_result,
    insert_pattern_signal,
    insert_run,
    upsert_strategy,
)

# ─── Shared helpers ──────────────────────────────────────────────────────────


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
    """LLM that always returns a fixed SMA param-delta JSON."""
    payload = json.dumps({"fast": fast, "slow": slow, "reasoning": "test mutation"})

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


def _seed_gen0(db_path: Path, run_id: str, tmp_path: Path) -> int:
    """Seed a gen=0 strategy + backtest so get_top_strategies_for_generation has results."""
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


def _make_proposal(
    parent_sid: int, child_config: dict, role: str = "explorer", generation: int = 0
) -> dict:
    """Build a proposal dict as explorer/exploiter nodes produce."""
    fp = f"{parent_sid}:{json.dumps(child_config, sort_keys=True)}"
    return {
        "generation": generation,
        "parent_strategy_id": parent_sid,
        "child_config": child_config,
        "reasoning": "test reasoning",
        "role": role,
        "fingerprint": fp,
    }


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
        hold_bars=5,
        init_cash=Decimal("100000"),
        mutators=(ParamDeltaMutator(_mock_sma_llm(fast=10, slow=25)),),
        top_n_parents=3,
    )


# ─── AgentRoleConfig ─────────────────────────────────────────────────────────


def test_agent_role_config_is_frozen_dataclass():
    """AgentRoleConfig is immutable and carries the expected fields."""
    cfg = AgentRoleConfig(
        role="explorer",
        temperature=0.9,
        max_iterations=4,
        system_prompt="You explore novel strategies.",
    )
    assert cfg.role == "explorer"
    assert cfg.temperature == 0.9
    assert cfg.max_iterations == 4
    assert cfg.system_prompt == "You explore novel strategies."

    # frozen — mutation must raise
    with pytest.raises((AttributeError, TypeError)):
        cfg.role = "other"  # type: ignore[misc]


def test_pipeline_deps_has_role_configs_with_empty_default():
    """PipelineDeps.role_configs defaults to empty dict — no breaking change for existing code."""
    import dataclasses

    field_map = {f.name: f for f in dataclasses.fields(PipelineDeps)}
    assert "role_configs" in field_map, "role_configs field missing from PipelineDeps"

    # Default factory produces empty dict
    default = field_map["role_configs"].default_factory()  # type: ignore[misc]
    assert default == {}


# ─── PipelineState new fields ────────────────────────────────────────────────


def test_state_proposed_mutations_is_operator_add_reducer():
    """proposed_mutations must use operator.add — required for multi-node accumulation."""
    from typing import get_type_hints

    from atforge.graph.state import PipelineState

    hints = get_type_hints(PipelineState, include_extras=True)
    assert "proposed_mutations" in hints, "proposed_mutations field missing from PipelineState"
    meta = getattr(hints["proposed_mutations"], "__metadata__", ())
    assert operator.add in meta, f"proposed_mutations missing operator.add reducer; metadata={meta}"


def test_state_vetoed_mutations_is_operator_add_reducer():
    """vetoed_mutations must use operator.add — critic appends per-proposal vetoes."""
    from typing import get_type_hints

    from atforge.graph.state import PipelineState

    hints = get_type_hints(PipelineState, include_extras=True)
    assert "vetoed_mutations" in hints, "vetoed_mutations field missing from PipelineState"
    meta = getattr(hints["vetoed_mutations"], "__metadata__", ())
    assert operator.add in meta, f"vetoed_mutations missing operator.add reducer; metadata={meta}"


# ─── explorer_node ───────────────────────────────────────────────────────────


def test_explorer_node_returns_proposed_mutations(deps, db_path, tmp_path):
    """explorer_node calls deps.mutators and wraps results into proposed_mutation dicts."""
    run_id = uuid4().hex[:12]
    _seed_gen0(db_path, run_id, tmp_path)

    node = make_explorer_node(deps)
    result = node(
        {
            "run_id": run_id,
            "generation": 0,
            "max_generations": 2,
        }
    )

    proposals = result.get("proposed_mutations", [])
    assert len(proposals) >= 1, "expected at least one proposal from explorer_node"

    p = proposals[0]
    assert p["role"] == "explorer"
    assert p["generation"] == 0
    assert "fingerprint" in p
    assert "child_config" in p
    assert "parent_strategy_id" in p
    assert "reasoning" in p


def test_explorer_node_skips_when_at_max_generations(deps):
    """generation + 1 >= max_generations → no-op, no proposals."""
    node = make_explorer_node(deps)
    result = node({"run_id": "x", "generation": 1, "max_generations": 1})
    assert result.get("proposed_mutations", []) == []


def test_explorer_node_skips_when_no_parents(deps, db_path):
    """DB has no strategies at this generation → no proposals, no crash."""
    run_id = uuid4().hex[:12]
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_id)

    node = make_explorer_node(deps)
    result = node({"run_id": run_id, "generation": 0, "max_generations": 2})
    assert result.get("proposed_mutations", []) == []


def test_explorer_proposals_have_stable_fingerprints(deps, db_path, tmp_path):
    """Two calls with identical parents produce identical fingerprints (dedup key is stable)."""
    run_id = uuid4().hex[:12]
    _seed_gen0(db_path, run_id, tmp_path)

    node = make_explorer_node(deps)
    state = {"run_id": run_id, "generation": 0, "max_generations": 2}
    r1 = node(state)
    r2 = node(state)

    fps1 = {p["fingerprint"] for p in r1.get("proposed_mutations", [])}
    fps2 = {p["fingerprint"] for p in r2.get("proposed_mutations", [])}
    assert fps1 == fps2, "fingerprints not stable across identical calls"


# ─── exploiter_node (Phase 6 stub) ───────────────────────────────────────────


def test_exploiter_node_is_noop_in_phase6(deps):
    """exploiter_node returns empty proposed_mutations in Phase 6 (wired fully in Phase 8)."""
    node = make_exploiter_node(deps)
    result = node({"run_id": "x", "generation": 0, "max_generations": 2})
    assert result.get("proposed_mutations", []) == []


# ─── critic_node (Phase 6 stub) ──────────────────────────────────────────────


def test_critic_node_accepts_all_in_phase6(deps, db_path, tmp_path):
    """critic_node stub returns empty vetoed_mutations — all proposals survive in Phase 6."""
    run_id = uuid4().hex[:12]
    parent_sid = _seed_gen0(db_path, run_id, tmp_path)

    proposals = [
        _make_proposal(parent_sid, {"type": "sma_crossover", "fast": 8, "slow": 22}),
        _make_proposal(parent_sid, {"type": "sma_crossover", "fast": 10, "slow": 30}),
    ]
    node = make_critic_node(deps)
    result = node(
        {
            "run_id": run_id,
            "generation": 0,
            "proposed_mutations": proposals,
        }
    )
    assert result.get("vetoed_mutations", []) == []


# ─── aggregate_node ──────────────────────────────────────────────────────────


def test_aggregate_node_upserts_survivors_to_db(deps, db_path, tmp_path):
    """Non-vetoed proposals are upserted to strategies table and appear in mutations."""
    run_id = uuid4().hex[:12]
    parent_sid = _seed_gen0(db_path, run_id, tmp_path)

    child_config = {"type": "sma_crossover", "fast": 10, "slow": 25}
    proposals = [_make_proposal(parent_sid, child_config)]

    node = make_aggregate_node(deps)
    result = node(
        {
            "run_id": run_id,
            "generation": 0,
            "max_generations": 2,
            "proposed_mutations": proposals,
            "vetoed_mutations": [],
        }
    )

    mutations = result.get("mutations", [])
    assert len(mutations) == 1
    m = mutations[0]
    assert m["parent_strategy_id"] == parent_sid
    assert m["generation"] == 0
    assert "child_strategy_id" in m
    assert m["mutation_json"] == json.dumps(child_config, sort_keys=True)

    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT strategy_id FROM strategies WHERE strategy_id=?",
            (m["child_strategy_id"],),
        ).fetchone()
    assert row is not None, "child strategy was not upserted to DB"


def test_aggregate_node_excludes_vetoed_proposals(deps, db_path, tmp_path):
    """Vetoed proposals are filtered out — not upserted, not in mutations."""
    run_id = uuid4().hex[:12]
    parent_sid = _seed_gen0(db_path, run_id, tmp_path)

    config_a = {"type": "sma_crossover", "fast": 8, "slow": 22}
    config_b = {"type": "sma_crossover", "fast": 10, "slow": 30}
    fp_a = f"{parent_sid}:{json.dumps(config_a, sort_keys=True)}"

    proposals = [
        _make_proposal(parent_sid, config_a),
        _make_proposal(parent_sid, config_b),
    ]
    vetoed = [
        {
            "generation": 0,
            "parent_strategy_id": parent_sid,
            "child_config": config_a,
            "fingerprint": fp_a,
            "veto_reason": "parent's children already tried this direction",
            "role": "critic",
        }
    ]

    node = make_aggregate_node(deps)
    result = node(
        {
            "run_id": run_id,
            "generation": 0,
            "max_generations": 2,
            "proposed_mutations": proposals,
            "vetoed_mutations": vetoed,
        }
    )

    mutations = result.get("mutations", [])
    assert len(mutations) == 1, f"expected 1 survivor, got {len(mutations)}"
    assert mutations[0]["mutation_json"] == json.dumps(config_b, sort_keys=True)

    # config_a was vetoed → must NOT be in strategies table (run in fresh DB so no collision)
    with connect(db_path) as conn:
        # config_b (survivor) must be present
        fp_b_sid = mutations[0]["child_strategy_id"]
        survivor_row = conn.execute(
            "SELECT params_json FROM strategies WHERE strategy_id=?", (fp_b_sid,)
        ).fetchone()
        assert survivor_row is not None

        # config_a fingerprint points to a strategy that should not exist
        # (it was vetoed before upsert — verify the upserted set has exactly 2 strategies: parent + config_b)
        all_strats = conn.execute("SELECT COUNT(*) c FROM strategies").fetchone()["c"]
    assert all_strats == 2, f"expected 2 strategies (parent + 1 survivor), found {all_strats}"


def test_aggregate_node_filters_by_current_generation(deps, db_path, tmp_path):
    """Proposals from a previous generation in the accumulated state are not re-processed."""
    run_id = uuid4().hex[:12]
    parent_sid = _seed_gen0(db_path, run_id, tmp_path)

    config_gen0 = {"type": "sma_crossover", "fast": 8, "slow": 22}
    config_gen1 = {"type": "sma_crossover", "fast": 12, "slow": 35}

    # Simulate two generations' proposals accumulated in state (reducer)
    proposals = [
        _make_proposal(parent_sid, config_gen0, generation=0),  # old generation
        _make_proposal(parent_sid, config_gen1, generation=1),  # current generation
    ]

    node = make_aggregate_node(deps)
    result = node(
        {
            "run_id": run_id,
            "generation": 1,  # only gen=1 proposals should be processed
            "max_generations": 3,
            "proposed_mutations": proposals,
            "vetoed_mutations": [],
        }
    )

    mutations = result.get("mutations", [])
    assert len(mutations) == 1, "only current-generation proposals should be processed"
    assert mutations[0]["mutation_json"] == json.dumps(config_gen1, sort_keys=True)


def test_aggregate_node_is_noop_when_no_proposals(deps, db_path):
    """Empty proposals → empty mutations, no DB writes."""
    run_id = uuid4().hex[:12]
    with connect(db_path) as conn, txn(conn):
        insert_run(conn, run_id)

    node = make_aggregate_node(deps)
    result = node(
        {
            "run_id": run_id,
            "generation": 0,
            "max_generations": 2,
            "proposed_mutations": [],
            "vetoed_mutations": [],
        }
    )

    assert result.get("mutations", []) == []

    with connect(db_path) as conn:
        n = conn.execute("SELECT COUNT(*) c FROM strategies").fetchone()["c"]
    assert n == 0


# ─── Pipeline topology ───────────────────────────────────────────────────────


def test_pipeline_topology_has_a2_nodes(deps):
    """build_pipeline produces a graph with the 4 A2 nodes visible in the node set."""
    from atforge.graph.pipeline import build_pipeline

    graph = build_pipeline(deps)
    # LangGraph compiled graph exposes node names via get_graph()
    mermaid = graph.get_graph().draw_mermaid()

    for node_name in ("explorer_node", "exploiter_node", "critic_node", "aggregate_node"):
        assert node_name in mermaid, f"node '{node_name}' missing from compiled pipeline topology"


def test_pipeline_does_not_have_old_mutate_strategies_node(deps):
    """mutate_strategies was replaced by the 4 A2 nodes — must not appear in topology."""
    from atforge.graph.pipeline import build_pipeline

    graph = build_pipeline(deps)
    mermaid = graph.get_graph().draw_mermaid()
    assert "mutate_strategies" not in mermaid, (
        "old mutate_strategies node still present — A2 refactor incomplete"
    )
