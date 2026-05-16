"""Pydantic models for /runs endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class RunSummary(BaseModel):
    run_id: str
    started_at: datetime | None
    finished_at: datetime | None
    status: Literal["running", "done", "failed", "unknown"]
    n_symbols: int | None
    max_generations: int | None
    current_generation: int | None
    n_backtests: int
    n_failures: int


class RunListResponse(BaseModel):
    runs: list[RunSummary]
    total: int
    limit: int
    offset: int


class EventEnvelope(BaseModel):
    event_id: int
    run_id: str
    ts_ms: int
    event_type: str
    generation: int | None
    payload: dict[str, Any]


class RankingRow(BaseModel):
    backtest_id: int
    symbol: str
    strategy_id: int
    strategy_name: str
    family: str
    generation: int
    n_trades: int
    sharpe: float | None
    sortino: float | None
    cagr: float | None
    win_rate: float | None
    max_drawdown: str | None
    total_return: str | None


class RunRankingsResponse(BaseModel):
    run_id: str
    rankings: list[RankingRow]


class ExperimentRow(BaseModel):
    experiment_id: int
    generation: int
    mutator: str | None
    accepted: int | None
    delta_sharpe: float | None
    reasoning: str | None
    composite_score: str | None
    mutation_json: str | None
    created_at: str | None
    parent_name: str | None
    child_name: str | None
    parent_strategy_id: int | None
    child_strategy_id: int | None


class GenerationSharpe(BaseModel):
    generation: int
    best_sharpe: float | None
    n_backtests: int


class RunEvolutionResponse(BaseModel):
    run_id: str
    experiments: list[ExperimentRow]
    sharpe_progression: list[GenerationSharpe]


class TimelineResponse(BaseModel):
    run_id: str
    events: list[EventEnvelope]
