"use client";

import { cn } from "@/lib/utils";
import type { EventEnvelope } from "@/lib/api/runs";

const PIPELINE_NODES = [
  { key: "load_universe",     label: "Load Universe",      phase: "setup" },
  { key: "fetch_data",        label: "Fetch Data",         phase: "setup" },
  { key: "detect_patterns",   label: "Detect Patterns",    phase: "setup" },
  { key: "run_backtest",      label: "Run Backtests",      phase: "eval" },
  { key: "ratchet_node",      label: "Ratchet",            phase: "eval" },
  { key: "rank",              label: "Rank",               phase: "eval" },
  { key: "explorer_node",     label: "Explorer",           phase: "agents" },
  { key: "exploiter_node",    label: "Exploiter",          phase: "agents" },
  { key: "critic_node",       label: "Critic",             phase: "agents" },
  { key: "aggregate_node",    label: "Aggregate",          phase: "agents" },
  { key: "loop_decision",     label: "Loop?",              phase: "loop" },
  { key: "advance_generation",label: "Next Gen",           phase: "loop" },
];

type Status = "pending" | "running" | "done";

const STATUS_STYLE: Record<Status, string> = {
  pending: "bg-muted text-muted-foreground border border-border",
  running: "bg-blue-500/20 text-blue-600 dark:text-blue-400 border border-blue-500 animate-pulse",
  done:    "bg-green-500/20 text-green-700 dark:text-green-400 border border-green-500",
};

const STATUS_ICON: Record<Status, string> = {
  pending: "○",
  running: "●",
  done:    "✓",
};

function deriveStatuses(events: EventEnvelope[]): Map<string, Status> {
  const m = new Map<string, Status>(PIPELINE_NODES.map((n) => [n.key, "pending"]));
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
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-semibold">Pipeline Nodes</span>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1"><span className="text-muted-foreground">○</span> Pending</span>
          <span className="flex items-center gap-1"><span className="text-blue-500">●</span> Running</span>
          <span className="flex items-center gap-1"><span className="text-green-500">✓</span> Done</span>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
        {PIPELINE_NODES.map((n) => {
          const s = statuses.get(n.key) ?? "pending";
          return (
            <div
              key={n.key}
              className={cn(
                "flex flex-col items-center gap-1 rounded-md px-2 py-2 text-center text-xs font-medium transition-all",
                STATUS_STYLE[s],
              )}
            >
              <span className="text-base leading-none">{STATUS_ICON[s]}</span>
              <span className="leading-tight">{n.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
