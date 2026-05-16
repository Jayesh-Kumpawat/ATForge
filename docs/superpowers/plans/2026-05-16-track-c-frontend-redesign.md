# Track C Frontend Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the ATForge web dashboard on a real "Refined Quant" design system with six run-first screens (Overview, Monitor, Runs, Run Detail, Strategies, Strategy Detail) plus four new read-only backend routes.

**Architecture:** Keep the correct frontend plumbing (API client, generated types, `useSSE`/`useDebounce` hooks, shadcn `ui/` primitives) and the existing FastAPI backend. Replace all UI on a documented design system. Add four additive read-only API routes. Backend stays additive/deletable; `web/` and `src/atforge/api/` never break the pipeline.

**Tech Stack:** Next.js 16 (App Router) · React 19 · TypeScript · Tailwind CSS v4 · shadcn/ui · TanStack Query v5 · Recharts · lightweight-charts v5 · FastAPI · pytest.

**Spec:** `docs/superpowers/specs/2026-05-16-track-c-frontend-redesign.md`

---

## Dev environment notes (read before starting)

- **pnpm** is installed at `~/Library/pnpm/bin`. Before any `pnpm`/`npx` command: `export PATH="$HOME/Library/pnpm/bin:$PATH"`.
- **Build & typecheck the frontend directly** — do NOT use `pnpm build` (the pnpm wrapper triggers a dependency-approval gate). From `web/`:
  - Typecheck: `./node_modules/.bin/tsc --noEmit`
  - Build: `./node_modules/.bin/next build`
- **shadcn components:** `npx shadcn@4.6.0 add <name> --yes` — version `4.6.0` is pinned (newer versions silently fail to write files).
- **Backend tests:** `uv run pytest tests/api/ -q`
- **Full backend suite:** `uv run pytest -q`
- All frontend paths below are relative to repo root (i.e. `web/src/...`). All backend paths under `src/atforge/...`.
- Existing rejected build: screen components under `web/src/app/*` and `web/src/components/*` will be overwritten by this plan. Files explicitly listed as "Create" are new; "Replace" overwrites an existing file.

---

## Phase A — Design System

### Task 1: Refined Quant design tokens

**Files:**
- Replace: `web/src/app/globals.css`

The current `globals.css` has shadcn oklch defaults. Replace with the Refined Quant palette. shadcn token *names* are kept (so `ui/` primitives keep working) but set to dark Refined-Quant values; extra custom tokens are added for surfaces and signal colors.

- [ ] **Step 1: Replace `web/src/app/globals.css`**

```css
@import "tailwindcss";

/* Dark mode: class-based (next-themes writes .dark on <html>) */
@custom-variant dark (&:where(.dark, .dark *));

/* ── Refined Quant tokens ── */
:root, .dark {
  /* shadcn-named tokens (consumed by components/ui/*) */
  --background: #0a0b0d;
  --foreground: #e6e8eb;
  --card: #131419;
  --card-foreground: #e6e8eb;
  --popover: #131419;
  --popover-foreground: #e6e8eb;
  --primary: #2dd4bf;
  --primary-foreground: #06302b;
  --secondary: #1a1c22;
  --secondary-foreground: #e6e8eb;
  --muted: #1a1c22;
  --muted-foreground: #9aa4af;
  --accent: #1f232c;
  --accent-foreground: #e6e8eb;
  --destructive: #f87171;
  --destructive-foreground: #2a0d0d;
  --border: #23262e;
  --input: #23262e;
  --ring: #2dd4bf;
  --radius: 0.5rem;

  /* Refined Quant extras */
  --surface: #0c0d10;
  --elevated: #131419;
  --border-strong: #2f333d;
  --text-secondary: #9aa4af;
  --text-muted: #6b7280;
  --accent-teal: #2dd4bf;
  --accent-dim: rgba(45, 212, 191, 0.12);
  --up: #34d399;
  --down: #f87171;
  --info: #60a5fa;
  --warn: #fbbf24;
  --violet: #a78bfa;
  --rose: #fb7185;
}

/* Light mode mirror */
.light {
  --background: #f7f8fa;
  --foreground: #14171c;
  --card: #ffffff;
  --card-foreground: #14171c;
  --popover: #ffffff;
  --popover-foreground: #14171c;
  --primary: #0d9488;
  --primary-foreground: #ffffff;
  --secondary: #eceef1;
  --secondary-foreground: #14171c;
  --muted: #eceef1;
  --muted-foreground: #5b6470;
  --accent: #eceef1;
  --accent-foreground: #14171c;
  --destructive: #dc2626;
  --destructive-foreground: #ffffff;
  --border: #dde0e5;
  --input: #dde0e5;
  --ring: #0d9488;
  --surface: #ffffff;
  --elevated: #ffffff;
  --border-strong: #c4c9d0;
  --text-secondary: #5b6470;
  --text-muted: #8b93a0;
  --accent-teal: #0d9488;
  --accent-dim: rgba(13, 148, 136, 0.1);
  --up: #059669;
  --down: #dc2626;
  --info: #2563eb;
  --warn: #d97706;
  --violet: #7c3aed;
  --rose: #e11d48;
}

/* ── Tailwind v4 theme mapping ── */
@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-destructive-foreground: var(--destructive-foreground);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --color-surface: var(--surface);
  --color-elevated: var(--elevated);
  --color-border-strong: var(--border-strong);
  --color-text-secondary: var(--text-secondary);
  --color-text-muted: var(--text-muted);
  --color-up: var(--up);
  --color-down: var(--down);
  --color-info: var(--info);
  --color-warn: var(--warn);
  --color-violet: var(--violet);
  --color-rose: var(--rose);
  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius);
  --font-sans: var(--font-inter, ui-sans-serif, system-ui, sans-serif);
  --font-mono: var(--font-mono-stack, ui-monospace, "JetBrains Mono", Menlo, monospace);
}

* { border-color: var(--border); }

body {
  background-color: var(--background);
  color: var(--foreground);
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* Numeric/monospace utility — use on numbers, IDs, timestamps */
.tabular { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
```

- [ ] **Step 2: Verify build**

From `web/`: `./node_modules/.bin/next build`
Expected: build succeeds. (Existing screens still render — restyled tokens only.)

- [ ] **Step 3: Commit**

```bash
git add web/src/app/globals.css
git commit -m "feat(web): Refined Quant design tokens (Track C redesign / A)"
```

---

### Task 2: Core primitives

**Files:**
- Create: `web/src/components/primitives/Card.tsx`
- Create: `web/src/components/primitives/SectionHeader.tsx`
- Create: `web/src/components/primitives/MetricTile.tsx`
- Create: `web/src/components/primitives/StatusPill.tsx`
- Create: `web/src/components/primitives/Chip.tsx`
- Create: `web/src/components/primitives/ValueText.tsx`
- Create: `web/src/components/primitives/index.ts`

- [ ] **Step 1: Create `web/src/components/primitives/Card.tsx`**

```tsx
import { cn } from "@/lib/utils";

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("rounded-lg border border-border bg-elevated", className)}>
      {children}
    </div>
  );
}
```

- [ ] **Step 2: Create `web/src/components/primitives/SectionHeader.tsx`**

```tsx
import { cn } from "@/lib/utils";

interface Props {
  title: string;
  hint?: string;
  right?: React.ReactNode;
  className?: string;
}

export function SectionHeader({ title, hint, right, className }: Props) {
  return (
    <div className={cn("flex items-center justify-between border-b border-border pb-2 mb-3", className)}>
      <div className="flex items-baseline gap-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-text-secondary">{title}</h2>
        {hint ? <span className="text-xs text-text-muted">{hint}</span> : null}
      </div>
      {right}
    </div>
  );
}
```

- [ ] **Step 3: Create `web/src/components/primitives/MetricTile.tsx`**

```tsx
import { cn } from "@/lib/utils";

interface Props {
  label: string;
  value: string | number;
  delta?: number | null;
  accent?: boolean;
  className?: string;
}

export function MetricTile({ label, value, delta, accent, className }: Props) {
  return (
    <div
      className={cn(
        "rounded-md border bg-elevated px-3 py-2.5 min-w-[120px]",
        accent ? "border-primary/30" : "border-border",
        className,
      )}
    >
      <div
        className={cn(
          "text-[10px] uppercase tracking-wide",
          accent ? "text-primary" : "text-text-muted",
        )}
      >
        {label}
      </div>
      <div
        className={cn(
          "tabular text-2xl font-semibold mt-0.5",
          accent ? "text-primary" : "text-foreground",
        )}
      >
        {value}
      </div>
      {delta != null ? (
        <div className={cn("tabular text-xs mt-0.5", delta >= 0 ? "text-up" : "text-down")}>
          {delta >= 0 ? "+" : ""}
          {delta.toFixed(2)}
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Create `web/src/components/primitives/StatusPill.tsx`**

```tsx
import { cn } from "@/lib/utils";

export type RunStatus = "running" | "done" | "failed" | "pending" | "unknown";

const STYLE: Record<RunStatus, string> = {
  running: "bg-primary/12 text-primary border-primary/30",
  done: "bg-up/12 text-up border-up/30",
  failed: "bg-down/12 text-down border-down/30",
  pending: "bg-muted text-text-muted border-border",
  unknown: "bg-muted text-text-muted border-border",
};

const ICON: Record<RunStatus, string> = {
  running: "●",
  done: "✓",
  failed: "✗",
  pending: "○",
  unknown: "○",
};

export function StatusPill({ status, className }: { status: RunStatus; className?: string }) {
  const s = (STYLE[status] ?? STYLE.unknown);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium",
        s,
        className,
      )}
    >
      <span>{ICON[status] ?? ICON.unknown}</span>
      {status}
    </span>
  );
}
```

- [ ] **Step 5: Create `web/src/components/primitives/Chip.tsx`**

```tsx
"use client";

import { cn } from "@/lib/utils";

interface Props {
  label: string;
  active?: boolean;
  onClick?: () => void;
  className?: string;
}

export function Chip({ label, active, onClick, className }: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-md border px-2.5 py-1 text-xs transition-colors",
        active
          ? "border-primary/30 bg-primary/12 text-primary"
          : "border-border bg-elevated text-text-secondary hover:border-border-strong hover:text-foreground",
        className,
      )}
    >
      {label}
    </button>
  );
}
```

- [ ] **Step 6: Create `web/src/components/primitives/ValueText.tsx`**

```tsx
import { cn } from "@/lib/utils";

type Kind = "sharpe" | "pnl" | "plain" | "pct";

function sharpeColor(v: number): string {
  if (v >= 2) return "text-up font-semibold";
  if (v >= 1) return "text-up";
  if (v >= 0) return "text-warn";
  return "text-down";
}

interface Props {
  value: number | null | undefined;
  kind?: Kind;
  className?: string;
}

