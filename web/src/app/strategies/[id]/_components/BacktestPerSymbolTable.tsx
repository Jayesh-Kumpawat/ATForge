"use client";

import { useQuery } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { fetchStrategyBacktests, strategiesQueryKeys } from "@/lib/api/strategies";
import { SHARPE_COLOR } from "@/lib/constants";

export function BacktestPerSymbolTable({ id }: { id: number }) {
  const { data, isLoading } = useQuery({
    queryKey: strategiesQueryKeys.backtests(id),
    queryFn: () => fetchStrategyBacktests(id),
  });

  if (isLoading) return <Loading />;
  if (!data || data.backtests.length === 0) return <EmptyState message="No backtests recorded for this strategy" />;

  return (
    <div className="rounded-lg border overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Symbol</TableHead>
            <TableHead>Run</TableHead>
            <TableHead className="text-right">Gen</TableHead>
            <TableHead className="text-right">Trades</TableHead>
            <TableHead className="text-right">Sharpe</TableHead>
            <TableHead className="text-right">Sortino</TableHead>
            <TableHead className="text-right">WR</TableHead>
            <TableHead className="text-right">Max DD</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.backtests.map((b, i) => (
            <TableRow key={`${b.run_id}-${b.symbol}-${i}`}>
              <TableCell className="font-medium">{b.symbol}</TableCell>
              <TableCell className="font-mono text-xs">{b.run_id.slice(0, 8)}…</TableCell>
              <TableCell className="text-right">{b.generation}</TableCell>
              <TableCell className="text-right">{b.n_trades}</TableCell>
              <TableCell className={`text-right ${SHARPE_COLOR(b.sharpe)}`}>{b.sharpe?.toFixed(2) ?? "—"}</TableCell>
              <TableCell className="text-right">{b.sortino?.toFixed(2) ?? "—"}</TableCell>
              <TableCell className="text-right">{b.win_rate ? `${(b.win_rate * 100).toFixed(0)}%` : "—"}</TableCell>
              <TableCell className="text-right text-red-500">{b.max_drawdown ? `${(b.max_drawdown * 100).toFixed(2)}%` : "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
