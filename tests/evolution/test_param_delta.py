"""Step 10 — ParamDeltaMutator tests with mocked LLM router."""

from __future__ import annotations

import json

from atforge.evolution.mutators.param_delta import ParamDeltaMutator
from atforge.evolution.types import StrategyRow
from atforge.llm.types import LlmRequest, LlmResponse


def _mock_llm(response_text: str):
    """Return a callable that ignores the request and returns response_text."""

    def _router(req: LlmRequest) -> LlmResponse:
        return LlmResponse(
            text=response_text,
            model="mock",
            provider="mock",
            input_tokens=10,
            output_tokens=20,
            latency_ms=1,
        )

    return _router


def _sma_row(strategy_id: int = 1, fast: int = 20, slow: int = 50) -> StrategyRow:
    return {
        "strategy_id": strategy_id,
        "name": f"SMA_{fast}x{slow}_bullish",
        "family": "indicator",
        "params_json": json.dumps({"type": "sma_crossover", "fast": fast, "slow": slow}),
        "mean_sharpe": 0.8,
        "mean_sortino": 1.1,
        "total_n_trades": 12,
        "max_drawdown": "0.15",
        "generation": 0,
    }


def _rsi_row(strategy_id: int = 2, period: int = 14, oversold: int = 30) -> StrategyRow:
    return {
        "strategy_id": strategy_id,
        "name": f"RSI_{period}_reclaim_{oversold}",
        "family": "indicator",
        "params_json": json.dumps({"type": "rsi_oversold", "period": period, "oversold": oversold}),
        "mean_sharpe": 0.5,
        "mean_sortino": 0.7,
        "total_n_trades": 8,
        "max_drawdown": "0.10",
        "generation": 0,
    }


def test_sma_param_delta_happy_path():
    resp = json.dumps({"fast": 15, "slow": 40, "reasoning": "shorter window"})
    mutator = ParamDeltaMutator(_mock_llm(resp))
    mutations = mutator.propose([_sma_row()], k=1)
    assert len(mutations) == 1
    m = mutations[0]
    assert m.mutator == "param_delta"
    assert m.child_config["type"] == "sma_crossover"
    assert m.child_config["fast"] == 15
    assert m.child_config["slow"] == 40
    assert "shorter" in m.reasoning


def test_rsi_param_delta_happy_path():
    resp = json.dumps({"period": 10, "oversold": 25, "reasoning": "tighter period"})
    mutator = ParamDeltaMutator(_mock_llm(resp))
    mutations = mutator.propose([_rsi_row()], k=1)
    assert len(mutations) == 1
    m = mutations[0]
    assert m.child_config["type"] == "rsi_oversold"
    assert m.child_config["period"] == 10


def test_sma_validation_rejects_fast_gte_slow():
    """LLM returns fast >= slow — Pydantic should reject, mutation skipped."""
    resp = json.dumps({"fast": 50, "slow": 30, "reasoning": "bad"})
    mutator = ParamDeltaMutator(_mock_llm(resp))
    mutations = mutator.propose([_sma_row()], k=1)
    assert mutations == []


def test_sma_strips_markdown_fences():
    inner = json.dumps({"fast": 10, "slow": 25, "reasoning": "fenced"})
    resp = f"```json\n{inner}\n```"
    mutator = ParamDeltaMutator(_mock_llm(resp))
    mutations = mutator.propose([_sma_row()], k=1)
    assert len(mutations) == 1
    assert mutations[0].child_config["fast"] == 10


def test_brace_match_fallback():
    """LLM adds preamble text before JSON — brace-match extracts it."""
    inner = json.dumps({"fast": 8, "slow": 21, "reasoning": "brace"})
    resp = f"Here is my suggestion: {inner} Hope that helps!"
    mutator = ParamDeltaMutator(_mock_llm(resp))
    mutations = mutator.propose([_sma_row()], k=1)
    assert len(mutations) == 1
    assert mutations[0].child_config["fast"] == 8


def test_talib_cdl_row_is_skipped():
    """param_delta mutator has no handler for CDL patterns — skips silently."""
    cdl_row: StrategyRow = {
        "strategy_id": 3,
        "name": "CDLENGULFING_bullish",
        "family": "candlestick",
        "params_json": json.dumps({"type": "talib_cdl", "cdl_name": "CDLENGULFING", "direction": "bullish"}),
        "mean_sharpe": 1.2,
        "mean_sortino": 1.5,
        "total_n_trades": 20,
        "max_drawdown": "0.08",
        "generation": 0,
    }
    mutator = ParamDeltaMutator(_mock_llm("{}"))
    mutations = mutator.propose([cdl_row], k=1)
    assert mutations == []


def test_multiple_parents_k_respected():
    """k caps the number of proposals (one per parent), not the number of parents consumed."""
    resp = json.dumps({"fast": 5, "slow": 20, "reasoning": "fast"})
    parents = [_sma_row(i, fast=20 - i, slow=50 + i) for i in range(1, 5)]
    mutator = ParamDeltaMutator(_mock_llm(resp))
    mutations = mutator.propose(parents, k=2)
    assert len(mutations) == 2


def test_malformed_json_skipped_gracefully():
    mutator = ParamDeltaMutator(_mock_llm("not json at all"))
    mutations = mutator.propose([_sma_row()], k=1)
    assert mutations == []


def _mock_llm_sequence(responses: list[str]):
    """Return a callable that returns responses in order, repeating the last."""
    calls: list[int] = [0]

    def _router(req: LlmRequest) -> LlmResponse:
        idx = min(calls[0], len(responses) - 1)
        calls[0] += 1
        return LlmResponse(
            text=responses[idx],
            model="mock",
            provider="mock",
            input_tokens=10,
            output_tokens=20,
            latency_ms=1,
        )

    return _router, calls


def test_retry_succeeds_on_second_attempt():
    """First LLM response is invalid JSON; second is valid — mutation succeeds."""
    good = json.dumps({"fast": 12, "slow": 35, "reasoning": "retry worked"})
    router, calls = _mock_llm_sequence(["not json", good])
    mutator = ParamDeltaMutator(router)
    mutations = mutator.propose([_sma_row()], k=1)
    assert len(mutations) == 1
    assert mutations[0].child_config["fast"] == 12
    assert calls[0] == 2  # called twice: once bad, once good


def test_retry_exhausted_calls_llm_max_retries_times():
    """All retries return invalid JSON — LLM called max_retries times, mutation dropped."""
    from atforge.evolution.mutators._utils import call_llm_with_schema
    from atforge.evolution.prompts import SmaParamsDelta
    from atforge.llm.types import LlmRequest

    router, calls = _mock_llm_sequence(["not json"])
    req = LlmRequest(prompt="p", system="s", trace_name="test")
    result = call_llm_with_schema(router, req, SmaParamsDelta, max_retries=3)
    assert result is None
    assert calls[0] == 3


def test_retry_fast_gte_slow_retries_then_drops():
    """Pydantic rejects fast>=slow on every attempt — exhausts retries, drops mutation."""
    bad = json.dumps({"fast": 50, "slow": 30, "reasoning": "bad"})
    router, calls = _mock_llm_sequence([bad])
    mutator = ParamDeltaMutator(router)
    mutations = mutator.propose([_sma_row()], k=1)
    assert mutations == []
    assert calls[0] == 3  # default max_retries=3