export function ValueText({ value, kind = "plain", className }: Props) {
  if (value == null) return <span className={cn("tabular text-text-muted", className)}>—</span>;

  let color = "text-foreground";
  let text = value.toFixed(2);

  if (kind === "sharpe") color = sharpeColor(value);
  else if (kind === "pnl") {
    color = value >= 0 ? "text-up" : "text-down";
    text = `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
  } else if (kind === "pct") {
    color = value >= 0 ? "text-up" : "text-down";
    text = `${(value * 100).toFixed(1)}%`;
  }

  return <span className={cn("tabular", color, className)}>{text}</span>;
}
```

- [ ] **Step 7: Create `web/src/components/primitives/index.ts`**

```ts
export { Card } from "./Card";
export { SectionHeader } from "./SectionHeader";
export { MetricTile } from "./MetricTile";
export { StatusPill, type RunStatus } from "./StatusPill";
export { Chip } from "./Chip";
export { ValueText } from "./ValueText";
```

- [ ] **Step 8: Typecheck + build**

From `web/`: `./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build`
Expected: both pass.

- [ ] **Step 9: Commit**

```bash
git add web/src/components/primitives/
git commit -m "feat(web): core design-system primitives — Card/MetricTile/StatusPill/Chip/ValueText (Track C redesign / A)"
```

---

### Task 3: DataTable primitive

**Files:**
- Create: `web/src/components/primitives/DataTable.tsx`
- Modify: `web/src/components/primitives/index.ts`

A generic sortable table. Columns are configured; sort state is owned by the caller (so screens can bind it to the URL). Numeric columns right-align and use the mono font via the column `align` field.

- [ ] **Step 1: Create `web/src/components/primitives/DataTable.tsx`**

```tsx
"use client";

import { cn } from "@/lib/utils";

export interface Column<T> {
  key: string;
  label: string;
  align?: "left" | "right";
  sortable?: boolean;
  render: (row: T) => React.ReactNode;
}

interface Props<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  sortKey?: string;
  sortDir?: "asc" | "desc";
  onSort?: (key: string) => void;
  onRowClick?: (row: T) => void;
  empty?: React.ReactNode;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  sortKey,
  sortDir,
  onSort,
  onRowClick,
  empty,
}: Props<T>) {
  if (rows.length === 0 && empty) return <>{empty}</>;

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-elevated">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border">
            {columns.map((c) => {
              const isSorted = sortKey === c.key;
              const clickable = c.sortable && onSort;
              return (
                <th
                  key={c.key}
                  onClick={clickable ? () => onSort!(c.key) : undefined}
                  className={cn(
                    "px-3 py-2 text-[10px] font-medium uppercase tracking-wide text-text-muted",
                    c.align === "right" ? "text-right" : "text-left",
                    clickable && "cursor-pointer select-none hover:text-foreground",
                    isSorted && "text-primary",
                  )}
                >
                  {c.label}
                  {isSorted ? <span className="ml-1">{sortDir === "asc" ? "▲" : "▼"}</span> : null}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cn(
                "border-b border-border/60 last:border-0",
                onRowClick && "cursor-pointer hover:bg-accent/40",
              )}
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={cn(
                    "px-3 py-2 text-foreground",
                    c.align === "right" && "text-right",
                  )}
                >
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Append to `web/src/components/primitives/index.ts`**

```ts
export { DataTable, type Column } from "./DataTable";
```

- [ ] **Step 3: Typecheck + build**

From `web/`: `./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build`
Expected: both pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/primitives/
git commit -m "feat(web): DataTable primitive — generic sortable table (Track C redesign / A)"
```

---

### Task 4: Timeline primitives

**Files:**
- Create: `web/src/components/primitives/Timeline.tsx`
- Modify: `web/src/components/primitives/index.ts`

`Timeline` renders an array of pipeline events grouped by generation. Each event is a `TimelineEvent` row; agent events (`EvtAgentReasoning`, `EvtAgentToolCall`) and verdict events are expandable. The event shape is `EventEnvelope` from `lib/api/runs.ts`.

- [ ] **Step 1: Create `web/src/components/primitives/Timeline.tsx`**

```tsx
"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { EventEnvelope } from "@/lib/api/runs";

const EVENT_META: Record<string, { icon: string; color: string; label: string }> = {
  EvtPipelineStart: { icon: "▶", color: "text-info", label: "pipeline start" },
  EvtPipelineDone: { icon: "■", color: "text-up", label: "pipeline done" },
  EvtNodeStart: { icon: "▸", color: "text-text-secondary", label: "node" },
  EvtNodeDone: { icon: "▸", color: "text-text-secondary", label: "node done" },
  EvtBacktestDone: { icon: "✓", color: "text-info", label: "backtest" },
  EvtAgentReasoning: { icon: "🧠", color: "text-violet", label: "reasoning" },
  EvtAgentToolCall: { icon: "🔧", color: "text-info", label: "tool call" },
  EvtMutationProposed: { icon: "✦", color: "text-violet", label: "proposal" },
  EvtRatchetVerdict: { icon: "⚖", color: "text-warn", label: "ratchet" },
  EvtCriticVerdict: { icon: "⚖", color: "text-down", label: "critic" },
  EvtGenerationDone: { icon: "◆", color: "text-primary", label: "generation done" },
};

function fmtTime(ms: number): string {
  return new Date(ms).toLocaleTimeString();
}

function isExpandable(e: EventEnvelope): boolean {
  return (
    e.event_type === "EvtAgentReasoning" ||
    e.event_type === "EvtAgentToolCall" ||
    e.event_type === "EvtCriticVerdict" ||
    e.event_type === "EvtRatchetVerdict" ||
    e.event_type === "EvtMutationProposed"
  );
}

function summary(e: EventEnvelope): string {
  const p = e.payload ?? {};
  const parts: string[] = [];
  for (const k of ["node_name", "symbol", "strategy", "role", "tool_name", "mutator"]) {
    if (p[k] != null) parts.push(String(p[k]));
  }
  if (typeof p.sharpe === "number") parts.push(`sharpe ${p.sharpe.toFixed(2)}`);
  if (typeof p.accepted === "boolean") parts.push(p.accepted ? "accepted" : "rejected");
  return parts.join(" · ");
}

function TimelineEvent({ event, langfuseHost }: { event: EventEnvelope; langfuseHost?: string | null }) {
  const [open, setOpen] = useState(false);
  const meta = EVENT_META[event.event_type] ?? { icon: "•", color: "text-text-muted", label: event.event_type };
  const expandable = isExpandable(event);
  const traceName = event.payload?.trace_name as string | undefined;

  return (
    <div className="border-b border-border/50 last:border-0">
      <div
        onClick={expandable ? () => setOpen((v) => !v) : undefined}
        className={cn(
          "flex items-center gap-2 px-3 py-1.5 font-mono text-[11px]",
          expandable && "cursor-pointer hover:bg-accent/30",
        )}
      >
        <span className="tabular text-text-muted">{fmtTime(event.ts_ms)}</span>
        <span className={meta.color}>{meta.icon}</span>
        <span className={meta.color}>{meta.label}</span>
        <span className="text-foreground truncate">{summary(event)}</span>
        {expandable ? (
          <span className="ml-auto text-[10px] text-primary">{open ? "▾" : "▸"} trace</span>
        ) : null}
      </div>
      {open ? (
        <div className="ml-4 mb-2 border-l-2 border-border pl-3 font-mono text-[10.5px] text-text-secondary">
          {Object.entries(event.payload ?? {}).map(([k, v]) => (
            <div key={k}>
              <span className="text-text-muted">{k}</span>{" "}
              {typeof v === "string" ? v : JSON.stringify(v)}
            </div>
          ))}
          {langfuseHost && traceName ? (
            <a
              href={`${langfuseHost}/traces?search=${encodeURIComponent(traceName)}`}
              target="_blank"
              rel="noreferrer"
              className="text-info hover:underline"
            >
              ↗ open full trace in Langfuse
            </a>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function Timeline({
  events,
  langfuseHost,
}: {
  events: EventEnvelope[];
  langfuseHost?: string | null;
}) {
  // group by generation, preserving event order
  const groups = new Map<number, EventEnvelope[]>();
  for (const e of events) {
    const g = e.generation ?? -1;
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g)!.push(e);
  }
  const gens = [...groups.keys()].sort((a, b) => a - b);

  return (
    <div className="rounded-lg border border-border bg-elevated">
      {gens.map((g) => (
        <div key={g}>
          <div className="border-b border-border bg-surface px-3 py-1.5 font-mono text-[10px] uppercase tracking-wide text-text-muted">
            {g < 0 ? "ungrouped" : `generation ${g}`}
          </div>
          {groups.get(g)!.map((e) => (
            <TimelineEvent key={e.event_id} event={e} langfuseHost={langfuseHost} />
          ))}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Append to `web/src/components/primitives/index.ts`**

```ts
export { Timeline } from "./Timeline";
```

- [ ] **Step 3: Typecheck + build**

From `web/`: `./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build`
Expected: both pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/primitives/
git commit -m "feat(web): Timeline primitive — generation-grouped event feed with expandable agent traces (Track C redesign / A)"
```

---

### Task 5: Remaining primitives — ChartCard, Sparkline, FilterBar, EmptyState, Loading

**Files:**
- Create: `web/src/components/primitives/ChartCard.tsx`
- Create: `web/src/components/primitives/Sparkline.tsx`
- Create: `web/src/components/primitives/FilterBar.tsx`
- Replace: `web/src/components/common/EmptyState.tsx`
- Replace: `web/src/components/common/Loading.tsx`
- Modify: `web/src/components/primitives/index.ts`

- [ ] **Step 1: Create `web/src/components/primitives/ChartCard.tsx`**

```tsx
import { Card } from "./Card";
import { SectionHeader } from "./SectionHeader";

interface Props {
  title: string;
  hint?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}

export function ChartCard({ title, hint, right, children }: Props) {
  return (
    <Card className="p-4">
      <SectionHeader title={title} hint={hint} right={right} />
      {children}
    </Card>
  );
}
```

- [ ] **Step 2: Create `web/src/components/primitives/Sparkline.tsx`**

```tsx
interface Props {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
}

export function Sparkline({ data, width = 80, height = 24, color = "var(--accent-teal)" }: Props) {
  if (data.length < 2) return <svg width={width} height={height} />;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const pts = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((v - min) / span) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg width={width} height={height}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}
```

- [ ] **Step 3: Create `web/src/components/primitives/FilterBar.tsx`**

```tsx
import { cn } from "@/lib/utils";

export function FilterBar({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2 rounded-lg border border-border bg-elevated p-3", className)}>
      {children}
    </div>
  );
}
```

- [ ] **Step 4: Replace `web/src/components/common/EmptyState.tsx`**

```tsx
import { Inbox } from "lucide-react";

export function EmptyState({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-text-muted">
      <Inbox className="size-8" />
      <p className="text-sm text-text-secondary">{message}</p>
      {hint ? <p className="text-xs">{hint}</p> : null}
    </div>
  );
}
```

- [ ] **Step 5: Replace `web/src/components/common/Loading.tsx`**

```tsx
export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-10 w-full animate-pulse rounded-md bg-muted" />
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Append to `web/src/components/primitives/index.ts`**

```ts
export { ChartCard } from "./ChartCard";
export { Sparkline } from "./Sparkline";
export { FilterBar } from "./FilterBar";
```

- [ ] **Step 7: Typecheck + build**

From `web/`: `./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build`
Expected: both pass.

- [ ] **Step 8: Commit**

```bash
git add web/src/components/primitives/ web/src/components/common/
git commit -m "feat(web): ChartCard/Sparkline/FilterBar primitives + restyled EmptyState/Loading (Track C redesign / A)"
```

---

### Task 6: Shell rebuild — run-first sidebar

**Files:**
- Replace: `web/src/components/Shell.tsx`

- [ ] **Step 1: Replace `web/src/components/Shell.tsx`**

```tsx
"use client";

import { LayoutDashboard, Activity, ListOrdered, BookOpen, Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard, exact: true },
  { href: "/monitor", label: "Monitor", icon: Activity, exact: false },
  { href: "/runs", label: "Runs", icon: ListOrdered, exact: false },
  { href: "/strategies", label: "Strategies", icon: BookOpen, exact: false },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="hidden md:flex w-52 shrink-0 flex-col border-r border-border bg-surface">
        <div className="border-b border-border px-4 py-4">
          <div className="text-sm font-bold tracking-tight">ATForge</div>
          <div className="mt-0.5 text-[11px] text-text-muted">Agentic Trading Forge</div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-3">
          {NAV.map(({ href, label, icon: Icon, exact }) => {
            const active = exact ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-primary/12 font-medium text-primary"
                    : "text-text-secondary hover:bg-accent hover:text-foreground",
                )}
              >
                <Icon className="size-4 shrink-0" />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-border p-3">
          <button
            type="button"
            onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-text-secondary hover:bg-accent hover:text-foreground"
          >
            {resolvedTheme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
            {resolvedTheme === "dark" ? "Light mode" : "Dark mode"}
          </button>
        </div>
      </aside>

      <div className="md:hidden fixed inset-x-0 top-0 z-20 flex h-12 items-center justify-between border-b border-border bg-surface px-4">
        <span className="text-sm font-bold">ATForge</span>
        <div className="flex gap-1">
          {NAV.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "rounded px-2 py-1 text-xs",
                (href === "/" ? pathname === href : pathname.startsWith(href))
                  ? "bg-primary/12 text-primary"
                  : "text-text-muted",
              )}
            >
              {label}
            </Link>
          ))}
        </div>
      </div>

      <main className="flex-1 overflow-x-hidden p-6 pt-16 md:pt-6">{children}</main>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck + build**

