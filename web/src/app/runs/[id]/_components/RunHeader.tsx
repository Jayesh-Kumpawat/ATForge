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
