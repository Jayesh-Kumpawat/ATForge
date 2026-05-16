"""/runs endpoints — list + detail."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from atforge.api.deps import _resolve_db_path, get_db
from atforge.api.events.stream import event_stream
from atforge.api.schemas.common import ErrorDetail
from atforge.api.schemas.runs import (
    EventEnvelope,
    ExperimentRow,
    GenerationSharpe,
    RankingRow,
    RunEvolutionResponse,
    RunListResponse,
    RunRankingsResponse,
    RunSummary,
    TimelineResponse,
)
from atforge.storage.repo import (
    get_best_sharpe_per_generation,
    get_experiments_for_run,
    top_rankings,
)

router = APIRouter(prefix="/runs", tags=["runs"])


def _ensure_run_exists(db: sqlite3.Connection, run_id: str) -> None:
    row = db.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": ErrorDetail(code="RUN_NOT_FOUND", message=f"run_id={run_id}").model_dump()
            },
        )


def _parse_iso(s: str | None) -> datetime | None:
    if s is None:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _row_to_summary(
    row: sqlite3.Row,
    n_backtests: int,
    n_failures: int,
    current_generation: int | None,
) -> RunSummary:
    keys = row.keys()
    status_raw = row["status"] if "status" in keys else None
    finished_at = _parse_iso(row["finished_at"] if "finished_at" in keys else None)

    if finished_at is not None:
        status = "failed" if status_raw == "failed" else "done"
    elif status_raw == "failed":
        status = "failed"
    elif status_raw in ("running", None):
        status = "running"
    else:
        status = "done"  # success / partial

    return RunSummary(
        run_id=row["run_id"],
        started_at=_parse_iso(row["started_at"] if "started_at" in keys else None),
        finished_at=finished_at,
        status=status,
        n_symbols=None,
        max_generations=None,
        current_generation=current_generation,
        n_backtests=n_backtests,
        n_failures=n_failures,
    )


def _count_backtests(db: sqlite3.Connection, run_id: str) -> int:
    row = db.execute(
        "SELECT COUNT(*) FROM backtest_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    return int(row[0]) if row else 0


def _count_failures(db: sqlite3.Connection, run_id: str) -> int:
    row = db.execute(
        "SELECT COUNT(*) FROM backtest_runs WHERE run_id = ? AND success = 0", (run_id,)
    ).fetchone()
    return int(row[0]) if row else 0


def _current_generation(db: sqlite3.Connection, run_id: str) -> int | None:
    row = db.execute(
        """
        SELECT MAX(generation) FROM pipeline_events
        WHERE run_id = ? AND event_type = 'EvtGenerationDone'
        """,
        (run_id,),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return int(row[0])


@router.get("", response_model=RunListResponse)
def list_runs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
) -> RunListResponse:
    total_row = db.execute("SELECT COUNT(*) FROM runs").fetchone()
    total = int(total_row[0]) if total_row else 0

    rows = db.execute(
        "SELECT * FROM runs ORDER BY started_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()

    summaries = [
        _row_to_summary(
            row,
            n_backtests=_count_backtests(db, row["run_id"]),
            n_failures=_count_failures(db, row["run_id"]),
            current_generation=_current_generation(db, row["run_id"]),
        )
        for row in rows
    ]

    return RunListResponse(runs=summaries, total=total, limit=limit, offset=offset)


@router.get("/{run_id}", response_model=RunSummary)
def get_run(run_id: str, db: sqlite3.Connection = Depends(get_db)) -> RunSummary:
    row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": ErrorDetail(
                    code="RUN_NOT_FOUND", message=f"run_id={run_id}"
                ).model_dump()
            },
        )
    return _row_to_summary(
        row,
        n_backtests=_count_backtests(db, run_id),
        n_failures=_count_failures(db, run_id),
        current_generation=_current_generation(db, run_id),
    )


@router.get("/{run_id}/events")
async def stream_events(run_id: str, after_event_id: int = 0) -> StreamingResponse:
    """SSE stream of pipeline_events for one run."""
    db_path = _resolve_db_path()

    async def _generator():
        async for chunk in event_stream(db_path, run_id, after_event_id):
            yield chunk

    return StreamingResponse(_generator(), media_type="text/event-stream")


@router.get("/{run_id}/rankings", response_model=RunRankingsResponse)
def get_run_rankings(
    run_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: sqlite3.Connection = Depends(get_db),
) -> RunRankingsResponse:
    _ensure_run_exists(db, run_id)
    rows = top_rankings(db, limit=limit, run_id=run_id)
    return RunRankingsResponse(run_id=run_id, rankings=[RankingRow(**r) for r in rows])


@router.get("/{run_id}/evolution", response_model=RunEvolutionResponse)
def get_run_evolution(
    run_id: str,
    db: sqlite3.Connection = Depends(get_db),
) -> RunEvolutionResponse:
    _ensure_run_exists(db, run_id)
    experiments = [ExperimentRow(**e) for e in get_experiments_for_run(db, run_id)]
    progression = [GenerationSharpe(**g) for g in get_best_sharpe_per_generation(db, run_id)]
    return RunEvolutionResponse(
        run_id=run_id, experiments=experiments, sharpe_progression=progression
    )


@router.get("/{run_id}/timeline", response_model=TimelineResponse)
def get_run_timeline(
    run_id: str,
    db: sqlite3.Connection = Depends(get_db),
) -> TimelineResponse:
    _ensure_run_exists(db, run_id)
    rows = db.execute(
        "SELECT event_id, run_id, generation, ts_ms, event_type, payload "
        "FROM pipeline_events WHERE run_id = ? ORDER BY event_id",
        (run_id,),
    ).fetchall()
    events = [
        EventEnvelope(
            event_id=r["event_id"],
            run_id=r["run_id"],
            generation=r["generation"],
            ts_ms=r["ts_ms"],
            event_type=r["event_type"],
            payload=json.loads(r["payload"]) if r["payload"] else {},
        )
        for r in rows
    ]
    return TimelineResponse(run_id=run_id, events=events)
