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
