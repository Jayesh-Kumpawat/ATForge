"""Pydantic models for /strategies endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class MetricsSummary(BaseModel):
    best_sharpe: float | None
    best_sortino: float | None
    avg_win_rate: float | None
    max_drawdown: float | None
    n_backtests: int


class StrategyListItem(BaseModel):
    strategy_id: int
    name: str
    family: str
    generation: int
    parent_strategy_id: int | None
    best_sharpe: float | None
    best_sortino: float | None
    avg_win_rate: float | None
    n_backtests: int


class StrategyListResponse(BaseModel):
    strategies: list[StrategyListItem]
    total: int
    page: int
    page_size: int


class StrategyDetail(BaseModel):
    strategy_id: int
    name: str
    family: str
    params: dict[str, Any]
    description: str | None
    parent_strategy_id: int | None
    created_at: datetime | None
    metrics_summary: MetricsSummary


class BacktestRow(BaseModel):
    run_id: str
    symbol: str
    generation: int
    n_trades: int
    sharpe: float | None
    sortino: float | None
    win_rate: float | None
    max_drawdown: float | None
    cagr: float | None


class BacktestListResponse(BaseModel):
    strategy_id: int
    backtests: list[BacktestRow]


class LineageNode(BaseModel):
    strategy_id: int
    name: str
    generation: int
    mutator: str | None
    accepted: bool | None
    sharpe: float | None


class LineageResponse(BaseModel):
    strategy_id: int
    ancestors: list[LineageNode]
    descendants: list[LineageNode]


class ReasoningEntry(BaseModel):
    run_id: str
    generation: int
    mutator: str
    parent_strategy_id: int | None
    reasoning: str
    accepted: bool
    delta_sharpe: float | None


class ReasoningResponse(BaseModel):
    strategy_id: int
    entries: list[ReasoningEntry]


class EquityPoint(BaseModel):
    t: int
    equity: float
    drawdown: float


class EquityResponse(BaseModel):
    strategy_id: int
    symbol: str
    run_id: str
    initial_capital: float
    points: list[EquityPoint]


class OHLCVBar(BaseModel):
    t: int
    o: float
    h: float
    l: float
    c: float
    v: float


class SignalMarker(BaseModel):
    t: int
    type: Literal["entry", "exit"]
    price: float


class SignalsResponse(BaseModel):
    strategy_id: int
    symbol: str
    run_id: str
    bars: list[OHLCVBar]
    signals: list[SignalMarker]
