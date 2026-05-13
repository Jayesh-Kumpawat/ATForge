# Track C — Frontend MVP Design

> **Status:** Design approved 2026-05-12. Ready for implementation planning via `writing-plans` skill.
> **Branch:** `feature/track-c-frontend`
> **Executor:** Sonnet in fresh session, following the phased plan in Section 9.

---

## 0. Context

ATForge currently exposes its data through a Streamlit dashboard (functional, 6 tabs). After A1 + A2 completion (289 tests passing, multi-agent topology, Langfuse tracing, agent activity dashboard), the system is rich and complex but not demonstrable to non-Python audiences.

Track C builds a production-grade read-only web dashboard so:
- Users (you now, the public later) can explore the system in a browser
- The multi-agent evolution becomes visible end-to-end
- Future Phase 3 trade-execution data has a UI hook to display through
- The system has portfolio-quality presentation

This document is the **complete design spec**. A fresh Sonnet session should be able to execute Track C using only this document + the existing `CLAUDE.md` files.

---

## 1. Goals + non-goals

### Goals (MVP)
1. Three core screens working end-to-end locally: Pipeline Monitor, Strategy Library, Strategy Detail
2. Live pipeline progress visible via SSE while CLI runs a pipeline
3. Strategy library browsable, filterable, sortable, deep-linkable
4. Strategy detail shows: metrics, equity curve, drawdown, OHLCV with signals, lineage, LLM reasoning, experiment history
5. Backend changes are additive only — `web/` and `src/atforge/api/` are deletable without breaking the pipeline or existing 289 tests
6. Dark + light themes with system-preference default
7. Pragmatic test coverage: 25 backend + 20 frontend tests, 3 Playwright e2e happy paths

### Non-goals (deferred to Phase 2 of Track C)
- Evolution Tree screen (D3 visualization of mutation lineage as a graph)
- Experiment Log screen (full ratchet + critic verdict explorer)
- "Compare strategies" feature
- Public deployment (Vercel + backend hosting)
- Authentication / user accounts
- Pipeline control (start/stop/configure runs from UI)
- Mobile-optimized layouts (desktop-first; basic responsive behavior only)
- Live trade display (Phase 3 dependency)

---

## 2. Locked decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Stack | FastAPI + Next.js/React + TypeScript | Industry-standard, mature, public-deploy-ready, Vercel free tier, decoupled backend |
| 2 | MVP screens | Pipeline Monitor + Strategy Library + Strategy Detail | Core observability; Evolution Tree + Experiment Log to Phase 2 |
| 3 | Control mode | Read-only observer (CLI triggers runs) | Simpler backend, no job queue, no auth needed |
| 4 | Auth | None for MVP | Public read-only dashboard |
| 5 | Deployment | Local dev only | Both servers on localhost; production deploy is a separate later task |
| 6 | Repo layout | Monorepo: `web/` + `src/atforge/api/` | Single git history, both deletable, isolation discipline |
| 7 | Real-time transport | Server-Sent Events (SSE) | One-way stream, FastAPI native via `sse-starlette`, EventSource browser API |
| 8 | Event bridge | New SQLite table `pipeline_events` | Cross-process bridge, durable, no IPC complexity |
| 9 | UI components | shadcn/ui + Tailwind | Owned, copy-pasted, no runtime dep, modern aesthetic |
| 10 | Charts | Recharts + lightweight-charts | Recharts for equity/drawdown/sparklines; lightweight-charts for OHLCV+signals |
| 11 | Server state | TanStack Query v5 | Caching, retry, refetch, query invalidation |
| 12 | Client state | Zustand | Minimal — sidebar collapse + filter persistence |
| 13 | Type generation | openapi-typescript from FastAPI OpenAPI | Zero hand-written API types |
| 14 | Forms | React Hook Form + Zod | Standard with shadcn/ui (forms minimal in MVP) |
| 15 | Testing | Playwright e2e + Vitest + RTL + MSW | Pragmatic, focused on happy paths |
| 16 | Theme | Dark + light + system default | Trading convention is dark; light supported via next-themes |

---

## 3. Architecture

### 3.1 Process topology

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User's browser                              │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  Next.js app (web/)        TanStack Query cache            │    │
│  │  ┌─────────┐  ┌──────────────┐  ┌───────────────┐          │    │
│  │  │ Pipeline│  │  Strategy    │  │ Strategy      │          │    │
│  │  │ Monitor │  │  Library     │  │ Detail        │          │    │
│  │  └────┬────┘  └──────┬───────┘  └───────┬───────┘          │    │
│  └───────┼─────────────┼──────────────────┼──────────────────┘    │
│          │             │                  │                        │
│          │  SSE        │  REST GET        │  REST GET              │
│          │             │                  │                        │
└──────────┼─────────────┼──────────────────┼────────────────────────┘
           │             │                  │
           ▼             ▼                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│       FastAPI app (src/atforge/api/)  uvicorn on :8000              │
