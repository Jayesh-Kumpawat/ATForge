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
    reasoning: str = Field(max_length=256)

    @model_validator(mode="after")
    def fast_lt_slow(self) -> SmaParamsDelta:
        if self.fast >= self.slow:
            raise ValueError(f"fast ({self.fast}) must be < slow ({self.slow})")
        return self


class RsiParamsDelta(BaseModel):
    period: int = Field(ge=2, le=50)
    oversold: int = Field(ge=10, le=45)
    reasoning: str = Field(max_length=256)


class CompositionChoice(BaseModel):
    op: Literal["AND", "OR"]
    reasoning: str = Field(max_length=256)


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SMA_SYSTEM = (
    "You are a quantitative analyst mutating a moving-average crossover strategy for NSE Indian equities (daily bars). "
    "Reply ONLY with a valid JSON object — no markdown fences, no extra text."
)

_RSI_SYSTEM = (
    "You are a quantitative analyst mutating an RSI mean-reversion strategy for NSE Indian equities (daily bars). "
    "Reply ONLY with a valid JSON object — no markdown fences, no extra text."
)

_COMPOSITION_SYSTEM = (
    "You are a quantitative analyst composing two trading strategies for NSE Indian equities (daily bars). "
    "Reply ONLY with a valid JSON object — no markdown fences, no extra text."
)

_SMA_SCHEMA = '{"fast": <int 2-50>, "slow": <int 10-200 and > fast>, "reasoning": "<one sentence>"}'
_RSI_SCHEMA = '{"period": <int 2-50>, "oversold": <int 10-45>, "reasoning": "<one sentence>"}'
_COMP_SCHEMA = '{"op": "AND" | "OR", "reasoning": "<one sentence>"}'

_SMA_EXAMPLES = (
    "Examples:\n"
    '  fast=5,slow=20,Sharpe=0.4,trades=8  → {"fast": 8, "slow": 30, "reasoning": "Widen both windows to reduce noise on daily NSE bars."}\n'
    '  fast=20,slow=60,Sharpe=1.2,trades=25 → {"fast": 15, "slow": 45, "reasoning": "Shorten windows to maintain quality while increasing trade frequency."}'
)

_RSI_EXAMPLES = (
    "Examples:\n"
    '  period=14,oversold=30,Sharpe=0.5,trades=10 → {"period": 10, "oversold": 25, "reasoning": "Shorter period and lower threshold to capture more reversals."}\n'
    '  period=7,oversold=20,Sharpe=0.3,trades=20  → {"period": 14, "oversold": 30, "reasoning": "Widen period and raise oversold level to improve signal precision."}'
)

_COMP_EXAMPLES = (
    "Examples:\n"
    '  SMA_10x30(Sharpe=0.8) + RSI_14_reclaim_30(Sharpe=0.5) → {"op": "AND", "reasoning": "AND filters to setups where trend and momentum align simultaneously."}\n'
    '  CDLENGULFING_bullish(Sharpe=0.6) + SMA_20x50(Sharpe=0.9) → {"op": "OR", "reasoning": "OR captures more entries since these two signals rarely overlap."}'
)


def sma_param_delta_prompt(
    current_fast: int,
    current_slow: int,
    mean_sharpe: float,
    mean_sortino: float,
    n_trades: int,
) -> str:
    return (
        f"Current SMA crossover: fast={current_fast}, slow={current_slow}.\n"
        f"Performance: Sharpe={mean_sharpe:.3f}, Sortino={mean_sortino:.3f}, trades={n_trades}.\n"
        f"\n"
        f"{_SMA_EXAMPLES}\n"
        f"\n"
        f"Constraints: 2 <= fast <= 50, fast < slow <= 200.\n"
        f"Propose new fast and slow values to improve risk-adjusted returns.\n"
        f"Output: {_SMA_SCHEMA}"
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
        f"Performance: Sharpe={mean_sharpe:.3f}, Sortino={mean_sortino:.3f}, trades={n_trades}.\n"
        f"\n"
        f"{_RSI_EXAMPLES}\n"
        f"\n"
        f"Constraints: 2 <= period <= 50, 10 <= oversold <= 45.\n"
        f"Propose new period and oversold values to improve signal quality.\n"
        f"Output: {_RSI_SCHEMA}"
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
        f"AND = both must fire on same bar (higher precision, fewer trades).\n"
        f"OR  = either fires (higher frequency, lower precision).\n"
        f"\n"
        f"{_COMP_EXAMPLES}\n"
        f"\n"
        f"Output: {_COMP_SCHEMA}"
    )


def get_system_prompt(mutator_type: str) -> str:
    if mutator_type == "sma":
        return _SMA_SYSTEM
    if mutator_type == "rsi":
        return _RSI_SYSTEM
    return _COMPOSITION_SYSTEM
