# Track C — Frontend Redesign Design

> Supersedes the screen/visual sections of `2026-05-12-track-c-frontend-design.md`.
> The backend architecture and additive/deletable invariants from that spec still hold.

## 0. Context

The first Track C build shipped three screens (Monitor, Strategy Library, Strategy
Detail) following the original MVP plan. On review (2026-05-16) the user rejected it:
the UI looked worse than the old Streamlit dashboard, had broken styling, and missed
most of the observability the user actually wanted — Rankings, Run History, DB Stats,
Evolution, and especially **step-by-step Agent Activity**.

This spec redesigns the frontend. The backend (FastAPI, `src/atforge/api/`) and the
working frontend plumbing are kept; the UI is rebuilt on a real design system and
expanded to six screens with run-first navigation.

## 1. Goals + non-goals

### Goals
1. Six screens, run-first navigation: Overview, Monitor, Runs, Run Detail, Strategies, Strategy Detail.
2. A documented "Refined Quant" design system — tokens + primitive components — so screens compose primitives instead of reinventing styling.
3. Full observability parity with the old Streamlit dashboard (rankings, run history, DB stats, evolution) **plus** the live Monitor.
4. Run Detail surfaces the agentic pipeline **step by step**: a chronological timeline where agent events expand to ReAct reasoning + tool calls, with a Langfuse deep-link per agent event.
5. Every table sortable, every ID/name/symbol clickable and cross-linked, filters composable and URL-driven.
6. Extensible structure: adding a screen or a Run Detail section is cheap and isolated.

### Non-goals
- D3 force-graph evolution tree (lineage stays a simple linear tree).
- In-app reconstruction of the full ReAct loop including tool *results* — that detail is reached via the Langfuse deep-link.
- Auth, multi-user, deployment hardening — local-first tool.
- Rebuilding backend architecture or the working frontend plumbing.

## 2. Locked decisions (from brainstorming, 2026-05-16)

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Navigation model | Run-first | One run = one page telling its whole story; no repeated run-pickers |
| 2 | Aesthetic | "Refined Quant" — dark-first, data-dense but breathing, mono numerals, teal accent | Quant tool needs density; the prior build's failure was rawness not density |
| 3 | Agent Activity depth | Depth C — full ReAct trace | User's priority feature |
| 4 | ReAct trace source | In-app shows reasoning + tool calls (already in `pipeline_events`); Langfuse deep-link for tool results / tokens / latency | No `agent_runner.py` change; near-zero backend cost |
| 5 | Approach | Approach 1 — keep correct plumbing, rebuild UI on a design system, delete what doesn't fit | Not a rewrite; same destination, less waste |

## 3. Architecture

Unchanged from the original spec. Three processes — Next.js browser app, FastAPI
server, pipeline CLI — decoupled via SQLite. Backend changes are **additive only**:
`src/atforge/api/` and `web/` remain fully deletable without breaking the pipeline.
Real-time via SSE for the Monitor screen; everything else is REST.

## 4. Kept / rebuilt / new / deleted

**Kept verbatim (correct, screen-agnostic plumbing):**
- `web/src/lib/api/client.ts`, `types.gen.ts` (extended with new schemas), `runs.ts`, `strategies.ts` (extended)
- `web/src/lib/hooks/useSSE.ts`, `useDebounce.ts`
- `web/src/lib/constants.ts`, `lib/utils.ts`
- shadcn primitives in `web/src/components/ui/`
- Next.js scaffold, `next.config.ts`, `package.json` deps, the `globals.css` CSS-variable + dark-mode fix
- All existing backend: `routes/health.py`, `routes/runs.py`, `routes/strategies.py`, `events/`, `schemas/`

**Rebuilt on the design system:**
- `Shell.tsx`, `ThemeProvider`, `QueryProvider`, `ErrorBoundary` (logic kept, restyled)
- All screen components for Monitor, Strategies, Strategy Detail
- Chart components (restyled to design-system tokens)
- `common/Loading.tsx`, `common/EmptyState.tsx`

**New:**
- Design-system primitives (section 5)
- Overview, Runs, Run Detail screens
- `Timeline` component (shared by Run Detail and Monitor)
- Backend routes + schemas (section 7)

**Deleted:** any current component that does not fit the new structure, rather than carried forward.

## 5. Design system — "Refined Quant"

Defined once in `web/src/app/globals.css` (tokens) + `web/src/components/primitives/`
(components). Dark is default; light mode mirrors via the existing theme toggle.

### 5.1 Tokens (CSS variables)

