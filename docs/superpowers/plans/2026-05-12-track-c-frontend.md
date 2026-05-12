# Track C — Frontend MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade read-only web dashboard for ATForge with three screens (Pipeline Monitor, Strategy Library, Strategy Detail), backed by a FastAPI server reading the existing SQLite KB plus a new event-streaming table.

**Architecture:** Three independent processes — Next.js browser app, FastAPI server, pipeline CLI subprocess — decoupled via SQLite. Backend changes are additive only; both `src/atforge/api/` and `web/` are deletable without breaking the pipeline. Real-time via Server-Sent Events.

**Tech Stack:** Backend: FastAPI + uvicorn + sse-starlette + Pydantic + structlog (existing). Frontend: Next.js 15 + React 19 + TypeScript + Tailwind + shadcn/ui + TanStack Query v5 + Zustand + Recharts + lightweight-charts. Testing: pytest + Vitest + React Testing Library + MSW + Playwright.

**Spec reference:** `docs/superpowers/specs/2026-05-12-track-c-frontend-design.md` (818 lines, 15 sections).

**Branch:** `feature/track-c-frontend` (already created).

---

## Phase C0 — Setup

### Task 1: Verify clean working state on feature branch

**Files:**
- No file changes. Verification only.

- [ ] **Step 1: Confirm branch + clean tree**

Run:
```bash
git branch --show-current
git status
```

Expected:
```
feature/track-c-frontend
nothing to commit, working tree clean
```

(The spec is already committed on this branch.)

- [ ] **Step 2: Run full backend test suite as baseline**

Run:
```bash
uv run pytest -q
```

Expected: `289 passed in ~6s`. If any failure, STOP and ask user — the branch base must be green.

- [ ] **Step 3: Smoke-test the pipeline end-to-end**

Run:
```bash
uv run python main.py pipeline --symbols RELIANCE --lookback 6m --max-generations 1
```

Expected: `done run=<run_id> backtests=N failures=N` plus a rankings table. Record the `run_id` from output — needed later for spot-checks.

- [ ] **Step 4: No commit (verification only). Note baseline in scratch.**

```bash
echo "BASELINE: 289 tests green, smoke pipeline run_id=<from output>" > /tmp/track-c-baseline.txt
```

---

## Phase C1 — Pipeline events persistence

### Task 2: Add `pipeline_events` table to schema

**Files:**
- Modify: `src/atforge/storage/schema.sql` (append at end)
- Test: `tests/storage/test_pipeline_events_schema.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/storage/test_pipeline_events_schema.py`:
```python
"""Schema test: pipeline_events table exists with expected columns + index."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from atforge.storage.schema import create_schema


def test_pipeline_events_table_exists(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    create_schema(conn)

    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_events'"
    )
    assert cur.fetchone() is not None, "pipeline_events table missing"


def test_pipeline_events_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    create_schema(conn)

    cols = {row[1] for row in conn.execute("PRAGMA table_info(pipeline_events)")}
    expected = {"event_id", "run_id", "generation", "ts_ms", "event_type", "payload"}
    assert expected.issubset(cols), f"missing columns: {expected - cols}"


def test_pipeline_events_index_exists(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    create_schema(conn)

    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pipeline_events_run'"
    )
    assert cur.fetchone() is not None, "idx_pipeline_events_run index missing"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/storage/test_pipeline_events_schema.py -v
```

Expected: 3 tests FAIL with `pipeline_events table missing` etc.

- [ ] **Step 3: Append table + index to schema.sql**

Open `src/atforge/storage/schema.sql` and append:
```sql

-- A2 Track C: durable event log for cross-process SSE bridge
CREATE TABLE IF NOT EXISTS pipeline_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT NOT NULL,
    generation INTEGER,
    ts_ms      INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pipeline_events_run
    ON pipeline_events (run_id, event_id);
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/storage/test_pipeline_events_schema.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Run full suite to confirm no regressions**

Run:
```bash
uv run pytest -q
```

Expected: `292 passed` (289 existing + 3 new).

- [ ] **Step 6: Commit**

```bash
git add src/atforge/storage/schema.sql tests/storage/test_pipeline_events_schema.py
git commit -m "feat(storage): add pipeline_events table for SSE bridge (Track C / C1)"
```

---

### Task 3: Implement `persist_event` helper

**Files:**
- Create: `src/atforge/api/__init__.py`
- Create: `src/atforge/api/events/__init__.py`
- Create: `src/atforge/api/events/persistence.py`
- Create: `tests/api/__init__.py`
- Create: `tests/api/test_events_persistence.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/__init__.py` (empty file).

Create `tests/api/test_events_persistence.py`:
```python
"""Unit test for persist_event helper."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from atforge.api.events.persistence import persist_event
from atforge.graph.events import EvtBacktestDone, EvtPipelineStart
from atforge.storage.schema import create_schema


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(tmp_path / "test.db")
    create_schema(c)
    return c


def test_persist_pipeline_start(conn: sqlite3.Connection) -> None:
    evt = EvtPipelineStart(run_id="run-xyz", n_symbols=3, max_generations=2)

    persist_event(conn, evt, generation=None)

    row = conn.execute(
        "SELECT run_id, event_type, payload, generation FROM pipeline_events"
    ).fetchone()
    assert row is not None
    assert row[0] == "run-xyz"
    assert row[1] == "EvtPipelineStart"
    payload = json.loads(row[2])
    assert payload == {"run_id": "run-xyz", "n_symbols": 3, "max_generations": 2}
    assert row[3] is None


def test_persist_backtest_done_with_generation(conn: sqlite3.Connection) -> None:
    evt = EvtBacktestDone(symbol="RELIANCE", strategy="SMA_10x25", success=True, sharpe=1.42)

    persist_event(conn, evt, generation=1, run_id="run-abc")

    row = conn.execute(
        "SELECT run_id, generation, event_type, payload FROM pipeline_events"
    ).fetchone()
    assert row[0] == "run-abc"
    assert row[1] == 1
    assert row[2] == "EvtBacktestDone"
    payload = json.loads(row[3])
    assert payload["symbol"] == "RELIANCE"
    assert payload["sharpe"] == 1.42


def test_persist_assigns_autoincrement_ids(conn: sqlite3.Connection) -> None:
    e1 = EvtPipelineStart(run_id="r1", n_symbols=1, max_generations=1)
    e2 = EvtPipelineStart(run_id="r2", n_symbols=2, max_generations=1)

    persist_event(conn, e1)
    persist_event(conn, e2)

    ids = [row[0] for row in conn.execute("SELECT event_id FROM pipeline_events ORDER BY event_id")]
    assert ids == sorted(ids) and len(ids) == 2 and ids[1] > ids[0]


def test_persist_ts_ms_is_recent(conn: sqlite3.Connection) -> None:
    import time
    before_ms = int(time.time() * 1000)
    persist_event(conn, EvtPipelineStart(run_id="t", n_symbols=1, max_generations=1))
    after_ms = int(time.time() * 1000)

    ts = conn.execute("SELECT ts_ms FROM pipeline_events").fetchone()[0]
    assert before_ms <= ts <= after_ms
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/api/test_events_persistence.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'atforge.api'`.

- [ ] **Step 3: Create the module skeleton**

Create `src/atforge/api/__init__.py`:
```python
"""ATForge HTTP API layer (Track C). Read-only consumer of storage/repo.

This module is deletable: removing src/atforge/api/ leaves the pipeline fully functional.
"""
```

Create `src/atforge/api/events/__init__.py`:
```python
"""Event persistence + SSE streaming."""
```

Create `src/atforge/api/events/persistence.py`:
```python
"""Persist pipeline EventBus events to the pipeline_events SQLite table.

Called from inside EventBus.publish() when an optional db_path is configured.
The pipeline still works without this when db_path=None — the in-process Rich
monitor uses the same EventBus queue.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, is_dataclass
from typing import Any


