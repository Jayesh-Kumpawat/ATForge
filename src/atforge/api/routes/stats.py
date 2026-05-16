"""/stats endpoint — DB-wide counts for the Overview screen."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from atforge.api.deps import get_db
from atforge.api.schemas.stats import FamilyCount, StatsResponse

router = APIRouter(tags=["stats"])

_COUNTABLE = {"runs", "strategies", "backtest_runs", "experiments"}


def _count(db: sqlite3.Connection, table: str) -> int:
    assert table in _COUNTABLE  # guard — table names are literals, never user input
    row = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0]) if row else 0


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: sqlite3.Connection = Depends(get_db)) -> StatsResponse:
    best_row = db.execute("SELECT MAX(sharpe) FROM backtest_runs WHERE success = 1").fetchone()
    best_sharpe = best_row[0] if best_row and best_row[0] is not None else None

    fam_rows = db.execute(
        "SELECT family, COUNT(*) AS n FROM strategies GROUP BY family ORDER BY n DESC, family"
    ).fetchall()

    return StatsResponse(
        n_runs=_count(db, "runs"),
        n_strategies=_count(db, "strategies"),
        n_backtests=_count(db, "backtest_runs"),
        n_experiments=_count(db, "experiments"),
        best_sharpe=best_sharpe,
        families=[FamilyCount(family=r[0], count=int(r[1])) for r in fam_rows],
    )
