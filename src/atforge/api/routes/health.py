"""Liveness + DB ping."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from atforge.api.deps import get_db
from atforge.api.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(db: sqlite3.Connection = Depends(get_db)) -> HealthResponse:
    try:
        db.execute("SELECT 1").fetchone()
        db_status = "ok"
    except Exception:
        db_status = "error"
    return HealthResponse(status="ok", db=db_status)
