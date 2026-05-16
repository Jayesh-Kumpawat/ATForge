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
