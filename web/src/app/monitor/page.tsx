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
