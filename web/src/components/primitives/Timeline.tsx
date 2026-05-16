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
