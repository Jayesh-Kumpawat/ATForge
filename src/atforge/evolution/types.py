"""Shared types for the Phase 2a evolution layer.

All mutators, the ratchet, and graph nodes import from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, TypedDict, runtime_checkable


class DetectorConfig(TypedDict, total=False):
    """Serializable config for any PatternDetector. 'type' is required."""

    type: str  # "sma_crossover" | "rsi_oversold" | "talib_cdl" | "and" | "or"
    # SmaCrossover
    fast: int
    slow: int
    # RsiOversoldReclaim
    period: int
    oversold: int
    # TalibCdlDetector
    cdl_name: str
    direction: str
    # AndDetector / OrDetector (nested)
    left: DetectorConfig
    right: DetectorConfig


class StrategyRow(TypedDict):
    """One aggregated strategy row as passed to mutators."""

    strategy_id: int
    name: str
    family: str
    params_json: str  # raw JSON from DB
    mean_sharpe: float
    mean_sortino: float
    total_n_trades: int
    max_drawdown: str  # str(Decimal)
    generation: int


@dataclass(frozen=True)
class ProposedMutation:
    """Output of a Mutator.propose call: a single candidate child config."""

    parent_strategy_id: int
    child_config: DetectorConfig
    reasoning: str
    mutator: str  # "param_delta" | "composition"


@dataclass(frozen=True)
class EvaluationResult:
    """Per-strategy aggregated metrics across all symbols in one run/generation."""

    strategy_id: int
    run_id: str
    generation: int
    mean_sharpe: float
    mean_sortino: float
    total_n_trades: int
    max_drawdown: Decimal  # max across symbols — stays Decimal, no float
    n_symbols: int


@dataclass(frozen=True)
class RatchetThresholds:
    min_delta_sharpe: float = 0.05
    min_delta_sortino: float = 0.02
    max_drawdown_tol: float = 0.10  # child_dd <= parent_dd * (1 + tol)
    min_n_trades: int = 5


@dataclass(frozen=True)
class RatchetVerdict:
    accepted: bool
    delta_sharpe: float
    delta_sortino: float
    dd_ratio: float  # float OK — analytical ratio, not money
    composite_score: dict[str, float]
    reasoning: str


@dataclass(frozen=True)
class MutationRecord:
    """Written to `experiments` table after ratchet judgment."""

    run_id: str
    generation: int
    parent_strategy_id: int
    child_strategy_id: int
    mutator: str
    mutation_json: str  # JSON of child_config
    verdict: RatchetVerdict


@runtime_checkable
class Mutator(Protocol):
    name: str

    def propose(
        self,
        parents: list[StrategyRow],
        k: int,
    ) -> list[ProposedMutation]: ...
