"""Pydantic models for the /stats endpoint."""
from __future__ import annotations

from pydantic import BaseModel


class FamilyCount(BaseModel):
    family: str
    count: int


class StatsResponse(BaseModel):
    n_runs: int
    n_strategies: int
    n_backtests: int
    n_experiments: int
    best_sharpe: float | None
    families: list[FamilyCount]