│   ┌──────────────────────────────────────────────────────────┐     │
│   │  Routes (11 endpoints, all read-only)                    │     │
│   └─────────────────────┬────────────────────────────────────┘     │
│                         │                                            │
│                         ▼  (read-only consumer)                      │
│   ┌──────────────────────────────────────────────────────────┐     │
│   │  Existing storage/repo.py functions  (no changes)        │     │
│   └─────────────────────┬────────────────────────────────────┘     │
└─────────────────────────┼───────────────────────────────────────────┘
                          │
                          ▼
            ┌─────────────────────────────┐
            │  SQLite (atforge.db)        │
            │  - existing tables          │
            │  - NEW: pipeline_events     │  ← additive only
            └─────────────────────────────┘
                          ▲
                          │  writes
                          │
            ┌─────────────────────────────┐
            │ Pipeline subprocess          │
            │ (uv run python main.py ...)  │
            │ EventBus → Rich monitor      │
            │           + persist_event()  │
            │              → pipeline_events│
            └─────────────────────────────┘
```

### 3.2 Key architectural properties

- **Three independent processes**: browser, FastAPI server, pipeline CLI. No shared memory.
- **Decoupling via SQLite**: pipeline writes events; FastAPI reads events; neither imports the other.
- **Additive only**: zero changes to existing tables; one new table; one new persist call in `EventBus.publish`.
- **Deletable**: removing `web/` or `src/atforge/api/` leaves backend fully functional.
- **No new business logic**: API routes are thin pass-throughs to existing `repo.py` functions.

---

## 4. Backend structure

### 4.1 File layout (all new under `src/atforge/api/`)

```
src/atforge/api/
├── __init__.py
├── app.py                                ← FastAPI() app factory + CORS + middleware
├── main.py                               ← uvicorn entrypoint (`uv run python -m atforge.api`)
├── routes/
│   ├── __init__.py
│   ├── runs.py                           ← /runs, /runs/{id}, /runs/{id}/events (SSE)
│   ├── strategies.py                     ← /strategies, /strategies/{id}, etc.
│   └── health.py                         ← /health
├── schemas/
│   ├── __init__.py
│   ├── runs.py                           ← RunSummary, RunDetail, EventEnvelope
│   ├── strategies.py                     ← StrategyListItem, StrategyDetail, etc.
│   └── common.py                         ← Pagination, ErrorResponse
├── events/
│   ├── __init__.py
│   ├── persistence.py                    ← _persist_event(conn, evt) — called from EventBus
│   ├── stream.py                         ← SSE generator
│   └── retention.py                      ← prune_old_events() on startup
└── deps.py                               ← FastAPI Depends(get_db)
```

### 4.2 Existing file modifications

| File | Change |
|---|---|
| `src/atforge/graph/events.py` | `EventBus` constructor accepts optional `db_path: str \| None`. If provided, `publish()` opens a short-lived sqlite3 connection per call and writes the event via `persistence.persist_event()`. If `db_path=None`, behavior is unchanged (in-process queue only — current CLI Rich monitor still works). Pipeline CLI passes `deps.db_path` when constructing EventBus. |
| `src/atforge/storage/schema.sql` | Append `CREATE TABLE pipeline_events` block + index |
| `pyproject.toml` | Add deps: `fastapi`, `uvicorn[standard]`, `sse-starlette` |

### 4.3 New SQLite table

```sql
CREATE TABLE IF NOT EXISTS pipeline_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT NOT NULL,
    generation INTEGER,
    ts_ms      INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload    TEXT NOT NULL              -- JSON of dataclass fields
);
CREATE INDEX IF NOT EXISTS idx_pipeline_events_run
    ON pipeline_events (run_id, event_id);
