"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchStrategy, strategiesQueryKeys } from "@/lib/api/strategies";
import { MetricPill } from "@/components/common/MetricPill";
import { SHARPE_COLOR } from "@/lib/constants";
import { Loading } from "@/components/common/Loading";

export function AggregateMetricsCard({ id }: { id: number }) {
  const { data, isLoading } = useQuery({
    queryKey: strategiesQueryKeys.detail(id),
    queryFn: () => fetchStrategy(id),
  });

  if (isLoading) return <Loading rows={1} />;
  if (!data) return null;

  const m = data.metrics_summary;
  return (
    <div className="flex flex-wrap gap-3">
      <MetricPill label="Best Sharpe" value={m.best_sharpe?.toFixed(2) ?? "—"} valueClassName={SHARPE_COLOR(m.best_sharpe)} />
      <MetricPill label="Best Sortino" value={m.best_sortino?.toFixed(2) ?? "—"} />
      <MetricPill label="Avg Win Rate" value={m.avg_win_rate ? `${(m.avg_win_rate * 100).toFixed(0)}%` : "—"} />
      <MetricPill label="Max Drawdown" value={m.max_drawdown ? `${(m.max_drawdown * 100).toFixed(2)}%` : "—"} />
      <MetricPill label="N Backtests" value={m.n_backtests} />
    </div>
  );
}