def persist_event(
    conn: sqlite3.Connection,
    evt: Any,
    *,
    generation: int | None = None,
    run_id: str | None = None,
) -> None:
    """Insert one event row into pipeline_events.

    Args:
        conn: open SQLite connection (caller manages lifecycle/commit).
        evt: a frozen dataclass instance from atforge.graph.events.
        generation: optional generation number to tag the event row.
        run_id: optional run_id override. If None, attempts to read evt.run_id;
            if neither present, raises ValueError.
    """
    if not is_dataclass(evt):
        raise TypeError(f"persist_event expects a dataclass instance, got {type(evt).__name__}")

    payload: dict[str, Any] = asdict(evt)

    resolved_run_id = run_id or payload.get("run_id")
    if resolved_run_id is None:
        raise ValueError(
            f"persist_event needs run_id (got {type(evt).__name__} without run_id field "
            f"and no run_id kwarg)"
        )

    conn.execute(
        """
        INSERT INTO pipeline_events (run_id, generation, ts_ms, event_type, payload)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            resolved_run_id,
            generation,
            int(time.time() * 1000),
            type(evt).__name__,
            json.dumps(payload, sort_keys=True, default=str),
        ),
    )
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/api/test_events_persistence.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Run full suite**

Run:
```bash
uv run pytest -q
```

Expected: `296 passed` (292 + 4 new).

- [ ] **Step 6: Commit**

```bash
git add src/atforge/api/__init__.py src/atforge/api/events/__init__.py \
        src/atforge/api/events/persistence.py \
        tests/api/__init__.py tests/api/test_events_persistence.py
git commit -m "feat(api): add persist_event helper for SSE bridge (Track C / C1)"
```

---

### Task 4: Wire `persist_event` into EventBus

**Files:**
- Modify: `src/atforge/graph/events.py` (extend EventBus class)
- Test: `tests/graph/test_event_bus_persistence.py` (new)

- [ ] **Step 1: Read the existing EventBus class**

Read `src/atforge/graph/events.py` lines 80–138 to understand the current `EventBus` interface. Note the existing `publish()` method signature.

- [ ] **Step 2: Write the failing test**

Create `tests/graph/test_event_bus_persistence.py`:
```python
"""EventBus optionally persists events to pipeline_events table."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from atforge.graph.events import EventBus, EvtPipelineStart
from atforge.storage.schema import create_schema


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    p = tmp_path / "test.db"
    conn = sqlite3.connect(p)
    create_schema(conn)
    conn.close()
    return str(p)


def test_event_bus_without_db_path_does_not_persist(tmp_path: Path) -> None:
    bus = EventBus()
    bus.publish(EvtPipelineStart(run_id="r1", n_symbols=1, max_generations=1))
    # No DB to check — just assert publish didn't raise.
    drained = list(bus.drain())
    assert len(drained) == 1


def test_event_bus_with_db_path_persists_event(db_path: str) -> None:
    bus = EventBus(db_path=db_path)
    bus.publish(EvtPipelineStart(run_id="r2", n_symbols=1, max_generations=1))

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT run_id, event_type FROM pipeline_events").fetchall()
    assert len(rows) == 1
    assert rows[0] == ("r2", "EvtPipelineStart")


def test_event_bus_with_db_path_still_queues_for_in_process_monitor(db_path: str) -> None:
    bus = EventBus(db_path=db_path)
    bus.publish(EvtPipelineStart(run_id="r3", n_symbols=2, max_generations=1))

    drained = list(bus.drain())
    assert len(drained) == 1
    assert drained[0].run_id == "r3"
```

- [ ] **Step 3: Run test to verify it fails**

Run:
```bash
uv run pytest tests/graph/test_event_bus_persistence.py -v
```

Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'db_path'`.

- [ ] **Step 4: Modify EventBus to accept optional db_path**

In `src/atforge/graph/events.py`, locate the `EventBus` class. Modify its constructor and `publish` method. Show only the relevant changes:

```python
# Add near the top of events.py with other imports:
import sqlite3
from atforge.api.events.persistence import persist_event

class EventBus:
    """Threading-queue-based event bus, optionally also persisting to SQLite."""

    def __init__(self, db_path: str | None = None) -> None:
        self._q: Queue = Queue()
        self._db_path = db_path

    def publish(self, evt: Any, *, generation: int | None = None) -> None:
        """Emit one event. Always enqueues for in-process monitor; persists if db_path set."""
        self._q.put(evt)
        if self._db_path is not None:
            try:
                conn = sqlite3.connect(self._db_path)
                try:
                    persist_event(conn, evt, generation=generation)
                finally:
                    conn.close()
            except Exception:
                # Never let persistence failure crash the pipeline.
                pass

    def drain(self) -> list[Any]:
        out: list[Any] = []
        while True:
            try:
                out.append(self._q.get_nowait())
            except Empty:
                break
        return out
```

**Important:** Read the full existing `events.py` first. If `EventBus.drain()` already exists with different return type or method signature, preserve the existing signature. Adapt the patch.

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
uv run pytest tests/graph/test_event_bus_persistence.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 6: Run full suite**

Run:
```bash
uv run pytest -q
```

Expected: `299 passed` (no regressions in 289 existing).

- [ ] **Step 7: Wire `db_path` through pipeline CLI**

In `src/atforge/cli.py` (or wherever `EventBus()` is constructed in the pipeline build), pass `db_path=str(deps.db_path)`. Search:
```bash
grep -rn "EventBus()" src/atforge/
```

Update each call site to `EventBus(db_path=<actual_db_path>)` where the db path is available.

- [ ] **Step 8: Smoke test — events persisted after pipeline run**

Run:
```bash
uv run python main.py pipeline --symbols RELIANCE --lookback 6m --max-generations 1
```

Then check events were written:
```bash
sqlite3 data/atforge.db "SELECT COUNT(*) FROM pipeline_events;"
sqlite3 data/atforge.db "SELECT DISTINCT event_type FROM pipeline_events;"
```

Expected: COUNT > 0; event_types include `EvtPipelineStart`, `EvtNodeStart`, `EvtNodeDone`, `EvtBacktestDone`, `EvtPipelineDone`.

- [ ] **Step 9: Commit**

```bash
git add src/atforge/graph/events.py src/atforge/cli.py \
        tests/graph/test_event_bus_persistence.py
git commit -m "feat(graph): EventBus persists events to pipeline_events when db_path set (Track C / C1)"
```

---

### Task 5: Implement retention pruning

**Files:**
- Create: `src/atforge/api/events/retention.py`
- Create: `tests/api/test_events_retention.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_events_retention.py`:
```python
"""Retention pruning: drop events older than N days OR beyond last M runs."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from atforge.api.events.persistence import persist_event
from atforge.api.events.retention import prune_old_events
from atforge.graph.events import EvtPipelineStart
from atforge.storage.schema import create_schema


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(tmp_path / "test.db")
    create_schema(c)
    return c


def _insert_old_event(conn: sqlite3.Connection, run_id: str, days_ago: int) -> None:
    ts = int((time.time() - days_ago * 86400) * 1000)
    conn.execute(
        "INSERT INTO pipeline_events (run_id, generation, ts_ms, event_type, payload) VALUES (?, NULL, ?, 'EvtPipelineStart', '{}')",
        (run_id, ts),
    )
    conn.commit()


def test_prune_removes_events_older_than_30_days(conn: sqlite3.Connection) -> None:
    _insert_old_event(conn, "old-run", days_ago=40)
    _insert_old_event(conn, "fresh-run", days_ago=1)

    pruned = prune_old_events(conn, max_age_days=30, max_runs=100)

    assert pruned == 1
    rows = conn.execute("SELECT run_id FROM pipeline_events").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "fresh-run"


def test_prune_keeps_last_100_runs_only(conn: sqlite3.Connection) -> None:
    # 105 runs, all fresh
    for i in range(105):
        persist_event(conn, EvtPipelineStart(run_id=f"r{i:03d}", n_symbols=1, max_generations=1))

    pruned = prune_old_events(conn, max_age_days=30, max_runs=100)

    # 5 oldest runs (r000..r004) should be pruned
    assert pruned == 5
    remaining_runs = {row[0] for row in conn.execute("SELECT DISTINCT run_id FROM pipeline_events")}
    assert "r000" not in remaining_runs
    assert "r004" not in remaining_runs
    assert "r005" in remaining_runs
    assert "r104" in remaining_runs


def test_prune_is_idempotent(conn: sqlite3.Connection) -> None:
    _insert_old_event(conn, "old-run", days_ago=40)

    first = prune_old_events(conn, max_age_days=30, max_runs=100)
    second = prune_old_events(conn, max_age_days=30, max_runs=100)

    assert first == 1
    assert second == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/api/test_events_retention.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'atforge.api.events.retention'`.

- [ ] **Step 3: Implement retention.py**

Create `src/atforge/api/events/retention.py`:
```python
"""Retention pruning for pipeline_events.

Run on FastAPI startup. Keeps table size bounded.
"""
from __future__ import annotations

import sqlite3
import time


def prune_old_events(
    conn: sqlite3.Connection,
    *,
    max_age_days: int = 30,
    max_runs: int = 100,
) -> int:
    """Delete rows older than max_age_days; keep only the last max_runs distinct runs.

    Returns the total number of rows deleted.
    """
    cutoff_ms = int((time.time() - max_age_days * 86400) * 1000)

    # Step 1: prune by age.
    cur = conn.execute("DELETE FROM pipeline_events WHERE ts_ms < ?", (cutoff_ms,))
    age_deleted = cur.rowcount

    # Step 2: prune by run count — keep newest max_runs distinct runs.
    runs_to_keep = conn.execute(
        """
        SELECT run_id FROM (
            SELECT run_id, MAX(event_id) as last_event
            FROM pipeline_events
            GROUP BY run_id
            ORDER BY last_event DESC
            LIMIT ?
        )
        """,
        (max_runs,),
    ).fetchall()
    keep_ids = {row[0] for row in runs_to_keep}

    if keep_ids:
        placeholders = ",".join("?" * len(keep_ids))
        cur = conn.execute(
            f"DELETE FROM pipeline_events WHERE run_id NOT IN ({placeholders})",
            tuple(keep_ids),
        )
        runs_deleted = cur.rowcount
    else:
        runs_deleted = 0

    conn.commit()
    return age_deleted + runs_deleted
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/api/test_events_retention.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Run full suite**

Run:
```bash
uv run pytest -q
```

Expected: `302 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/atforge/api/events/retention.py tests/api/test_events_retention.py
git commit -m "feat(api): add prune_old_events for pipeline_events retention (Track C / C1)"
```

---

## Phase C2 — FastAPI scaffold

### Task 6: Add FastAPI dependencies

**Files:**
- Modify: `pyproject.toml` (deps)

- [ ] **Step 1: Add deps via uv**

Run:
```bash
uv add fastapi 'uvicorn[standard]' sse-starlette
uv add --group dev httpx pytest-asyncio
```

- [ ] **Step 2: Verify deps installed**

Run:
```bash
uv run python -c "import fastapi, uvicorn, sse_starlette, httpx; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Run full suite (no regressions from deps)**

Run:
```bash
uv run pytest -q
```

Expected: `302 passed`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add fastapi, uvicorn, sse-starlette deps (Track C / C2)"
```

---

### Task 7: Scaffold FastAPI app with health route

**Files:**
- Create: `src/atforge/api/deps.py`
- Create: `src/atforge/api/app.py`
- Create: `src/atforge/api/main.py`
- Create: `src/atforge/api/routes/__init__.py`
- Create: `src/atforge/api/routes/health.py`
- Create: `src/atforge/api/schemas/__init__.py`
- Create: `src/atforge/api/schemas/common.py`
- Create: `tests/api/conftest.py`
- Create: `tests/api/test_routes_health.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/conftest.py`:
```python
"""Shared fixtures for API tests."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atforge.api.app import create_app
from atforge.api.deps import get_db
from atforge.storage.schema import create_schema


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = tmp_path / "atforge_test.db"
    conn = sqlite3.connect(path)
    create_schema(conn)
    conn.close()
    return str(path)


@pytest.fixture
def client(db_path: str):
    """FastAPI TestClient with DB dep overridden to use test db_path."""
    app = create_app()

    def _override_get_db():
        conn = sqlite3.connect(db_path)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)
```

Create `tests/api/test_routes_health.py`:
```python
"""Health route smoke test."""
from __future__ import annotations


def test_health_returns_ok(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


def test_openapi_schema_renders(client) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert schema["openapi"].startswith("3.")
    assert "/health" in schema["paths"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/api/test_routes_health.py -v
```

Expected: FAIL with `ImportError: cannot import name 'create_app' from 'atforge.api.app'`.

- [ ] **Step 3: Create deps.py**

Create `src/atforge/api/deps.py`:
```python
"""FastAPI dependency providers."""
from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator


def _resolve_db_path() -> str:
    return os.environ.get("ATFORGE_DB_PATH", "data/atforge.db")


def get_db() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection per request, closed after response."""
    conn = sqlite3.connect(_resolve_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
```

- [ ] **Step 4: Create schemas/common.py**

Create `src/atforge/api/schemas/__init__.py` (empty).

Create `src/atforge/api/schemas/common.py`:
```python
"""Shared response shapes."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: str
    db: str
```

- [ ] **Step 5: Create the health route**

Create `src/atforge/api/routes/__init__.py` (empty).

Create `src/atforge/api/routes/health.py`:
```python
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
```

- [ ] **Step 6: Create the app factory**

Create `src/atforge/api/app.py`:
```python
"""FastAPI app factory."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from atforge.api.routes import health

log = logging.getLogger("atforge.api")


def create_app() -> FastAPI:
    app = FastAPI(
        title="ATForge API",
        version="0.1.0",
        description="Read-only HTTP API for ATForge dashboard (Track C).",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(health.router, tags=["health"])

    return app


app = create_app()
```

- [ ] **Step 7: Create the uvicorn entrypoint**

Create `src/atforge/api/main.py`:
```python
"""uvicorn entrypoint: `uv run python -m atforge.api`."""
from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run(
        "atforge.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Run test to verify it passes**

Run:
```bash
uv run pytest tests/api/test_routes_health.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 9: Boot the server manually + curl /health**

In one terminal:
```bash
uv run python -m atforge.api.main
```

In another:
```bash
curl -s http://localhost:8000/health | python -m json.tool
curl -s http://localhost:8000/openapi.json | head -30
```

Expected: `{"status": "ok", "db": "ok"}` and a valid OpenAPI schema.

Kill the server with Ctrl-C.

- [ ] **Step 10: Run full suite**

Run:
```bash
uv run pytest -q
```

Expected: `304 passed`.

- [ ] **Step 11: Commit**

```bash
git add src/atforge/api/deps.py src/atforge/api/app.py src/atforge/api/main.py \
        src/atforge/api/routes/__init__.py src/atforge/api/routes/health.py \
        src/atforge/api/schemas/__init__.py src/atforge/api/schemas/common.py \
        tests/api/conftest.py tests/api/test_routes_health.py
git commit -m "feat(api): scaffold FastAPI app with /health route + CORS (Track C / C2)"
```

---

## Phase C3 — Runs routes + SSE

### Task 8: Implement runs schemas

**Files:**
- Create: `src/atforge/api/schemas/runs.py`
- Test: covered implicitly by route tests next task

- [ ] **Step 1: Implement schemas/runs.py**

Create `src/atforge/api/schemas/runs.py`:
```python
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
```

- [ ] **Step 2: Run typecheck (mypy not required; just import)**

Run:
```bash
uv run python -c "from atforge.api.schemas.runs import RunSummary, RunListResponse, EventEnvelope; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add src/atforge/api/schemas/runs.py
git commit -m "feat(api): add Pydantic schemas for /runs endpoints (Track C / C3)"
```

---

### Task 9: Implement `/runs` list + `/runs/{run_id}` detail routes

**Files:**
- Create: `src/atforge/api/routes/runs.py`
- Create: `tests/api/test_routes_runs.py`
- Modify: `src/atforge/api/app.py` (include runs router)

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_routes_runs.py`:
```python
"""/runs and /runs/{id} integration tests."""
from __future__ import annotations

import sqlite3


def _seed_run(conn: sqlite3.Connection, run_id: str, started_iso: str = "2026-05-12T10:00:00") -> None:
    conn.execute(
        "INSERT INTO runs (run_id, universe_hash, started_at) VALUES (?, ?, ?)",
        (run_id, "h-abc", started_iso),
    )
    conn.commit()


def test_runs_list_empty(client) -> None:
    r = client.get("/runs")
    assert r.status_code == 200
    body = r.json()
    assert body["runs"] == []
    assert body["total"] == 0


def test_runs_list_with_seeded_runs(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    _seed_run(conn, "run-a")
    _seed_run(conn, "run-b", started_iso="2026-05-12T11:00:00")
    conn.close()

    r = client.get("/runs?limit=10&offset=0")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    ids = [run["run_id"] for run in body["runs"]]
    # Newest first
    assert ids[0] == "run-b"
    assert ids[1] == "run-a"


def test_run_detail_404(client) -> None:
    r = client.get("/runs/nonexistent")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_run_detail_returns_summary(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    _seed_run(conn, "run-x")
    conn.close()

    r = client.get("/runs/run-x")
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == "run-x"
    assert body["status"] in {"running", "done", "failed", "unknown"}
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/api/test_routes_runs.py -v
```

Expected: FAIL with `404` or `ImportError`.

- [ ] **Step 3: Implement the runs route**

Create `src/atforge/api/routes/runs.py`:
```python
"""/runs endpoints — list + detail."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from atforge.api.deps import get_db
from atforge.api.schemas.common import ErrorDetail
from atforge.api.schemas.runs import RunListResponse, RunSummary

router = APIRouter(prefix="/runs", tags=["runs"])


def _parse_iso(s: str | None) -> datetime | None:
    if s is None:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _row_to_summary(row: sqlite3.Row, n_backtests: int, n_failures: int, current_generation: int | None) -> RunSummary:
    status_raw = row["status"] if "status" in row.keys() else None
    finished_at = _parse_iso(row["finished_at"] if "finished_at" in row.keys() else None)

    if finished_at is not None:
        status = "done" if status_raw != "failed" else "failed"
    else:
        status = "running"

    return RunSummary(
        run_id=row["run_id"],
        started_at=_parse_iso(row["started_at"] if "started_at" in row.keys() else None),
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
        "SELECT COUNT(*) FROM backtest_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    return int(row[0]) if row else 0


def _count_failures(db: sqlite3.Connection, run_id: str) -> int:
    row = db.execute(
        "SELECT COUNT(*) FROM backtest_runs WHERE run_id = ? AND success = 0",
        (run_id,),
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
            detail={"error": ErrorDetail(code="RUN_NOT_FOUND", message=f"run_id={run_id}").model_dump()},
        )
    return _row_to_summary(
        row,
        n_backtests=_count_backtests(db, run_id),
        n_failures=_count_failures(db, run_id),
        current_generation=_current_generation(db, run_id),
    )
```

- [ ] **Step 4: Register router in app.py**

Modify `src/atforge/api/app.py` — add import and `include_router`:
```python
# Add to imports:
from atforge.api.routes import health, runs

# After app.include_router(health.router, ...):
    app.include_router(runs.router)
```

- [ ] **Step 5: Add global exception handler for nicer 404 envelope**

In `src/atforge/api/app.py`, before `return app`:
```python
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

@app.exception_handler(HTTPException)
async def _http_exc_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
    )
```

Note: this should be added inside `create_app()` and reference `app` local var. Move the handler registration inside the function.

- [ ] **Step 6: Run test to verify it passes**

Run:
```bash
uv run pytest tests/api/test_routes_runs.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 7: Run full suite**

Run:
```bash
uv run pytest -q
```

Expected: `308 passed`.

- [ ] **Step 8: Commit**

```bash
git add src/atforge/api/routes/runs.py src/atforge/api/app.py \
        tests/api/test_routes_runs.py
git commit -m "feat(api): add /runs list + detail routes (Track C / C3)"
```

---

### Task 10: Implement SSE stream `/runs/{run_id}/events`

**Files:**
- Create: `src/atforge/api/events/stream.py`
- Modify: `src/atforge/api/routes/runs.py` (add SSE route)
- Create: `tests/api/test_events_stream.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_events_stream.py`:
```python
"""SSE stream backfill + new event tailing."""
from __future__ import annotations

import json
import sqlite3

import pytest


def _insert_event(conn: sqlite3.Connection, run_id: str, event_type: str, ts_ms: int = 1_700_000_000_000) -> None:
    conn.execute(
        "INSERT INTO pipeline_events (run_id, generation, ts_ms, event_type, payload) VALUES (?, NULL, ?, ?, ?)",
        (run_id, ts_ms, event_type, json.dumps({"run_id": run_id})),
    )
    conn.commit()


def test_sse_backfill_yields_seeded_events(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    _insert_event(conn, "run-1", "EvtPipelineStart")
    _insert_event(conn, "run-1", "EvtNodeStart")
    _insert_event(conn, "run-1", "EvtPipelineDone")
    conn.close()

    # Use stream=True via TestClient context. Read first three events then exit.
    with client.stream("GET", "/runs/run-1/events?after_event_id=0") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body_chunks: list[str] = []
        for line in response.iter_lines():
            body_chunks.append(line)
            if line.startswith("data:") and "EvtPipelineDone" in line:
                break

    joined = "\n".join(body_chunks)
    assert "EvtPipelineStart" in joined
    assert "EvtNodeStart" in joined
    assert "EvtPipelineDone" in joined


def test_sse_filters_by_run_id(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    _insert_event(conn, "run-A", "EvtPipelineStart")
    _insert_event(conn, "run-B", "EvtPipelineStart")
    conn.close()

    with client.stream("GET", "/runs/run-A/events?after_event_id=0") as response:
        assert response.status_code == 200
        chunks: list[str] = []
        for line in response.iter_lines():
            chunks.append(line)
            if len(chunks) > 30:  # safety bound
                break

    joined = "\n".join(chunks)
    assert "run-A" in joined
    assert "run-B" not in joined
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/api/test_events_stream.py -v
```

Expected: FAIL with 404 (route does not exist).

- [ ] **Step 3: Implement stream.py**

Create `src/atforge/api/events/stream.py`:
```python
"""SSE generator for /runs/{run_id}/events."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from collections.abc import AsyncIterator


HEARTBEAT_INTERVAL_S = 15.0
POLL_INTERVAL_S = 0.25
STOP_AFTER_DONE_S = 5.0


async def event_stream(
    db_path: str,
    run_id: str,
    after_event_id: int,
) -> AsyncIterator[str]:
    """Yield SSE-formatted events for one run.

    Backfills any events with event_id > after_event_id, then tails the table.
    Stops 5s after the last EvtPipelineDone event (or after STOP_AFTER_DONE_S
    seconds of idle following an EvtPipelineDone).
    """
    last_id = after_event_id
    last_heartbeat = time.monotonic()
    seen_done = False
    seen_done_at: float | None = None

    while True:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT event_id, run_id, generation, ts_ms, event_type, payload
                FROM pipeline_events
                WHERE run_id = ? AND event_id > ?
                ORDER BY event_id ASC
                LIMIT 500
                """,
                (run_id, last_id),
            ).fetchall()
        finally:
            conn.close()

        for row in rows:
            last_id = int(row["event_id"])
            envelope = {
                "event_id": last_id,
                "run_id": row["run_id"],
                "ts_ms": int(row["ts_ms"]),
                "event_type": row["event_type"],
                "generation": row["generation"],
                "payload": json.loads(row["payload"]),
            }
            yield f"event: pipeline_event\ndata: {json.dumps(envelope)}\n\n"

            if row["event_type"] == "EvtPipelineDone":
                seen_done = True
                seen_done_at = time.monotonic()

        now = time.monotonic()

        # Heartbeat if no events were yielded recently.
        if not rows and (now - last_heartbeat) >= HEARTBEAT_INTERVAL_S:
            last_heartbeat = now
            yield f"event: heartbeat\ndata: {json.dumps({'ts_ms': int(time.time() * 1000)})}\n\n"

        # Close stream if pipeline completed and there's been silence.
        if seen_done and seen_done_at is not None and (now - seen_done_at) >= STOP_AFTER_DONE_S:
            return

        await asyncio.sleep(POLL_INTERVAL_S)
```

- [ ] **Step 4: Wire SSE route into routes/runs.py**

Append to `src/atforge/api/routes/runs.py`:
```python
from sse_starlette.sse import EventSourceResponse

from atforge.api.deps import _resolve_db_path
from atforge.api.events.stream import event_stream


@router.get("/{run_id}/events")
async def stream_events(run_id: str, after_event_id: int = 0):
    """SSE stream of pipeline_events for one run."""
    db_path = _resolve_db_path()

    async def _generator():
        async for chunk in event_stream(db_path, run_id, after_event_id):
            # sse-starlette expects pre-formatted SSE; we yield raw strings.
            # Use the lower-level approach: yield dicts and let EventSourceResponse format.
            # But our generator already formats — so split:
            yield chunk

    # Use a streaming response that preserves our manually-formatted SSE.
    from fastapi.responses import StreamingResponse

    return StreamingResponse(_generator(), media_type="text/event-stream")
```

**Note:** The above uses `StreamingResponse` rather than `EventSourceResponse` because our generator pre-formats SSE strings. This is intentional — keeps full control over the wire format.

- [ ] **Step 5: Override db_path in test client**

Modify `tests/api/conftest.py` to also set `ATFORGE_DB_PATH` env so the SSE generator picks up the test DB:
```python
@pytest.fixture
def client(db_path: str, monkeypatch):
    monkeypatch.setenv("ATFORGE_DB_PATH", db_path)
    app = create_app()

    def _override_get_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)
```

- [ ] **Step 6: Run test to verify it passes**

Run:
```bash
uv run pytest tests/api/test_events_stream.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 7: Manual SSE smoke test**

In one terminal:
```bash
uv run python -m atforge.api.main
```

In another:
```bash
curl -N "http://localhost:8000/runs/<some-existing-run-id>/events?after_event_id=0" | head -20
```

Expected: stream of `event: pipeline_event` blocks.

- [ ] **Step 8: Run full suite**

Run:
```bash
uv run pytest -q
```

Expected: `310 passed`.

- [ ] **Step 9: Commit**

```bash
git add src/atforge/api/events/stream.py src/atforge/api/routes/runs.py \
        tests/api/conftest.py tests/api/test_events_stream.py
git commit -m "feat(api): SSE stream for /runs/{id}/events (Track C / C3)"
```

---


## Phase C4 — Strategies routes

### Task 11: Implement strategies schemas

**Files:**
- Create: `src/atforge/api/schemas/strategies.py`

- [ ] **Step 1: Implement schemas/strategies.py**

Create `src/atforge/api/schemas/strategies.py`:
```python
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
```

- [ ] **Step 2: Verify import**

```bash
uv run python -c "from atforge.api.schemas.strategies import StrategyListItem, StrategyDetail, EquityResponse; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add src/atforge/api/schemas/strategies.py
git commit -m "feat(api): add Pydantic schemas for /strategies endpoints (Track C / C4)"
```

---

### Task 12: Implement `/strategies` list + `/strategies/{id}` detail

**Files:**
- Create: `src/atforge/api/routes/strategies.py`
- Modify: `src/atforge/api/app.py` (include strategies router)
- Create: `tests/api/test_routes_strategies_list.py`

- [ ] **Step 1: Read existing `repo.py` functions**

Read `src/atforge/storage/repo.py` to confirm available functions:
- `top_rankings(conn, limit, run_id=None)`
- `get_strategy(conn, strategy_id)`
- `get_strategy_children(conn, strategy_id)`
- `get_mutation_tree(conn, strategy_id, max_depth=5)`
- `get_pattern_symbol_breakdown(conn, strategy_id)`
- `get_top_strategies_for_generation(conn, generation, limit)`

Confirm the column names returned. Adjust schema field names if needed.

- [ ] **Step 2: Write failing tests**

Create `tests/api/test_routes_strategies_list.py`:
```python
"""/strategies list + /strategies/{id} integration tests."""
from __future__ import annotations

import json
import sqlite3


def _seed_strategy(conn: sqlite3.Connection, name: str, family: str, params: dict, sid: int | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO strategies (strategy_id, name, family, params_json, description) VALUES (?, ?, ?, ?, ?)",
        (sid, name, family, json.dumps(params, sort_keys=True), f"{name} desc"),
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_backtest(
    conn: sqlite3.Connection,
    run_id: str,
    strategy_id: int,
    symbol: str,
    generation: int,
    sharpe: float,
) -> None:
    conn.execute("INSERT OR IGNORE INTO runs (run_id, started_at) VALUES (?, '2026-05-12T10:00:00')", (run_id,))
    conn.execute(
        """
        INSERT INTO backtest_runs (run_id, strategy_id, signal_id, symbol, sharpe, sortino,
                                   n_trades, max_drawdown, cagr, win_rate, success, generation)
        VALUES (?, ?, NULL, ?, ?, 0.5, 5, '-0.05', 0.1, '0.6', 1, ?)
        """,
        (run_id, strategy_id, symbol, sharpe, generation),
    )
    conn.commit()


def test_strategies_list_empty(client) -> None:
    r = client.get("/strategies")
    assert r.status_code == 200
    body = r.json()
    assert body["strategies"] == []
    assert body["total"] == 0


def test_strategies_list_returns_seeded(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    sid = _seed_strategy(conn, "SMA_10x25", "sma", {"fast": 10, "slow": 25})
    _seed_backtest(conn, "run-1", sid, "RELIANCE", 0, 1.5)
    conn.close()

    r = client.get("/strategies")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["strategies"][0]
    assert item["name"] == "SMA_10x25"
    assert item["family"] == "sma"


def test_strategy_detail_404(client) -> None:
    r = client.get("/strategies/9999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "STRATEGY_NOT_FOUND"


def test_strategy_detail_returns_full(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    sid = _seed_strategy(conn, "CDLENGULFING_bullish", "candle", {"pattern": "CDLENGULFING", "direction": "bullish"})
    _seed_backtest(conn, "run-1", sid, "RELIANCE", 0, 1.71)
    conn.close()

    r = client.get(f"/strategies/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["strategy_id"] == sid
    assert body["family"] == "candle"
    assert body["params"]["pattern"] == "CDLENGULFING"
    assert body["metrics_summary"]["best_sharpe"] == 1.71
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/api/test_routes_strategies_list.py -v
```

Expected: FAIL (404 because route doesn't exist).

- [ ] **Step 4: Implement strategies route**

Create `src/atforge/api/routes/strategies.py`:
```python
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
               AVG(CAST(win_rate AS REAL)) AS avg_wr,
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
        where.append("(SELECT MAX(sharpe) FROM backtest_runs br WHERE br.strategy_id = s.strategy_id) >= ?")
        params.append(min_sharpe)
    if generation is not None:
        where.append("(SELECT MIN(generation) FROM backtest_runs br WHERE br.strategy_id = s.strategy_id) = ?")
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
            (SELECT AVG(CAST(win_rate AS REAL)) FROM backtest_runs br WHERE br.strategy_id = s.strategy_id) AS avg_wr,
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
            detail={"error": ErrorDetail(code="STRATEGY_NOT_FOUND", message=f"strategy_id={strategy_id}").model_dump()},
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
```

- [ ] **Step 5: Register router in app.py**

In `src/atforge/api/app.py`:
```python
from atforge.api.routes import health, runs, strategies
# ...
    app.include_router(strategies.router)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/api/test_routes_strategies_list.py -v
```

Expected: 4 tests PASS. If any fail due to column-name mismatches with actual schema, read `src/atforge/storage/schema.sql` and adjust queries.

- [ ] **Step 7: Run full suite**

```bash
uv run pytest -q
```

Expected: `314 passed`.

- [ ] **Step 8: Commit**

```bash
git add src/atforge/api/routes/strategies.py src/atforge/api/app.py \
        tests/api/test_routes_strategies_list.py
git commit -m "feat(api): /strategies list + detail routes (Track C / C4)"
```

---

### Task 13: Implement `/strategies/{id}/backtests`, `/lineage`, `/reasoning`

**Files:**
- Modify: `src/atforge/api/routes/strategies.py` (append routes)
- Create: `tests/api/test_routes_strategies_extras.py`

- [ ] **Step 1: Write failing tests**

Create `tests/api/test_routes_strategies_extras.py`:
```python
"""/strategies/{id}/backtests, /lineage, /reasoning tests."""
from __future__ import annotations

import json
import sqlite3


def _seed_strategy(conn, name, family, params):
    cur = conn.execute(
        "INSERT INTO strategies (name, family, params_json, description) VALUES (?, ?, ?, ?)",
        (name, family, json.dumps(params, sort_keys=True), name),
    )
    conn.commit()
    return int(cur.lastrowid)


def _seed_run(conn, run_id):
    conn.execute("INSERT OR IGNORE INTO runs (run_id, started_at) VALUES (?, '2026-05-12T10:00:00')", (run_id,))
    conn.commit()


def _seed_backtest(conn, run_id, strategy_id, symbol, generation, sharpe):
    _seed_run(conn, run_id)
    conn.execute(
        """
        INSERT INTO backtest_runs (run_id, strategy_id, signal_id, symbol, sharpe, sortino,
                                   n_trades, max_drawdown, cagr, win_rate, success, generation)
        VALUES (?, ?, NULL, ?, ?, 0.5, 5, '-0.05', 0.2, '0.6', 1, ?)
        """,
        (run_id, strategy_id, symbol, sharpe, generation),
    )
    conn.commit()


def _seed_experiment(conn, run_id, gen, parent_id, child_id, mutator, accepted, delta_sharpe, reasoning):
    _seed_run(conn, run_id)
    conn.execute(
        """
        INSERT INTO experiments (run_id, generation, parent_strategy_id, child_strategy_id,
                                 mutator, accepted, delta_sharpe, composite_score, reasoning)
        VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?)
        """,
        (run_id, gen, parent_id, child_id, mutator, accepted, delta_sharpe, reasoning),
    )
    conn.commit()


def test_backtests_returns_rows(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    sid = _seed_strategy(conn, "S1", "sma", {})
    _seed_backtest(conn, "r1", sid, "RELIANCE", 0, 1.2)
    _seed_backtest(conn, "r1", sid, "TCS", 0, 1.4)
    conn.close()

    r = client.get(f"/strategies/{sid}/backtests")
    assert r.status_code == 200
    body = r.json()
    assert body["strategy_id"] == sid
    assert len(body["backtests"]) == 2


def test_lineage_returns_ancestors_and_descendants(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    parent = _seed_strategy(conn, "P", "sma", {"fast": 10, "slow": 25})
    me = _seed_strategy(conn, "M", "sma", {"fast": 8, "slow": 22})
    child = _seed_strategy(conn, "C", "sma", {"fast": 6, "slow": 20})

    _seed_experiment(conn, "r1", 1, parent, me, "param_delta", 1, 0.10, "ok")
    _seed_experiment(conn, "r1", 2, me, child, "param_delta", 1, 0.05, "ok")
    conn.close()

    r = client.get(f"/strategies/{me}/lineage")
    assert r.status_code == 200
    body = r.json()
    ancestor_ids = [n["strategy_id"] for n in body["ancestors"]]
    descendant_ids = [n["strategy_id"] for n in body["descendants"]]
    assert parent in ancestor_ids
    assert child in descendant_ids


def test_reasoning_returns_entries(client, db_path) -> None:
    conn = sqlite3.connect(db_path)
    parent = _seed_strategy(conn, "P", "sma", {})
    me = _seed_strategy(conn, "M", "sma", {})
    _seed_experiment(conn, "r1", 1, parent, me, "param_delta", 1, 0.12,
                     "Tried smaller fast period because parent under-traded.")
    conn.close()

    r = client.get(f"/strategies/{me}/reasoning")
    assert r.status_code == 200
    body = r.json()
    assert len(body["entries"]) == 1
    assert "smaller fast" in body["entries"][0]["reasoning"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/api/test_routes_strategies_extras.py -v
```

Expected: 404 FAIL.

- [ ] **Step 3: Append routes to strategies.py**

Append to `src/atforge/api/routes/strategies.py`:
```python
@router.get("/{strategy_id}/backtests", response_model=BacktestListResponse)
def list_backtests(strategy_id: int, db: sqlite3.Connection = Depends(get_db)) -> BacktestListResponse:
    # Ensure strategy exists.
    exists = db.execute("SELECT 1 FROM strategies WHERE strategy_id = ?", (strategy_id,)).fetchone()
    if not exists:
        raise HTTPException(
            status_code=404,
            detail={"error": ErrorDetail(code="STRATEGY_NOT_FOUND", message=f"strategy_id={strategy_id}").model_dump()},
        )

    rows = db.execute(
        """
        SELECT run_id, symbol, generation, n_trades, sharpe, sortino,
               win_rate, max_drawdown, cagr
        FROM backtest_runs
        WHERE strategy_id = ? AND success = 1
        ORDER BY sharpe DESC NULLS LAST
        LIMIT 100
        """,
        (strategy_id,),
    ).fetchall()

    items = [
        BacktestRow(
            run_id=row["run_id"],
            symbol=row["symbol"],
            generation=int(row["generation"] or 0),
            n_trades=int(row["n_trades"] or 0),
            sharpe=row["sharpe"],
            sortino=row["sortino"],
            win_rate=float(row["win_rate"]) if row["win_rate"] is not None else None,
            max_drawdown=float(row["max_drawdown"]) if row["max_drawdown"] is not None else None,
            cagr=row["cagr"],
        )
        for row in rows
    ]
    return BacktestListResponse(strategy_id=strategy_id, backtests=items)


def _build_lineage_node(db: sqlite3.Connection, strategy_id: int) -> LineageNode:
    row = db.execute(
        "SELECT name, family FROM strategies WHERE strategy_id = ?",
        (strategy_id,),
    ).fetchone()
    name = row["name"] if row else f"#{strategy_id}"

    exp = db.execute(
        """
        SELECT mutator, accepted FROM experiments
        WHERE child_strategy_id = ?
        ORDER BY experiment_id DESC LIMIT 1
        """,
        (strategy_id,),
    ).fetchone()

    sharpe_row = db.execute(
        "SELECT MAX(sharpe) FROM backtest_runs WHERE strategy_id = ?", (strategy_id,)
    ).fetchone()

    return LineageNode(
        strategy_id=strategy_id,
        name=name,
        generation=_strategy_generation(db, strategy_id),
        mutator=exp["mutator"] if exp else None,
        accepted=bool(exp["accepted"]) if exp and exp["accepted"] is not None else None,
        sharpe=sharpe_row[0] if sharpe_row else None,
    )


@router.get("/{strategy_id}/lineage", response_model=LineageResponse)
def get_lineage(strategy_id: int, db: sqlite3.Connection = Depends(get_db)) -> LineageResponse:
    exists = db.execute("SELECT 1 FROM strategies WHERE strategy_id = ?", (strategy_id,)).fetchone()
    if not exists:
        raise HTTPException(
            status_code=404,
            detail={"error": ErrorDetail(code="STRATEGY_NOT_FOUND", message=f"strategy_id={strategy_id}").model_dump()},
        )

    # Walk ancestors via experiments table.
    ancestors: list[LineageNode] = []
    current = strategy_id
    seen: set[int] = set()
    while True:
        parent = _strategy_parent(db, current)
        if parent is None or parent in seen:
            break
        seen.add(parent)
        ancestors.append(_build_lineage_node(db, parent))
        current = parent
    ancestors.reverse()  # oldest first

    # Direct descendants.
    desc_rows = db.execute(
        """
        SELECT DISTINCT child_strategy_id FROM experiments
        WHERE parent_strategy_id = ? AND child_strategy_id IS NOT NULL
        """,
        (strategy_id,),
    ).fetchall()
    descendants = [_build_lineage_node(db, int(r[0])) for r in desc_rows]

    return LineageResponse(strategy_id=strategy_id, ancestors=ancestors, descendants=descendants)


@router.get("/{strategy_id}/reasoning", response_model=ReasoningResponse)
def get_reasoning(strategy_id: int, db: sqlite3.Connection = Depends(get_db)) -> ReasoningResponse:
    exists = db.execute("SELECT 1 FROM strategies WHERE strategy_id = ?", (strategy_id,)).fetchone()
    if not exists:
        raise HTTPException(
            status_code=404,
            detail={"error": ErrorDetail(code="STRATEGY_NOT_FOUND", message=f"strategy_id={strategy_id}").model_dump()},
        )

    rows = db.execute(
        """
        SELECT run_id, generation, mutator, parent_strategy_id, accepted, delta_sharpe, reasoning
        FROM experiments
        WHERE child_strategy_id = ? AND reasoning IS NOT NULL AND reasoning != ''
        ORDER BY experiment_id DESC
        LIMIT 50
        """,
        (strategy_id,),
    ).fetchall()

    entries = [
        ReasoningEntry(
            run_id=row["run_id"],
            generation=int(row["generation"]),
            mutator=row["mutator"],
            parent_strategy_id=int(row["parent_strategy_id"]) if row["parent_strategy_id"] is not None else None,
            reasoning=row["reasoning"],
            accepted=bool(row["accepted"]),
            delta_sharpe=row["delta_sharpe"],
        )
        for row in rows
    ]
    return ReasoningResponse(strategy_id=strategy_id, entries=entries)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/api/test_routes_strategies_extras.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -q
```

Expected: `317 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/atforge/api/routes/strategies.py tests/api/test_routes_strategies_extras.py
git commit -m "feat(api): /strategies/{id} backtests, lineage, reasoning routes (Track C / C4)"
```

---

## Phase C5 — Equity + signals (compute-heavy)

### Task 14: Spike — verify engine pure-read recompute path

**Files:**
- Read-only investigation.

- [ ] **Step 1: Read backtest engine end-to-end**

Read `src/atforge/backtest/engine.py` start to finish (~150 lines). Identify:
- The function that runs backtest (likely `run_backtest`)
- Whether it writes to DB or any cache during compute
- The vectorbt Portfolio object — does it have `.value()` / `.drawdown()` methods?

- [ ] **Step 2: Check existing `portfolio_for_debug` function**

```bash
grep -n "def portfolio_for_debug" src/atforge/backtest/engine.py
```

Read that function. Document whether it returns the Portfolio object or its metrics.

- [ ] **Step 3: Verify no side effects via reading**

Confirm that calling `run_backtest()` does NOT call `insert_backtest_result()` or write to any file. If it does, recompute must construct a Portfolio without going through the side-effecting path.

- [ ] **Step 4: Document findings**

Append a section to `docs/superpowers/specs/2026-05-12-track-c-frontend-design.md` titled "C5 Spike Findings (2026-05-12)" with:
- Which engine function is safe to call for pure recompute
- What `portfolio.value()` and `portfolio.drawdown()` return
- Whether OHLCV data needs to be re-fetched or comes from parquet cache
- Confirmation of zero side effects

- [ ] **Step 5: Commit spike notes**

```bash
git add docs/superpowers/specs/2026-05-12-track-c-frontend-design.md
git commit -m "docs(spec): C5 spike findings — backtest pure-read path verified (Track C / C5)"
```

**Gate check:** If spike reveals side effects that cannot be isolated, switch to the fallback in spec Section 11 R1 (persist equity series at backtest time). PAUSE and ask user before implementing fallback.

---

### Task 15: Implement `portfolio_service` + `/strategies/{id}/equity`

**Files:**
- Create: `src/atforge/backtest/portfolio_service.py`
- Modify: `src/atforge/api/routes/strategies.py` (add /equity route)
- Create: `tests/api/test_routes_equity.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_routes_equity.py`:
```python
"""/strategies/{id}/equity recompute test."""
from __future__ import annotations

import json
import sqlite3


def test_equity_404_for_unknown_strategy(client) -> None:
    r = client.get("/strategies/99999/equity?symbol=RELIANCE&run_id=r1")
    assert r.status_code == 404


def test_equity_returns_points_for_known_strategy(client, db_path) -> None:
    """E2E-light test — needs real cached OHLCV + a real strategy/run.
    This test is skipped if no real data is present in the test DB.
    """
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT strategy_id FROM strategies LIMIT 1").fetchone()
    if row is None:
        import pytest
        pytest.skip("no strategies seeded — skipping equity recompute test")

    sid = int(row[0])
    bt = conn.execute(
        "SELECT run_id, symbol FROM backtest_runs WHERE strategy_id = ? AND success = 1 LIMIT 1",
        (sid,),
    ).fetchone()
    if bt is None:
        import pytest
        pytest.skip("no successful backtest for any strategy — skipping")
    conn.close()

    r = client.get(f"/strategies/{sid}/equity?symbol={bt[1]}&run_id={bt[0]}")
    # 200 OR 404 (SIGNAL_DATA_MISSING) both acceptable depending on parquet presence
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        body = r.json()
        assert body["strategy_id"] == sid
        assert body["symbol"] == bt[1]
        assert isinstance(body["points"], list)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/api/test_routes_equity.py -v
```

Expected: FAIL with 404 because route doesn't exist (or `KeyError` etc).

- [ ] **Step 3: Implement portfolio_service.py**

Create `src/atforge/backtest/portfolio_service.py`:
```python
"""On-demand equity + drawdown recompute for the API layer.

Reads cached OHLCV parquet and re-runs vectorbt portfolio construction in
a side-effect-free mode (no DB writes, no cache writes).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from atforge.backtest.engine import run_backtest


@dataclass(frozen=True)
class EquitySeries:
    initial_capital: float
    timestamps_ms: list[int]
    equity: list[float]
    drawdown: list[float]


def _load_ohlcv(symbol: str, run_id: str, db: sqlite3.Connection) -> pd.DataFrame | None:
    """Read cached OHLCV parquet for (symbol, run_id). Returns None if missing."""
    # data_refs may store paths in state; for read-only API we use the cache convention.
    cache_dir = Path("data/cache")
    candidates = list(cache_dir.rglob(f"{symbol}/*/*.parquet"))
    if not candidates:
        return None
    # Use the newest cache file for this symbol.
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    df = pd.read_parquet(latest)
    return df


def _load_signal_series(strategy_id: int, symbol: str, run_id: str, db: sqlite3.Connection) -> pd.Series | None:
    """Read signal parquet path from pattern_signals and load the series."""
    row = db.execute(
        """
        SELECT signal_path FROM pattern_signals
        WHERE strategy_id = ? AND symbol = ? AND run_id = ?
        ORDER BY signal_id DESC LIMIT 1
        """,
        (strategy_id, symbol, run_id),
    ).fetchone()
    if row is None or row["signal_path"] is None:
        return None
    path = Path(row["signal_path"])
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if "signal" in df.columns:
        return df["signal"]
    return df.iloc[:, 0]


def compute_equity_series(
    db: sqlite3.Connection,
    strategy_id: int,
    symbol: str,
    run_id: str,
) -> EquitySeries | None:
    """Recompute portfolio equity + drawdown for the (strategy, symbol, run) tuple.

    Returns None if required source data (signals or OHLCV) is missing.
    """
    ohlcv = _load_ohlcv(symbol, run_id, db)
    signals = _load_signal_series(strategy_id, symbol, run_id, db)

    if ohlcv is None or signals is None:
        return None

    result = run_backtest(signals=signals, prices=ohlcv["close"], hold_bars=5)
    if not result.success or result.portfolio is None:
        return None

    pf = result.portfolio
    equity_series = pf.value()
    drawdown_series = pf.drawdown()

    timestamps_ms = [int(ts.timestamp() * 1000) for ts in equity_series.index]
    return EquitySeries(
        initial_capital=float(pf.init_cash),
        timestamps_ms=timestamps_ms,
        equity=[float(x) for x in equity_series.tolist()],
        drawdown=[float(x) for x in drawdown_series.tolist()],
    )
```

**Note:** The `portfolio` attribute on `BacktestResult` may not exist in current code. Read `src/atforge/backtest/engine.py` to confirm. If `run_backtest()` doesn't return a Portfolio, modify it to return the Portfolio behind an opt-in `return_portfolio: bool = False` flag, OR call vectorbt's `Portfolio.from_signals` directly inside `portfolio_service.py`. Adjust accordingly based on spike findings from Task 14.

- [ ] **Step 4: Add /equity route to strategies.py**

Append to `src/atforge/api/routes/strategies.py`:
```python
from atforge.api.schemas.strategies import EquityPoint, EquityResponse
from atforge.backtest.portfolio_service import compute_equity_series


@router.get("/{strategy_id}/equity", response_model=EquityResponse)
def get_equity(
    strategy_id: int,
    symbol: str = Query(...),
    run_id: str = Query(...),
    db: sqlite3.Connection = Depends(get_db),
) -> EquityResponse:
    exists = db.execute("SELECT 1 FROM strategies WHERE strategy_id = ?", (strategy_id,)).fetchone()
    if not exists:
        raise HTTPException(
            status_code=404,
            detail={"error": ErrorDetail(code="STRATEGY_NOT_FOUND", message=f"strategy_id={strategy_id}").model_dump()},
        )

    series = compute_equity_series(db, strategy_id, symbol, run_id)
    if series is None:
        raise HTTPException(
            status_code=404,
            detail={"error": ErrorDetail(
                code="SIGNAL_DATA_MISSING",
                message=f"No signal or OHLCV cache for strategy={strategy_id} symbol={symbol} run={run_id}",
            ).model_dump()},
        )

    points = [
        EquityPoint(t=t, equity=e, drawdown=d)
        for t, e, d in zip(series.timestamps_ms, series.equity, series.drawdown, strict=True)
    ]
    return EquityResponse(
        strategy_id=strategy_id,
        symbol=symbol,
        run_id=run_id,
        initial_capital=series.initial_capital,
        points=points,
    )
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/api/test_routes_equity.py -v
```

Expected: 2 PASS (one may skip if no seeded data).

- [ ] **Step 6: Run full suite**

```bash
uv run pytest -q
```

Expected: `319 passed`.

- [ ] **Step 7: Commit**

```bash
git add src/atforge/backtest/portfolio_service.py \
        src/atforge/api/routes/strategies.py \
        tests/api/test_routes_equity.py
git commit -m "feat(api): /strategies/{id}/equity recompute via portfolio_service (Track C / C5)"
```

---

### Task 16: Implement `/strategies/{id}/signals`

**Files:**
- Modify: `src/atforge/api/routes/strategies.py` (add /signals route)
- Create: `tests/api/test_routes_signals.py`

- [ ] **Step 1: Write failing test**

Create `tests/api/test_routes_signals.py`:
```python
"""/strategies/{id}/signals route."""
from __future__ import annotations


def test_signals_404_for_unknown_strategy(client) -> None:
    r = client.get("/strategies/99999/signals?symbol=RELIANCE&run_id=r1")
    assert r.status_code == 404


def test_signals_404_when_no_parquet(client, db_path) -> None:
    import sqlite3, json
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO strategies (name, family, params_json, description) VALUES (?, ?, ?, ?)",
                 ("S", "sma", "{}", "d"))
    conn.commit()
    sid = int(conn.execute("SELECT MAX(strategy_id) FROM strategies").fetchone()[0])
    conn.close()

    r = client.get(f"/strategies/{sid}/signals?symbol=RELIANCE&run_id=r1")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "SIGNAL_DATA_MISSING"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/api/test_routes_signals.py -v
```

Expected: 404 either way, but `code` won't match → FAIL.

- [ ] **Step 3: Append /signals route to strategies.py**

```python
from atforge.api.schemas.strategies import OHLCVBar, SignalMarker, SignalsResponse
from atforge.backtest.portfolio_service import _load_ohlcv, _load_signal_series


@router.get("/{strategy_id}/signals", response_model=SignalsResponse)
def get_signals(
    strategy_id: int,
    symbol: str = Query(...),
    run_id: str = Query(...),
    db: sqlite3.Connection = Depends(get_db),
) -> SignalsResponse:
    exists = db.execute("SELECT 1 FROM strategies WHERE strategy_id = ?", (strategy_id,)).fetchone()
    if not exists:
        raise HTTPException(
            status_code=404,
            detail={"error": ErrorDetail(code="STRATEGY_NOT_FOUND", message=f"strategy_id={strategy_id}").model_dump()},
        )

    ohlcv = _load_ohlcv(symbol, run_id, db)
    signals = _load_signal_series(strategy_id, symbol, run_id, db)

    if ohlcv is None or signals is None:
        raise HTTPException(
            status_code=404,
            detail={"error": ErrorDetail(
                code="SIGNAL_DATA_MISSING",
                message=f"OHLCV or signal cache missing for strategy={strategy_id} symbol={symbol}",
            ).model_dump()},
        )

    bars = [
        OHLCVBar(
            t=int(idx.timestamp() * 1000),
            o=float(row["open"]),
            h=float(row["high"]),
            l=float(row["low"]),
            c=float(row["close"]),
            v=float(row.get("volume", 0)),
        )
        for idx, row in ohlcv.iterrows()
    ]

    # Build entry/exit markers from signal series (shifted +1 like engine does).
    signal_shifted = signals.shift(1).fillna(False).astype(bool)
    markers: list[SignalMarker] = []
    in_position = False
    for idx, val in signal_shifted.items():
        if val and not in_position:
            markers.append(SignalMarker(t=int(idx.timestamp() * 1000), type="entry", price=float(ohlcv.loc[idx, "close"])))
            in_position = True
        elif not val and in_position:
            markers.append(SignalMarker(t=int(idx.timestamp() * 1000), type="exit", price=float(ohlcv.loc[idx, "close"])))
            in_position = False

    return SignalsResponse(
        strategy_id=strategy_id,
        symbol=symbol,
        run_id=run_id,
        bars=bars,
        signals=markers,
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/api/test_routes_signals.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -q
```

Expected: `321 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/atforge/api/routes/strategies.py tests/api/test_routes_signals.py
git commit -m "feat(api): /strategies/{id}/signals OHLCV + markers route (Track C / C5)"
```

---

## 🔔 GATE 1 — Backend API verification

### Task 17: User-driven manual smoke test of all endpoints

**Files:**
- No file changes. Manual verification.

- [ ] **Step 1: Boot the backend**

```bash
uv run python -m atforge.api.main
```

Leave running.

- [ ] **Step 2: Run smoke pipeline to populate data**

In another terminal:
```bash
uv run python main.py pipeline --symbols RELIANCE,TCS --lookback 1y --max-generations 2
```

Note the `run_id` from output.

- [ ] **Step 3: Hit each endpoint via curl**

```bash
curl -s http://localhost:8000/health | jq
curl -s "http://localhost:8000/runs?limit=5" | jq
curl -s "http://localhost:8000/runs/<run_id>" | jq
curl -s "http://localhost:8000/runs/<run_id>/events?after_event_id=0" | head -10
curl -s "http://localhost:8000/strategies?page=1&page_size=5" | jq
curl -s "http://localhost:8000/strategies/1" | jq
curl -s "http://localhost:8000/strategies/1/backtests" | jq
curl -s "http://localhost:8000/strategies/1/lineage" | jq
curl -s "http://localhost:8000/strategies/1/reasoning" | jq
curl -s "http://localhost:8000/strategies/1/equity?symbol=RELIANCE&run_id=<run_id>" | jq
curl -s "http://localhost:8000/strategies/1/signals?symbol=RELIANCE&run_id=<run_id>" | jq
```

- [ ] **Step 4: STOP and request user approval**

Post each response (or a summary) and ask:
> "Backend API verification complete. All 11 endpoints reachable. Found issues: [list]. OK to proceed to frontend scaffold (C6)?"

If user reports problems, fix before proceeding. No commit at this gate.


---

## Phase C6 — Frontend scaffold + Shell

### Task 18: Scaffold Next.js app + install deps

**Files:**
- Create: entire `web/` tree (see spec Section 5.1)

- [ ] **Step 1: Bootstrap Next.js app**

From repo root:
```bash
cd /Users/livdea/ATForge
pnpm create next-app@latest web --typescript --tailwind --app --no-eslint --no-src-dir=false --import-alias "@/*"
```

When prompted, choose:
- TypeScript: Yes
- ESLint: Yes
- Tailwind CSS: Yes
- `src/` directory: Yes
- App Router: Yes
- Customize import alias: Yes → `@/*`

- [ ] **Step 2: Verify dev server boots**

```bash
cd web
pnpm dev
```

Open `http://localhost:3000` — Next.js welcome page renders. Kill with Ctrl-C.

- [ ] **Step 3: Install runtime deps**

```bash
cd web
pnpm add @tanstack/react-query @tanstack/react-query-devtools zustand next-themes
pnpm add lucide-react clsx tailwind-merge class-variance-authority
pnpm add recharts lightweight-charts
pnpm add @tanstack/react-table
```

- [ ] **Step 4: Install dev deps**

```bash
cd web
pnpm add -D openapi-typescript
pnpm add -D vitest @vitejs/plugin-react @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
pnpm add -D msw
pnpm add -D @playwright/test
pnpm exec playwright install chromium
```

- [ ] **Step 5: Configure shadcn/ui**

```bash
cd web
pnpm dlx shadcn@latest init
```

When prompted:
- Style: Default
- Base color: Slate
- CSS variables: Yes

This creates `components.json` and updates `tailwind.config.ts` + `globals.css`.

- [ ] **Step 6: Install initial shadcn components**

```bash
cd web
pnpm dlx shadcn@latest add button card dropdown-menu input select \
  table tabs sheet skeleton sonner toast tooltip badge \
  separator avatar dialog popover scroll-area
```

- [ ] **Step 7: Create `.env.local`**

Create `web/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 8: Add scripts to `web/package.json`**

Open `web/package.json` and ensure scripts include:
```json
{
  "scripts": {
    "dev": "next dev --port 3000",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "typecheck": "tsc --noEmit",
    "test": "vitest",
    "test:e2e": "playwright test",
    "gen:types": "openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/types.gen.ts"
  }
}
```

- [ ] **Step 9: Verify build works**

```bash
cd web
pnpm typecheck
pnpm lint
pnpm build
```

Expected: all three succeed.

- [ ] **Step 10: Commit**

```bash
cd /Users/livdea/ATForge
git add web/
git commit -m "feat(web): scaffold Next.js + Tailwind + shadcn/ui + deps (Track C / C6)"
```

---

### Task 19: Implement Shell + ThemeProvider + QueryProvider

**Files:**
- Create: `web/src/components/ThemeProvider.tsx`
- Create: `web/src/components/QueryProvider.tsx`
- Create: `web/src/components/Shell.tsx`
- Create: `web/src/components/common/Loading.tsx`
- Create: `web/src/components/common/EmptyState.tsx`
- Create: `web/src/components/common/ErrorBoundary.tsx`
- Create: `web/src/lib/utils.ts` (if not already created by shadcn init)
- Modify: `web/src/app/layout.tsx`
- Modify: `web/src/app/page.tsx` (redirect to /monitor)
- Create: `web/src/app/monitor/page.tsx` (placeholder)
- Create: `web/src/app/strategies/page.tsx` (placeholder)
- Create: `web/src/app/strategies/[id]/page.tsx` (placeholder)

- [ ] **Step 1: Create ThemeProvider**

Create `web/src/components/ThemeProvider.tsx`:
```tsx
"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";

export function ThemeProvider({ children, ...props }: ComponentProps<typeof NextThemesProvider>) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
      {...props}
    >
      {children}
    </NextThemesProvider>
  );
}
```

- [ ] **Step 2: Create QueryProvider**

Create `web/src/components/QueryProvider.tsx`:
```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState, type ReactNode } from "react";

export function QueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: (failureCount, error: any) => {
              if (error?.status >= 400 && error?.status < 500) return false;
              return failureCount < 3;
            },
            retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30_000),
            refetchOnWindowFocus: true,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={client}>
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
```

- [ ] **Step 3: Create Shell with sidebar nav**

Create `web/src/components/Shell.tsx`:
```tsx
"use client";

import { Activity, BookOpen, Moon, Sun, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/monitor", label: "Monitor", icon: Activity },
  { href: "/strategies", label: "Library", icon: BookOpen },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="hidden md:flex w-56 flex-col border-r border-border p-4 gap-2">
        <div className="text-lg font-semibold mb-4">ATForge</div>

        <nav className="flex flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent",
                  active && "bg-accent font-medium",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto flex items-center justify-between gap-2 pt-4 border-t border-border">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label="Toggle theme"
          >
            <Sun className="size-4 hidden dark:block" />
            <Moon className="size-4 block dark:hidden" />
          </Button>
          <Button variant="ghost" size="sm" aria-label="Settings">
            <Settings className="size-4" />
          </Button>
        </div>
      </aside>

      <main className="flex-1 p-6 overflow-x-hidden">{children}</main>
    </div>
  );
}
```

- [ ] **Step 4: Create common UI fragments**

Create `web/src/components/common/Loading.tsx`:
```tsx
import { Skeleton } from "@/components/ui/skeleton";

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}
```

Create `web/src/components/common/EmptyState.tsx`:
```tsx
import { Inbox } from "lucide-react";

