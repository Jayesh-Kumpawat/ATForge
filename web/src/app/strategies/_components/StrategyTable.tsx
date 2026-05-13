"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { fetchStrategies, strategiesQueryKeys, type StrategyFilters as Filters } from "@/lib/api/strategies";
import { SHARPE_COLOR } from "@/lib/constants";

export function StrategyTable() {
  const router = useRouter();
  const params = useSearchParams();

  const filters: Filters = {
    family: params.get("family") ?? undefined,
    minSharpe: params.get("min_sharpe") ? Number(params.get("min_sharpe")) : undefined,
    generation: params.get("generation") ? Number(params.get("generation")) : undefined,
    sort: (params.get("sort") as Filters["sort"]) ?? "sharpe_desc",
    page: params.get("page") ? Number(params.get("page")) : 1,
    pageSize: 50,
  };

  const { data, isLoading, error } = useQuery({
    queryKey: strategiesQueryKeys.list(filters),
    queryFn: () => fetchStrategies(filters),
  });

  if (isLoading) return <Loading rows={5} />;
  if (error) return <EmptyState message="Failed to load strategies" hint={(error as Error).message} />;
  if (!data || data.strategies.length === 0)
    return <EmptyState message="No strategies match these filters." hint="Adjust filters or clear all." />;

  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));

  return (
    <div className="flex flex-col gap-2">
      <div className="text-sm text-muted-foreground">
        Total: {data.total} strategies — Page {data.page} of {totalPages}
      </div>

      <div className="rounded-lg border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Family</TableHead>
              <TableHead className="text-right">Gen</TableHead>
              <TableHead className="text-right">Parent</TableHead>
              <TableHead className="text-right">Sharpe</TableHead>
              <TableHead className="text-right">Sortino</TableHead>
              <TableHead className="text-right">Win Rate</TableHead>
              <TableHead className="text-right">N Backtests</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.strategies.map((s) => (
              <TableRow
                key={s.strategy_id}
                className="cursor-pointer hover:bg-accent/40"
                onClick={() => router.push(`/strategies/${s.strategy_id}`)}
              >
                <TableCell className="font-medium">{s.name}</TableCell>
                <TableCell>{s.family}</TableCell>
                <TableCell className="text-right">{s.generation}</TableCell>
                <TableCell className="text-right">
                  {s.parent_strategy_id ? (
                    <Link
                      onClick={(e) => e.stopPropagation()}
                      className="underline text-blue-500"
                      href={`/strategies/${s.parent_strategy_id}`}
                    >
                      #{s.parent_strategy_id}
                    </Link>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className={`text-right ${SHARPE_COLOR(s.best_sharpe)}`}>
                  {s.best_sharpe?.toFixed(2) ?? "—"}
                </TableCell>
                <TableCell className="text-right">{s.best_sortino?.toFixed(2) ?? "—"}</TableCell>
                <TableCell className="text-right">
                  {s.avg_win_rate ? `${(s.avg_win_rate * 100).toFixed(0)}%` : "—"}
                </TableCell>
                <TableCell className="text-right">{s.n_backtests}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="flex justify-end gap-2 items-center text-sm">
        <Button
          variant="ghost"
          size="sm"
          disabled={data.page <= 1}
          onClick={() => {
            const next = new URLSearchParams(params.toString());
            next.set("page", String(data.page - 1));
            router.push(`/strategies?${next.toString()}`);
          }}
        >
          ‹ Prev
        </Button>
        <span>Page {data.page} of {totalPages}</span>
        <Button
          variant="ghost"
          size="sm"
          disabled={data.page >= totalPages}
          onClick={() => {
            const next = new URLSearchParams(params.toString());
            next.set("page", String(data.page + 1));
            router.push(`/strategies?${next.toString()}`);
          }}
        >
          Next ›
        </Button>
      </div>
    </div>
  );
}
