"""Tests for ResearchAgentMutator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atforge.evolution.mutators.research_agent import ResearchAgentMutator
from atforge.evolution.types import StrategyRow
from atforge.llm.types import LlmRequest, LlmResponse
from atforge.storage.db import connect, init_db, txn
from atforge.storage.repo import insert_run


def _resp(text: str) -> LlmResponse:
    return LlmResponse(
        text=text,
        model="test",
        provider="test",
        input_tokens=10,
        output_tokens=10,
        latency_ms=5,
        stop_reason="end_turn",
    )


def _sma_proposal(fast: int = 8, slow: int = 25, conf: float = 0.8) -> str:
    return json.dumps(
        {
            "proposal_type": "sma_param_delta",
            "sma": {"fast": fast, "slow": slow, "reasoning": "wider windows reduce noise"},
            "rsi": None,
            "research_summary": "Top SMA strategies use wider windows.",
            "confidence": conf,
        }
    )


def _rsi_proposal(period: int = 10, oversold: int = 25) -> str:
    return json.dumps(
        {
            "proposal_type": "rsi_param_delta",
            "sma": None,
            "rsi": {
                "period": period,
                "oversold": oversold,
                "reasoning": "shorter period more signals",
            },
            "research_summary": "RSI 10/25 has better signal frequency.",
            "confidence": 0.7,
        }
    )


def _parent(strategy_id: int, params: dict, sharpe: float = 1.2) -> StrategyRow:
    return {
        "strategy_id": strategy_id,
        "name": f"strategy_{strategy_id}",
        "family": "indicator",
        "params_json": json.dumps(params, sort_keys=True),
        "mean_sharpe": sharpe,
        "mean_sortino": sharpe * 1.2,
        "total_n_trades": 20,
        "max_drawdown": "-0.05",
        "generation": 0,
    }


@pytest.fixture
def db(tmp_db_path: Path) -> Path:
    init_db(tmp_db_path)
    with connect(tmp_db_path) as conn, txn(conn):
        insert_run(conn, "run-research-test")
    return tmp_db_path


# ── happy paths ───────────────────────────────────────────────────────────────


def test_propose_sma_parent_returns_mutation(db: Path) -> None:
    mutator = ResearchAgentMutator(lambda req: _resp(_sma_proposal()), db_path=db)
    mutations = mutator.propose(
        [_parent(1, {"type": "sma_crossover", "fast": 10, "slow": 30})], k=1
    )
    assert len(mutations) == 1
    assert mutations[0].child_config["type"] == "sma_crossover"
    assert mutations[0].child_config["fast"] == 8
    assert mutations[0].child_config["slow"] == 25


def test_propose_rsi_parent_returns_mutation(db: Path) -> None:
    mutator = ResearchAgentMutator(lambda req: _resp(_rsi_proposal()), db_path=db)
    mutations = mutator.propose(
        [_parent(2, {"type": "rsi_oversold", "period": 14, "oversold": 30})], k=1
    )
    assert len(mutations) == 1
    assert mutations[0].child_config["type"] == "rsi_oversold"
    assert mutations[0].child_config["period"] == 10
    assert mutations[0].child_config["oversold"] == 25


def test_mutator_name_is_research(db: Path) -> None:
    mutator = ResearchAgentMutator(lambda req: _resp(_sma_proposal()), db_path=db)
    mutations = mutator.propose(
        [_parent(3, {"type": "sma_crossover", "fast": 10, "slow": 30})], k=1
    )
    assert mutations[0].mutator == "research"


def test_reasoning_includes_research_prefix_and_confidence(db: Path) -> None:
    mutator = ResearchAgentMutator(lambda req: _resp(_sma_proposal(conf=0.9)), db_path=db)
    mutations = mutator.propose(
        [_parent(4, {"type": "sma_crossover", "fast": 10, "slow": 30})], k=1
    )
    assert "[research]" in mutations[0].reasoning
    assert "0.90" in mutations[0].reasoning


# ── skip conditions ───────────────────────────────────────────────────────────


def test_talib_cdl_parent_skipped(db: Path) -> None:
    mutator = ResearchAgentMutator(lambda req: _resp(_sma_proposal()), db_path=db)
    mutations = mutator.propose(
        [_parent(5, {"type": "talib_cdl", "cdl_name": "CDLENGULFING", "direction": "bullish"})], k=1
    )
    assert mutations == []


def test_composite_parent_skipped(db: Path) -> None:
    mutator = ResearchAgentMutator(lambda req: _resp(_sma_proposal()), db_path=db)
    mutations = mutator.propose(
        [_parent(6, {"type": "and", "left": {"type": "sma_crossover"}, "right": {}})], k=1
    )
    assert mutations == []


# ── error handling ────────────────────────────────────────────────────────────


def test_bad_llm_response_returns_empty(db: Path) -> None:
    mutator = ResearchAgentMutator(lambda req: _resp("not valid json!!!"), db_path=db)
    mutations = mutator.propose(
        [_parent(7, {"type": "sma_crossover", "fast": 10, "slow": 30})], k=1
    )
    assert mutations == []


def test_llm_exception_returns_empty(db: Path) -> None:
    def boom(_: LlmRequest) -> LlmResponse:
        raise RuntimeError("provider down")

    mutator = ResearchAgentMutator(boom, db_path=db)
    mutations = mutator.propose(
        [_parent(8, {"type": "sma_crossover", "fast": 10, "slow": 30})], k=1
    )
    assert mutations == []


def test_k_limits_parents_processed(db: Path) -> None:
    call_count = 0

    def counting_llm(req: LlmRequest) -> LlmResponse:
        nonlocal call_count
        call_count += 1
        return _resp(_sma_proposal())

    parents = [_parent(i, {"type": "sma_crossover", "fast": 10, "slow": 30}) for i in range(1, 6)]
    mutator = ResearchAgentMutator(counting_llm, db_path=db)
    mutator.propose(parents, k=2)
    assert call_count == 2
