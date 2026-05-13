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
