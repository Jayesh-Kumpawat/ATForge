"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { fetchStrategy, strategiesQueryKeys } from "@/lib/api/strategies";
import { Card, MetricTile } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

export function StrategyHeader({ id }: { id: number }) {
  const { data, isLoading, error } = useQuery({
    queryKey: strategiesQueryKeys.detail(id),
    queryFn: () => fetchStrategy(id),
  });

  if (isLoading) return <Loading rows={2} />;
  if (error || !data) return <EmptyState message="Strategy not found" hint={(error as Error)?.message} />;

  const m = data.metrics_summary;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/strategies" className="text-xs text-text-muted hover:text-foreground">
          ← Strategies
        </Link>
        <h1 className="text-xl font-semibold">{data.name}</h1>
        <span className="rounded-md border border-border bg-elevated px-2 py-0.5 text-xs text-text-secondary">
          {data.family}
        </span>
        {data.parent_strategy_id ? (
          <Link href={`/strategies/${data.parent_strategy_id}`} className="text-xs text-primary">
            parent #{data.parent_strategy_id}
          </Link>
        ) : (
          <span className="text-xs text-text-muted">gen-0 seed</span>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <MetricTile label="Best Sharpe" value={m.best_sharpe != null ? m.best_sharpe.toFixed(2) : "—"} accent />
        <MetricTile label="Best Sortino" value={m.best_sortino != null ? m.best_sortino.toFixed(2) : "—"} />
        <MetricTile
          label="Avg Win Rate"
          value={m.avg_win_rate != null ? `${(m.avg_win_rate * 100).toFixed(0)}%` : "—"}
        />
        <MetricTile
          label="Max Drawdown"
          value={m.max_drawdown != null ? `${(m.max_drawdown * 100).toFixed(1)}%` : "—"}
        />
        <MetricTile label="Backtests" value={m.n_backtests} />
      </div>
      <Card className="p-3">
        <pre className="overflow-x-auto text-xs text-text-secondary">
          {JSON.stringify(data.params, null, 2)}
        </pre>
      </Card>
    </div>
  );
}