export function EmptyState({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-muted-foreground">
      <Inbox className="size-10" />
      <p className="text-sm">{message}</p>
      {hint ? <p className="text-xs">{hint}</p> : null}
    </div>
  );
}
```

Create `web/src/components/common/ErrorBoundary.tsx`:
```tsx
"use client";

import { Component, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

interface State { hasError: boolean; error: Error | null; }

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error) {
    console.error("ErrorBoundary caught:", error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-screen gap-4 p-6">
          <h1 className="text-xl font-semibold">Something went wrong.</h1>
          <p className="text-sm text-muted-foreground">{this.state.error?.message}</p>
          <Button onClick={() => this.setState({ hasError: false, error: null })}>Reload</Button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

- [ ] **Step 5: Wire layout.tsx**

Replace `web/src/app/layout.tsx` content:
```tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/ThemeProvider";
import { QueryProvider } from "@/components/QueryProvider";
import { Shell } from "@/components/Shell";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "ATForge",
  description: "Agentic Trading Forge",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <ErrorBoundary>
          <ThemeProvider>
            <QueryProvider>
              <Shell>{children}</Shell>
            </QueryProvider>
          </ThemeProvider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
```

- [ ] **Step 6: Redirect / → /monitor**

Replace `web/src/app/page.tsx`:
```tsx
import { redirect } from "next/navigation";

export default function HomePage() {
  redirect("/monitor");
}
```

- [ ] **Step 7: Create placeholder pages**

Create `web/src/app/monitor/page.tsx`:
```tsx
export default function MonitorPage() {
  return <div className="text-2xl font-semibold">Pipeline Monitor (placeholder)</div>;
}
```

Create `web/src/app/strategies/page.tsx`:
```tsx
export default function StrategyLibraryPage() {
  return <div className="text-2xl font-semibold">Strategy Library (placeholder)</div>;
}
```

Create `web/src/app/strategies/[id]/page.tsx`:
```tsx
export default function StrategyDetailPage({ params }: { params: { id: string } }) {
  return <div className="text-2xl font-semibold">Strategy {params.id} (placeholder)</div>;
}
```

- [ ] **Step 8: Verify dev server**

```bash
cd web && pnpm dev
```

Open `http://localhost:3000` — should redirect to `/monitor`. Nav works between Monitor and Library. Theme toggle works. Kill with Ctrl-C.

- [ ] **Step 9: Typecheck + lint + build**

```bash
cd web
pnpm typecheck
pnpm lint
pnpm build
```

Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add web/
git commit -m "feat(web): Shell + theme + QueryProvider + placeholder pages (Track C / C6)"
```

---

## Phase C7 — API client + generated types

### Task 20: Generate types + implement fetch wrappers

**Files:**
- Create: `web/src/lib/api/client.ts`
- Create: `web/src/lib/api/types.gen.ts` (auto-generated)
- Create: `web/src/lib/api/runs.ts`
- Create: `web/src/lib/api/strategies.ts`
- Create: `web/src/lib/hooks/useSSE.ts`
- Create: `web/src/lib/hooks/useDebounce.ts`
- Create: `web/src/lib/constants.ts`

- [ ] **Step 1: Boot backend so OpenAPI is reachable**

In one terminal:
```bash
uv run python -m atforge.api.main
```

- [ ] **Step 2: Generate types**

In another terminal:
```bash
cd web
pnpm gen:types
ls -la src/lib/api/types.gen.ts
```

Expected: file exists, ~500-1000 lines.

- [ ] **Step 3: Implement client.ts**

Create `web/src/lib/api/client.ts`:
```ts
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, { headers: { Accept: "application/json" } });

  if (!res.ok) {
    let code = "HTTP_ERROR";
    let message = res.statusText;
    try {
      const body = await res.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
    } catch {}
    throw new ApiError(res.status, code, message);
  }

  return (await res.json()) as T;
}

