"use client";

import { useQuery } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { fetchStrategyReasoning, strategiesQueryKeys } from "@/lib/api/strategies";

export function ExperimentHistoryTable({ id }: { id: number }) {
  const { data, isLoading } = useQuery({
    queryKey: strategiesQueryKeys.reasoning(id),
    queryFn: () => fetchStrategyReasoning(id),
  });

  if (isLoading) return <Loading />;
  if (!data || data.entries.length === 0)
    return <EmptyState message="No experiment history" />;

  return (
    <div className="rounded-lg border overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Run</TableHead>
            <TableHead className="text-right">Gen</TableHead>
            <TableHead>Mutator</TableHead>
            <TableHead>Verdict</TableHead>
            <TableHead className="text-right">ΔSharpe</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.entries.map((e, i) => (
            <TableRow key={i}>
              <TableCell className="font-mono text-xs">{e.run_id.slice(0, 8)}…</TableCell>
              <TableCell className="text-right">{e.generation}</TableCell>
              <TableCell>{e.mutator}</TableCell>
              <TableCell className={e.accepted ? "text-green-500" : "text-red-500"}>
                {e.accepted ? "✓ accepted" : "✗ rejected"}
              </TableCell>
              <TableCell className="text-right">{e.delta_sharpe?.toFixed(2) ?? "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
