"""/strategies endpoints — list, detail, backtests, lineage, reasoning."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from atforge.api.deps import get_db
from atforge.api.schemas.common import ErrorDetail
from atforge.api.schemas.strategies import (
    BacktestListResponse,
    BacktestRow,
    LineageNode,
    LineageResponse,
    MetricsSummary,
    ReasoningEntry,
    ReasoningResponse,
    StrategyDetail,
    StrategyListItem,
    StrategyListResponse,
)

router = APIRouter(prefix="/strategies", tags=["strategies"])


def _strategy_metrics(db: sqlite3.Connection, strategy_id: int) -> MetricsSummary:
    row = db.execute(
        """
        SELECT MAX(sharpe) AS best_sharpe,
               MAX(sortino) AS best_sortino,
               AVG(win_rate) AS avg_wr,
               MIN(CAST(max_drawdown AS REAL)) AS max_dd,
               COUNT(*) AS n
        FROM backtest_runs
        WHERE strategy_id = ? AND success = 1
        """,
        (strategy_id,),
    ).fetchone()
    return MetricsSummary(
        best_sharpe=row["best_sharpe"],
        best_sortino=row["best_sortino"],
        avg_win_rate=row["avg_wr"],
        max_drawdown=row["max_dd"],
        n_backtests=int(row["n"] or 0),
    )


def _strategy_parent(db: sqlite3.Connection, strategy_id: int) -> int | None:
    row = db.execute(
        """
        SELECT parent_strategy_id FROM experiments
        WHERE child_strategy_id = ? AND child_strategy_id IS NOT NULL
        ORDER BY experiment_id DESC LIMIT 1
        """,
        (strategy_id,),
    ).fetchone()
    return int(row["parent_strategy_id"]) if row and row["parent_strategy_id"] is not None else None


def _strategy_generation(db: sqlite3.Connection, strategy_id: int) -> int:
    row = db.execute(
        "SELECT MIN(generation) AS gen FROM backtest_runs WHERE strategy_id = ?",
        (strategy_id,),
    ).fetchone()
    return int(row["gen"]) if row and row["gen"] is not None else 0


@router.get("", response_model=StrategyListResponse)
def list_strategies(
    family: str | None = Query(None),
    min_sharpe: float | None = Query(None),
    generation: int | None = Query(None),
    sort: str = Query("sharpe_desc", pattern="^(sharpe_desc|sharpe_asc|name_asc|gen_desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: sqlite3.Connection = Depends(get_db),
) -> StrategyListResponse:
    where: list[str] = []
    params: list[Any] = []

    if family is not None:
        families = [f.strip() for f in family.split(",") if f.strip()]
        if families:
            where.append("s.family IN (" + ",".join("?" * len(families)) + ")")
            params.extend(families)
    if min_sharpe is not None:
        where.append(
            "(SELECT MAX(sharpe) FROM backtest_runs br WHERE br.strategy_id = s.strategy_id) >= ?"
        )
        params.append(min_sharpe)
    if generation is not None:
        where.append(
            "(SELECT MIN(generation) FROM backtest_runs br WHERE br.strategy_id = s.strategy_id) = ?"
        )
        params.append(generation)

    where_clause = ("WHERE " + " AND ".join(where)) if where else ""

    order_by = {
        "sharpe_desc": "best_sharpe DESC NULLS LAST",
        "sharpe_asc": "best_sharpe ASC NULLS LAST",
        "name_asc": "s.name ASC",
        "gen_desc": "min_gen DESC",
    }[sort]

    total_row = db.execute(f"SELECT COUNT(*) FROM strategies s {where_clause}", params).fetchone()
    total = int(total_row[0]) if total_row else 0

    offset = (page - 1) * page_size
    rows = db.execute(
        f"""
        SELECT
            s.strategy_id, s.name, s.family, s.params_json,
            (SELECT MAX(sharpe) FROM backtest_runs br WHERE br.strategy_id = s.strategy_id) AS best_sharpe,
            (SELECT MAX(sortino) FROM backtest_runs br WHERE br.strategy_id = s.strategy_id) AS best_sortino,
            (SELECT AVG(win_rate) FROM backtest_runs br WHERE br.strategy_id = s.strategy_id) AS avg_wr,
            (SELECT MIN(generation) FROM backtest_runs br WHERE br.strategy_id = s.strategy_id) AS min_gen,
            (SELECT COUNT(*) FROM backtest_runs br WHERE br.strategy_id = s.strategy_id) AS n_backtests
        FROM strategies s
        {where_clause}
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    ).fetchall()

    items: list[StrategyListItem] = []
    for row in rows:
        items.append(
            StrategyListItem(
                strategy_id=int(row["strategy_id"]),
                name=row["name"],
                family=row["family"],
                generation=int(row["min_gen"] or 0),
                parent_strategy_id=_strategy_parent(db, int(row["strategy_id"])),
                best_sharpe=row["best_sharpe"],
                best_sortino=row["best_sortino"],
                avg_win_rate=row["avg_wr"],
                n_backtests=int(row["n_backtests"] or 0),
            )
        )

    return StrategyListResponse(strategies=items, total=total, page=page, page_size=page_size)


@router.get("/{strategy_id}", response_model=StrategyDetail)
def get_strategy(strategy_id: int, db: sqlite3.Connection = Depends(get_db)) -> StrategyDetail:
    row = db.execute(
        "SELECT strategy_id, name, family, params_json, description FROM strategies WHERE strategy_id = ?",
        (strategy_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": ErrorDetail(
                    code="STRATEGY_NOT_FOUND", message=f"strategy_id={strategy_id}"
                ).model_dump()
            },
        )
    return StrategyDetail(
        strategy_id=int(row["strategy_id"]),
        name=row["name"],
        family=row["family"],
        params=json.loads(row["params_json"]),
        description=row["description"],
        parent_strategy_id=_strategy_parent(db, strategy_id),
        created_at=None,
        metrics_summary=_strategy_metrics(db, strategy_id),
    )