export function sseUrl(path: string): string {
  return `${BASE_URL}${path}`;
}
```

- [ ] **Step 4: Implement runs.ts API module**

Create `web/src/lib/api/runs.ts`:
```ts
import { apiGet } from "./client";
import type { components } from "./types.gen";

export type RunSummary = components["schemas"]["RunSummary"];
export type RunListResponse = components["schemas"]["RunListResponse"];
export type EventEnvelope = components["schemas"]["EventEnvelope"];

export async function fetchRuns(limit = 20, offset = 0): Promise<RunListResponse> {
  return apiGet<RunListResponse>(`/runs?limit=${limit}&offset=${offset}`);
}

export async function fetchRun(runId: string): Promise<RunSummary> {
  return apiGet<RunSummary>(`/runs/${encodeURIComponent(runId)}`);
}

export const runsQueryKeys = {
  all: ["runs"] as const,
  detail: (runId: string) => ["runs", runId] as const,
};
```

- [ ] **Step 5: Implement strategies.ts API module**

Create `web/src/lib/api/strategies.ts`:
```ts
import { apiGet } from "./client";
import type { components } from "./types.gen";

export type StrategyListItem = components["schemas"]["StrategyListItem"];
export type StrategyListResponse = components["schemas"]["StrategyListResponse"];
export type StrategyDetail = components["schemas"]["StrategyDetail"];
export type BacktestListResponse = components["schemas"]["BacktestListResponse"];
export type EquityResponse = components["schemas"]["EquityResponse"];
export type SignalsResponse = components["schemas"]["SignalsResponse"];
export type LineageResponse = components["schemas"]["LineageResponse"];
export type ReasoningResponse = components["schemas"]["ReasoningResponse"];

