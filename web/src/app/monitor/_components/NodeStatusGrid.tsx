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
