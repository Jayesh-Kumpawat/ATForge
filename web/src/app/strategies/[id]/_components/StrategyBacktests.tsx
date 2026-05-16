"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchStrategyBacktests, strategiesQueryKeys } from "@/lib/api/strategies";
import type { components } from "@/lib/api/types.gen";
import { Card, SectionHeader, DataTable, ValueText, type Column } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

type BacktestRow = components["schemas"]["BacktestRow"];

export function StrategyBacktests({ id }: { id: number }) {
  const { data, isLoading, error } = useQuery({
    queryKey: strategiesQueryKeys.backtests(id),
    queryFn: () => fetchStrategyBacktests(id),
  });

  const columns: Column<BacktestRow>[] = [
    { key: "symbol", label: "Symbol", render: (b) => b.symbol },
    { key: "run_id", label: "Run", render: (b) => <span className="tabular text-text-muted">{b.run_id}</span> },
    { key: "generation", label: "Gen", align: "right", render: (b) => <span className="tabular">{b.generation}</span> },
    { key: "n_trades", label: "Trades", align: "right", render: (b) => <span className="tabular">{b.n_trades}</span> },
    { key: "sharpe", label: "Sharpe", align: "right", render: (b) => <ValueText value={b.sharpe} kind="sharpe" /> },
    { key: "sortino", label: "Sortino", align: "right", render: (b) => <ValueText value={b.sortino} /> },
    { key: "win_rate", label: "Win%", align: "right", render: (b) => <ValueText value={b.win_rate} kind="pct" /> },
  ];

  return (
    <Card className="p-4">
      <SectionHeader title="Backtest History" />
      {isLoading ? (
        <Loading rows={3} />
      ) : error ? (
        <EmptyState message="Failed to load backtests" />
      ) : !data || data.backtests.length === 0 ? (
        <EmptyState message="No backtests recorded" />
      ) : (
        <DataTable
          columns={columns}
          rows={data.backtests}
          rowKey={(b) => `${b.run_id}-${b.symbol}-${b.generation}`}
        />
      )}
    </Card>
  );
}