From `web/`: `./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build`
Expected: both pass.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/Shell.tsx
git commit -m "feat(web): rebuild Shell with run-first sidebar nav (Track C redesign / A)"
```

---

## Phase B — Backend routes

All routes read-only. Test seed SQL must satisfy NOT NULL columns: `runs(run_id, started_at, status)`, `strategies(name, family, params_json, created_at)`, `backtest_runs(run_id, strategy_id, symbol, success, created_at)`, `experiments(created_at)`, `pipeline_events(run_id, ts_ms, event_type, payload)`. `runs.status` has CHECK in `('running','success','partial','failed')`.

### Task 7: `GET /stats` route

**Files:**
- Create: `src/atforge/api/schemas/stats.py`
- Create: `src/atforge/api/routes/stats.py`
- Modify: `src/atforge/api/app.py`
- Create: `tests/api/test_routes_stats.py`

- [ ] **Step 1: Write the failing test — create `tests/api/test_routes_stats.py`**

```python
"""Tests for GET /stats."""
from __future__ import annotations

import sqlite3


def test_stats_empty_db(client) -> None:
    resp = client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_runs"] == 0
    assert body["n_strategies"] == 0
    assert body["n_backtests"] == 0
    assert body["n_experiments"] == 0
    assert body["best_sharpe"] is None
    assert body["families"] == []


def test_stats_counts_and_families(client, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status) VALUES ('r1', '2026-05-16T10:00:00', 'success')"
    )
    conn.execute(
        "INSERT INTO strategies (name, family, params_json, created_at) "
        "VALUES ('S1', 'sma', '{}', '2026-05-16T10:00:00')"
    )
    conn.execute(
        "INSERT INTO strategies (name, family, params_json, created_at) "
        "VALUES ('S2', 'sma', '{\"a\":1}', '2026-05-16T10:00:00')"
    )
    conn.execute(
        "INSERT INTO backtest_runs (run_id, strategy_id, symbol, success, sharpe, created_at) "
        "VALUES ('r1', 1, 'RELIANCE', 1, 2.4, '2026-05-16T10:00:00')"
    )
    conn.commit()
    conn.close()

    resp = client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_runs"] == 1
    assert body["n_strategies"] == 2
    assert body["n_backtests"] == 1
    assert body["best_sharpe"] == 2.4
    assert body["families"] == [{"family": "sma", "count": 2}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_routes_stats.py -v`
Expected: FAIL — `/stats` route does not exist (404).

- [ ] **Step 3: Create `src/atforge/api/schemas/stats.py`**

```python
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
```

- [ ] **Step 4: Create `src/atforge/api/routes/stats.py`**

```python
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
```

- [ ] **Step 5: Register the router — modify `src/atforge/api/app.py`**

Change the import line:
```python
from atforge.api.routes import health, runs, stats, strategies
```

Add after `app.include_router(strategies.router)`:
```python
    app.include_router(stats.router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/api/test_routes_stats.py -v`
Expected: 2 tests PASS.

- [ ] **Step 7: Run full backend suite**

Run: `uv run pytest -q`
Expected: all pass (existing + 2 new).

- [ ] **Step 8: Commit**

```bash
git add src/atforge/api/schemas/stats.py src/atforge/api/routes/stats.py \
        src/atforge/api/app.py tests/api/test_routes_stats.py
git commit -m "feat(api): GET /stats route for Overview screen (Track C redesign / B)"
```

---

### Task 8: `GET /runs/{run_id}/rankings` route

**Files:**
- Modify: `src/atforge/storage/repo.py` (add `strategy_id` to `top_rankings` SELECT)
- Modify: `src/atforge/api/schemas/runs.py` (add `RankingRow`, `RunRankingsResponse`)
- Modify: `src/atforge/api/routes/runs.py`
- Create: `tests/api/test_routes_run_rankings.py`

- [ ] **Step 1: Write the failing test — create `tests/api/test_routes_run_rankings.py`**

```python
"""Tests for GET /runs/{run_id}/rankings."""
from __future__ import annotations

import sqlite3


def _seed(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status) VALUES ('r1', '2026-05-16T10:00:00', 'success')"
    )
    conn.execute(
        "INSERT INTO strategies (name, family, params_json, created_at) "
        "VALUES ('SMA_10x25', 'sma', '{}', '2026-05-16T10:00:00')"
    )
    conn.execute(
        "INSERT INTO backtest_runs "
        "(run_id, strategy_id, symbol, success, n_trades, sharpe, sortino, cagr, win_rate, "
        " max_drawdown, total_return, generation, created_at) "
        "VALUES ('r1', 1, 'RELIANCE', 1, 37, 2.41, 2.9, 0.31, 0.61, '-0.082', '0.45', 1, "
        "'2026-05-16T10:00:00')"
    )
    conn.commit()
    conn.close()


def test_rankings_unknown_run_404(client) -> None:
    resp = client.get("/runs/nope/rankings")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_rankings_empty_run(client, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status) VALUES ('r1', '2026-05-16T10:00:00', 'success')"
    )
    conn.commit()
    conn.close()
    resp = client.get("/runs/r1/rankings")
    assert resp.status_code == 200
    assert resp.json() == {"run_id": "r1", "rankings": []}


def test_rankings_returns_row(client, db_path: str) -> None:
    _seed(db_path)
    resp = client.get("/runs/r1/rankings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "r1"
    assert len(body["rankings"]) == 1
    row = body["rankings"][0]
    assert row["symbol"] == "RELIANCE"
    assert row["strategy_id"] == 1
    assert row["strategy_name"] == "SMA_10x25"
    assert row["sharpe"] == 2.41
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_routes_run_rankings.py -v`
Expected: FAIL — route does not exist.

- [ ] **Step 3: Add `strategy_id` to `top_rankings` — modify `src/atforge/storage/repo.py`**

In `top_rankings`, the outer SELECT column list — change:
```python
        SELECT backtest_id, run_id, symbol, strategy_name, family,
               generation, n_trades, total_return, final_value, max_drawdown,
               sharpe, sortino, cagr, win_rate
```
to:
```python
        SELECT backtest_id, run_id, symbol, strategy_id, strategy_name, family,
               generation, n_trades, total_return, final_value, max_drawdown,
               sharpe, sortino, cagr, win_rate
```

And in the inner SELECT, change:
```python
                b.backtest_id, b.run_id, b.symbol,
                s.name AS strategy_name, s.family,
```
to:
```python
                b.backtest_id, b.run_id, b.symbol, b.strategy_id,
                s.name AS strategy_name, s.family,
```

- [ ] **Step 4: Add schemas — modify `src/atforge/api/schemas/runs.py`**

Append at end of file:
```python
class RankingRow(BaseModel):
    backtest_id: int
    symbol: str
    strategy_id: int
    strategy_name: str
    family: str
    generation: int
    n_trades: int
    sharpe: float | None
    sortino: float | None
    cagr: float | None
    win_rate: float | None
    max_drawdown: str | None
    total_return: str | None


class RunRankingsResponse(BaseModel):
    run_id: str
    rankings: list[RankingRow]
```

- [ ] **Step 5: Add route — modify `src/atforge/api/routes/runs.py`**

Add to the imports at the top of the file:
```python
from atforge.api.schemas.runs import (
    RankingRow,
    RunListResponse,
    RunRankingsResponse,
    RunSummary,
)
from atforge.storage.repo import top_rankings
```
(Replace the existing `from atforge.api.schemas.runs import RunListResponse, RunSummary` line with the multi-line import above.)

Add this helper after `_current_generation`:
```python
def _ensure_run_exists(db: sqlite3.Connection, run_id: str) -> None:
    row = db.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": ErrorDetail(code="RUN_NOT_FOUND", message=f"run_id={run_id}").model_dump()
            },
        )
```

Add this route at the end of the file:
```python
@router.get("/{run_id}/rankings", response_model=RunRankingsResponse)
def get_run_rankings(
    run_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: sqlite3.Connection = Depends(get_db),
) -> RunRankingsResponse:
    _ensure_run_exists(db, run_id)
    rows = top_rankings(db, limit=limit, run_id=run_id)
    return RunRankingsResponse(run_id=run_id, rankings=[RankingRow(**r) for r in rows])
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/api/test_routes_run_rankings.py tests/storage/ -q`
Expected: new tests PASS; existing storage tests still PASS (the extra column is additive).

- [ ] **Step 7: Run full backend suite**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/atforge/storage/repo.py src/atforge/api/schemas/runs.py \
        src/atforge/api/routes/runs.py tests/api/test_routes_run_rankings.py
git commit -m "feat(api): GET /runs/{id}/rankings route (Track C redesign / B)"
```

---

### Task 9: `GET /runs/{run_id}/evolution` route

**Files:**
- Modify: `src/atforge/api/schemas/runs.py`
- Modify: `src/atforge/api/routes/runs.py`
- Create: `tests/api/test_routes_run_evolution.py`

- [ ] **Step 1: Write the failing test — create `tests/api/test_routes_run_evolution.py`**

```python
"""Tests for GET /runs/{run_id}/evolution."""
from __future__ import annotations

import sqlite3


def test_evolution_unknown_run_404(client) -> None:
    resp = client.get("/runs/nope/evolution")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_evolution_empty_run(client, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status) VALUES ('r1', '2026-05-16T10:00:00', 'success')"
    )
    conn.commit()
    conn.close()
    resp = client.get("/runs/r1/evolution")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"run_id": "r1", "experiments": [], "sharpe_progression": []}


def test_evolution_returns_experiment_and_progression(client, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status) VALUES ('r1', '2026-05-16T10:00:00', 'success')"
    )
    conn.execute(
        "INSERT INTO strategies (name, family, params_json, created_at) "
        "VALUES ('P', 'sma', '{}', '2026-05-16T10:00:00')"
    )
    conn.execute(
        "INSERT INTO strategies (name, family, params_json, created_at) "
        "VALUES ('C', 'sma', '{\"a\":1}', '2026-05-16T10:00:00')"
    )
    conn.execute(
        "INSERT INTO experiments "
        "(run_id, generation, parent_strategy_id, child_strategy_id, mutator, mutation_json, "
        " accepted, delta_sharpe, composite_score, reasoning, created_at) "
        "VALUES ('r1', 1, 1, 2, 'param_delta', '{}', 1, 0.18, '{}', 'accepted', "
        "'2026-05-16T10:01:00')"
    )
    conn.execute(
        "INSERT INTO backtest_runs (run_id, strategy_id, symbol, success, sharpe, generation, created_at) "
        "VALUES ('r1', 1, 'RELIANCE', 1, 2.41, 1, '2026-05-16T10:00:00')"
    )
    conn.commit()
    conn.close()

    resp = client.get("/runs/r1/evolution")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["experiments"]) == 1
    exp = body["experiments"][0]
    assert exp["mutator"] == "param_delta"
    assert exp["accepted"] == 1
    assert exp["parent_name"] == "P"
    assert exp["child_name"] == "C"
    assert body["sharpe_progression"] == [
        {"generation": 1, "best_sharpe": 2.41, "n_backtests": 1}
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_routes_run_evolution.py -v`
Expected: FAIL — route does not exist.

