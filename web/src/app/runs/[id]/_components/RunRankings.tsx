"use client";

import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchRunRankings, runsQueryKeys, type RankingRow } from "@/lib/api/runs";
import { Card, SectionHeader, DataTable, ValueText, type Column } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

export function RunRankings({ runId }: { runId: string }) {
  const router = useRouter();
  const { data, isLoading, error } = useQuery({
    queryKey: runsQueryKeys.rankings(runId),
    queryFn: () => fetchRunRankings(runId),
  });

  const columns: Column<RankingRow>[] = [
    { key: "symbol", label: "Symbol", render: (r) => <span className="text-primary">{r.symbol}</span> },
    {
      key: "strategy_name",
      label: "Strategy",
      render: (r) => <span className="text-primary">{r.strategy_name}</span>,
    },
    { key: "generation", label: "Gen", align: "right", render: (r) => <span className="tabular">{r.generation}</span> },
    { key: "n_trades", label: "Trades", align: "right", render: (r) => <span className="tabular">{r.n_trades}</span> },
    { key: "sharpe", label: "Sharpe", align: "right", render: (r) => <ValueText value={r.sharpe} kind="sharpe" /> },
    { key: "sortino", label: "Sortino", align: "right", render: (r) => <ValueText value={r.sortino} /> },
    { key: "win_rate", label: "Win%", align: "right", render: (r) => <ValueText value={r.win_rate} kind="pct" /> },
  ];

  return (
    <Card className="p-4">
      <SectionHeader title="Rankings" hint="top backtests this run" />
      {isLoading ? (
        <Loading rows={4} />
      ) : error ? (
        <EmptyState message="Failed to load rankings" />
      ) : !data || data.rankings.length === 0 ? (
        <EmptyState message="No backtests for this run" />
      ) : (
        <DataTable
          columns={columns}
          rows={data.rankings}
          rowKey={(r) => r.backtest_id}
          onRowClick={(r) => router.push(`/strategies/${r.strategy_id}`)}
        />
      )}
    </Card>
  );
}
