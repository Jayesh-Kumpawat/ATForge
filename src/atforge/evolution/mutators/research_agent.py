"""ResearchAgentMutator — ReAct-loop mutator with DB tool access.

Extends param_delta style mutations with multi-turn tool calling: the agent
queries past experiments and strategy lineage before proposing, avoiding
directions already tried in previous generations.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import structlog

from atforge.evolution.agent_runner import run_react_loop
from atforge.evolution.agent_tools import build_research_tools
from atforge.evolution.mutators._utils import _parse_json
from atforge.evolution.prompts import ResearchProposal
from atforge.evolution.research_prompts import RESEARCH_SYSTEM, research_initial_message
from atforge.evolution.types import DetectorConfig, ProposedMutation, StrategyRow
from atforge.graph.events import EventBus
from atforge.llm.types import LlmRequest, LlmResponse
from atforge.storage.db import connect

log = structlog.get_logger(__name__)

_SUPPORTED_TYPES = frozenset({"sma_crossover", "rsi_oversold"})


class ResearchAgentMutator:
    """Mutator that runs a ReAct loop to query DB history before proposing mutations."""

    name = "research"

    def __init__(
        self,
        llm_router: Callable[[LlmRequest], LlmResponse],
        *,
        db_path: Path,
        event_bus: EventBus | None = None,
        model: str | None = None,
        max_iterations: int = 6,
        temperature: float = 0.7,
        system_prompt_override: str | None = None,
    ) -> None:
        self._llm = llm_router
        self._db_path = db_path
        self._event_bus = event_bus
        self._model = model
        self._max_iterations = max_iterations
        self._temperature = temperature
        self._system_prompt = system_prompt_override or RESEARCH_SYSTEM

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
                    "research_agent_propose_failed",
                    strategy_id=parent["strategy_id"],
                    error=str(exc),
                )
        return mutations

    def _propose_one(self, parent: StrategyRow) -> ProposedMutation | None:
        try:
            cfg: dict = json.loads(parent["params_json"])
        except (json.JSONDecodeError, KeyError):
            return None

        detector_type = cfg.get("type")
        if detector_type not in _SUPPORTED_TYPES:
            return None

        initial_msg = research_initial_message(
            strategy_id=parent["strategy_id"],
            strategy_name=parent["name"],
            detector_type=detector_type,
            params=cfg,
            mean_sharpe=parent["mean_sharpe"],
            mean_sortino=parent["mean_sortino"],
            n_trades=parent["total_n_trades"],
        )
        tools = build_research_tools()

        with connect(self._db_path) as conn:
            raw = run_react_loop(
                self._llm,
                tools,
                self._system_prompt,
                initial_msg,
                conn,
                max_iterations=self._max_iterations,
                event_bus=self._event_bus,
                role="research",
                parent_strategy_id=parent["strategy_id"],
                model=self._model,
                temperature=self._temperature,
                trace_name="research_agent_mutator",
            )

        if raw is None:
            return None

        try:
            data = _parse_json(raw)
            proposal = ResearchProposal.model_validate(data)
        except Exception as exc:
            log.warning("research_agent_parse_failed", error=str(exc)[:120])
            return None

        if proposal.proposal_type == "sma_param_delta":
            if proposal.sma is None:
                return None
            child_config: DetectorConfig = {
                "type": "sma_crossover",
                "fast": proposal.sma.fast,
                "slow": proposal.sma.slow,
            }
            reasoning = proposal.sma.reasoning
        else:
            if proposal.rsi is None:
                return None
            child_config = {
                "type": "rsi_oversold",
                "period": proposal.rsi.period,
                "oversold": proposal.rsi.oversold,
            }
            reasoning = proposal.rsi.reasoning

        return ProposedMutation(
            parent_strategy_id=parent["strategy_id"],
            child_config=child_config,
            reasoning=f"[research] {reasoning} (conf={proposal.confidence:.2f})",
            mutator=self.name,
        )
