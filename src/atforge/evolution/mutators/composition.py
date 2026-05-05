"""CompositionMutator — LLM picks AND/OR combination of two parent detectors.

Emits nested DetectorConfig. Bounded by max_nesting_depth to prevent explosion.
Skips pairs where either parent is already at max nesting depth.
Validates LLM response with up to 3 retries on parse failure.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Callable

import structlog

from atforge.evolution.mutators._utils import call_llm_with_schema
from atforge.evolution.prompts import CompositionChoice, composition_prompt, get_system_prompt
from atforge.evolution.types import DetectorConfig, ProposedMutation, StrategyRow
from atforge.llm.types import LlmRequest, LlmResponse

log = structlog.get_logger(__name__)


def _nesting_depth(cfg: dict) -> int:
    """Max nesting depth of a DetectorConfig tree. Leaf = 0."""
    t = cfg.get("type")
    if t in ("and", "or"):
        return 1 + max(_nesting_depth(cfg["left"]), _nesting_depth(cfg["right"]))
    return 0


class CompositionMutator:
    """Propose AND/OR compositions of top-N parent strategy pairs via LLM."""

    name = "composition"

    def __init__(
        self,
        llm_router: Callable[[LlmRequest], LlmResponse],
        *,
        max_nesting_depth: int = 2,
        model: str | None = None,
        temperature: float = 0.7,
    ) -> None:
        self._llm = llm_router
        self._max_depth = max_nesting_depth
        self._model = model
        self._temperature = temperature

    def propose(
        self,
        parents: list[StrategyRow],
        k: int,
    ) -> list[ProposedMutation]:
        mutations: list[ProposedMutation] = []
        pairs = list(itertools.combinations(parents, 2))
        for left_row, right_row in pairs[: k * 2]:  # cap to avoid N^2 explosion
            try:
                mut = self._propose_pair(left_row, right_row)
                if mut is not None:
                    mutations.append(mut)
                if len(mutations) >= k:
                    break
            except Exception as exc:
                log.warning(
                    "composition_propose_failed",
                    left=left_row["strategy_id"],
                    right=right_row["strategy_id"],
                    error=str(exc),
                )
        return mutations

    def _propose_pair(
        self,
        left_row: StrategyRow,
        right_row: StrategyRow,
    ) -> ProposedMutation | None:
        try:
            left_cfg: dict = json.loads(left_row["params_json"])
            right_cfg: dict = json.loads(right_row["params_json"])
        except (json.JSONDecodeError, KeyError):
            return None

        # Enforce max nesting depth
        if (
            _nesting_depth(left_cfg) >= self._max_depth
            or _nesting_depth(right_cfg) >= self._max_depth
        ):
            log.debug("composition_depth_limit", left=left_row["name"], right=right_row["name"])
            return None

        prompt = composition_prompt(
            left_name=left_row["name"],
            left_sharpe=left_row["mean_sharpe"],
            right_name=right_row["name"],
            right_sharpe=right_row["mean_sharpe"],
        )
        request = LlmRequest(
            prompt=prompt,
            system=get_system_prompt("composition"),
            model=self._model,
            temperature=self._temperature,
            max_tokens=1024,
            trace_name="composition_mutator",
            response_schema=CompositionChoice,
        )
        choice = call_llm_with_schema(self._llm, request, CompositionChoice)
        if choice is None:
            return None

        child_config: DetectorConfig = {
            "type": "and" if choice.op == "AND" else "or",
            "left": left_cfg,
            "right": right_cfg,
        }

        # Use the higher-Sharpe parent as the "parent_strategy_id"
        parent_row = left_row if left_row["mean_sharpe"] >= right_row["mean_sharpe"] else right_row
        return ProposedMutation(
            parent_strategy_id=parent_row["strategy_id"],
            child_config=child_config,
            reasoning=choice.reasoning,
            mutator=self.name,
        )