```
Surfaces   bg #0a0b0d · surface #0c0d10 · elevated #131419
Borders    border rgba(255,255,255,.07) · border-strong rgba(255,255,255,.12)
Text       text #e6e8eb · text-secondary #9aa4af · text-muted #6b7280
Accent     accent #2dd4bf · accent-dim rgba(45,212,191,.12)
Signal     up #34d399 · down #f87171 · info #60a5fa · warn #fbbf24
Charts     #2dd4bf #60a5fa #fbbf24 #a78bfa #fb7185
Radius     card 8px · tile/pill 6px · small 4px
```

Light mode: a parallel `:root` light set; component classes reference tokens only,
never raw colors.

### 5.2 Typography

- **Inter** — UI, labels, body.
- **Monospace** (`ui-monospace` / JetBrains Mono if available) — all numbers, IDs, timestamps, params. This is the core quant visual signal.
- Scale: page title 20/600 · section label 11/uppercase/tracked · body 13 · table 12 · metric value 22/600 mono.

### 5.3 Primitive components (`web/src/components/primitives/`)

| Primitive | Purpose |
|---|---|
| `Card` / `Panel` | Base elevated surface |
| `SectionHeader` | Titled section divider within a page |
| `MetricTile` | KPI: uppercase label + large mono value + optional delta |
| `StatusPill` | run/node status (running / done / failed / pending) |
| `Chip` | filter chip — clickable, toggle/active states |
| `DataTable` | sortable columns, hairline rows, hover tint, right-aligned mono numerics, row-click navigation, empty + loading states |
| `FilterBar` | container for composable, URL-bound filter controls |
| `Timeline` / `TimelineEvent` | chronological event feed; events collapsed by default, agent events expand to reasoning + tool calls + Langfuse link |
| `Sparkline` | inline mini chart |
| `ChartCard` | titled wrapper for Recharts / candlestick charts |
| `EmptyState`, `Loading` | no-data and skeleton states |
| `ValueText` | numeric with Sharpe/PnL color coding |

Screens compose only these. No per-screen inline styling — this is the anti-bloat lever.

## 6. Screens

Shared shell: left sidebar (Overview / Monitor / Runs / Strategies), brand, theme
toggle, mobile top bar. Content area renders the active screen.

**Cross-cutting UX rules (apply to every screen):**
- Every run ID, strategy name, symbol, and parent reference is a link to its detail/filtered view.
- Every DataTable column is sortable; sort state lives in the URL.
- Filters are composable and URL-bound (shareable, back-button works); chips are click-to-toggle.
- Data-dense but with clear hierarchy — section headers, spacing, and the elevated/surface/bg layering create distinction so screens do not read as cluttered.

### 6.1 Overview (`/`)
Home dashboard. MetricTile row: Runs, Strategies, Backtests, Experiments, Best Sharpe.
Below, three panels: **Recent Runs** (last 5, link to Run Detail), **Top Strategies**
(top 5 by Sharpe, link to Strategy Detail), and **Strategy Family Breakdown**
(count per family — clickable through to a filtered Strategies view).

### 6.2 Monitor (`/monitor?run=<id>`)
Live SSE view of a running pipeline. Run picker; node-status grid (animated running
state); generation-progress strip; live backtest feed; **the shared `Timeline`
component fed by SSE**. Pause / resume / clear controls.

### 6.3 Runs (`/runs`)
Browsable history of every run. DataTable: run ID (mono), started, status pill,
backtests, failures, generations. Sortable; row-click → Run Detail.

### 6.4 Run Detail (`/runs/[id]`) — hub screen
One run's whole story. Header (run ID, status, started→finished, duration) + metric
row (backtests, failures, generations, accepted, vetoed, best Sharpe). Then sections:

- **Rankings** — top backtests for this run; sortable DataTable; symbol + strategy links.
- **Evolution** — best-Sharpe-per-generation chart + accepted/rejected/veto counts + mutation log table.
- **Agent Activity** — the shared `Timeline`, fed by a static GET. Chronological, generation-grouped. Composable filters: event type (all / agents / verdicts / nodes), generation, agent role. Agent events (`EvtAgentReasoning`, `EvtAgentToolCall`, proposals, vetoes, ratchet verdicts) expand to per-iteration reasoning + tool calls, with an "open full trace in Langfuse" link.

Sections are independent components — a new section can be added without touching others.