```

### 4.4 Backend startup

```bash
uv run python -m atforge.api          # uvicorn on http://localhost:8000
```

### 4.5 Backend tests (`tests/api/`)

Approximately 25 new tests covering: persistence, retention, stream, all 11 routes, CORS, error envelopes. Existing 289 tests untouched and must remain green.

---

## 5. Frontend structure

### 5.1 File layout (all new under `web/`)

```
web/
├── package.json                          ← Next.js 15 + React 19 + TypeScript
├── pnpm-lock.yaml
├── next.config.mjs
├── tailwind.config.ts
├── tsconfig.json
├── .env.local                            ← NEXT_PUBLIC_API_URL=http://localhost:8000
├── README.md
├── public/
└── src/
    ├── app/
    │   ├── layout.tsx                    ← ThemeProvider > QueryProvider > Shell
    │   ├── page.tsx                      ← / → redirects to /monitor
    │   ├── globals.css                   ← Tailwind base + shadcn CSS vars
    │   ├── monitor/
    │   │   ├── page.tsx
    │   │   └── _components/
    │   │       ├── RunSelector.tsx
    │   │       ├── LiveEventStream.tsx
    │   │       ├── NodeStatusGrid.tsx
    │   │       ├── GenerationProgress.tsx
    │   │       └── LiveBacktestTable.tsx
    │   ├── strategies/
    │   │   ├── page.tsx
    │   │   ├── _components/
    │   │   │   ├── StrategyFilters.tsx
    │   │   │   ├── StrategyTable.tsx
    │   │   │   └── StrategyTableRow.tsx
    │   │   └── [id]/
    │   │       ├── page.tsx
    │   │       └── _components/                  ← 10 components for Strategy Detail
    │   │           ├── StrategyHeader.tsx
    │   │           ├── AggregateMetricsCard.tsx
    │   │           ├── SymbolRunSelector.tsx      ← combined symbol + run dropdowns
    │   │           ├── EquityCurveCard.tsx
    │   │           ├── DrawdownCard.tsx
    │   │           ├── PriceSignalChart.tsx
    │   │           ├── LineageTree.tsx
    │   │           ├── BacktestPerSymbolTable.tsx
    │   │           ├── ReasoningCard.tsx
    │   │           └── ExperimentHistoryTable.tsx
    ├── components/
    │   ├── ui/                           ← shadcn/ui components
    │   ├── Shell.tsx
    │   ├── ThemeProvider.tsx
    │   ├── QueryProvider.tsx
    │   ├── charts/
    │   │   ├── RechartsBase.tsx
    │   │   ├── EquityCurve.tsx
    │   │   ├── DrawdownArea.tsx
    │   │   └── PriceWithSignals.tsx
    │   └── common/
    │       ├── MetricPill.tsx
    │       ├── EmptyState.tsx
    │       ├── ErrorBoundary.tsx
    │       └── Loading.tsx
    ├── lib/
    │   ├── api/
    │   │   ├── client.ts
    │   │   ├── types.gen.ts              ← auto-generated
    │   │   ├── runs.ts
    │   │   └── strategies.ts
    │   ├── hooks/
    │   │   ├── useSSE.ts
    │   │   ├── useDebounce.ts
    │   │   └── useTheme.ts
    │   ├── stores/
    │   │   └── ui.ts
    │   ├── utils.ts
    │   └── constants.ts
    └── styles/                           ← (Tailwind only — no extra files)
```

### 5.2 Build commands (`web/package.json` scripts)

```json
{
  "dev":        "next dev --port 3000",
  "build":      "next build",
  "start":      "next start",
  "lint":       "next lint",
  "typecheck":  "tsc --noEmit",
  "test":       "vitest",
  "test:e2e":   "playwright test",
  "gen:types":  "openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/types.gen.ts"
}
```

### 5.3 Provider tree (top of `app/layout.tsx`)

```
<html lang="en" suppressHydrationWarning>
  <body>
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <QueryProvider>
        <Shell>
          {children}
        </Shell>
      </QueryProvider>
    </ThemeProvider>
  </body>
