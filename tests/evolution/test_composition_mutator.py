"""Step 10 — CompositionMutator tests with mocked LLM router."""

from __future__ import annotations

import json

from atforge.evolution.mutators.composition import CompositionMutator, _nesting_depth
from atforge.evolution.types import StrategyRow
from atforge.llm.types import LlmRequest, LlmResponse


def _mock_llm(response_text: str):
    def _router(req: LlmRequest) -> LlmResponse:
        return LlmResponse(
            text=response_text,
            model="mock",
            provider="mock",
            input_tokens=5,
            output_tokens=10,
            latency_ms=1,
        )
    return _router


def _row(strategy_id: int, name: str, cfg: dict, sharpe: float = 1.0) -> StrategyRow:
    return {
        "strategy_id": strategy_id,
        "name": name,
        "family": "indicator",
        "params_json": json.dumps(cfg),
        "mean_sharpe": sharpe,
        "mean_sortino": sharpe * 1.2,
        "total_n_trades": 10,
        "max_drawdown": "0.10",
        "generation": 0,
    }


SMA_ROW = _row(1, "SMA_5x20_bullish", {"type": "sma_crossover", "fast": 5, "slow": 20}, sharpe=0.9)
RSI_ROW = _row(2, "RSI_14_reclaim_30", {"type": "rsi_oversold", "period": 14, "oversold": 30}, sharpe=0.7)


def test_and_composition_happy_path():
    resp = json.dumps({"op": "AND", "reasoning": "confirmation filter"})
    mut = CompositionMutator(_mock_llm(resp))
    mutations = mut.propose([SMA_ROW, RSI_ROW], k=1)
    assert len(mutations) == 1
    m = mutations[0]
    assert m.child_config["type"] == "and"
    assert m.child_config["left"]["type"] == "sma_crossover"
    assert m.child_config["right"]["type"] == "rsi_oversold"
    assert m.mutator == "composition"
    assert "confirmation" in m.reasoning


def test_or_composition_happy_path():
    resp = json.dumps({"op": "OR", "reasoning": "wider net"})
    mut = CompositionMutator(_mock_llm(resp))
    mutations = mut.propose([SMA_ROW, RSI_ROW], k=1)
    assert len(mutations) == 1
    assert mutations[0].child_config["type"] == "or"


def test_parent_with_higher_sharpe_is_parent_strategy_id():
    resp = json.dumps({"op": "AND", "reasoning": "test"})
    mut = CompositionMutator(_mock_llm(resp))
    mutations = mut.propose([SMA_ROW, RSI_ROW], k=1)
    # SMA has sharpe=0.9 > RSI sharpe=0.7
    assert mutations[0].parent_strategy_id == SMA_ROW["strategy_id"]


def test_max_nesting_depth_enforced():
    """A parent at max depth is skipped, not combined."""
    deep_cfg = {
        "type": "and",
        "left": {"type": "sma_crossover", "fast": 5, "slow": 20},
        "right": {
            "type": "or",
            "left": {"type": "sma_crossover", "fast": 10, "slow": 30},
            "right": {"type": "rsi_oversold", "period": 14, "oversold": 30},
        },
    }
    deep_row = _row(3, "deep", deep_cfg, sharpe=1.5)
    resp = json.dumps({"op": "AND", "reasoning": "would be too deep"})
    mut = CompositionMutator(_mock_llm(resp), max_nesting_depth=2)
    # deep_cfg has depth=2, which equals max_depth — should be skipped
    mutations = mut.propose([deep_row, RSI_ROW], k=2)
    assert mutations == []


def test_malformed_llm_response_skipped():
    mut = CompositionMutator(_mock_llm("sorry, I can't do that"))
    mutations = mut.propose([SMA_ROW, RSI_ROW], k=1)
    assert mutations == []


def test_invalid_op_rejected():
    """LLM returns op='XOR' which is not in Literal['AND','OR']."""
    resp = json.dumps({"op": "XOR", "reasoning": "oops"})
    mut = CompositionMutator(_mock_llm(resp))
    mutations = mut.propose([SMA_ROW, RSI_ROW], k=1)
    assert mutations == []


def test_nesting_depth_leaf():
    assert _nesting_depth({"type": "sma_crossover", "fast": 5, "slow": 20}) == 0


def test_nesting_depth_one_level():
    cfg = {
        "type": "and",
        "left": {"type": "sma_crossover", "fast": 5, "slow": 20},
        "right": {"type": "rsi_oversold", "period": 14, "oversold": 30},
    }
    assert _nesting_depth(cfg) == 1


def test_nesting_depth_two_levels():
    cfg = {
        "type": "and",
        "left": {"type": "sma_crossover", "fast": 5, "slow": 20},
        "right": {
            "type": "or",
            "left": {"type": "sma_crossover", "fast": 10, "slow": 30},
            "right": {"type": "rsi_oversold", "period": 14, "oversold": 30},
        },
    }
    assert _nesting_depth(cfg) == 2
