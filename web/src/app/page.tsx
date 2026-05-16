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