</html>
```

### 5.4 Routing

- `/` → redirect to `/monitor`
- `/monitor?run=<id>` → Pipeline Monitor
- `/strategies?family=&min_sharpe=&sort=...` → Strategy Library
- `/strategies/[id]?symbol=&run=` → Strategy Detail

---

## 6. Data flow + API contracts

### 6.1 Endpoint inventory (11 routes)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness + DB ping |
| GET | `/runs?limit=20&offset=0` | List recent runs |
| GET | `/runs/{run_id}` | Run summary |
| GET | `/runs/{run_id}/events?after_event_id=0` | SSE stream |
| GET | `/strategies?family=&min_sharpe=&generation=&sort=&page=&page_size=` | Paginated strategy list |
| GET | `/strategies/{id}` | Strategy detail (params, lineage parent, top metrics) |
| GET | `/strategies/{id}/backtests` | Per-symbol per-run breakdown |
| GET | `/strategies/{id}/equity?symbol=X&run_id=Y` | Recomputed equity + drawdown series |
| GET | `/strategies/{id}/signals?symbol=X&run_id=Y` | OHLCV bars + signal markers |
| GET | `/strategies/{id}/lineage` | Ancestor chain |
| GET | `/strategies/{id}/reasoning` | LLM reasoning from `experiments` table |

### 6.2 Response schemas (Pydantic)

```python
# schemas/runs.py
class RunSummary(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: datetime | None
    status: Literal["running", "done", "failed"]
    n_symbols: int
    max_generations: int
    current_generation: int | None
    n_backtests: int
    n_failures: int

class EventEnvelope(BaseModel):
    event_id: int
    run_id: str
    ts_ms: int
    event_type: str                       # "EvtBacktestDone" etc.
    generation: int | None
    payload: dict[str, Any]               # dataclass fields as dict

# schemas/strategies.py
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

class StrategyDetail(BaseModel):
    strategy_id: int
    name: str
    family: str
    params: dict[str, Any]
    description: str | None
    parent_strategy_id: int | None
    created_at: datetime
    metrics_summary: MetricsSummary

class EquityPoint(BaseModel):
    t: int                                # unix ms
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
    symbol: str
    bars: list[OHLCVBar]
    signals: list[SignalMarker]

class LineageNode(BaseModel):
    strategy_id: int
    name: str
    generation: int
    mutator: str | None
    accepted: bool | None
    sharpe: float | None

# schemas/common.py
class ErrorDetail(BaseModel):
    code: str                             # "STRATEGY_NOT_FOUND" etc.
    message: str
    details: dict[str, Any] | None = None

class ErrorResponse(BaseModel):
    error: ErrorDetail
```

### 6.3 SSE protocol

**Client request:**
```
GET /runs/{run_id}/events?after_event_id=0
Accept: text/event-stream
```

**Server response (streaming):**
```
event: pipeline_event
data: {"event_id":1,"run_id":"ad4245","event_type":"EvtPipelineStart","ts_ms":...,"payload":{...}}

event: pipeline_event
data: {"event_id":2,"run_id":"ad4245","event_type":"EvtNodeStart","ts_ms":...,"payload":{...}}

event: heartbeat
data: {"ts_ms": ...}
```

**Server logic (events/stream.py):**
1. Backfill: query `WHERE run_id=? AND event_id > after_event_id ORDER BY event_id ASC`; yield each as `pipeline_event`.
2. Poll loop: every 250ms, query for new rows past last sent `event_id`.
3. Heartbeat every 15s if no new events.
4. Stop: if last event was `EvtPipelineDone` AND no new events for 5s, close.

**Client (`lib/hooks/useSSE.ts`):**
- Wraps native EventSource.
- Reconnects with `after_event_id=lastReceivedEventId` (replay on reconnect).
- Cleans up on unmount.
- Returns `{events, isConnected, error}`.

### 6.4 TanStack Query keys + cache policy

| Query key | Stale time | Refetch on focus |
|---|---|---|
| `['runs']` | 30s | Yes |
| `['runs', runId]` | 5s (live) / ∞ (done) | Live: yes |
| `['strategies', filters, sort, page]` | 60s | Yes |
| `['strategies', strategyId]` | ∞ | No |
| `['strategies', strategyId, 'backtests']` | ∞ | No |
| `['strategies', strategyId, 'equity', symbol, runId]` | ∞ | No |
| `['strategies', strategyId, 'signals', symbol, runId]` | ∞ | No |
| `['strategies', strategyId, 'lineage']` | ∞ | No |
| `['strategies', strategyId, 'reasoning']` | ∞ | No |

Past run/strategy data is immutable; only `runs` list and live run summary need fresh data.

### 6.5 Equity computation strategy

Equity curves are NOT persisted in SQLite. Strategy Detail recomputes on-demand:
- New helper `backtest/portfolio_service.py` wraps the existing `engine.run_backtest()` in pure-read mode.
- Returns equity + drawdown series.
- Cached by TanStack Query infinitely once computed.
- Expected latency: ~100ms per `(strategy, symbol, run_id)` tuple.

**Risk:** existing engine may have write side effects. **Mitigation:** Phase C5 starts with a 4-hour spike to verify pure-read mode is feasible.

---

## 7. Screen designs

### 7.1 Shared shell

Sidebar with: nav (Monitor, Library), recent runs list, settings/about, theme toggle. Collapses to icon-only below `md` (768px).

### 7.2 Pipeline Monitor (`/monitor?run=<id>`)

**Components:**
- `RunSelector` — dropdown + URL-synced
- `RunStatusHeader` — badge + run meta
- `NodeStatusGrid` — visual pipeline topology with current node highlighted, derived from `EvtNodeStart` / `EvtNodeDone`
- `GenerationProgress` — table per generation: backtests count, accepted, vetoed, veto rate, best sharpe
- `LiveBacktestTable` — backtests stream in as `EvtBacktestDone` arrives
- `LiveEventStream` — virtualized scrolling list, color-coded by event_type, pause button
- `AgentActivityCard` — explorer/exploiter/critic call counts
- `FailuresCard` — collapsible, lists `state["failures"]`

**Empty states:**
- No runs → "Run a pipeline first: `uv run python main.py pipeline ...`"
- Run done but no events → "This run completed before event persistence was added"
- SSE error → "Connection lost. Retrying… (auto-reconnect every 5s)"

### 7.3 Strategy Library (`/strategies`)

**Components:**
- `StrategyFilters` — sticky bar: family multi-select, generation range, min sharpe slider, mutator filter, search, sort; URL-synced; chips show active filters
- `DistributionPanel` — 3 mini-charts: by family, by generation, Sharpe distribution
- `StrategyTable` — TanStack Table with sortable columns: name, family, generation, parent, Sharpe (with ↑↓ vs parent), Sortino, WR, n_backtests
- Parent ID is clickable → navigates to that strategy's detail
- Pagination

**Empty state:** "No strategies match these filters. [Clear all]"

### 7.4 Strategy Detail (`/strategies/[id]?symbol=&run=`)

**Components (10 cards on this screen):**
1. `StrategyHeader` — name, family, params, generation, parent link, created
2. `AggregateMetricsCard` — 5 KPI tiles (best Sharpe, best Sortino, avg WR, max DD, n backtests) with parent-delta indicators
3. `SymbolRunSelector` — combined symbol + run dropdowns, URL-synced, drives chart data fetches
4. `PriceSignalChart` — lightweight-charts OHLCV with entry/exit markers
5. `EquityCurveCard` — Recharts line chart
6. `DrawdownCard` — Recharts area chart (red palette)
7. `BacktestPerSymbolTable` — per-symbol per-run rows
8. `LineageTree` — indented text-tree (D3 viz deferred to Phase 2 of Track C)
9. `ReasoningCard` — LLM reasoning text + provider, tokens, latency
10. `ExperimentHistoryTable` — ratchet verdicts where this strategy was the child

**Layout grid:**
- Mobile (<768px): single column, all stacked
- Tablet (≥768px): 2-column for Equity/Drawdown pair
- Desktop (≥1280px): 2-column where natural, headers full-width

**Empty states:**
- No backtests → "No backtests recorded"
- No signals parquet → "Signal data unavailable for this strategy/run combination"
- No reasoning → "No LLM reasoning recorded — likely gen-0 seed"
- No lineage parent → "Gen-0 seed strategy (no parent)"

---

## 8. Build order (phased execution)

### 8.1 Phase dependency graph

```
C0 (branch) ─→ C1 (events table) ─→ C3 (SSE route) ─┐
                  │                                  │
                  └→ C2 (FastAPI scaffold) ─→ C3     │
                          │                          │
                          ├→ C4 (strategy routes) ───┤
                          └→ C5 (equity/signals) ────┤
                                                     │
                                                     ▼
                                          C7 (gen types) ─→ C6 (FE shell)
                                                              │
                                                              ├→ C8 (Library)
                                                              ├→ C9 (Detail)
                                                              └→ C10 (Monitor)
                                                                    │
                                                                    ▼
                                                                  C11 (e2e + polish)
                                                                    │
                                                                    ▼
                                                                  C12 (merge)
```

### 8.2 Per-phase plan

| # | Phase | Estimate | Risk | Verification |
|---|---|---|---|---|
| C0 | Branch + setup | 0.5 d | low | `git branch --show-current` = `feature/track-c-frontend`; tests pass |
| C1 | `pipeline_events` table + persistence hook | 1 d | low | New tests pass; smoke pipeline inserts events; existing 289 still green |
| C2 | FastAPI scaffold (`app.py`, `main.py`, `/health`) | 1 d | low | `uv run python -m atforge.api` boots; `/health` 200; `/openapi.json` valid |
| C3 | Runs routes + SSE stream | 1 d | medium | curl `/runs` returns list; SSE stream emits backfill + new events |
| C4 | Strategies routes (list/detail/backtests/lineage/reasoning) | 1.5 d | low | Each route returns JSON matching schema |
| C5 | Equity + signals routes (compute) | 1.5 d (incl. 4h spike) | **high** | Equity matches existing engine output for known input |
| **🔔** | **GATE: user verifies all API endpoints (Postman/curl)** | — | — | Manual review |
| C6 | Frontend scaffold + Shell + theme + nav | 1 d | low | `pnpm dev` boots; theme toggle works; nav between routes |
| C7 | API client + generated types | 0.5 d | medium | `pnpm gen:types` clean; types compile |
| C8 | Strategy Library screen | 1 d | low | Filter change updates URL + refetches; row click navigates |
| C9 | Strategy Detail screen | 2 d | medium | All cards render for known strategy_id; symbol selector switches chart data |
| C10 | Pipeline Monitor screen | 2 d | **high** | Live run from CLI streams into UI; pause works; reconnect on drop |
| **🔔** | **GATE: user visual review of all 3 screens, both themes** | — | — | Manual UI review |
| C11 | E2E tests + polish + READMEs | 1 d | low | `pnpm test:e2e` passes 3 paths; docs clear |
| C12 | Merge to main (squash) | 0.5 d | low | All tests green; merged |

**Total: ~13.5 days (~2.5–3 weeks single-developer sequential).**

### 8.3 Approval gates for Sonnet

The plan has **2 mandatory gates** where Sonnet pauses and asks the user:

1. **After C5** — user verifies backend endpoints work end-to-end via Postman/curl
2. **After C10** — user visually reviews all 3 screens in both themes

Additional natural pause points where Sonnet **must ask** before proceeding:
- C1: confirm event table schema (no surprises)
- C5: confirm equity recompute path before implementation (spike result review)
- C6: shadcn/ui `init` color/style choices (slate / zinc / neutral; border radius value)
- C9: card grid layout review on Strategy Detail before all cards built

### 8.4 Commit cadence

One commit per phase. Conventional Commits format. Branch contains 13 commits; squash-merge to main.

```
feat(api): add pipeline_events table and EventBus persistence (C1)
feat(api): scaffold FastAPI app with health route (C2)
feat(api): runs list + SSE stream (C3)
feat(api): strategies list/detail/backtests/lineage/reasoning routes (C4)
feat(api): equity + signals routes with portfolio_service (C5)
feat(web): Next.js scaffold + Shell + theme + nav (C6)
feat(web): API client + generated types (C7)
feat(web): strategy library screen (C8)
feat(web): strategy detail screen with charts (C9)
feat(web): pipeline monitor screen with SSE (C10)
test(web): playwright e2e for 3 MVP flows (C11)
feat: Track C MVP — read-only dashboard (C12 — squash merge)
```

---

## 9. Testing strategy

### 9.1 Test pyramid

- **Playwright e2e (3 tests)**: critical user journeys end-to-end
- **RTL + MSW component tests (~10)**: key components only
- **Vitest hooks/utils (~10)**: useSSE, useDebounce, formatters
- **pytest backend integration (~20)**: every API route
- **pytest backend unit (~5)**: persistence, retention, schemas

**Target: ~45 new tests total. Run time: under 35s additional.**

### 9.2 Backend test files (`tests/api/`)

| File | Type | Cases |
|---|---|---|
| `test_events_persistence.py` | unit | persist_event writes correct row, JSON roundtrips, autoincrement |
| `test_events_retention.py` | unit | prune removes >30d events, keeps last 100 runs |
| `test_events_stream.py` | integration | backfill, new events, heartbeat, stop on EvtPipelineDone |
| `test_routes_health.py` | integration | /health returns 200 + DB ping |
| `test_routes_runs.py` | integration | /runs paginates; /runs/{id} 200+404; SSE content-type |
| `test_routes_strategies.py` | integration | filters, sorts, 404s, lineage, reasoning, backtests |
| `test_routes_equity.py` | integration | equity matches known portfolio for fixture |
| `test_routes_signals.py` | integration | parquet read correct; 404 when missing |
| `test_cors.py` | integration | CORS preflight from localhost:3000 |

### 9.3 Frontend test files (`web/tests/`)

| File | Type | Cases |
|---|---|---|
| `unit/useSSE.test.ts` | hook | connect, accumulate, reconnect with cursor, cleanup |
| `unit/useDebounce.test.ts` | hook | delays update by configured ms |
| `unit/formatters.test.ts` | util | Sharpe colors, drawdown sign, dates |
| `unit/lib/api/runs.test.ts` | api | query keys, fetch wrapper |
| `components/StrategyTable.test.tsx` | RTL | rows, sort, row click |
| `components/StrategyFilters.test.tsx` | RTL | filter chips update URL |
| `components/LiveEventStream.test.tsx` | RTL | render events, pause, color-code |
| `components/EquityCurveCard.test.tsx` | RTL | empty state, Recharts render |
| `e2e/monitor-live.spec.ts` | playwright | seeded events render in UI |
| `e2e/library-filter-navigate.spec.ts` | playwright | filter → row click → detail page |
| `e2e/detail-cards-render.spec.ts` | playwright | all 9 cards present; symbol switch |

### 9.4 Not tested in MVP

- Theme visual diff (manual review at gate)
- Every shadcn component (trusted upstream)
- Mobile viewport (desktop chrome only in MVP)
- Performance benchmarks
- Coverage thresholds

### 9.5 Preflight script

`scripts/preflight.sh` runs: ruff, pytest, pnpm typecheck, pnpm lint, pnpm test. Manual call before push. ~30s. No husky hook for MVP.

---

## 10. Error handling

### 10.1 Backend layers

```
Request
  → CORSMiddleware
  → RequestIDMiddleware
  → Pydantic query/path validation (auto-422 on bad input)
  → Route handler
       ├ HTTPException(404, ...) for missing resources
       ├ HTTPException(400, ...) for semantic invalid
       └ Repo call → exception → global handler
                                    → log full trace (structlog)
                                    → ErrorResponse(500, ..., request_id)
```

**Specific codes:**
- `STRATEGY_NOT_FOUND` → 404
- `SIGNAL_DATA_MISSING` → 404 (frontend renders empty state)
- `EQUITY_RECOMPUTE_FAILED` → 500
- `INVALID_FILTER` → 400

**Never log:** full response payloads, OHLCV bars, raw LLM outputs.

### 10.2 Frontend layers

```
<ErrorBoundary>                            ← React render errors
  <QueryProvider>                          ← TanStack default retry (3x exp backoff for 5xx, 0 for 4xx)
    Page
      → useQuery
          isLoading → <Skeleton />
          isError && 4xx → <EmptyState message={error.message} />
          isError && 5xx after retries → <ErrorPanel onRetry={refetch} />
          data → <Card />
```

**SSE errors:** handled in `useSSE` — show "Connection lost. Retrying…" banner, auto-reconnect every 5s with `after_event_id` cursor.

**No Sentry in MVP.** Deferred to public deploy phase.

---

## 11. Risk register

| ID | Risk | Severity | Mitigation | Fallback |
|---|---|---|---|---|
| R1 | C5 equity recompute slow or has side effects | HIGH | C5 starts with 4h spike on existing engine in pure-read mode | Persist equity series on backtest completion (one-line change to `insert_backtest_result`) |
| R2 | C10 SSE reconnect / replay edge cases | HIGH | `after_event_id` cursor, idempotent event merge, ring buffer for backpressure | Swap SSE → polling every 1s reading `pipeline_events` |
| R3 | openapi-typescript codegen gaps for Pydantic patterns | MEDIUM | Schemas avoid discriminated unions in MVP; `dict[str, Any]` → `Record<string, unknown>` is acceptable | Hand-write 3-5 awkward types in `types.ts` alongside generated `types.gen.ts` |
| R4 | SSE in Next.js dev buffer issues | MEDIUM | Frontend hits FastAPI directly via `NEXT_PUBLIC_API_URL`; CORS configured | Already documented as primary path |
| R5 | lightweight-charts SSR mismatch | MEDIUM | `next/dynamic({ ssr: false })`; parent Card `"use client"` | Already planned in component design |
| R6 | `pipeline_events` table growth unbounded | LOW | Retention prunes >30 days and >100 runs on FastAPI startup | Manual prune via SQL |
| R7 | 26 parallel workers writing events out of order | LOW | `event_id INTEGER PRIMARY KEY AUTOINCREMENT` provides monotonic global ordering | None needed |
| R8 | Sonnet over-engineers beyond MVP | MEDIUM | Plan explicitly lists in-scope vs deferred; Sonnet asks at gates before scope expansion | Hard revert and trim |

---

## 12. Architectural invariants (post-Track C)

These invariants extend the existing CLAUDE.md hard rules:

1. **API routes are read-only.** No POST, PUT, PATCH, DELETE endpoints in MVP. Future write endpoints (Phase 3 trade approval) introduce their own design.
2. **API routes never compute business logic.** Routes parse request → call `repo.py` or `portfolio_service.py` → serialize response. Any business logic belongs in `src/atforge/` modules outside `api/`.
3. **Backend depends on frontend = NEVER.** Backend must function fully without `web/`.
4. **Pipeline depends on API = NEVER.** Pipeline must run fully without `src/atforge/api/`.
5. **Single source of truth: SQLite.** No in-memory caches in API routes (TanStack Query handles client-side caching).
6. **Generated types `types.gen.ts` must never be hand-edited.** Run `pnpm gen:types` on schema changes.

---

## 13. Out-of-scope (explicit deferrals)

| Feature | When |
|---|---|
| Evolution Tree screen (D3 mutation graph) | Phase 2 of Track C |
| Experiment Log screen (full ratchet/critic explorer) | Phase 2 of Track C |
| Compare strategies feature | Phase 2 of Track C |
| Public deployment (Vercel + backend hosting) | After MVP works end-to-end locally |
| Authentication | When write endpoints introduced (Phase 3) |
| Pipeline control from UI | When job queue needed (Phase 3) |
| Mobile-optimized layouts | Phase 2 of Track C |
| Live trade display | Phase 3 of overall project (after broker integration) |
| Sentry error reporting | Public deploy |
| Husky pre-commit hooks | Public deploy |
| Storybook | If component library grows beyond ~30 components |

---

## 14. Commands cheat sheet

### Backend
```bash
uv add fastapi 'uvicorn[standard]' sse-starlette          # add deps
uv run python -m atforge.api                              # start backend
uv run pytest tests/api/                                  # run API tests
uv run pytest                                             # all tests
```

### Frontend
```bash
cd web
pnpm install                                              # install deps
pnpm dev                                                  # dev server :3000
pnpm gen:types                                            # regen API types
pnpm typecheck && pnpm lint                               # static checks
pnpm test                                                 # unit + RTL
pnpm test:e2e                                             # Playwright
pnpm build                                                # production build
```

### Workflow
```bash
git checkout feature/track-c-frontend                     # working branch
./scripts/preflight.sh                                    # all checks before push
```

---

## 15. Deliverables checklist (for Sonnet)

End of Track C MVP, Sonnet should be able to demonstrate:

- [ ] `git log feature/track-c-frontend` shows 13 commits, one per phase
- [ ] `uv run pytest` shows 289 (existing) + ~25 (new API) tests green
- [ ] `cd web && pnpm test` shows ~10 unit + ~10 RTL tests green
- [ ] `cd web && pnpm test:e2e` shows 3 e2e tests green
- [ ] `uv run python -m atforge.api` boots on :8000; `/openapi.json` renders
- [ ] `cd web && pnpm dev` boots on :3000; all 3 screens accessible
- [ ] Running `uv run python main.py pipeline --symbols RELIANCE --max-generations 2` and opening `/monitor?run=<id>` shows live events
- [ ] `/strategies` shows all strategies, filter works, click row navigates
- [ ] `/strategies/{id}` shows all 10 cards including charts
- [ ] Dark + light themes both render correctly (manual review)
- [ ] `web/README.md` documents setup steps
- [ ] Root `CLAUDE.md` updated with Track C status + API/web commands

---

*Design owner: Claude (Opus 4.7). Implementation owner: Sonnet (4.6 or higher), fresh session. Approved by user 2026-05-12.*

---

## C5 Spike Findings (2026-05-13)

**Decision: R1 fallback taken** — persist equity + signals at backtest time.

### engine.py analysis
- `run_backtest()` — zero side effects: no DB writes, no file I/O, pure compute
- `portfolio_for_debug()` — returns raw `vbt.Portfolio`, safe escape hatch
- `vbt.Portfolio.value()` → `pd.Series` (portfolio equity over time)
- `vbt.Portfolio.drawdown()` → `pd.Series` (drawdown fraction over time)
- `portfolio.trades.records_readable` → DataFrame with entry/exit info per trade

### Why pure-read recompute was rejected
- `pattern_signals` table stores only metadata (`n_signals`, `first_date`, `last_date`) — **signal boolean series not persisted**
- Recompute would require: re-fetch OHLCV + re-run pattern detection + re-run backtest
- API layer would need to import `patterns/` + detector registry — breaks "API is deletable" invariant
- Cache is exact-range-match only; stale if date range changes

### R1 implementation (Tasks 15+16)
1. Migration `0004_equity_signals.sql`: add `equity_json TEXT`, `signals_json TEXT` to `backtest_runs`
2. `engine.py`: `BacktestResult` gains optional `equity_json` + `signals_json` fields; extraction helpers added
3. `repo.py` `insert_backtest_result`: stores JSON columns
4. API routes read from DB; return `SIGNAL_DATA_MISSING` 404 if columns are NULL (old runs)