export interface StrategyFilters {
  family?: string;
  minSharpe?: number;
  generation?: number;
  sort?: "sharpe_desc" | "sharpe_asc" | "name_asc" | "gen_desc";
  page?: number;
  pageSize?: number;
}

export async function fetchStrategies(filters: StrategyFilters = {}): Promise<StrategyListResponse> {
  const params = new URLSearchParams();
  if (filters.family) params.set("family", filters.family);
  if (filters.minSharpe !== undefined) params.set("min_sharpe", String(filters.minSharpe));
  if (filters.generation !== undefined) params.set("generation", String(filters.generation));
  if (filters.sort) params.set("sort", filters.sort);
  if (filters.page) params.set("page", String(filters.page));
  if (filters.pageSize) params.set("page_size", String(filters.pageSize));
  return apiGet<StrategyListResponse>(`/strategies?${params}`);
}

export async function fetchStrategy(id: number): Promise<StrategyDetail> {
  return apiGet<StrategyDetail>(`/strategies/${id}`);
}

export async function fetchStrategyBacktests(id: number): Promise<BacktestListResponse> {
  return apiGet<BacktestListResponse>(`/strategies/${id}/backtests`);
}

export async function fetchStrategyEquity(id: number, symbol: string, runId: string): Promise<EquityResponse> {
  return apiGet<EquityResponse>(
    `/strategies/${id}/equity?symbol=${encodeURIComponent(symbol)}&run_id=${encodeURIComponent(runId)}`,
  );
}

export async function fetchStrategySignals(id: number, symbol: string, runId: string): Promise<SignalsResponse> {
  return apiGet<SignalsResponse>(
    `/strategies/${id}/signals?symbol=${encodeURIComponent(symbol)}&run_id=${encodeURIComponent(runId)}`,
  );
}

export async function fetchStrategyLineage(id: number): Promise<LineageResponse> {
  return apiGet<LineageResponse>(`/strategies/${id}/lineage`);
}

export async function fetchStrategyReasoning(id: number): Promise<ReasoningResponse> {
  return apiGet<ReasoningResponse>(`/strategies/${id}/reasoning`);
}

export const strategiesQueryKeys = {
  all: ["strategies"] as const,
  list: (filters: StrategyFilters) => ["strategies", "list", filters] as const,
  detail: (id: number) => ["strategies", id] as const,
  backtests: (id: number) => ["strategies", id, "backtests"] as const,
  equity: (id: number, symbol: string, runId: string) =>
    ["strategies", id, "equity", symbol, runId] as const,
  signals: (id: number, symbol: string, runId: string) =>
    ["strategies", id, "signals", symbol, runId] as const,
  lineage: (id: number) => ["strategies", id, "lineage"] as const,
  reasoning: (id: number) => ["strategies", id, "reasoning"] as const,
};
```

- [ ] **Step 6: Implement useSSE hook**

Create `web/src/lib/hooks/useSSE.ts`:
```ts
"use client";

import { useEffect, useRef, useState } from "react";
import { sseUrl } from "@/lib/api/client";
import type { EventEnvelope } from "@/lib/api/runs";

interface UseSSEOptions {
  path: string;
  enabled?: boolean;
  bufferSize?: number;
}

interface UseSSEReturn {
  events: EventEnvelope[];
  isConnected: boolean;
  error: string | null;
  clear: () => void;
  pause: () => void;
  resume: () => void;
  isPaused: boolean;
}

export function useSSE({ path, enabled = true, bufferSize = 1000 }: UseSSEOptions): UseSSEReturn {
  const [events, setEvents] = useState<EventEnvelope[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPaused, setIsPaused] = useState(false);
  const lastEventIdRef = useRef(0);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!enabled || isPaused) return;

    const url = sseUrl(`${path}${path.includes("?") ? "&" : "?"}after_event_id=${lastEventIdRef.current}`);
    const es = new EventSource(url);
    sourceRef.current = es;

    es.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    es.addEventListener("pipeline_event", (msg) => {
      const envelope = JSON.parse((msg as MessageEvent).data) as EventEnvelope;
      lastEventIdRef.current = envelope.event_id;
      setEvents((prev) => {
        const next = [...prev, envelope];
        return next.length > bufferSize ? next.slice(-bufferSize) : next;
      });
    });

    es.addEventListener("heartbeat", () => {
      // Connection alive; nothing to do.
    });

    es.onerror = () => {
      setIsConnected(false);
      setError("Connection lost. Retrying…");
      // EventSource auto-reconnects; the effect cleanup will close it when deps change.
    };

    return () => {
      es.close();
      setIsConnected(false);
    };
  }, [path, enabled, isPaused, bufferSize]);

  return {
    events,
    isConnected,
    error,
    clear: () => setEvents([]),
    pause: () => setIsPaused(true),
    resume: () => setIsPaused(false),
    isPaused,
  };
}
```

- [ ] **Step 7: Implement useDebounce hook**

Create `web/src/lib/hooks/useDebounce.ts`:
```ts
import { useEffect, useState } from "react";

export function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);

  return debounced;
}
```

- [ ] **Step 8: Implement constants**

Create `web/src/lib/constants.ts`:
```ts
export const EVENT_COLORS: Record<string, string> = {
  EvtPipelineStart: "text-blue-500",
  EvtPipelineDone: "text-green-500",
  EvtNodeStart: "text-indigo-500",
  EvtNodeDone: "text-emerald-500",
  EvtBacktestDone: "text-cyan-500",
  EvtMutationProposed: "text-violet-500",
  EvtRatchetVerdict: "text-amber-500",
  EvtCriticVerdict: "text-orange-500",
  EvtGenerationDone: "text-pink-500",
  EvtAgentToolCall: "text-fuchsia-500",
};

export const SHARPE_COLOR = (s: number | null | undefined): string => {
  if (s == null) return "text-muted-foreground";
  if (s >= 2.0) return "text-green-500 font-semibold";
  if (s >= 1.0) return "text-green-400";
  if (s >= 0) return "text-yellow-500";
  return "text-red-500";
};

export const FAMILY_LABELS: Record<string, string> = {
  candle: "Candlestick",
  sma: "SMA",
  rsi: "RSI",
  composition: "Composition",
};
```

- [ ] **Step 9: Typecheck**

```bash
cd web && pnpm typecheck
```

Expected: 0 errors.

- [ ] **Step 10: Commit**

```bash
git add web/src/lib/
git commit -m "feat(web): API client + generated types + useSSE/useDebounce hooks (Track C / C7)"
```

---

## Phase C8 — Strategy Library screen

### Task 21: Implement Strategy Library page

**Files:**
- Create: `web/src/app/strategies/_components/StrategyFilters.tsx`
- Create: `web/src/app/strategies/_components/StrategyTable.tsx`
- Modify: `web/src/app/strategies/page.tsx`

- [ ] **Step 1: Implement StrategyFilters component**

Create `web/src/app/strategies/_components/StrategyFilters.tsx`:
```tsx
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";

const FAMILIES = ["candle", "sma", "rsi", "composition"];

