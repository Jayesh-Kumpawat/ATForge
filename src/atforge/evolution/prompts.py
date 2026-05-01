"""Prompt templates and Pydantic response schemas for LLM-driven mutators."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Pydantic response schemas — LLM must emit JSON matching these shapes.
# ---------------------------------------------------------------------------


class SmaParamsDelta(BaseModel):
    fast: int = Field(ge=2, le=50)
    slow: int = Field(ge=10, le=200)
    reasoning: str

    @model_validator(mode="after")
    def fast_lt_slow(self) -> SmaParamsDelta:
        if self.fast >= self.slow:
            raise ValueError(f"fast ({self.fast}) must be < slow ({self.slow})")
        return self


class RsiParamsDelta(BaseModel):
    period: int = Field(ge=2, le=50)
    oversold: int = Field(ge=10, le=45)
    reasoning: str


class CompositionChoice(BaseModel):
    op: Literal["AND", "OR"]
    reasoning: str


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SMA_SYSTEM = (
    "You are a quantitative analyst mutating a moving-average crossover strategy. "
    "Reply ONLY with a valid JSON object — no markdown fences, no extra text."
)

_RSI_SYSTEM = (
    "You are a quantitative analyst mutating an RSI mean-reversion strategy. "
    "Reply ONLY with a valid JSON object — no markdown fences, no extra text."
)

_COMPOSITION_SYSTEM = (
    "You are a quantitative analyst composing two trading strategies. "
    "Reply ONLY with a valid JSON object — no markdown fences, no extra text."
)

_SMA_SCHEMA = '{"fast": <int 2-50>, "slow": <int 10-200 and > fast>, "reasoning": "<str>"}'
_RSI_SCHEMA = '{"period": <int 2-50>, "oversold": <int 10-45>, "reasoning": "<str>"}'
_COMP_SCHEMA = '{"op": "AND" | "OR", "reasoning": "<str>"}'


def sma_param_delta_prompt(
    current_fast: int,
    current_slow: int,
    mean_sharpe: float,
    mean_sortino: float,
    n_trades: int,
) -> str:
    return (
        f"Current SMA crossover: fast={current_fast}, slow={current_slow}.\n"
        f"Performance: Sharpe={mean_sharpe:.3f}, Sortino={mean_sortino:.3f}, n_trades={n_trades}.\n"
        f"Propose new fast and slow window values to improve risk-adjusted returns.\n"
        f"Constraints: 2 <= fast <= 50, fast < slow <= 200.\n"
        f"Output schema: {_SMA_SCHEMA}"
    )


def rsi_param_delta_prompt(
    current_period: int,
    current_oversold: int,
    mean_sharpe: float,
    mean_sortino: float,
    n_trades: int,
) -> str:
    return (
        f"Current RSI strategy: period={current_period}, oversold={current_oversold}.\n"
        f"Performance: Sharpe={mean_sharpe:.3f}, Sortino={mean_sortino:.3f}, n_trades={n_trades}.\n"
        f"Propose new period and oversold values to improve signal quality.\n"
        f"Constraints: 2 <= period <= 50, 10 <= oversold <= 45.\n"
        f"Output schema: {_RSI_SCHEMA}"
    )


def composition_prompt(
    left_name: str,
    left_sharpe: float,
    right_name: str,
    right_sharpe: float,
) -> str:
    return (
        f"Strategy A: '{left_name}' (Sharpe={left_sharpe:.3f})\n"
        f"Strategy B: '{right_name}' (Sharpe={right_sharpe:.3f})\n"
        "Choose AND (both must fire on same bar) or OR (either fires).\n"
        "AND reduces trade frequency but improves precision; OR increases frequency.\n"
        f"Output schema: {_COMP_SCHEMA}"
    )


def get_system_prompt(mutator_type: str) -> str:
    if mutator_type == "sma":
        return _SMA_SYSTEM
    if mutator_type == "rsi":
        return _RSI_SYSTEM
    return _COMPOSITION_SYSTEM
