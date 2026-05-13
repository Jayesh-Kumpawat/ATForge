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
