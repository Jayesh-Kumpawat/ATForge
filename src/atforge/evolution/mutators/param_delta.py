"""ParamDeltaMutator — LLM-guided parameter mutations for indicator-family detectors.

Handles SMA crossover (fast/slow) and RSI oversold (period/oversold).
Validates LLM response via Pydantic schemas with up to 3 retries on parse failure.
Returns success=False silently on exhausted retries (never raises).
"""

from __future__ import annotations

import json
from collections.abc import Callable

import structlog

from atforge.evolution.mutators._utils import call_llm_with_schema
from atforge.evolution.prompts import (
    RsiParamsDelta,
    SmaParamsDelta,
    get_system_prompt,
    rsi_param_delta_prompt,
    sma_param_delta_prompt,
)
from atforge.evolution.types import DetectorConfig, ProposedMutation, StrategyRow
from atforge.llm.types import LlmRequest, LlmResponse

log = structlog.get_logger(__name__)


class ParamDeltaMutator:
    """Propose parameter mutations for SMA and RSI detectors via LLM."""

    name = "param_delta"

    def __init__(
        self,
        llm_router: Callable[[LlmRequest], LlmResponse],
        *,
        model: str | None = None,
        temperature: float = 0.8,
    ) -> None:
        self._llm = llm_router
        self._model = model
        self._temperature = temperature

    def propose(
        self,
        parents: list[StrategyRow],
        k: int,
    ) -> list[ProposedMutation]:
        mutations: list[ProposedMutation] = []
        for parent in parents[:k]:
            try:
                mut = self._propose_one(parent)
                if mut is not None:
                    mutations.append(mut)
            except Exception as exc:
                log.warning(
                    "param_delta_propose_failed", strategy_id=parent["strategy_id"], error=str(exc)
                )
        return mutations

    def _propose_one(self, parent: StrategyRow) -> ProposedMutation | None:
        try:
            cfg: dict = json.loads(parent["params_json"])
        except (json.JSONDecodeError, KeyError):
            return None

        detector_type = cfg.get("type")

        if detector_type == "sma_crossover":
            return self._mutate_sma(parent, cfg)
        if detector_type == "rsi_oversold":
            return self._mutate_rsi(parent, cfg)
        # talib_cdl and composites: param_delta mutator skips them
        return None

    def _mutate_sma(self, parent: StrategyRow, cfg: dict) -> ProposedMutation | None:
        prompt = sma_param_delta_prompt(
            current_fast=cfg["fast"],
            current_slow=cfg["slow"],
            mean_sharpe=parent["mean_sharpe"],
            mean_sortino=parent["mean_sortino"],
            n_trades=parent["total_n_trades"],
        )
        request = LlmRequest(
            prompt=prompt,
            system=get_system_prompt("sma"),
            model=self._model,
            temperature=self._temperature,
            max_tokens=1024,
            trace_name="param_delta_sma",
            response_schema=SmaParamsDelta,
        )
        validated = call_llm_with_schema(self._llm, request, SmaParamsDelta)
        if validated is None:
            return None

        child_config: DetectorConfig = {
            "type": "sma_crossover",
            "fast": validated.fast,
            "slow": validated.slow,
        }
        return ProposedMutation(
            parent_strategy_id=parent["strategy_id"],
            child_config=child_config,
            reasoning=validated.reasoning,
            mutator=self.name,
        )

    def _mutate_rsi(self, parent: StrategyRow, cfg: dict) -> ProposedMutation | None:
        prompt = rsi_param_delta_prompt(
            current_period=cfg["period"],
            current_oversold=cfg["oversold"],
            mean_sharpe=parent["mean_sharpe"],
            mean_sortino=parent["mean_sortino"],
            n_trades=parent["total_n_trades"],
        )
        request = LlmRequest(
            prompt=prompt,
            system=get_system_prompt("rsi"),
            model=self._model,
            temperature=self._temperature,
            max_tokens=1024,
            trace_name="param_delta_rsi",
            response_schema=RsiParamsDelta,
        )
        validated = call_llm_with_schema(self._llm, request, RsiParamsDelta)
        if validated is None:
            return None

        child_config: DetectorConfig = {
            "type": "rsi_oversold",
            "period": validated.period,
            "oversold": validated.oversold,
        }
        return ProposedMutation(
            parent_strategy_id=parent["strategy_id"],
            child_config=child_config,
            reasoning=validated.reasoning,
            mutator=self.name,
        )