### 6.5 Strategies (`/strategies`)
Browse all strategies across runs. `FilterBar`: family chips (click-to-toggle),
min-Sharpe, generation, sort — all composable and URL-bound. Sortable DataTable;
row-click → Strategy Detail.

### 6.6 Strategy Detail (`/strategies/[id]?symbol=&run=`)
Header + metric tiles; symbol/run selector; price+signals candlestick chart; equity
and drawdown charts; lineage tree (clickable nodes); LLM reasoning cards; backtest
history table (sortable).

## 7. Backend additions

All new routes are read-only and wrap existing `storage/repo.py` functions (the
Streamlit dashboard already uses them). New Pydantic schemas under `api/schemas/`.

| Route | Repo function(s) | Feeds |
|---|---|---|
| `GET /stats` | table counts, family breakdown, cache size | Overview |
| `GET /runs/{id}/rankings` | `top_rankings(conn, run_id=…)` | Run Detail · Rankings |
| `GET /runs/{id}/evolution` | `get_experiments_for_run`, `get_best_sharpe_per_generation` | Run Detail · Evolution |
| `GET /runs/{id}/timeline` | ordered `pipeline_events` for run (incl. agent reasoning/tool-call events) | Run Detail · Agent Activity |

Already existing and kept: `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/events`
(SSE), and all `/strategies/*` routes.

`pipeline_events` already persists `EvtAgentReasoning` and `EvtAgentToolCall`
(via the EventBus `db_path` wiring). The timeline route exposes them; no change to
`agent_runner.py` or the ReAct loop is required.

**Langfuse deep-link:** each agent event renders a link to the Langfuse trace view,
keyed by the event's `trace_name` (e.g. `research_agent_iter0`) and run. This opens
the run/trace-filtered view in Langfuse for the full ReAct detail (tool results,
tokens, latency). Precise per-iteration linking is a later refinement if event
payloads are extended to carry Langfuse trace IDs; until then the link opens the
filtered trace list. The link is shown only when a Langfuse host is configured.

## 8. Data flow

- **TanStack Query** for all REST. Query keys namespaced: `["stats"]`, `["runs"]`, `["run", id]`, `["run", id, "rankings"]`, `["run", id, "evolution"]`, `["run", id, "timeline"]`, `["strategies", filters]`, `["strategy", id, …]`.
- **SSE** only for Monitor (`useSSE` hook, existing).
- **URL is the source of truth** for filters, sort, pagination, and selected run/symbol — views are shareable and the back button works.
- The `Timeline` component is source-agnostic: Run Detail feeds it a static array from `GET /runs/{id}/timeline`; Monitor feeds it the live SSE event array. Same rendering.

## 9. Error handling

- **Backend:** consistent `{error: {code, message}}`; 404 on missing run/strategy; empty arrays (not errors) for valid-but-no-data.
- **Frontend:** typed `ApiError`; per-screen `ErrorBoundary`; `EmptyState` for no-data; skeleton `Loading`; SSE auto-reconnect (existing). Query retry skips 4xx.

## 10. Testing

- **Backend:** pytest per new route — happy path, 404, empty-data. Consistent with existing `tests/api/`.
- **Frontend:** `tsc --noEmit` + `next build` gates on every task. Playwright e2e for golden paths (Overview loads, Runs→Run Detail navigation, timeline expand, Strategies filter+sort).
- A run with `--max-generations 2+` must exist in the DB so Evolution + Agent Activity have real data to render.

## 11. Extensibility

- Design-system primitives mean a new screen is mostly composition — low marginal cost.
- Run Detail sections are independent components; adding a section is isolated.
- `api/` + `web/` stay additive and deletable; new backend routes follow the existing route/schema pattern.
- The `Timeline` component is reused (live + static) — one place to extend event rendering.

## 12. Build order (high level)

Detailed task breakdown is produced by the writing-plans step. Phases:

1. **Design system** — tokens in `globals.css` + primitive components + Shell.
2. **Backend routes** — `/stats`, `/runs/{id}/rankings|evolution|timeline` + schemas + tests.
3. **API client extension** — new fetch wrappers + types for the new routes.
4. **Overview + Runs** — the two simpler screens, validate the design system.
5. **Run Detail** — Summary, Rankings, Evolution, then the Agent Activity `Timeline`.
6. **Monitor** — rebuilt on design system, reuse `Timeline` via SSE.
7. **Strategies + Strategy Detail** — rebuilt on design system, charts restyled.
8. **Polish + e2e** — Playwright, both themes, empty/loading/error states, READMEs.

Each task: build → typecheck + `next build` → commit. Backend tasks add pytest.