- [ ] **Step 3: Add schemas — modify `src/atforge/api/schemas/runs.py`**

Append at end of file:
```python
class ExperimentRow(BaseModel):
    experiment_id: int
    generation: int
    mutator: str | None
    accepted: int | None
    delta_sharpe: float | None
    reasoning: str | None
    composite_score: str | None
    mutation_json: str | None
    created_at: str | None
    parent_name: str | None
    child_name: str | None
    parent_strategy_id: int | None
    child_strategy_id: int | None


class GenerationSharpe(BaseModel):
    generation: int
    best_sharpe: float | None
    n_backtests: int


class RunEvolutionResponse(BaseModel):
    run_id: str
    experiments: list[ExperimentRow]
    sharpe_progression: list[GenerationSharpe]
```

- [ ] **Step 4: Add route — modify `src/atforge/api/routes/runs.py`**

Extend the schema import block to also import `ExperimentRow, GenerationSharpe, RunEvolutionResponse`. Extend the repo import to:
```python
from atforge.storage.repo import (
    get_best_sharpe_per_generation,
    get_experiments_for_run,
    top_rankings,
)
```

Add this route at the end of the file:
```python
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
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/api/test_routes_run_evolution.py -v`
Expected: 3 tests PASS.

- [ ] **Step 6: Run full backend suite**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/atforge/api/schemas/runs.py src/atforge/api/routes/runs.py \
        tests/api/test_routes_run_evolution.py
git commit -m "feat(api): GET /runs/{id}/evolution route (Track C redesign / B)"
```

---

### Task 10: `GET /runs/{run_id}/timeline` route

**Files:**
- Modify: `src/atforge/api/schemas/runs.py`
- Modify: `src/atforge/api/routes/runs.py`
- Create: `tests/api/test_routes_run_timeline.py`

- [ ] **Step 1: Write the failing test — create `tests/api/test_routes_run_timeline.py`**

```python
"""Tests for GET /runs/{run_id}/timeline."""
from __future__ import annotations

import sqlite3


def test_timeline_unknown_run_404(client) -> None:
    resp = client.get("/runs/nope/timeline")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_timeline_empty_run(client, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status) VALUES ('r1', '2026-05-16T10:00:00', 'success')"
    )
    conn.commit()
    conn.close()
    resp = client.get("/runs/r1/timeline")
    assert resp.status_code == 200
    assert resp.json() == {"run_id": "r1", "events": []}