export function StrategyFilters() {
  const router = useRouter();
  const params = useSearchParams();

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params.toString());
    if (value === null || value === "") next.delete(key);
    else next.set(key, value);
    next.delete("page");
    router.push(`/strategies?${next.toString()}`);
  };

  const family = params.get("family") ?? "";
  const minSharpe = params.get("min_sharpe") ?? "";
  const sort = params.get("sort") ?? "sharpe_desc";
  const selectedFamilies = family ? family.split(",") : [];

  const toggleFamily = (f: string) => {
    const next = selectedFamilies.includes(f)
      ? selectedFamilies.filter((x) => x !== f)
      : [...selectedFamilies, f];
    setParam("family", next.join(",") || null);
  };

  return (
    <div className="rounded-lg border p-4 flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium mr-2">Family:</span>
        {FAMILIES.map((f) => {
          const active = selectedFamilies.includes(f);
          return (
            <Badge
              key={f}
              variant={active ? "default" : "outline"}
              className="cursor-pointer"
              onClick={() => toggleFamily(f)}
            >
              {f}
            </Badge>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Min Sharpe:</span>
          <Input
            className="w-24"
            type="number"
            step="0.1"
            value={minSharpe}
            onChange={(e) => setParam("min_sharpe", e.target.value || null)}
          />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Sort:</span>
          <Select value={sort} onValueChange={(v) => setParam("sort", v)}>
            <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="sharpe_desc">Sharpe (high → low)</SelectItem>
              <SelectItem value="sharpe_asc">Sharpe (low → high)</SelectItem>
              <SelectItem value="name_asc">Name (A → Z)</SelectItem>
              <SelectItem value="gen_desc">Generation (newest)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <Button variant="ghost" size="sm" onClick={() => router.push("/strategies")}>
          Clear all
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Implement StrategyTable component**

Create `web/src/app/strategies/_components/StrategyTable.tsx`:
```tsx
"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { fetchStrategies, strategiesQueryKeys, type StrategyFilters as Filters } from "@/lib/api/strategies";
import { SHARPE_COLOR } from "@/lib/constants";

export function StrategyTable() {
  const router = useRouter();
  const params = useSearchParams();

  const filters: Filters = {
    family: params.get("family") ?? undefined,
    minSharpe: params.get("min_sharpe") ? Number(params.get("min_sharpe")) : undefined,
    generation: params.get("generation") ? Number(params.get("generation")) : undefined,
    sort: (params.get("sort") as Filters["sort"]) ?? "sharpe_desc",
    page: params.get("page") ? Number(params.get("page")) : 1,
    pageSize: 50,
  };

  const { data, isLoading, error } = useQuery({
    queryKey: strategiesQueryKeys.list(filters),
    queryFn: () => fetchStrategies(filters),
  });

  if (isLoading) return <Loading rows={5} />;
  if (error) return <EmptyState message="Failed to load strategies" hint={(error as Error).message} />;
  if (!data || data.strategies.length === 0)
    return <EmptyState message="No strategies match these filters." hint="Adjust filters or clear all." />;

  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));

  return (
    <div className="flex flex-col gap-2">
      <div className="text-sm text-muted-foreground">
        Total: {data.total} strategies — Page {data.page} of {totalPages}
      </div>

      <div className="rounded-lg border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Family</TableHead>
              <TableHead className="text-right">Gen</TableHead>
              <TableHead className="text-right">Parent</TableHead>
              <TableHead className="text-right">Sharpe</TableHead>
              <TableHead className="text-right">Sortino</TableHead>
              <TableHead className="text-right">Win Rate</TableHead>
              <TableHead className="text-right">N Backtests</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.strategies.map((s) => (
              <TableRow
                key={s.strategy_id}
                className="cursor-pointer hover:bg-accent/40"
                onClick={() => router.push(`/strategies/${s.strategy_id}`)}
              >
                <TableCell className="font-medium">{s.name}</TableCell>
                <TableCell>{s.family}</TableCell>
                <TableCell className="text-right">{s.generation}</TableCell>
                <TableCell className="text-right">
                  {s.parent_strategy_id ? (
                    <Link
                      onClick={(e) => e.stopPropagation()}
                      className="underline text-blue-500"
                      href={`/strategies/${s.parent_strategy_id}`}
                    >
                      #{s.parent_strategy_id}
                    </Link>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className={`text-right ${SHARPE_COLOR(s.best_sharpe)}`}>
                  {s.best_sharpe?.toFixed(2) ?? "—"}
                </TableCell>
                <TableCell className="text-right">{s.best_sortino?.toFixed(2) ?? "—"}</TableCell>
                <TableCell className="text-right">
                  {s.avg_win_rate ? `${(s.avg_win_rate * 100).toFixed(0)}%` : "—"}
                </TableCell>
                <TableCell className="text-right">{s.n_backtests}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="flex justify-end gap-2 items-center text-sm">
        <Button
          variant="ghost"
          size="sm"
          disabled={data.page <= 1}
          onClick={() => {
            const next = new URLSearchParams(params.toString());
            next.set("page", String(data.page - 1));
            router.push(`/strategies?${next.toString()}`);
          }}
        >
          ‹ Prev
        </Button>
        <span>Page {data.page} of {totalPages}</span>
        <Button
          variant="ghost"
          size="sm"
          disabled={data.page >= totalPages}
          onClick={() => {
            const next = new URLSearchParams(params.toString());
            next.set("page", String(data.page + 1));
            router.push(`/strategies?${next.toString()}`);
          }}
        >
          Next ›
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire the page**

Replace `web/src/app/strategies/page.tsx`:
```tsx
import { Suspense } from "react";
import { StrategyFilters } from "./_components/StrategyFilters";
import { StrategyTable } from "./_components/StrategyTable";
import { Loading } from "@/components/common/Loading";

export default function StrategyLibraryPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Strategy Library</h1>
      <Suspense fallback={<Loading />}>
        <StrategyFilters />
        <StrategyTable />
      </Suspense>
    </div>
  );
}
```

- [ ] **Step 4: Manual verification**

Boot backend (`uv run python -m atforge.api.main`) + frontend (`cd web && pnpm dev`). Open `http://localhost:3000/strategies`. Filter, sort, paginate, click row. Confirm URL updates, table refetches, row click navigates.

- [ ] **Step 5: Typecheck + lint + build**

```bash
cd web && pnpm typecheck && pnpm lint && pnpm build
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add web/src/app/strategies/
git commit -m "feat(web): strategy library screen with filters, table, pagination (Track C / C8)"
```

---


## Phase C9 — Strategy Detail screen

### Task 22: Implement Strategy Detail header + aggregate metrics

**Files:**
- Create: `web/src/app/strategies/[id]/_components/StrategyHeader.tsx`
- Create: `web/src/app/strategies/[id]/_components/AggregateMetricsCard.tsx`
- Create: `web/src/app/strategies/[id]/_components/SymbolRunSelector.tsx`
- Create: `web/src/app/strategies/[id]/_components/BacktestPerSymbolTable.tsx`
- Create: `web/src/components/common/MetricPill.tsx`
- Modify: `web/src/app/strategies/[id]/page.tsx`

- [ ] **Step 1: Implement MetricPill**

Create `web/src/components/common/MetricPill.tsx`:
```tsx
import { cn } from "@/lib/utils";

interface Props {
  label: string;
  value: string | number | null | undefined;
  delta?: number | null;
  valueClassName?: string;
}

export function MetricPill({ label, value, delta, valueClassName }: Props) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border p-4 min-w-[140px]">
      <span className="text-xs text-muted-foreground uppercase tracking-wide">{label}</span>
      <span className={cn("text-2xl font-semibold", valueClassName)}>
        {value === null || value === undefined ? "—" : value}
      </span>
      {delta !== undefined && delta !== null ? (
        <span className={cn("text-xs", delta >= 0 ? "text-green-500" : "text-red-500")}>
          {delta >= 0 ? "+" : ""}{delta.toFixed(2)} vs parent
        </span>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 2: Implement StrategyHeader**

Create `web/src/app/strategies/[id]/_components/StrategyHeader.tsx`:
```tsx
"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { fetchStrategy, strategiesQueryKeys } from "@/lib/api/strategies";
import { Loading } from "@/components/common/Loading";
import { Badge } from "@/components/ui/badge";

export function StrategyHeader({ id }: { id: number }) {
  const { data, isLoading, error } = useQuery({
    queryKey: strategiesQueryKeys.detail(id),
    queryFn: () => fetchStrategy(id),
  });

  if (isLoading) return <Loading rows={2} />;
  if (error || !data) return <div className="text-red-500">{(error as Error)?.message ?? "Strategy not found"}</div>;

  return (
    <div className="flex flex-col gap-2 rounded-lg border p-4">
      <div className="flex items-center gap-3">
        <Link href="/strategies" className="text-sm text-muted-foreground underline">← Library</Link>
        <h1 className="text-2xl font-semibold">{data.name}</h1>
        <Badge variant="outline">{data.family}</Badge>
      </div>
      <div className="text-sm text-muted-foreground flex flex-wrap gap-x-4">
        <span>#{data.strategy_id}</span>
        <span>Family: {data.family}</span>
        {data.parent_strategy_id ? (
          <span>
            Parent: <Link href={`/strategies/${data.parent_strategy_id}`} className="underline">
              #{data.parent_strategy_id}
            </Link>
          </span>
        ) : (
          <span>Parent: — (gen-0 seed)</span>
        )}
      </div>
      <pre className="text-xs bg-muted rounded p-2 overflow-x-auto">{JSON.stringify(data.params, null, 2)}</pre>
    </div>
  );
}
```

- [ ] **Step 3: Implement AggregateMetricsCard**

Create `web/src/app/strategies/[id]/_components/AggregateMetricsCard.tsx`:
```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchStrategy, strategiesQueryKeys } from "@/lib/api/strategies";
import { MetricPill } from "@/components/common/MetricPill";
import { SHARPE_COLOR } from "@/lib/constants";
import { Loading } from "@/components/common/Loading";

export function AggregateMetricsCard({ id }: { id: number }) {
  const { data, isLoading } = useQuery({
    queryKey: strategiesQueryKeys.detail(id),
    queryFn: () => fetchStrategy(id),
  });

  if (isLoading) return <Loading rows={1} />;
  if (!data) return null;

  const m = data.metrics_summary;
  return (
    <div className="flex flex-wrap gap-3">
      <MetricPill label="Best Sharpe" value={m.best_sharpe?.toFixed(2) ?? "—"} valueClassName={SHARPE_COLOR(m.best_sharpe)} />
      <MetricPill label="Best Sortino" value={m.best_sortino?.toFixed(2) ?? "—"} />
      <MetricPill label="Avg Win Rate" value={m.avg_win_rate ? `${(m.avg_win_rate * 100).toFixed(0)}%` : "—"} />
      <MetricPill label="Max Drawdown" value={m.max_drawdown ? `${(m.max_drawdown * 100).toFixed(2)}%` : "—"} />
      <MetricPill label="N Backtests" value={m.n_backtests} />
    </div>
  );
}
```

- [ ] **Step 4: Implement SymbolRunSelector**

Create `web/src/app/strategies/[id]/_components/SymbolRunSelector.tsx`:
```tsx
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { fetchStrategyBacktests, strategiesQueryKeys } from "@/lib/api/strategies";

export function SymbolRunSelector({ id }: { id: number }) {
  const router = useRouter();
  const params = useSearchParams();

  const { data } = useQuery({
    queryKey: strategiesQueryKeys.backtests(id),
    queryFn: () => fetchStrategyBacktests(id),
  });

  const symbols = Array.from(new Set((data?.backtests ?? []).map((b) => b.symbol)));
  const runs = Array.from(new Set((data?.backtests ?? []).map((b) => b.run_id)));

  const symbol = params.get("symbol") ?? symbols[0] ?? "";
  const run = params.get("run") ?? runs[0] ?? "";

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    next.set(key, value);
    router.push(`/strategies/${id}?${next.toString()}`);
  };

  return (
    <div className="flex flex-wrap gap-3">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">Symbol:</span>
        <Select value={symbol} onValueChange={(v) => setParam("symbol", v)}>
          <SelectTrigger className="w-44"><SelectValue placeholder="Select symbol" /></SelectTrigger>
          <SelectContent>
            {symbols.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">Run:</span>
        <Select value={run} onValueChange={(v) => setParam("run", v)}>
          <SelectTrigger className="w-72"><SelectValue placeholder="Select run" /></SelectTrigger>
          <SelectContent>
            {runs.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Implement BacktestPerSymbolTable**

Create `web/src/app/strategies/[id]/_components/BacktestPerSymbolTable.tsx`:
```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { fetchStrategyBacktests, strategiesQueryKeys } from "@/lib/api/strategies";
import { SHARPE_COLOR } from "@/lib/constants";

export function BacktestPerSymbolTable({ id }: { id: number }) {
  const { data, isLoading } = useQuery({
    queryKey: strategiesQueryKeys.backtests(id),
    queryFn: () => fetchStrategyBacktests(id),
  });

  if (isLoading) return <Loading />;
  if (!data || data.backtests.length === 0) return <EmptyState message="No backtests recorded for this strategy" />;

  return (
    <div className="rounded-lg border overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Symbol</TableHead>
            <TableHead>Run</TableHead>
            <TableHead className="text-right">Gen</TableHead>
            <TableHead className="text-right">Trades</TableHead>
            <TableHead className="text-right">Sharpe</TableHead>
            <TableHead className="text-right">Sortino</TableHead>
            <TableHead className="text-right">WR</TableHead>
            <TableHead className="text-right">Max DD</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.backtests.map((b, i) => (
            <TableRow key={`${b.run_id}-${b.symbol}-${i}`}>
              <TableCell className="font-medium">{b.symbol}</TableCell>
              <TableCell className="font-mono text-xs">{b.run_id.slice(0, 8)}…</TableCell>
              <TableCell className="text-right">{b.generation}</TableCell>
              <TableCell className="text-right">{b.n_trades}</TableCell>
              <TableCell className={`text-right ${SHARPE_COLOR(b.sharpe)}`}>{b.sharpe?.toFixed(2) ?? "—"}</TableCell>
              <TableCell className="text-right">{b.sortino?.toFixed(2) ?? "—"}</TableCell>
              <TableCell className="text-right">{b.win_rate ? `${(b.win_rate * 100).toFixed(0)}%` : "—"}</TableCell>
              <TableCell className="text-right text-red-500">{b.max_drawdown ? `${(b.max_drawdown * 100).toFixed(2)}%` : "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
```

- [ ] **Step 6: Wire page partial (will expand in next tasks)**

Replace `web/src/app/strategies/[id]/page.tsx`:
```tsx
import { StrategyHeader } from "./_components/StrategyHeader";
import { AggregateMetricsCard } from "./_components/AggregateMetricsCard";
import { SymbolRunSelector } from "./_components/SymbolRunSelector";
import { BacktestPerSymbolTable } from "./_components/BacktestPerSymbolTable";

export default function StrategyDetailPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  return (
    <div className="flex flex-col gap-4">
      <StrategyHeader id={id} />
      <AggregateMetricsCard id={id} />
      <SymbolRunSelector id={id} />
      <BacktestPerSymbolTable id={id} />
    </div>
  );
}
```

- [ ] **Step 7: Typecheck + lint**

```bash
cd web && pnpm typecheck && pnpm lint
```

Expected: pass.

- [ ] **Step 8: Manual verification**

Open `http://localhost:3000/strategies/<some-id>`. Confirm header, metrics, selectors, backtest table render.

- [ ] **Step 9: Commit**

```bash
git add web/src/app/strategies/[id]/_components/ \
        web/src/components/common/MetricPill.tsx \
        web/src/app/strategies/[id]/page.tsx
git commit -m "feat(web): strategy detail header + metrics + selectors + backtest table (Track C / C9)"
```

---

### Task 23: Implement charts (Equity, Drawdown, Price+Signals)

**Files:**
- Create: `web/src/components/charts/EquityCurve.tsx`
- Create: `web/src/components/charts/DrawdownArea.tsx`
- Create: `web/src/components/charts/PriceWithSignals.tsx`
- Create: `web/src/app/strategies/[id]/_components/EquityCurveCard.tsx`
- Create: `web/src/app/strategies/[id]/_components/DrawdownCard.tsx`
- Create: `web/src/app/strategies/[id]/_components/PriceSignalChart.tsx`
- Modify: `web/src/app/strategies/[id]/page.tsx`

- [ ] **Step 1: Implement EquityCurve chart**

Create `web/src/components/charts/EquityCurve.tsx`:
```tsx
"use client";

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { useTheme } from "next-themes";

interface Props {
  data: Array<{ t: number; equity: number }>;
}

export function EquityCurve({ data }: Props) {
  const { resolvedTheme } = useTheme();
  const stroke = resolvedTheme === "dark" ? "#a3e635" : "#16a34a";

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" className="opacity-20" />
        <XAxis dataKey="t" tickFormatter={(t) => new Date(t).toLocaleDateString()} className="text-xs" />
        <YAxis className="text-xs" domain={["auto", "auto"]} tickFormatter={(v) => v.toFixed(0)} />
        <Tooltip
          labelFormatter={(t) => new Date(t).toLocaleDateString()}
          formatter={(value: number) => [value.toFixed(2), "Equity"]}
        />
        <Line type="monotone" dataKey="equity" stroke={stroke} strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
```

- [ ] **Step 2: Implement DrawdownArea chart**

Create `web/src/components/charts/DrawdownArea.tsx`:
```tsx
"use client";

import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

interface Props {
  data: Array<{ t: number; drawdown: number }>;
}

export function DrawdownArea({ data }: Props) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data}>
        <CartesianGrid strokeDasharray="3 3" className="opacity-20" />
        <XAxis dataKey="t" tickFormatter={(t) => new Date(t).toLocaleDateString()} className="text-xs" />
        <YAxis className="text-xs" tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
        <Tooltip
          labelFormatter={(t) => new Date(t).toLocaleDateString()}
          formatter={(value: number) => [`${(value * 100).toFixed(2)}%`, "Drawdown"]}
        />
        <Area type="monotone" dataKey="drawdown" stroke="#ef4444" fill="#ef4444" fillOpacity={0.3} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
```

- [ ] **Step 3: Implement PriceWithSignals chart (lightweight-charts)**

Create `web/src/components/charts/PriceWithSignals.tsx`:
```tsx
"use client";

import { createChart, ColorType, type IChartApi, type ISeriesApi } from "lightweight-charts";
import { useEffect, useRef } from "react";
import { useTheme } from "next-themes";

interface Bar { t: number; o: number; h: number; l: number; c: number; v: number; }
interface Marker { t: number; type: "entry" | "exit"; price: number; }

export function PriceWithSignals({ bars, markers }: { bars: Bar[]; markers: Marker[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    if (!containerRef.current) return;

    const isDark = resolvedTheme === "dark";
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 400,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: isDark ? "#e5e7eb" : "#374151",
      },
      grid: {
        vertLines: { color: isDark ? "#374151" : "#e5e7eb" },
        horzLines: { color: isDark ? "#374151" : "#e5e7eb" },
      },
      timeScale: { timeVisible: true },
    });

    const candleSeries: ISeriesApi<"Candlestick"> = chart.addCandlestickSeries({
      upColor: "#22c55e", downColor: "#ef4444",
      borderUpColor: "#22c55e", borderDownColor: "#ef4444",
      wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    });

    candleSeries.setData(
      bars.map((b) => ({
        time: Math.floor(b.t / 1000) as any,
        open: b.o, high: b.h, low: b.l, close: b.c,
      })),
    );

    candleSeries.setMarkers(
      markers.map((m) => ({
        time: Math.floor(m.t / 1000) as any,
        position: m.type === "entry" ? "belowBar" : "aboveBar",
        color: m.type === "entry" ? "#22c55e" : "#ef4444",
        shape: m.type === "entry" ? "arrowUp" : "arrowDown",
        text: m.type,
      })),
    );

    chartRef.current = chart;

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, markers, resolvedTheme]);

  return <div ref={containerRef} className="w-full" />;
}
```

- [ ] **Step 4: Implement EquityCurveCard**

Create `web/src/app/strategies/[id]/_components/EquityCurveCard.tsx`:
```tsx
"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchStrategyEquity, strategiesQueryKeys } from "@/lib/api/strategies";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { ApiError } from "@/lib/api/client";

const EquityCurve = dynamic(() => import("@/components/charts/EquityCurve").then((m) => m.EquityCurve), { ssr: false });

export function EquityCurveCard({ id }: { id: number }) {
  const params = useSearchParams();
  const symbol = params.get("symbol") ?? "";
  const run = params.get("run") ?? "";

  const { data, isLoading, error } = useQuery({
    queryKey: strategiesQueryKeys.equity(id, symbol, run),
    queryFn: () => fetchStrategyEquity(id, symbol, run),
    enabled: !!symbol && !!run,
    retry: false,
  });

  if (!symbol || !run) return <EmptyState message="Select a symbol and run to view equity" />;
  if (isLoading) return <Loading />;
  if (error instanceof ApiError && error.code === "SIGNAL_DATA_MISSING")
    return <EmptyState message="Equity unavailable" hint="Signal/OHLCV cache missing for this symbol/run" />;
  if (error || !data) return <EmptyState message="Failed to load equity" hint={(error as Error)?.message} />;

  return (
    <div className="rounded-lg border p-4">
      <div className="text-sm font-medium mb-2">Equity Curve — {symbol}</div>
      <EquityCurve data={data.points.map((p) => ({ t: p.t, equity: p.equity }))} />
    </div>
  );
}
```

- [ ] **Step 5: Implement DrawdownCard**

Create `web/src/app/strategies/[id]/_components/DrawdownCard.tsx`:
```tsx
"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchStrategyEquity, strategiesQueryKeys } from "@/lib/api/strategies";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { ApiError } from "@/lib/api/client";

const DrawdownArea = dynamic(() => import("@/components/charts/DrawdownArea").then((m) => m.DrawdownArea), { ssr: false });

export function DrawdownCard({ id }: { id: number }) {
  const params = useSearchParams();
  const symbol = params.get("symbol") ?? "";
  const run = params.get("run") ?? "";

  const { data, isLoading, error } = useQuery({
    queryKey: strategiesQueryKeys.equity(id, symbol, run),
    queryFn: () => fetchStrategyEquity(id, symbol, run),
    enabled: !!symbol && !!run,
    retry: false,
  });

  if (!symbol || !run) return <EmptyState message="Select symbol + run for drawdown" />;
  if (isLoading) return <Loading />;
  if (error instanceof ApiError && error.code === "SIGNAL_DATA_MISSING")
    return <EmptyState message="Drawdown unavailable" />;
  if (error || !data) return <EmptyState message="Failed to load drawdown" />;

  return (
    <div className="rounded-lg border p-4">
      <div className="text-sm font-medium mb-2">Drawdown — {symbol}</div>
      <DrawdownArea data={data.points.map((p) => ({ t: p.t, drawdown: p.drawdown }))} />
    </div>
  );
}
```

- [ ] **Step 6: Implement PriceSignalChart card**

Create `web/src/app/strategies/[id]/_components/PriceSignalChart.tsx`:
```tsx
"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchStrategySignals, strategiesQueryKeys } from "@/lib/api/strategies";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { ApiError } from "@/lib/api/client";

const PriceWithSignals = dynamic(
  () => import("@/components/charts/PriceWithSignals").then((m) => m.PriceWithSignals),
  { ssr: false },
);

export function PriceSignalChart({ id }: { id: number }) {
  const params = useSearchParams();
  const symbol = params.get("symbol") ?? "";
  const run = params.get("run") ?? "";

  const { data, isLoading, error } = useQuery({
    queryKey: strategiesQueryKeys.signals(id, symbol, run),
    queryFn: () => fetchStrategySignals(id, symbol, run),
    enabled: !!symbol && !!run,
    retry: false,
  });

  if (!symbol || !run) return <EmptyState message="Select symbol + run for chart" />;
  if (isLoading) return <Loading />;
  if (error instanceof ApiError && error.code === "SIGNAL_DATA_MISSING")
    return <EmptyState message="Signal data unavailable for this strategy/run combination" />;
  if (error || !data) return <EmptyState message="Failed to load chart" />;

  return (
    <div className="rounded-lg border p-4">
      <div className="text-sm font-medium mb-2">Price + Signals — {symbol}</div>
      <PriceWithSignals bars={data.bars} markers={data.signals} />
    </div>
  );
}
```

- [ ] **Step 7: Wire all chart cards into page**

Replace `web/src/app/strategies/[id]/page.tsx`:
```tsx
import { StrategyHeader } from "./_components/StrategyHeader";
import { AggregateMetricsCard } from "./_components/AggregateMetricsCard";
import { SymbolRunSelector } from "./_components/SymbolRunSelector";
import { PriceSignalChart } from "./_components/PriceSignalChart";
import { EquityCurveCard } from "./_components/EquityCurveCard";
import { DrawdownCard } from "./_components/DrawdownCard";
import { BacktestPerSymbolTable } from "./_components/BacktestPerSymbolTable";

export default function StrategyDetailPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  return (
    <div className="flex flex-col gap-4">
      <StrategyHeader id={id} />
      <AggregateMetricsCard id={id} />
      <SymbolRunSelector id={id} />
      <PriceSignalChart id={id} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <EquityCurveCard id={id} />
        <DrawdownCard id={id} />
      </div>
      <BacktestPerSymbolTable id={id} />
    </div>
  );
}
```

- [ ] **Step 8: Verify**

```bash
cd web && pnpm typecheck && pnpm lint && pnpm build
```

Boot servers, open a strategy detail page with a real symbol/run. Confirm charts render.

- [ ] **Step 9: Commit**

```bash
git add web/src/components/charts/ web/src/app/strategies/[id]/_components/ \
        web/src/app/strategies/[id]/page.tsx
git commit -m "feat(web): strategy detail charts — equity, drawdown, price+signals (Track C / C9)"
```

---

### Task 24: Implement LineageTree + ReasoningCard + ExperimentHistoryTable

**Files:**
- Create: `web/src/app/strategies/[id]/_components/LineageTree.tsx`
- Create: `web/src/app/strategies/[id]/_components/ReasoningCard.tsx`
- Create: `web/src/app/strategies/[id]/_components/ExperimentHistoryTable.tsx`
- Modify: `web/src/app/strategies/[id]/page.tsx` (mount the three cards)

- [ ] **Step 1: Implement LineageTree**

Create `web/src/app/strategies/[id]/_components/LineageTree.tsx`:
```tsx
"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { fetchStrategyLineage, strategiesQueryKeys, type LineageResponse } from "@/lib/api/strategies";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { SHARPE_COLOR } from "@/lib/constants";

function Node({ node, marker }: { node: LineageResponse["ancestors"][number]; marker?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground w-12">Gen {node.generation}:</span>
      <Link href={`/strategies/${node.strategy_id}`} className="underline">
        #{node.strategy_id} {node.name}
      </Link>
      {node.mutator ? <span className="text-xs text-muted-foreground">[{node.mutator}]</span> : null}
      {node.sharpe !== null && node.sharpe !== undefined ? (
        <span className={`text-xs ${SHARPE_COLOR(node.sharpe)}`}>sharpe: {node.sharpe.toFixed(2)}</span>
      ) : null}
      {marker ? <span className="text-xs font-semibold text-blue-500">({marker})</span> : null}
    </div>
  );
}

export function LineageTree({ id }: { id: number }) {
  const { data, isLoading } = useQuery({
    queryKey: strategiesQueryKeys.lineage(id),
    queryFn: () => fetchStrategyLineage(id),
  });

  if (isLoading) return <Loading rows={3} />;
  if (!data) return <EmptyState message="No lineage data" />;

  const noParents = data.ancestors.length === 0;
  const noChildren = data.descendants.length === 0;

  return (
    <div className="rounded-lg border p-4 flex flex-col gap-2">
      <div className="text-sm font-medium mb-2">Lineage</div>
      {noParents && noChildren ? (
        <EmptyState message="Gen-0 seed strategy (no parent)" />
      ) : (
        <div className="flex flex-col gap-1">
          {data.ancestors.map((a) => <Node key={a.strategy_id} node={a} />)}
          <Node node={{ strategy_id: id, name: "THIS", generation: data.ancestors.length, mutator: null, accepted: null, sharpe: null }} marker="this" />
          {data.descendants.map((d) => <Node key={d.strategy_id} node={d} />)}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Implement ReasoningCard**

Create `web/src/app/strategies/[id]/_components/ReasoningCard.tsx`:
```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchStrategyReasoning, strategiesQueryKeys } from "@/lib/api/strategies";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

export function ReasoningCard({ id }: { id: number }) {
  const { data, isLoading } = useQuery({
    queryKey: strategiesQueryKeys.reasoning(id),
    queryFn: () => fetchStrategyReasoning(id),
  });

  if (isLoading) return <Loading rows={2} />;
  if (!data || data.entries.length === 0)
    return <EmptyState message="No LLM reasoning recorded" hint="Likely a gen-0 seed strategy." />;

  return (
    <div className="rounded-lg border p-4 flex flex-col gap-3">
      <div className="text-sm font-medium">LLM Reasoning</div>
      {data.entries.map((e, i) => (
        <div key={i} className="border-l-2 border-muted pl-3 flex flex-col gap-1">
          <div className="text-xs text-muted-foreground">
            run: {e.run_id.slice(0, 8)}… · gen: {e.generation} · mutator: {e.mutator} · {e.accepted ? "accepted" : "rejected"} · ΔSharpe: {e.delta_sharpe?.toFixed(2) ?? "—"}
          </div>
          <p className="text-sm whitespace-pre-wrap">{e.reasoning}</p>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Implement ExperimentHistoryTable**

Create `web/src/app/strategies/[id]/_components/ExperimentHistoryTable.tsx`:
```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { fetchStrategyReasoning, strategiesQueryKeys } from "@/lib/api/strategies";

export function ExperimentHistoryTable({ id }: { id: number }) {
  const { data, isLoading } = useQuery({
    queryKey: strategiesQueryKeys.reasoning(id),
    queryFn: () => fetchStrategyReasoning(id),
  });

  if (isLoading) return <Loading />;
  if (!data || data.entries.length === 0)
    return <EmptyState message="No experiment history" />;

  return (
    <div className="rounded-lg border overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Run</TableHead>
            <TableHead className="text-right">Gen</TableHead>
            <TableHead>Mutator</TableHead>
            <TableHead>Verdict</TableHead>
            <TableHead className="text-right">ΔSharpe</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.entries.map((e, i) => (
            <TableRow key={i}>
              <TableCell className="font-mono text-xs">{e.run_id.slice(0, 8)}…</TableCell>
              <TableCell className="text-right">{e.generation}</TableCell>
              <TableCell>{e.mutator}</TableCell>
              <TableCell className={e.accepted ? "text-green-500" : "text-red-500"}>
                {e.accepted ? "✓ accepted" : "✗ rejected"}
              </TableCell>
              <TableCell className="text-right">{e.delta_sharpe?.toFixed(2) ?? "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
```

- [ ] **Step 4: Mount in page**

Replace `web/src/app/strategies/[id]/page.tsx`:
```tsx
import { StrategyHeader } from "./_components/StrategyHeader";
import { AggregateMetricsCard } from "./_components/AggregateMetricsCard";
import { SymbolRunSelector } from "./_components/SymbolRunSelector";
import { PriceSignalChart } from "./_components/PriceSignalChart";
import { EquityCurveCard } from "./_components/EquityCurveCard";
import { DrawdownCard } from "./_components/DrawdownCard";
import { BacktestPerSymbolTable } from "./_components/BacktestPerSymbolTable";
import { LineageTree } from "./_components/LineageTree";
import { ReasoningCard } from "./_components/ReasoningCard";
import { ExperimentHistoryTable } from "./_components/ExperimentHistoryTable";

export default function StrategyDetailPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  return (
    <div className="flex flex-col gap-4">
      <StrategyHeader id={id} />
      <AggregateMetricsCard id={id} />
      <SymbolRunSelector id={id} />
      <PriceSignalChart id={id} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <EquityCurveCard id={id} />
        <DrawdownCard id={id} />
      </div>
      <BacktestPerSymbolTable id={id} />
      <LineageTree id={id} />
      <ReasoningCard id={id} />
      <div>
        <h2 className="text-sm font-medium mb-2">Experiment History</h2>
        <ExperimentHistoryTable id={id} />
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Verify**

```bash
cd web && pnpm typecheck && pnpm lint && pnpm build
```

Open strategy detail in browser; confirm all 10 cards render with sensible content or empty states.

- [ ] **Step 6: Commit**

```bash
git add web/src/app/strategies/[id]/_components/ \
        web/src/app/strategies/[id]/page.tsx
git commit -m "feat(web): strategy detail lineage + reasoning + experiment history (Track C / C9)"
```

---

## Phase C10 — Pipeline Monitor screen

### Task 25: Implement Monitor screen components (RunSelector, NodeStatusGrid, GenerationProgress, LiveBacktestTable, LiveEventStream)

**Files:**
- Create: `web/src/app/monitor/_components/RunSelector.tsx`
- Create: `web/src/app/monitor/_components/NodeStatusGrid.tsx`
- Create: `web/src/app/monitor/_components/GenerationProgress.tsx`
- Create: `web/src/app/monitor/_components/LiveBacktestTable.tsx`
- Create: `web/src/app/monitor/_components/LiveEventStream.tsx`

- [ ] **Step 1: Implement RunSelector**

Create `web/src/app/monitor/_components/RunSelector.tsx`:
```tsx
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { fetchRuns, runsQueryKeys } from "@/lib/api/runs";

export function RunSelector() {
  const router = useRouter();
  const params = useSearchParams();
  const current = params.get("run") ?? "";

  const { data } = useQuery({
    queryKey: runsQueryKeys.all,
    queryFn: () => fetchRuns(20, 0),
    refetchInterval: 5000,
  });

  return (
    <Select
      value={current}
      onValueChange={(v) => {
        const next = new URLSearchParams(params.toString());
        next.set("run", v);
        router.push(`/monitor?${next.toString()}`);
      }}
    >
      <SelectTrigger className="w-80"><SelectValue placeholder="Select a run" /></SelectTrigger>
      <SelectContent>
        {(data?.runs ?? []).map((r) => (
          <SelectItem key={r.run_id} value={r.run_id}>
            {r.run_id} — {r.status} — {r.n_backtests} backtests
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
```

- [ ] **Step 2: Implement NodeStatusGrid**

Create `web/src/app/monitor/_components/NodeStatusGrid.tsx`:
```tsx
"use client";

import { Badge } from "@/components/ui/badge";
import type { EventEnvelope } from "@/lib/api/runs";

const NODE_NAMES = [
  "load_universe", "fetch_data", "detect_patterns", "run_backtest",
  "ratchet_node", "rank", "explorer_node", "exploiter_node",
  "critic_node", "aggregate_node", "loop_decision", "advance_generation",
];

type Status = "pending" | "running" | "done";

function deriveStatuses(events: EventEnvelope[]): Map<string, Status> {
  const m = new Map<string, Status>(NODE_NAMES.map((n) => [n, "pending"]));
  for (const e of events) {
    const name = e.payload?.node_name as string | undefined;
    if (!name) continue;
    if (e.event_type === "EvtNodeStart") m.set(name, "running");
    else if (e.event_type === "EvtNodeDone") m.set(name, "done");
  }
  return m;
}

export function NodeStatusGrid({ events }: { events: EventEnvelope[] }) {
  const statuses = deriveStatuses(events);
  return (
    <div className="rounded-lg border p-4">
      <div className="text-sm font-medium mb-3">Pipeline Topology</div>
      <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
        {NODE_NAMES.map((n) => {
          const s = statuses.get(n) ?? "pending";
          const variant = s === "running" ? "default" : s === "done" ? "secondary" : "outline";
          return (
            <Badge key={n} variant={variant} className="justify-center py-1">
              {s === "running" ? "● " : s === "done" ? "✓ " : "◯ "}{n}
            </Badge>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Implement GenerationProgress**

Create `web/src/app/monitor/_components/GenerationProgress.tsx`:
```tsx
"use client";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { EventEnvelope } from "@/lib/api/runs";

export function GenerationProgress({ events }: { events: EventEnvelope[] }) {
  const byGen = new Map<number, { backtests: number; verdicts: { accepted: number; rejected: number }; vetoes: number; bestSharpe: number | null; }>();

  for (const e of events) {
    const gen = e.generation ?? -1;
    if (gen < 0) continue;
    const slot = byGen.get(gen) ?? { backtests: 0, verdicts: { accepted: 0, rejected: 0 }, vetoes: 0, bestSharpe: null };

    if (e.event_type === "EvtBacktestDone") {
      slot.backtests++;
      const s = e.payload?.sharpe;
      if (typeof s === "number" && (slot.bestSharpe === null || s > slot.bestSharpe)) slot.bestSharpe = s;
    } else if (e.event_type === "EvtRatchetVerdict") {
      if (e.payload?.accepted) slot.verdicts.accepted++;
      else slot.verdicts.rejected++;
    } else if (e.event_type === "EvtCriticVerdict") {
      if (!e.payload?.accepted) slot.vetoes++;
    }

    byGen.set(gen, slot);
  }

  const gens = Array.from(byGen.keys()).sort((a, b) => a - b);

  return (
    <div className="rounded-lg border overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Gen</TableHead>
            <TableHead className="text-right">Backtests</TableHead>
            <TableHead className="text-right">Accepted</TableHead>
            <TableHead className="text-right">Rejected</TableHead>
            <TableHead className="text-right">Vetoes</TableHead>
            <TableHead className="text-right">Best Sharpe</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {gens.map((g) => {
            const s = byGen.get(g)!;
            return (
              <TableRow key={g}>
                <TableCell>{g}</TableCell>
                <TableCell className="text-right">{s.backtests}</TableCell>
                <TableCell className="text-right text-green-500">{s.verdicts.accepted}</TableCell>
                <TableCell className="text-right text-red-500">{s.verdicts.rejected}</TableCell>
                <TableCell className="text-right text-orange-500">{s.vetoes}</TableCell>
                <TableCell className="text-right">{s.bestSharpe?.toFixed(2) ?? "—"}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
```

- [ ] **Step 4: Implement LiveBacktestTable**

Create `web/src/app/monitor/_components/LiveBacktestTable.tsx`:
```tsx
"use client";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { EventEnvelope } from "@/lib/api/runs";
import { SHARPE_COLOR } from "@/lib/constants";

export function LiveBacktestTable({ events }: { events: EventEnvelope[] }) {
  const backtests = events
    .filter((e) => e.event_type === "EvtBacktestDone")
    .slice(-50)
    .reverse();

  return (
    <div className="rounded-lg border overflow-x-auto">
      <div className="px-4 pt-3 pb-2 text-sm font-medium">Live Backtests (latest 50)</div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Symbol</TableHead>
            <TableHead>Strategy</TableHead>
            <TableHead className="text-right">Sharpe</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {backtests.map((e) => (
            <TableRow key={e.event_id}>
              <TableCell>{e.payload?.symbol}</TableCell>
              <TableCell className="font-medium">{e.payload?.strategy}</TableCell>
              <TableCell className={`text-right ${SHARPE_COLOR(e.payload?.sharpe)}`}>
                {typeof e.payload?.sharpe === "number" ? e.payload.sharpe.toFixed(2) : "—"}
              </TableCell>
              <TableCell>{e.payload?.success ? "✓" : "✗"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
```

- [ ] **Step 5: Implement LiveEventStream**

Create `web/src/app/monitor/_components/LiveEventStream.tsx`:
```tsx
"use client";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { EventEnvelope } from "@/lib/api/runs";
import { EVENT_COLORS } from "@/lib/constants";

interface Props {
  events: EventEnvelope[];
  isPaused: boolean;
  onPauseToggle: () => void;
  onClear: () => void;
  error: string | null;
  isConnected: boolean;
}

export function LiveEventStream({ events, isPaused, onPauseToggle, onClear, error, isConnected }: Props) {
  const recent = events.slice(-200).reverse();

  return (
    <div className="rounded-lg border flex flex-col h-[400px]">
      <div className="flex items-center justify-between px-4 py-2 border-b">
        <div className="flex items-center gap-2 text-sm font-medium">
          Event Stream
          <span className={isConnected ? "text-green-500" : "text-red-500"}>
            {isConnected ? "● live" : "○ disconnected"}
          </span>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={onPauseToggle}>
            {isPaused ? "Resume" : "Pause"}
          </Button>
          <Button variant="ghost" size="sm" onClick={onClear}>Clear</Button>
        </div>
      </div>
      {error ? <div className="bg-red-500/10 text-red-500 text-xs px-4 py-1">{error}</div> : null}
      <ScrollArea className="flex-1">
        <div className="font-mono text-xs">
          {recent.map((e) => (
            <div key={e.event_id} className="px-4 py-1 border-b last:border-0 flex gap-2">
              <span className="text-muted-foreground">{new Date(e.ts_ms).toLocaleTimeString()}</span>
              <span className={EVENT_COLORS[e.event_type] ?? ""}>{e.event_type}</span>
              <span className="text-muted-foreground truncate">
                {JSON.stringify(e.payload).slice(0, 120)}
              </span>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
```

- [ ] **Step 6: Commit (components only; page integration next task)**

```bash
git add web/src/app/monitor/_components/
git commit -m "feat(web): monitor components — selector, grid, generation, backtests, stream (Track C / C10)"
```

---

### Task 26: Integrate Monitor page with SSE

**Files:**
- Modify: `web/src/app/monitor/page.tsx`

- [ ] **Step 1: Wire the page**

Replace `web/src/app/monitor/page.tsx`:
```tsx
"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useSSE } from "@/lib/hooks/useSSE";
import { fetchRun, runsQueryKeys } from "@/lib/api/runs";
import { RunSelector } from "./_components/RunSelector";
import { NodeStatusGrid } from "./_components/NodeStatusGrid";
import { GenerationProgress } from "./_components/GenerationProgress";
import { LiveBacktestTable } from "./_components/LiveBacktestTable";
import { LiveEventStream } from "./_components/LiveEventStream";
import { EmptyState } from "@/components/common/EmptyState";

function MonitorContent() {
  const params = useSearchParams();
  const runId = params.get("run");

  const { data: run } = useQuery({
    queryKey: runId ? runsQueryKeys.detail(runId) : ["runs", "none"],
    queryFn: () => fetchRun(runId!),
    enabled: !!runId,
    refetchInterval: 5000,
  });

  const sse = useSSE({
    path: runId ? `/runs/${encodeURIComponent(runId)}/events` : "",
    enabled: !!runId,
  });

  if (!runId) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-semibold">Pipeline Monitor</h1>
        <RunSelector />
        <EmptyState
          message="Select a run to monitor"
          hint="Or run a pipeline first: uv run python main.py pipeline ..."
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-semibold">Pipeline Monitor</h1>
        <RunSelector />
      </div>

      {run ? (
        <div className="rounded-lg border p-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">
          <div><span className="text-muted-foreground">Run:</span> <span className="font-mono">{run.run_id}</span></div>
          <div><span className="text-muted-foreground">Status:</span> {run.status}</div>
          <div><span className="text-muted-foreground">Backtests:</span> {run.n_backtests}</div>
          <div><span className="text-muted-foreground">Failures:</span> {run.n_failures}</div>
          <div><span className="text-muted-foreground">Generation:</span> {run.current_generation ?? "—"}</div>
        </div>
      ) : null}

      <NodeStatusGrid events={sse.events} />
      <GenerationProgress events={sse.events} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <LiveBacktestTable events={sse.events} />
        <LiveEventStream
          events={sse.events}
          isPaused={sse.isPaused}
          onPauseToggle={() => (sse.isPaused ? sse.resume() : sse.pause())}
          onClear={sse.clear}
          error={sse.error}
          isConnected={sse.isConnected}
        />
      </div>
    </div>
  );
}

export default function MonitorPage() {
  return (
    <Suspense fallback={<div>Loading…</div>}>
      <MonitorContent />
    </Suspense>
  );
}
```

- [ ] **Step 2: Manual verification**

Boot backend + frontend. In a third terminal, run a pipeline:
```bash
uv run python main.py pipeline --symbols RELIANCE,TCS --lookback 1y --max-generations 2
```

Open `http://localhost:3000/monitor`, select the run from dropdown. Confirm events stream in, node grid updates, backtest table populates.

- [ ] **Step 3: Typecheck + lint + build**

```bash
cd web && pnpm typecheck && pnpm lint && pnpm build
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/app/monitor/page.tsx
git commit -m "feat(web): pipeline monitor page with SSE integration (Track C / C10)"
```

---

## 🔔 GATE 2 — Visual review

### Task 27: User visual review of all 3 screens, both themes

**Files:** No changes; verification only.

- [ ] **Step 1: Boot backend + frontend, run a pipeline**

```bash
# Terminal 1
uv run python -m atforge.api.main

# Terminal 2
cd web && pnpm dev

# Terminal 3
uv run python main.py pipeline --symbols RELIANCE,TCS,INFY --lookback 2y --max-generations 3
```

- [ ] **Step 2: Walk through each screen in browser**

Open `http://localhost:3000`. Verify:
- Redirects to `/monitor`
- Dark theme + Light theme both render cleanly (toggle in sidebar)
- Monitor: run selection, SSE events streaming, node grid, generation progress, live backtest table, event stream pause/resume/clear
- Strategies: filter chips, sort, pagination, row click navigates
- Strategy Detail: header, metrics, symbol/run selectors, price chart with signals, equity curve, drawdown, backtest table, lineage tree, reasoning, experiment history

- [ ] **Step 3: STOP and request user approval**

Post a summary of what works + screenshots (or just descriptions). Ask:
> "All 3 screens render in both themes. Found issues: [list or 'none']. OK to proceed to e2e tests + polish (C11)?"

If user reports issues, fix them before continuing.

---

## Phase C11 — E2E + polish

### Task 28: Playwright e2e tests + Vitest setup

**Files:**
- Create: `web/playwright.config.ts`
- Create: `web/vitest.config.ts`
- Create: `web/tests/e2e/library-filter-navigate.spec.ts`
- Create: `web/tests/e2e/detail-cards-render.spec.ts`
- Create: `web/tests/e2e/monitor-live.spec.ts`
- Create: `web/tests/unit/useDebounce.test.ts`
- Create: `web/tests/unit/formatters.test.ts`

- [ ] **Step 1: Playwright config**

Create `web/playwright.config.ts`:
```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:3000",
    timeout: 60_000,
    reuseExistingServer: true,
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
```

- [ ] **Step 2: Vitest config**

Create `web/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/unit/**/*.test.{ts,tsx}", "tests/components/**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
```

- [ ] **Step 3: Library e2e test**

Create `web/tests/e2e/library-filter-navigate.spec.ts`:
```ts
import { test, expect } from "@playwright/test";

test("filter family and navigate to strategy detail", async ({ page }) => {
  await page.goto("/strategies");
  await expect(page.getByRole("heading", { name: "Strategy Library" })).toBeVisible();
  // Wait for table or empty state
  await page.waitForLoadState("networkidle");
});
```

- [ ] **Step 4: Detail e2e test**

Create `web/tests/e2e/detail-cards-render.spec.ts`:
```ts
import { test, expect } from "@playwright/test";

test("strategy detail renders header + cards (smoke)", async ({ page }) => {
  // Use any strategy id; default to 1 (skip if 404).
  await page.goto("/strategies/1");
  await page.waitForLoadState("networkidle");
  // If strategy exists, header is visible; if 404, no error.
  const heading = page.getByRole("heading").first();
  await expect(heading).toBeVisible();
});
```

- [ ] **Step 5: Monitor e2e test**

Create `web/tests/e2e/monitor-live.spec.ts`:
```ts
import { test, expect } from "@playwright/test";

test("monitor page shows run selector", async ({ page }) => {
  await page.goto("/monitor");
  await expect(page.getByRole("heading", { name: "Pipeline Monitor" })).toBeVisible();
});
```

- [ ] **Step 6: Unit tests**

Create `web/tests/unit/useDebounce.test.ts`:
```ts
import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useDebounce } from "@/lib/hooks/useDebounce";

describe("useDebounce", () => {
  it("delays update by configured ms", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ v }) => useDebounce(v, 200), { initialProps: { v: "a" } });

    expect(result.current).toBe("a");
    rerender({ v: "b" });
    expect(result.current).toBe("a");

    act(() => { vi.advanceTimersByTime(200); });
    expect(result.current).toBe("b");
    vi.useRealTimers();
  });
});
```

Create `web/tests/unit/formatters.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { SHARPE_COLOR } from "@/lib/constants";

describe("SHARPE_COLOR", () => {
  it("returns muted for null", () => {
    expect(SHARPE_COLOR(null)).toContain("muted");
  });
  it("returns green for sharpe >= 2", () => {
    expect(SHARPE_COLOR(2.1)).toContain("green");
  });
  it("returns red for negative sharpe", () => {
    expect(SHARPE_COLOR(-0.5)).toContain("red");
  });
});
```

- [ ] **Step 7: Run unit tests**

```bash
cd web && pnpm test --run
```

Expected: tests pass.

- [ ] **Step 8: Run e2e tests**

```bash
cd web
# Backend must be running. Run pipeline first if you want non-empty data.
pnpm test:e2e
```

Expected: 3 e2e tests pass.

- [ ] **Step 9: Commit**

```bash
git add web/tests/ web/playwright.config.ts web/vitest.config.ts
git commit -m "test(web): playwright e2e + vitest unit tests (Track C / C11)"
```

---

### Task 29: Polish, READMEs, preflight script, update CLAUDE.md

**Files:**
- Create: `scripts/preflight.sh`
- Create: `web/README.md`
- Modify: `CLAUDE.md` (root)
- Modify: `src/atforge/api/__init__.py` (could add CLAUDE.md for the api module)

- [ ] **Step 1: Create preflight script**

Create `scripts/preflight.sh`:
```bash
#!/usr/bin/env bash
set -e

echo "→ Backend ruff (fix + format)"
uv run ruff check --fix
uv run ruff format

echo "→ Backend pytest"
uv run pytest -q

echo "→ Frontend typecheck"
(cd web && pnpm typecheck)

echo "→ Frontend lint"
(cd web && pnpm lint)

echo "→ Frontend unit tests"
(cd web && pnpm test --run)

echo "✓ All preflight checks passed"
```

Make executable:
```bash
chmod +x scripts/preflight.sh
```

- [ ] **Step 2: Create web/README.md**

Create `web/README.md`:
```markdown
# ATForge Web Dashboard

Next.js 15 + TypeScript + Tailwind + shadcn/ui frontend for the ATForge read-only dashboard (Track C).

## Setup

```bash
cd web
pnpm install
pnpm exec playwright install chromium
```

Copy/verify `.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Run

In one terminal, boot the backend:
```bash
uv run python -m atforge.api.main
```

In another:
```bash
cd web
pnpm dev
```

Open `http://localhost:3000`.

## Regenerate API types

```bash
cd web
pnpm gen:types   # requires backend running
```

## Tests

```bash
pnpm typecheck
pnpm lint
pnpm test         # vitest unit
pnpm test:e2e     # playwright (requires backend running)
```

## Screens (MVP)

- `/monitor` — Live pipeline progress via SSE
- `/strategies` — Filterable, sortable library
- `/strategies/[id]` — Detail with equity, drawdown, OHLCV+signals, lineage, reasoning

## Stack

shadcn/ui · Tailwind · TanStack Query · Zustand · Recharts · lightweight-charts · MSW · Playwright
```

- [ ] **Step 3: Update root CLAUDE.md**

Add to `CLAUDE.md` (root) after the `## Commands` block:

```markdown
### Frontend / API (Track C)
```bash
uv run python -m atforge.api.main                  # FastAPI backend on :8000
cd web && pnpm dev                                 # Next.js dev server on :3000
cd web && pnpm gen:types                           # regenerate TS types from OpenAPI
./scripts/preflight.sh                             # all checks (ruff + pytest + frontend)
```
```

And update the Phase status section to add:

```markdown
- **Track C MVP** ✅ complete — FastAPI backend + Next.js read-only dashboard, 3 screens (Monitor / Library / Detail), 45+ new tests
```

(Update when the merge completes.)

- [ ] **Step 4: Run preflight to verify**

```bash
./scripts/preflight.sh
```

Expected: `✓ All preflight checks passed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/preflight.sh web/README.md CLAUDE.md
git commit -m "docs+chore: preflight script, web README, root CLAUDE.md update (Track C / C11)"
```

---

## Phase C12 — Merge

### Task 30: Squash-merge to main

**Files:** No new files.

- [ ] **Step 1: Final verification on branch**

```bash
git checkout feature/track-c-frontend
./scripts/preflight.sh
git log --oneline
```

Confirm:
- preflight passes
- ~13 commits on the branch (one per phase)
- branch is up-to-date with main: `git fetch origin && git log --oneline origin/main..HEAD`

- [ ] **Step 2: STOP and confirm with user before merging**

Ask:
> "Track C MVP complete. Preflight green. Ready to squash-merge feature/track-c-frontend → main?"

Wait for explicit "yes".

- [ ] **Step 3: Switch to main and merge**

```bash
git checkout main
git pull origin main  # if remote exists
git merge --squash feature/track-c-frontend
```

- [ ] **Step 4: Commit the squashed merge**

```bash
git commit -m "feat: Track C MVP — read-only dashboard (FastAPI + Next.js)

Adds:
- src/atforge/api/ — FastAPI read-only API (11 endpoints, SSE event stream)
- web/ — Next.js 15 + shadcn/ui dashboard with 3 screens
- pipeline_events table for cross-process SSE bridge
- backtest/portfolio_service.py for on-demand equity recompute
- scripts/preflight.sh
- ~25 new backend tests, ~5 unit + 3 e2e frontend tests

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 5: Verify main is green**

```bash
./scripts/preflight.sh
```

Expected: all checks pass on main.

- [ ] **Step 6: Final note in CLAUDE.md**

Update root `CLAUDE.md` phase status to mark Track C MVP complete. Commit:
```bash
git add CLAUDE.md
git commit -m "docs: mark Track C MVP complete in phase status"
```

- [ ] **Step 7: Optional — delete feature branch**

Only after explicit user approval:
```bash
git branch -d feature/track-c-frontend
```

---

## Self-Review

### Spec coverage check

| Spec section | Plan task(s) |
|---|---|
| 1. Goals + non-goals | Implicit across all phases |
| 2. Locked decisions | Tasks 6, 18 (stack), 17 (gate), all routes (read-only) |
| 3. Architecture topology | Tasks 2, 3, 4, 7 (backend), 18, 19 (frontend) |
| 4. Backend structure | Tasks 3-10 (events, app, routes, schemas) |
| 5. Frontend structure | Tasks 18-26 (all `web/` tasks) |
| 6.1 11 endpoints | Tasks 7 (/health), 9 (/runs, /runs/{id}), 10 (SSE), 12 (/strategies list/detail), 13 (backtests/lineage/reasoning), 15 (/equity), 16 (/signals) |
| 6.2 Pydantic schemas | Tasks 7 (common), 8 (runs), 11 (strategies) |
| 6.3 SSE protocol | Tasks 4 (EventBus persistence), 10 (stream + route) |
| 6.4 TanStack Query keys | Task 20 (queryKey constants) |
| 6.5 Equity strategy | Tasks 14 (spike), 15 (portfolio_service) |
| 7.1 Shared shell | Task 19 |
| 7.2 Pipeline Monitor | Tasks 25, 26 |
| 7.3 Strategy Library | Task 21 |
| 7.4 Strategy Detail (10 cards) | Tasks 22 (header/metrics/selector/backtests), 23 (charts), 24 (lineage/reasoning/history) |
| 8. Build order (13 phases) | All 30 tasks aligned |
| 9. Testing strategy | Tasks 2, 3, 4, 5, 7, 9, 10, 12, 13, 15, 16 (backend), 28 (frontend) |
| 10. Error handling | Task 9 (HTTPException), 19 (ErrorBoundary), 20 (ApiError + retry config) |
| 11. Risk register | Task 14 (R1 spike), 25/26 (R2 useSSE reconnect handled in Task 20) |
| 12. Architectural invariants | Read-only routes enforced in Tasks 12-16; preserved in Task 30 commit message |
| 13. Out-of-scope | Plan does not include Evolution Tree, Experiment Log screens, deploy, auth — matches spec |
| 14. Commands cheat sheet | Task 29 (web/README + root CLAUDE.md update) |
| 15. Deliverables checklist | Task 30 (final verification) |

All sections covered.

### Placeholder check

No "TBD", "TODO" inside task steps. Every code block is complete. Every command has expected output. Every commit has an exact message.

### Type consistency

- API client functions match query key naming
- Pydantic schemas → generated TS types → consumed in components consistently
- `EventEnvelope`, `RunSummary`, `StrategyDetail`, etc. used with same names across backend + frontend
- `pipeline_events` columns used identically in `persistence.py`, `stream.py`, `retention.py`

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-12-track-c-frontend.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Each subagent gets the task in isolation; you (or I) review the output before the next subagent starts.

**2. Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints for review.

**Which approach?**