def test_timeline_returns_ordered_events(client, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status) VALUES ('r1', '2026-05-16T10:00:00', 'success')"
    )
    conn.execute(
        "INSERT INTO pipeline_events (run_id, generation, ts_ms, event_type, payload) "
        "VALUES ('r1', 0, 1000, 'EvtPipelineStart', '{\"n_symbols\": 2}')"
    )
    conn.execute(
        "INSERT INTO pipeline_events (run_id, generation, ts_ms, event_type, payload) "
        "VALUES ('r1', 1, 2000, 'EvtAgentReasoning', '{\"role\": \"explorer\"}')"
    )
    conn.commit()
    conn.close()

    resp = client.get("/runs/r1/timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "r1"
    assert [e["event_type"] for e in body["events"]] == [
        "EvtPipelineStart",
        "EvtAgentReasoning",
    ]
    assert body["events"][0]["payload"] == {"n_symbols": 2}
    assert body["events"][1]["generation"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_routes_run_timeline.py -v`
Expected: FAIL — route does not exist.

- [ ] **Step 3: Add schema — modify `src/atforge/api/schemas/runs.py`**

`EventEnvelope` already exists in this file. Append at end:
```python
class TimelineResponse(BaseModel):
    run_id: str
    events: list[EventEnvelope]
```

- [ ] **Step 4: Add route — modify `src/atforge/api/routes/runs.py`**

Add `import json` to the top of the file. Extend the schema import block to also import `EventEnvelope, TimelineResponse`.

Add this route at the end of the file:
```python
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
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/api/test_routes_run_timeline.py -v`
Expected: 3 tests PASS.

- [ ] **Step 6: Run full backend suite**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/atforge/api/schemas/runs.py src/atforge/api/routes/runs.py \
        tests/api/test_routes_run_timeline.py
git commit -m "feat(api): GET /runs/{id}/timeline route (Track C redesign / B)"
```

---

## Phase C — API client extension

### Task 11: Extend types + fetch wrappers for the new routes

**Files:**
- Modify: `web/src/lib/api/types.gen.ts`
- Create: `web/src/lib/api/stats.ts`
- Modify: `web/src/lib/api/runs.ts`

- [ ] **Step 1: Add schema types — modify `web/src/lib/api/types.gen.ts`**

Inside the `schemas` object (alongside the existing entries, before its closing `};`), add:
```ts
    FamilyCount: { family: string; count: number };
    StatsResponse: {
      n_runs: number;
      n_strategies: number;
      n_backtests: number;
      n_experiments: number;
      best_sharpe: number | null;
      families: components["schemas"]["FamilyCount"][];
    };
    RankingRow: {
      backtest_id: number;
      symbol: string;
      strategy_id: number;
      strategy_name: string;
      family: string;
      generation: number;
      n_trades: number;
      sharpe: number | null;
      sortino: number | null;
      cagr: number | null;
      win_rate: number | null;
      max_drawdown: string | null;
      total_return: string | null;
    };
    RunRankingsResponse: {
      run_id: string;
      rankings: components["schemas"]["RankingRow"][];
    };
    ExperimentRow: {
      experiment_id: number;
      generation: number;
      mutator: string | null;
      accepted: number | null;
      delta_sharpe: number | null;
      reasoning: string | null;
      composite_score: string | null;
      mutation_json: string | null;
      created_at: string | null;
      parent_name: string | null;
      child_name: string | null;
      parent_strategy_id: number | null;
      child_strategy_id: number | null;
    };
    GenerationSharpe: {
      generation: number;
      best_sharpe: number | null;
      n_backtests: number;
    };
    RunEvolutionResponse: {
      run_id: string;
      experiments: components["schemas"]["ExperimentRow"][];
      sharpe_progression: components["schemas"]["GenerationSharpe"][];
    };
    TimelineResponse: {
      run_id: string;
      events: components["schemas"]["EventEnvelope"][];
    };
```

- [ ] **Step 2: Create `web/src/lib/api/stats.ts`**

```ts
import { apiGet } from "./client";
import type { components } from "./types.gen";

export type StatsResponse = components["schemas"]["StatsResponse"];

export async function fetchStats(): Promise<StatsResponse> {
  return apiGet<StatsResponse>("/stats");
}

export const statsQueryKey = ["stats"] as const;
```

- [ ] **Step 3: Extend `web/src/lib/api/runs.ts`**

Add these type exports after the existing ones:
```ts
export type RunRankingsResponse = components["schemas"]["RunRankingsResponse"];
export type RankingRow = components["schemas"]["RankingRow"];
export type RunEvolutionResponse = components["schemas"]["RunEvolutionResponse"];
export type ExperimentRow = components["schemas"]["ExperimentRow"];
export type TimelineResponse = components["schemas"]["TimelineResponse"];
```

Add these fetch functions:
```ts
export async function fetchRunRankings(runId: string): Promise<RunRankingsResponse> {
  return apiGet<RunRankingsResponse>(`/runs/${encodeURIComponent(runId)}/rankings`);
}

export async function fetchRunEvolution(runId: string): Promise<RunEvolutionResponse> {
  return apiGet<RunEvolutionResponse>(`/runs/${encodeURIComponent(runId)}/evolution`);
}

export async function fetchRunTimeline(runId: string): Promise<TimelineResponse> {
  return apiGet<TimelineResponse>(`/runs/${encodeURIComponent(runId)}/timeline`);
}
```

Replace the `runsQueryKeys` object with:
```ts
export const runsQueryKeys = {
  all: ["runs"] as const,
  detail: (runId: string) => ["runs", runId] as const,
  rankings: (runId: string) => ["runs", runId, "rankings"] as const,
  evolution: (runId: string) => ["runs", runId, "evolution"] as const,
  timeline: (runId: string) => ["runs", runId, "timeline"] as const,
};
```

- [ ] **Step 4: Typecheck**

From `web/`: `./node_modules/.bin/tsc --noEmit`
Expected: passes.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/api/
git commit -m "feat(web): API client wrappers for /stats and run rankings/evolution/timeline (Track C redesign / C)"
```

---

## Phase D — Screens

All screen pages are client components (`"use client"`) — they use TanStack Query hooks.
The `Shell` from `layout.tsx` already wraps every page.

### Task 12: Overview screen (`/`)

**Files:**
- Replace: `web/src/app/page.tsx`

The current `page.tsx` redirects to `/monitor`. It now renders the Overview dashboard.

- [ ] **Step 1: Replace `web/src/app/page.tsx`**

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { fetchStats, statsQueryKey } from "@/lib/api/stats";
import { fetchRuns, runsQueryKeys } from "@/lib/api/runs";
import { fetchStrategies, strategiesQueryKeys } from "@/lib/api/strategies";
import { Card, SectionHeader, MetricTile, StatusPill, ValueText } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

export default function OverviewPage() {
  const router = useRouter();
  const stats = useQuery({ queryKey: statsQueryKey, queryFn: fetchStats });
  const runs = useQuery({ queryKey: runsQueryKeys.all, queryFn: () => fetchRuns(5, 0) });
  const top = useQuery({
    queryKey: strategiesQueryKeys.list({ sort: "sharpe_desc", pageSize: 5 }),
    queryFn: () => fetchStrategies({ sort: "sharpe_desc", pageSize: 5 }),
  });

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-xl font-semibold">Overview</h1>

      {stats.isLoading ? (
        <Loading rows={1} />
      ) : stats.error || !stats.data ? (
        <EmptyState message="Failed to load stats" hint={(stats.error as Error)?.message} />
      ) : (
        <div className="flex flex-wrap gap-2">
          <MetricTile label="Runs" value={stats.data.n_runs} />
          <MetricTile label="Strategies" value={stats.data.n_strategies} />
          <MetricTile label="Backtests" value={stats.data.n_backtests} />
          <MetricTile label="Experiments" value={stats.data.n_experiments} />
          <MetricTile
            label="Best Sharpe"
            value={stats.data.best_sharpe != null ? stats.data.best_sharpe.toFixed(2) : "—"}
            accent
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Recent runs */}
        <Card className="p-4">
          <SectionHeader title="Recent Runs" />
          {runs.isLoading ? (
            <Loading rows={3} />
          ) : !runs.data || runs.data.runs.length === 0 ? (
            <EmptyState message="No runs yet" />
          ) : (
            <div className="flex flex-col">
              {runs.data.runs.map((r) => (
                <button
                  key={r.run_id}
                  type="button"
                  onClick={() => router.push(`/runs/${r.run_id}`)}
                  className="flex items-center justify-between border-b border-border/50 py-2 text-left last:border-0 hover:text-primary"
                >
                  <span className="tabular text-xs">{r.run_id}</span>
                  <StatusPill status={r.status} />
                </button>
              ))}
            </div>
          )}
        </Card>

        {/* Top strategies */}
        <Card className="p-4">
          <SectionHeader title="Top Strategies" />
          {top.isLoading ? (
            <Loading rows={3} />
          ) : !top.data || top.data.strategies.length === 0 ? (
            <EmptyState message="No strategies yet" />
          ) : (
            <div className="flex flex-col">
              {top.data.strategies.map((s) => (
                <button
                  key={s.strategy_id}
                  type="button"
                  onClick={() => router.push(`/strategies/${s.strategy_id}`)}
                  className="flex items-center justify-between border-b border-border/50 py-2 text-left text-xs last:border-0 hover:text-primary"
                >
                  <span>{s.name}</span>
                  <ValueText value={s.best_sharpe} kind="sharpe" />
                </button>
              ))}
            </div>
          )}
        </Card>

        {/* Family breakdown */}
        <Card className="p-4">
          <SectionHeader title="Strategy Families" />
          {stats.isLoading ? (
            <Loading rows={3} />
          ) : !stats.data || stats.data.families.length === 0 ? (
            <EmptyState message="No strategies yet" />
          ) : (
            <div className="flex flex-col">
              {stats.data.families.map((f) => (
                <button
                  key={f.family}
                  type="button"
                  onClick={() => router.push(`/strategies?family=${encodeURIComponent(f.family)}`)}
                  className="flex items-center justify-between border-b border-border/50 py-2 text-left text-xs last:border-0 hover:text-primary"
                >
                  <span>{f.family}</span>
                  <span className="tabular text-text-secondary">{f.count}</span>
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck + build**

From `web/`: `./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build`
Expected: both pass.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/page.tsx
git commit -m "feat(web): Overview screen (Track C redesign / D)"
```

---

### Task 13: Runs screen (`/runs`)

**Files:**
- Create: `web/src/app/runs/page.tsx`

- [ ] **Step 1: Create `web/src/app/runs/page.tsx`**

```tsx
"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchRuns, runsQueryKeys, type RunSummary } from "@/lib/api/runs";
import { DataTable, StatusPill, type Column } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

type SortKey = "run_id" | "started_at" | "n_backtests" | "n_failures";

function sortRuns(rows: RunSummary[], key: SortKey, dir: "asc" | "desc"): RunSummary[] {
  const sorted = [...rows].sort((a, b) => {
    const av = a[key] ?? "";
    const bv = b[key] ?? "";
    if (av < bv) return -1;
    if (av > bv) return 1;
    return 0;
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

function RunsContent() {
  const router = useRouter();
  const params = useSearchParams();
  const sortKey = (params.get("sort") as SortKey) ?? "started_at";
  const sortDir = (params.get("dir") as "asc" | "desc") ?? "desc";

  const { data, isLoading, error } = useQuery({
    queryKey: runsQueryKeys.all,
    queryFn: () => fetchRuns(100, 0),
  });

  const onSort = (key: string) => {
    const next = new URLSearchParams(params.toString());
    if (sortKey === key) {
      next.set("dir", sortDir === "asc" ? "desc" : "asc");
    } else {
      next.set("sort", key);
      next.set("dir", "desc");
    }
    router.push(`/runs?${next.toString()}`);
  };

  const columns: Column<RunSummary>[] = [
    {
      key: "run_id",
      label: "Run ID",
      sortable: true,
      render: (r) => <span className="tabular text-primary">{r.run_id}</span>,
    },
    {
      key: "started_at",
      label: "Started",
      sortable: true,
      render: (r) => (
        <span className="tabular text-text-secondary">
          {r.started_at ? r.started_at.replace("T", " ").slice(0, 16) : "—"}
        </span>
      ),
    },
    { key: "status", label: "Status", render: (r) => <StatusPill status={r.status} /> },
    {
      key: "n_backtests",
      label: "Backtests",
      align: "right",
      sortable: true,
      render: (r) => <span className="tabular">{r.n_backtests}</span>,
    },
    {
      key: "n_failures",
      label: "Failures",
      align: "right",
      sortable: true,
      render: (r) => <span className="tabular text-down">{r.n_failures}</span>,
    },
    {
      key: "current_generation",
      label: "Gen",
      align: "right",
      render: (r) => <span className="tabular">{r.current_generation ?? "—"}</span>,
    },
  ];

  if (isLoading) return <Loading rows={6} />;
  if (error) return <EmptyState message="Failed to load runs" hint={(error as Error).message} />;
  if (!data || data.runs.length === 0) return <EmptyState message="No runs yet" hint="Run the pipeline to populate this." />;

  const rows = sortRuns(data.runs, sortKey, sortDir);

  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(r) => r.run_id}
      sortKey={sortKey}
      sortDir={sortDir}
      onSort={onSort}
      onRowClick={(r) => router.push(`/runs/${r.run_id}`)}
    />
  );
}

export default function RunsPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">Runs</h1>
      <Suspense fallback={<Loading rows={6} />}>
        <RunsContent />
      </Suspense>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck + build**

From `web/`: `./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build`
Expected: both pass.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/runs/page.tsx
git commit -m "feat(web): Runs list screen (Track C redesign / D)"
```

---

### Task 14: Run Detail — page shell + header + Rankings section

**Files:**
- Create: `web/src/app/runs/[id]/page.tsx`
- Create: `web/src/app/runs/[id]/_components/RunHeader.tsx`
- Create: `web/src/app/runs/[id]/_components/RunRankings.tsx`

- [ ] **Step 1: Create `web/src/app/runs/[id]/_components/RunHeader.tsx`**

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchRun, runsQueryKeys } from "@/lib/api/runs";
import { MetricTile, StatusPill } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

export function RunHeader({ runId }: { runId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: runsQueryKeys.detail(runId),
    queryFn: () => fetchRun(runId),
  });

  if (isLoading) return <Loading rows={2} />;
  if (error || !data) return <EmptyState message="Run not found" hint={(error as Error)?.message} />;

  const dur =
    data.started_at && data.finished_at
      ? `${Math.round(
          (new Date(data.finished_at).getTime() - new Date(data.started_at).getTime()) / 1000,
        )}s`
      : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className="tabular text-xl font-semibold">{data.run_id}</span>
        <StatusPill status={data.status} />
        <span className="text-xs text-text-muted">
          {data.started_at?.replace("T", " ").slice(0, 16) ?? "—"}
          {dur ? ` · ${dur}` : ""}
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        <MetricTile label="Backtests" value={data.n_backtests} />
        <MetricTile label="Failures" value={data.n_failures} />
        <MetricTile label="Generations" value={data.current_generation ?? "—"} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `web/src/app/runs/[id]/_components/RunRankings.tsx`**

```tsx
"use client";

import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchRunRankings, runsQueryKeys, type RankingRow } from "@/lib/api/runs";
import { Card, SectionHeader, DataTable, ValueText, type Column } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

export function RunRankings({ runId }: { runId: string }) {
  const router = useRouter();
  const { data, isLoading, error } = useQuery({
    queryKey: runsQueryKeys.rankings(runId),
    queryFn: () => fetchRunRankings(runId),
  });

  const columns: Column<RankingRow>[] = [
    { key: "symbol", label: "Symbol", render: (r) => <span className="text-primary">{r.symbol}</span> },
    {
      key: "strategy_name",
      label: "Strategy",
      render: (r) => <span className="text-primary">{r.strategy_name}</span>,
    },
    { key: "generation", label: "Gen", align: "right", render: (r) => <span className="tabular">{r.generation}</span> },
    { key: "n_trades", label: "Trades", align: "right", render: (r) => <span className="tabular">{r.n_trades}</span> },
    { key: "sharpe", label: "Sharpe", align: "right", render: (r) => <ValueText value={r.sharpe} kind="sharpe" /> },
    { key: "sortino", label: "Sortino", align: "right", render: (r) => <ValueText value={r.sortino} /> },
    { key: "win_rate", label: "Win%", align: "right", render: (r) => <ValueText value={r.win_rate} kind="pct" /> },
  ];

  return (
    <Card className="p-4">
      <SectionHeader title="Rankings" hint="top backtests this run" />
      {isLoading ? (
        <Loading rows={4} />
      ) : error ? (
        <EmptyState message="Failed to load rankings" />
      ) : !data || data.rankings.length === 0 ? (
        <EmptyState message="No backtests for this run" />
      ) : (
        <DataTable
          columns={columns}
          rows={data.rankings}
          rowKey={(r) => r.backtest_id}
          onRowClick={(r) => router.push(`/strategies/${r.strategy_id}`)}
        />
      )}
    </Card>
  );
}
```

- [ ] **Step 3: Create `web/src/app/runs/[id]/page.tsx`**

```tsx
"use client";

import { useParams } from "next/navigation";
import { RunHeader } from "./_components/RunHeader";
import { RunRankings } from "./_components/RunRankings";

export default function RunDetailPage() {
  const params = useParams();
  const runId = String(params.id);

  return (
    <div className="flex flex-col gap-5">
      <RunHeader runId={runId} />
      <RunRankings runId={runId} />
    </div>
  );
}
```

- [ ] **Step 4: Typecheck + build**

From `web/`: `./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build`
Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/runs/
git commit -m "feat(web): Run Detail — header + rankings section (Track C redesign / D)"
```

---

### Task 15: Run Detail — Evolution section

**Files:**
- Create: `web/src/app/runs/[id]/_components/RunEvolution.tsx`
- Modify: `web/src/app/runs/[id]/page.tsx`

- [ ] **Step 1: Create `web/src/app/runs/[id]/_components/RunEvolution.tsx`**

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { fetchRunEvolution, runsQueryKeys, type ExperimentRow } from "@/lib/api/runs";
import { Card, SectionHeader, MetricTile, DataTable, ValueText, type Column } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

export function RunEvolution({ runId }: { runId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: runsQueryKeys.evolution(runId),
    queryFn: () => fetchRunEvolution(runId),
  });

  const columns: Column<ExperimentRow>[] = [
    { key: "generation", label: "Gen", align: "right", render: (e) => <span className="tabular">{e.generation}</span> },
    { key: "mutator", label: "Mutator", render: (e) => e.mutator ?? "—" },
    {
      key: "lineage",
      label: "Parent → Child",
      render: (e) => (
        <span className="text-text-secondary">
          {e.parent_name ?? "—"} → {e.child_name ?? "—"}
        </span>
      ),
    },
    {
      key: "delta_sharpe",
      label: "ΔSharpe",
      align: "right",
      render: (e) => <ValueText value={e.delta_sharpe} kind="pnl" />,
    },
    {
      key: "accepted",
      label: "Verdict",
      render: (e) =>
        e.mutator === "critic_veto" ? (
          <span className="text-warn">⚖ vetoed</span>
        ) : e.accepted === 1 ? (
          <span className="text-up">✓ accepted</span>
        ) : (
          <span className="text-down">✗ rejected</span>
        ),
    },
  ];

  return (
    <Card className="p-4">
      <SectionHeader title="Evolution" hint="ratchet verdicts" />
      {isLoading ? (
        <Loading rows={4} />
      ) : error ? (
        <EmptyState message="Failed to load evolution data" />
      ) : !data || data.experiments.length === 0 ? (
        <EmptyState
          message="No evolution data for this run"
          hint="Single-pass run (max_generations=1). Run with --max-generations 2+ to see mutations."
        />
      ) : (
        <RunEvolutionBody
          experiments={data.experiments}
          progression={data.sharpe_progression}
          columns={columns}
        />
      )}
    </Card>
  );
}

function RunEvolutionBody({
  experiments,
  progression,
  columns,
}: {
  experiments: ExperimentRow[];
  progression: { generation: number; best_sharpe: number | null; n_backtests: number }[];
  columns: Column<ExperimentRow>[];
}) {
  const accepted = experiments.filter((e) => e.accepted === 1 && e.mutator !== "critic_veto").length;
  const rejected = experiments.filter((e) => e.accepted === 0 && e.mutator !== "critic_veto").length;
  const vetoed = experiments.filter((e) => e.mutator === "critic_veto").length;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        <MetricTile label="Accepted" value={accepted} />
        <MetricTile label="Rejected" value={rejected} />
        <MetricTile label="Vetoed" value={vetoed} />
      </div>

      {progression.length > 0 ? (
        <div>
          <div className="mb-2 text-[11px] uppercase tracking-wide text-text-muted">
            Best Sharpe per generation
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={progression}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="generation" stroke="var(--text-muted)" fontSize={11} />
              <YAxis stroke="var(--text-muted)" fontSize={11} />
              <Tooltip
                contentStyle={{
                  background: "var(--elevated)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Bar dataKey="best_sharpe" fill="var(--accent-teal)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : null}

      <div>
        <div className="mb-2 text-[11px] uppercase tracking-wide text-text-muted">Mutation log</div>
        <DataTable columns={columns} rows={experiments} rowKey={(e) => e.experiment_id} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Mount it — modify `web/src/app/runs/[id]/page.tsx`**

Replace the file with:
```tsx
"use client";

import { useParams } from "next/navigation";
import { RunHeader } from "./_components/RunHeader";
import { RunRankings } from "./_components/RunRankings";
import { RunEvolution } from "./_components/RunEvolution";

export default function RunDetailPage() {
  const params = useParams();
  const runId = String(params.id);

  return (
    <div className="flex flex-col gap-5">
      <RunHeader runId={runId} />
      <RunRankings runId={runId} />
      <RunEvolution runId={runId} />
    </div>
  );
}
```

- [ ] **Step 3: Typecheck + build**

From `web/`: `./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build`
Expected: both pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/app/runs/
git commit -m "feat(web): Run Detail — evolution section (Track C redesign / D)"
```

---

### Task 16: Run Detail — Agent Activity timeline section

**Files:**
- Create: `web/src/app/runs/[id]/_components/RunAgentActivity.tsx`
- Modify: `web/src/app/runs/[id]/page.tsx`

- [ ] **Step 1: Create `web/src/app/runs/[id]/_components/RunAgentActivity.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchRunTimeline, runsQueryKeys } from "@/lib/api/runs";
import type { EventEnvelope } from "@/lib/api/runs";
import { Card, SectionHeader, Chip, Timeline } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

type FilterKey = "all" | "agents" | "verdicts" | "nodes";

const AGENT_TYPES = new Set(["EvtAgentReasoning", "EvtAgentToolCall", "EvtMutationProposed"]);
const VERDICT_TYPES = new Set(["EvtRatchetVerdict", "EvtCriticVerdict"]);
const NODE_TYPES = new Set(["EvtNodeStart", "EvtNodeDone"]);

function applyFilter(events: EventEnvelope[], f: FilterKey): EventEnvelope[] {
  if (f === "all") return events;
  if (f === "agents") return events.filter((e) => AGENT_TYPES.has(e.event_type));
  if (f === "verdicts") return events.filter((e) => VERDICT_TYPES.has(e.event_type));
  return events.filter((e) => NODE_TYPES.has(e.event_type));
}

const LANGFUSE_HOST = process.env.NEXT_PUBLIC_LANGFUSE_HOST ?? null;

export function RunAgentActivity({ runId }: { runId: string }) {
  const [filter, setFilter] = useState<FilterKey>("all");
  const { data, isLoading, error } = useQuery({
    queryKey: runsQueryKeys.timeline(runId),
    queryFn: () => fetchRunTimeline(runId),
  });

  const filters: { key: FilterKey; label: string }[] = [
    { key: "all", label: "All events" },
    { key: "agents", label: "Agents" },
    { key: "verdicts", label: "Verdicts" },
    { key: "nodes", label: "Nodes" },
  ];

  return (
    <Card className="p-4">
      <SectionHeader
        title="Agent Activity"
        hint="step-by-step timeline"
        right={
          <div className="flex gap-1.5">
            {filters.map((f) => (
              <Chip
                key={f.key}
                label={f.label}
                active={filter === f.key}
                onClick={() => setFilter(f.key)}
              />
            ))}
          </div>
        }
      />
      {isLoading ? (
        <Loading rows={5} />
      ) : error ? (
        <EmptyState message="Failed to load timeline" />
      ) : !data || data.events.length === 0 ? (
        <EmptyState message="No events recorded for this run" />
      ) : (
        <Timeline events={applyFilter(data.events, filter)} langfuseHost={LANGFUSE_HOST} />
      )}
    </Card>
  );
}
```

- [ ] **Step 2: Final page assembly — modify `web/src/app/runs/[id]/page.tsx`**

Replace the file with:
```tsx
"use client";

import { useParams } from "next/navigation";
import { RunHeader } from "./_components/RunHeader";
import { RunRankings } from "./_components/RunRankings";
import { RunEvolution } from "./_components/RunEvolution";
import { RunAgentActivity } from "./_components/RunAgentActivity";

export default function RunDetailPage() {
  const params = useParams();
  const runId = String(params.id);

  return (
    <div className="flex flex-col gap-5">
      <RunHeader runId={runId} />
      <RunRankings runId={runId} />
      <RunEvolution runId={runId} />
      <RunAgentActivity runId={runId} />
    </div>
  );
}
```

- [ ] **Step 3: Typecheck + build**

From `web/`: `./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build`
Expected: both pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/app/runs/
git commit -m "feat(web): Run Detail — agent activity timeline (Track C redesign / D)"
```

---

### Task 17: Monitor screen (`/monitor`)

**Files:**
- Create: `web/src/app/monitor/_components/NodeStatusGrid.tsx`
- Create: `web/src/app/monitor/_components/MonitorContent.tsx`
- Replace: `web/src/app/monitor/page.tsx`

Note: the rejected build left files under `web/src/app/monitor/_components/`. Overwrite `NodeStatusGrid.tsx`, create `MonitorContent.tsx`, and delete the now-unused old files (`RunSelector.tsx`, `GenerationProgress.tsx`, `LiveBacktestTable.tsx`, `LiveEventStream.tsx`) in Step 4.

- [ ] **Step 1: Create `web/src/app/monitor/_components/NodeStatusGrid.tsx`**

```tsx
"use client";

import { cn } from "@/lib/utils";
import { Card, SectionHeader } from "@/components/primitives";
import type { EventEnvelope } from "@/lib/api/runs";

const NODES = [
  "load_universe", "fetch_data", "detect_patterns", "run_backtest",
  "ratchet_node", "rank", "explorer_node", "exploiter_node",
  "critic_node", "aggregate_node", "loop_decision", "advance_generation",
];

type Status = "pending" | "running" | "done";

export function NodeStatusGrid({ events }: { events: EventEnvelope[] }) {
  const statuses = new Map<string, Status>(NODES.map((n) => [n, "pending"]));
  for (const e of events) {
    const name = e.payload?.node_name as string | undefined;
    if (!name) continue;
    if (e.event_type === "EvtNodeStart") statuses.set(name, "running");
    else if (e.event_type === "EvtNodeDone") statuses.set(name, "done");
  }

  return (
    <Card className="p-4">
      <SectionHeader
        title="Pipeline Nodes"
        right={
          <div className="flex gap-3 text-[10px] text-text-muted">
            <span>○ pending</span>
            <span className="text-primary">● running</span>
            <span className="text-up">✓ done</span>
          </div>
        }
      />
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
        {NODES.map((n) => {
          const s = statuses.get(n) ?? "pending";
          return (
            <div
              key={n}
              className={cn(
                "rounded-md border px-2 py-2 text-center text-[11px] font-medium",
                s === "running" && "animate-pulse border-primary/40 bg-primary/12 text-primary",
                s === "done" && "border-up/30 bg-up/12 text-up",
                s === "pending" && "border-border bg-muted text-text-muted",
              )}
            >
              {s === "running" ? "● " : s === "done" ? "✓ " : "○ "}
              {n}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
```

- [ ] **Step 2: Create `web/src/app/monitor/_components/MonitorContent.tsx`**

```tsx
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchRuns, runsQueryKeys } from "@/lib/api/runs";
import { useSSE } from "@/lib/hooks/useSSE";
import { Card, SectionHeader, Chip, Timeline } from "@/components/primitives";
import { EmptyState } from "@/components/common/EmptyState";
import { NodeStatusGrid } from "./NodeStatusGrid";

const LANGFUSE_HOST = process.env.NEXT_PUBLIC_LANGFUSE_HOST ?? null;

export function MonitorContent() {
  const router = useRouter();
  const params = useSearchParams();
  const runId = params.get("run") ?? "";

  const runs = useQuery({ queryKey: runsQueryKeys.all, queryFn: () => fetchRuns(20, 0) });
  const sse = useSSE({
    path: runId ? `/runs/${encodeURIComponent(runId)}/events` : "",
    enabled: !!runId,
  });

  return (
    <div className="flex flex-col gap-4">
      <select
        value={runId}
        onChange={(e) => router.push(`/monitor?run=${encodeURIComponent(e.target.value)}`)}
        className="w-full max-w-sm rounded-md border border-border bg-elevated px-3 py-2 text-sm"
      >
        <option value="">Select a run…</option>
        {(runs.data?.runs ?? []).map((r) => (
          <option key={r.run_id} value={r.run_id}>
            {r.run_id} — {r.status} — {r.n_backtests} backtests
          </option>
        ))}
      </select>

      {!runId ? (
        <EmptyState message="Select a run to monitor" hint="Or run the pipeline first." />
      ) : (
        <>
          <NodeStatusGrid events={sse.events} />
          <Card className="p-4">
            <SectionHeader
              title="Live Event Stream"
              right={
                <div className="flex items-center gap-2">
                  <span className={sse.isConnected ? "text-xs text-up" : "text-xs text-down"}>
                    {sse.isConnected ? "● live" : "○ disconnected"}
                  </span>
                  <Chip
                    label={sse.isPaused ? "Resume" : "Pause"}
                    onClick={() => (sse.isPaused ? sse.resume() : sse.pause())}
                  />
                  <Chip label="Clear" onClick={sse.clear} />
                </div>
              }
            />
            {sse.error ? (
              <div className="mb-2 text-xs text-down">{sse.error}</div>
            ) : null}
            {sse.events.length === 0 ? (
              <EmptyState message="Waiting for events…" />
            ) : (
              <Timeline events={sse.events} langfuseHost={LANGFUSE_HOST} />
            )}
          </Card>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Replace `web/src/app/monitor/page.tsx`**

```tsx
"use client";

import { Suspense } from "react";
import { MonitorContent } from "./_components/MonitorContent";
import { Loading } from "@/components/common/Loading";

export default function MonitorPage() {
  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-xl font-semibold">Pipeline Monitor</h1>
      <Suspense fallback={<Loading rows={4} />}>
        <MonitorContent />
      </Suspense>
    </div>
  );
}
```

- [ ] **Step 4: Delete unused old monitor components**

```bash
rm web/src/app/monitor/_components/RunSelector.tsx \
   web/src/app/monitor/_components/GenerationProgress.tsx \
   web/src/app/monitor/_components/LiveBacktestTable.tsx \
   web/src/app/monitor/_components/LiveEventStream.tsx
```

- [ ] **Step 5: Typecheck + build**

From `web/`: `./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build`
Expected: both pass.

- [ ] **Step 6: Commit**

```bash
git add web/src/app/monitor/
git commit -m "feat(web): rebuild Monitor screen on design system (Track C redesign / D)"
```

---

### Task 18: Strategies screen (`/strategies`)

**Files:**
- Replace: `web/src/app/strategies/page.tsx`
- Create: `web/src/app/strategies/_components/StrategiesContent.tsx`
- Delete: `web/src/app/strategies/_components/StrategyFilters.tsx`, `web/src/app/strategies/_components/StrategyTable.tsx` (old rejected-build files)

Family filter chips are sourced dynamically from `GET /stats` (the `families` list) — no hardcoded family names.

- [ ] **Step 1: Create `web/src/app/strategies/_components/StrategiesContent.tsx`**

```tsx
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchStats, statsQueryKey } from "@/lib/api/stats";
import {
  fetchStrategies,
  strategiesQueryKeys,
  type StrategyFilters,
  type StrategyListItem,
} from "@/lib/api/strategies";
import { FilterBar, Chip, DataTable, ValueText, type Column } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

const SORTS: { key: NonNullable<StrategyFilters["sort"]>; label: string }[] = [
  { key: "sharpe_desc", label: "Sharpe ↓" },
  { key: "sharpe_asc", label: "Sharpe ↑" },
  { key: "name_asc", label: "Name A–Z" },
  { key: "gen_desc", label: "Newest gen" },
];

export function StrategiesContent() {
  const router = useRouter();
  const params = useSearchParams();

  const family = params.get("family") ?? undefined;
  const sort = (params.get("sort") as StrategyFilters["sort"]) ?? "sharpe_desc";
  const minSharpe = params.get("min_sharpe") ? Number(params.get("min_sharpe")) : undefined;

  const filters: StrategyFilters = { family, sort, minSharpe, pageSize: 100 };

  const stats = useQuery({ queryKey: statsQueryKey, queryFn: fetchStats });
  const strategies = useQuery({
    queryKey: strategiesQueryKeys.list(filters),
    queryFn: () => fetchStrategies(filters),
  });

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params.toString());
    if (value === null) next.delete(key);
    else next.set(key, value);
    router.push(`/strategies?${next.toString()}`);
  };

  const columns: Column<StrategyListItem>[] = [
    { key: "name", label: "Name", render: (s) => <span className="text-primary">{s.name}</span> },
    { key: "family", label: "Family", render: (s) => <span className="text-text-secondary">{s.family}</span> },
    { key: "generation", label: "Gen", align: "right", render: (s) => <span className="tabular">{s.generation}</span> },
    {
      key: "parent",
      label: "Parent",
      align: "right",
      render: (s) => <span className="tabular text-text-muted">{s.parent_strategy_id ?? "—"}</span>,
    },
    { key: "best_sharpe", label: "Sharpe", align: "right", render: (s) => <ValueText value={s.best_sharpe} kind="sharpe" /> },
    { key: "best_sortino", label: "Sortino", align: "right", render: (s) => <ValueText value={s.best_sortino} /> },
    { key: "avg_win_rate", label: "Win%", align: "right", render: (s) => <ValueText value={s.avg_win_rate} kind="pct" /> },
    { key: "n_backtests", label: "Backtests", align: "right", render: (s) => <span className="tabular">{s.n_backtests}</span> },
  ];

  return (
    <div className="flex flex-col gap-4">
      <FilterBar>
        <span className="text-xs font-medium text-text-secondary">Family:</span>
        {(stats.data?.families ?? []).map((f) => (
          <Chip
            key={f.family}
            label={`${f.family} (${f.count})`}
            active={family === f.family}
            onClick={() => setParam("family", family === f.family ? null : f.family)}
          />
        ))}
        <span className="ml-3 text-xs font-medium text-text-secondary">Sort:</span>
        {SORTS.map((s) => (
          <Chip key={s.key} label={s.label} active={sort === s.key} onClick={() => setParam("sort", s.key)} />
        ))}
        <button
          type="button"
          onClick={() => router.push("/strategies")}
          className="ml-auto text-xs text-text-muted hover:text-foreground"
        >
          Clear all
        </button>
      </FilterBar>

      {strategies.isLoading ? (
        <Loading rows={6} />
      ) : strategies.error ? (
        <EmptyState message="Failed to load strategies" hint={(strategies.error as Error).message} />
      ) : !strategies.data || strategies.data.strategies.length === 0 ? (
        <EmptyState message="No strategies match these filters" hint="Adjust or clear the filters." />
      ) : (
        <DataTable
          columns={columns}
          rows={strategies.data.strategies}
          rowKey={(s) => s.strategy_id}
          onRowClick={(s) => router.push(`/strategies/${s.strategy_id}`)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Replace `web/src/app/strategies/page.tsx`**

```tsx
"use client";

import { Suspense } from "react";
import { StrategiesContent } from "./_components/StrategiesContent";
import { Loading } from "@/components/common/Loading";

export default function StrategiesPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">Strategies</h1>
      <Suspense fallback={<Loading rows={6} />}>
        <StrategiesContent />
      </Suspense>
    </div>
  );
}
```

- [ ] **Step 3: Delete old rejected-build files**

```bash
rm web/src/app/strategies/_components/StrategyFilters.tsx \
   web/src/app/strategies/_components/StrategyTable.tsx
```

- [ ] **Step 4: Typecheck + build**

From `web/`: `./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build`
Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/strategies/page.tsx web/src/app/strategies/_components/
git commit -m "feat(web): rebuild Strategies screen with dynamic family filters (Track C redesign / D)"
```

---

### Task 19: Strategy Detail screen (`/strategies/[id]`)

**Files:**
- Create: `web/src/app/strategies/[id]/_components/StrategyHeader.tsx`
- Create: `web/src/app/strategies/[id]/_components/StrategyCharts.tsx`
- Create: `web/src/app/strategies/[id]/_components/StrategyLineage.tsx`
- Create: `web/src/app/strategies/[id]/_components/StrategyBacktests.tsx`
- Replace: `web/src/app/strategies/[id]/page.tsx`
- Delete: the old rejected-build `_components` files (listed in Step 6)

Reuses the existing chart components in `web/src/components/charts/` (`EquityCurve`, `DrawdownArea`, `PriceWithSignals`) and the existing API wrappers in `web/src/lib/api/strategies.ts` (`fetchStrategy`, `fetchStrategyBacktests`, `fetchStrategyEquity`, `fetchStrategySignals`, `fetchStrategyLineage`, `fetchStrategyReasoning` + `strategiesQueryKeys`). No new backend.

- [ ] **Step 1: Create `web/src/app/strategies/[id]/_components/StrategyHeader.tsx`**

```tsx
"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { fetchStrategy, strategiesQueryKeys } from "@/lib/api/strategies";
import { Card, MetricTile } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

export function StrategyHeader({ id }: { id: number }) {
  const { data, isLoading, error } = useQuery({
    queryKey: strategiesQueryKeys.detail(id),
    queryFn: () => fetchStrategy(id),
  });

  if (isLoading) return <Loading rows={2} />;
  if (error || !data) return <EmptyState message="Strategy not found" hint={(error as Error)?.message} />;

  const m = data.metrics_summary;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/strategies" className="text-xs text-text-muted hover:text-foreground">
          ← Strategies
        </Link>
        <h1 className="text-xl font-semibold">{data.name}</h1>
        <span className="rounded-md border border-border bg-elevated px-2 py-0.5 text-xs text-text-secondary">
          {data.family}
        </span>
        {data.parent_strategy_id ? (
          <Link href={`/strategies/${data.parent_strategy_id}`} className="text-xs text-primary">
            parent #{data.parent_strategy_id}
          </Link>
        ) : (
          <span className="text-xs text-text-muted">gen-0 seed</span>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <MetricTile label="Best Sharpe" value={m.best_sharpe != null ? m.best_sharpe.toFixed(2) : "—"} accent />
        <MetricTile label="Best Sortino" value={m.best_sortino != null ? m.best_sortino.toFixed(2) : "—"} />
        <MetricTile
          label="Avg Win Rate"
          value={m.avg_win_rate != null ? `${(m.avg_win_rate * 100).toFixed(0)}%` : "—"}
        />
        <MetricTile
          label="Max Drawdown"
          value={m.max_drawdown != null ? `${(m.max_drawdown * 100).toFixed(1)}%` : "—"}
        />
        <MetricTile label="Backtests" value={m.n_backtests} />
      </div>
      <Card className="p-3">
        <pre className="overflow-x-auto text-xs text-text-secondary">
          {JSON.stringify(data.params, null, 2)}
        </pre>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Create `web/src/app/strategies/[id]/_components/StrategyCharts.tsx`**

```tsx
"use client";

import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  fetchStrategyBacktests,
  fetchStrategyEquity,
  fetchStrategySignals,
  strategiesQueryKeys,
} from "@/lib/api/strategies";
import { ApiError } from "@/lib/api/client";
import { Card, SectionHeader } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

const EquityCurve = dynamic(() => import("@/components/charts/EquityCurve").then((m) => m.EquityCurve), { ssr: false });
const DrawdownArea = dynamic(() => import("@/components/charts/DrawdownArea").then((m) => m.DrawdownArea), { ssr: false });
const PriceWithSignals = dynamic(
  () => import("@/components/charts/PriceWithSignals").then((m) => m.PriceWithSignals),
  { ssr: false },
);

export function StrategyCharts({ id }: { id: number }) {
  const router = useRouter();
  const params = useSearchParams();

  const backtests = useQuery({
    queryKey: strategiesQueryKeys.backtests(id),
    queryFn: () => fetchStrategyBacktests(id),
  });

  const symbols = [...new Set((backtests.data?.backtests ?? []).map((b) => b.symbol))];
  const runs = [...new Set((backtests.data?.backtests ?? []).map((b) => b.run_id))];
  const symbol = params.get("symbol") ?? symbols[0] ?? "";
  const run = params.get("run") ?? runs[0] ?? "";

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    next.set(key, value);
    router.push(`/strategies/${id}?${next.toString()}`);
  };

  const equity = useQuery({
    queryKey: strategiesQueryKeys.equity(id, symbol, run),
    queryFn: () => fetchStrategyEquity(id, symbol, run),
    enabled: !!symbol && !!run,
    retry: false,
  });
  const signals = useQuery({
    queryKey: strategiesQueryKeys.signals(id, symbol, run),
    queryFn: () => fetchStrategySignals(id, symbol, run),
    enabled: !!symbol && !!run,
    retry: false,
  });

  const missing = (e: unknown) => e instanceof ApiError && e.code === "SIGNAL_DATA_MISSING";

  return (
    <Card className="p-4">
      <SectionHeader
        title="Charts"
        right={
          <div className="flex gap-2">
            <select
              value={symbol}
              onChange={(e) => setParam("symbol", e.target.value)}
              className="rounded-md border border-border bg-elevated px-2 py-1 text-xs"
            >
              {symbols.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <select
              value={run}
              onChange={(e) => setParam("run", e.target.value)}
              className="rounded-md border border-border bg-elevated px-2 py-1 text-xs"
            >
              {runs.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
        }
      />
      {backtests.isLoading ? (
        <Loading rows={4} />
      ) : !symbol || !run ? (
        <EmptyState message="No backtests for this strategy" />
      ) : (
        <div className="flex flex-col gap-4">
          <div>
            <div className="mb-2 text-[11px] uppercase tracking-wide text-text-muted">Price + Signals — {symbol}</div>
            {signals.isLoading ? (
              <Loading rows={3} />
            ) : missing(signals.error) ? (
              <EmptyState message="Signal data unavailable for this symbol/run" />
            ) : signals.error || !signals.data ? (
              <EmptyState message="Failed to load chart" />
            ) : (
              <PriceWithSignals bars={signals.data.bars} markers={signals.data.signals} />
            )}
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <div className="mb-2 text-[11px] uppercase tracking-wide text-text-muted">Equity</div>
              {equity.isLoading ? (
                <Loading rows={2} />
              ) : missing(equity.error) ? (
                <EmptyState message="Equity unavailable" />
              ) : equity.error || !equity.data ? (
                <EmptyState message="Failed to load equity" />
              ) : (
                <EquityCurve data={equity.data.points.map((p) => ({ t: p.t, equity: p.equity }))} />
              )}
            </div>
            <div>
              <div className="mb-2 text-[11px] uppercase tracking-wide text-text-muted">Drawdown</div>
              {equity.isLoading ? (
                <Loading rows={2} />
              ) : equity.error || !equity.data ? (
                <EmptyState message="Drawdown unavailable" />
              ) : (
                <DrawdownArea data={equity.data.points.map((p) => ({ t: p.t, drawdown: p.drawdown }))} />
              )}
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
```

- [ ] **Step 3: Create `web/src/app/strategies/[id]/_components/StrategyLineage.tsx`**

```tsx
"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  fetchStrategyLineage,
  fetchStrategyReasoning,
  strategiesQueryKeys,
} from "@/lib/api/strategies";
import { Card, SectionHeader, ValueText } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

export function StrategyLineage({ id }: { id: number }) {
  const lineage = useQuery({
    queryKey: strategiesQueryKeys.lineage(id),
    queryFn: () => fetchStrategyLineage(id),
  });
  const reasoning = useQuery({
    queryKey: strategiesQueryKeys.reasoning(id),
    queryFn: () => fetchStrategyReasoning(id),
  });

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card className="p-4">
        <SectionHeader title="Lineage" />
        {lineage.isLoading ? (
          <Loading rows={3} />
        ) : !lineage.data ||
          (lineage.data.ancestors.length === 0 && lineage.data.descendants.length === 0) ? (
          <EmptyState message="Gen-0 seed — no lineage" />
        ) : (
          <div className="flex flex-col gap-1 font-mono text-xs">
            {[...lineage.data.ancestors,
              { strategy_id: id, name: "THIS", generation: -1, mutator: null, accepted: null, sharpe: null },
              ...lineage.data.descendants,
            ].map((n) => (
              <div key={`${n.strategy_id}-${n.name}`} className="flex items-center gap-2">
                {n.name === "THIS" ? (
                  <span className="font-semibold text-primary">#{n.strategy_id} {n.name}</span>
                ) : (
                  <Link href={`/strategies/${n.strategy_id}`} className="text-primary hover:underline">
                    #{n.strategy_id} {n.name}
                  </Link>
                )}
                {n.mutator ? <span className="text-text-muted">[{n.mutator}]</span> : null}
                {n.sharpe != null ? <ValueText value={n.sharpe} kind="sharpe" /> : null}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card className="p-4">
        <SectionHeader title="LLM Reasoning" />
        {reasoning.isLoading ? (
          <Loading rows={2} />
        ) : !reasoning.data || reasoning.data.entries.length === 0 ? (
          <EmptyState message="No reasoning recorded" hint="Likely a gen-0 seed." />
        ) : (
          <div className="flex flex-col gap-3">
            {reasoning.data.entries.map((e, i) => (
              <div key={i} className="border-l-2 border-border pl-3">
                <div className="text-[10px] text-text-muted">
                  gen {e.generation} · {e.mutator} · {e.accepted ? "accepted" : "rejected"}
                </div>
                <p className="mt-0.5 whitespace-pre-wrap text-xs text-text-secondary">{e.reasoning}</p>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Create `web/src/app/strategies/[id]/_components/StrategyBacktests.tsx`**

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchStrategyBacktests, strategiesQueryKeys } from "@/lib/api/strategies";
import type { components } from "@/lib/api/types.gen";
import { Card, SectionHeader, DataTable, ValueText, type Column } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

type BacktestRow = components["schemas"]["BacktestRow"];

export function StrategyBacktests({ id }: { id: number }) {
  const { data, isLoading, error } = useQuery({
    queryKey: strategiesQueryKeys.backtests(id),
    queryFn: () => fetchStrategyBacktests(id),
  });

  const columns: Column<BacktestRow>[] = [
    { key: "symbol", label: "Symbol", render: (b) => b.symbol },
    { key: "run_id", label: "Run", render: (b) => <span className="tabular text-text-muted">{b.run_id}</span> },
    { key: "generation", label: "Gen", align: "right", render: (b) => <span className="tabular">{b.generation}</span> },
    { key: "n_trades", label: "Trades", align: "right", render: (b) => <span className="tabular">{b.n_trades}</span> },
    { key: "sharpe", label: "Sharpe", align: "right", render: (b) => <ValueText value={b.sharpe} kind="sharpe" /> },
    { key: "sortino", label: "Sortino", align: "right", render: (b) => <ValueText value={b.sortino} /> },
    { key: "win_rate", label: "Win%", align: "right", render: (b) => <ValueText value={b.win_rate} kind="pct" /> },
  ];

  return (
    <Card className="p-4">
      <SectionHeader title="Backtest History" />
      {isLoading ? (
        <Loading rows={3} />
      ) : error ? (
        <EmptyState message="Failed to load backtests" />
      ) : !data || data.backtests.length === 0 ? (
        <EmptyState message="No backtests recorded" />
      ) : (
        <DataTable
          columns={columns}
          rows={data.backtests}
          rowKey={(b) => `${b.run_id}-${b.symbol}-${b.generation}`}
        />
      )}
    </Card>
  );
}
```

- [ ] **Step 5: Replace `web/src/app/strategies/[id]/page.tsx`**

```tsx
"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { StrategyHeader } from "./_components/StrategyHeader";
import { StrategyCharts } from "./_components/StrategyCharts";
import { StrategyLineage } from "./_components/StrategyLineage";
import { StrategyBacktests } from "./_components/StrategyBacktests";
import { Loading } from "@/components/common/Loading";

export default function StrategyDetailPage() {
  const params = useParams();
  const id = Number(params.id);

  return (
    <Suspense fallback={<Loading rows={4} />}>
      <div className="flex flex-col gap-5">
        <StrategyHeader id={id} />
        <StrategyCharts id={id} />
        <StrategyLineage id={id} />
        <StrategyBacktests id={id} />
      </div>
    </Suspense>
  );
}
```

- [ ] **Step 6: Delete old rejected-build Strategy Detail components**

```bash
rm web/src/app/strategies/[id]/_components/AggregateMetricsCard.tsx \
   web/src/app/strategies/[id]/_components/BacktestPerSymbolTable.tsx \
   web/src/app/strategies/[id]/_components/DrawdownCard.tsx \
   web/src/app/strategies/[id]/_components/EquityCurveCard.tsx \
   web/src/app/strategies/[id]/_components/ExperimentHistoryTable.tsx \
   web/src/app/strategies/[id]/_components/LineageTree.tsx \
   web/src/app/strategies/[id]/_components/PriceSignalChart.tsx \
   web/src/app/strategies/[id]/_components/ReasoningCard.tsx \
   web/src/app/strategies/[id]/_components/SymbolRunSelector.tsx
```
(The old `StrategyHeader.tsx` is overwritten by Step 1, so it is not deleted here.)

- [ ] **Step 7: Typecheck + build**

From `web/`: `./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build`
Expected: both pass.

- [ ] **Step 8: Commit**

```bash
git add web/src/app/strategies/
git commit -m "feat(web): rebuild Strategy Detail screen on design system (Track C redesign / D)"
```

---

## Phase E — Polish + verification

### Task 20: Manual verification — all screens, both themes

**Files:** none (verification only).

- [ ] **Step 1: Ensure test data exists**

A run with evolution + agent data must exist. If unsure, run:
```bash
uv run python main.py pipeline --symbols RELIANCE,TCS --lookback 1y --max-generations 2
```

- [ ] **Step 2: Boot backend**

```bash
uv run python -m atforge.api.main
```

- [ ] **Step 3: Boot frontend** (separate terminal)

```bash
cd web && export PATH="$HOME/Library/pnpm/bin:$PATH" && ./node_modules/.bin/next dev
```

- [ ] **Step 4: Walk every screen**

Open `http://localhost:3000`. Verify:
- Overview — metric tiles populate, three panels render, family chip click navigates to filtered Strategies.
- Runs — table loads, column sort works, row click opens Run Detail.
- Run Detail — header + metrics, Rankings table, Evolution chart + mutation log, Agent Activity timeline; timeline filter chips work; an agent event expands to reasoning/tool calls.
- Strategies — family chips (from /stats) filter, sort chips work, row click opens Strategy Detail.
- Strategy Detail — header, params, charts (or empty states), lineage links, reasoning, backtest table.
- Monitor — run select; if a pipeline is running, events stream; pause/resume/clear work.
- Toggle theme (sidebar) — both dark and light render correctly on every screen.

- [ ] **Step 5: No commit** — verification only. Note any defects and fix in their owning task before proceeding.

---

### Task 21: READMEs + docs update

**Files:**
- Replace: `web/README.md`
- Modify: `CLAUDE.md` (phase status line)

- [ ] **Step 1: Replace `web/README.md`**

```markdown
# ATForge Web Dashboard (Track C)

Read-only Next.js dashboard for ATForge. Six screens, run-first navigation:
Overview, Monitor (live SSE), Runs, Run Detail, Strategies, Strategy Detail.

## Run

Backend (from repo root):
```bash
uv run python -m atforge.api.main          # serves http://localhost:8000
```

Frontend (from `web/`):
```bash
export PATH="$HOME/Library/pnpm/bin:$PATH"
./node_modules/.bin/next dev                # serves http://localhost:3000
```

## Build / typecheck

```bash
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/next build
```

## Environment

- `NEXT_PUBLIC_API_URL` — backend base URL (default `http://localhost:8000`).
- `NEXT_PUBLIC_LANGFUSE_HOST` — optional; enables "open full trace in Langfuse" links on agent timeline events.

## Architecture

`web/` is fully deletable without affecting the pipeline. Design system lives in
`src/components/primitives/`; screens compose primitives only. See
`docs/superpowers/specs/2026-05-16-track-c-frontend-redesign.md`.
```

- [ ] **Step 2: Update `CLAUDE.md` phase status**

Find the Track C / Phase status area and add a line noting the redesign:
```
- **Track C redesign** ✅ complete — run-first dashboard: Overview/Monitor/Runs/Run Detail/Strategies/Strategy Detail, Refined Quant design system, 4 new read-only API routes (/stats, /runs/{id}/rankings|evolution|timeline)
```

- [ ] **Step 3: Full verification**

```bash
uv run pytest -q
cd web && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build
```
Expected: backend suite green; frontend typecheck + build clean.

- [ ] **Step 4: Commit**

```bash
git add web/README.md CLAUDE.md
git commit -m "docs(web): READMEs + phase status for Track C redesign (Track C redesign / E)"
```

---

## Self-review notes

- **Spec coverage:** All six screens (§6) → Tasks 12–19; design system (§5) → Tasks 1–6; backend routes (§7) → Tasks 7–10; API client (§8 data flow) → Task 11; error/empty/loading states → built into every screen task + Task 20; testing (§10) → backend pytest in Tasks 7–10, manual walk in Task 20.
- **Backend tests are TDD** (failing test first). Frontend tasks use typecheck + `next build` as the correctness gate — appropriate for UI composition with no unit-test harness in this project.
- **Playwright e2e** from the spec is intentionally reduced to the manual screen walk in Task 20: the project has no Playwright setup and adding one is disproportionate for a local-only tool. If automated e2e is wanted later it is a clean follow-up task.
- **Extensibility:** new screens compose `components/primitives/`; Run Detail sections are independent components; backend routes follow the existing route/schema pattern.

