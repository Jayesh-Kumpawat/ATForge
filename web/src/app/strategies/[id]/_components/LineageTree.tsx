"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { fetchStrategyLineage, strategiesQueryKeys, type LineageResponse } from "@/lib/api/strategies";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { SHARPE_COLOR } from "@/lib/constants";

function Node({ node, marker }: { node: LineageResponse["ancestors"][number]; marker?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground w-12">Gen {node.generation}:</span>
      <Link href={`/strategies/${node.strategy_id}`} className="underline">
        #{node.strategy_id} {node.name}
      </Link>
      {node.mutator ? <span className="text-xs text-muted-foreground">[{node.mutator}]</span> : null}
      {node.sharpe !== null && node.sharpe !== undefined ? (
        <span className={`text-xs ${SHARPE_COLOR(node.sharpe)}`}>sharpe: {node.sharpe.toFixed(2)}</span>
      ) : null}
      {marker ? <span className="text-xs font-semibold text-blue-500">({marker})</span> : null}
    </div>
  );
}

export function LineageTree({ id }: { id: number }) {
  const { data, isLoading } = useQuery({
    queryKey: strategiesQueryKeys.lineage(id),
    queryFn: () => fetchStrategyLineage(id),
  });

  if (isLoading) return <Loading rows={3} />;
  if (!data) return <EmptyState message="No lineage data" />;

  const noParents = data.ancestors.length === 0;
  const noChildren = data.descendants.length === 0;

  return (
    <div className="rounded-lg border p-4 flex flex-col gap-2">
      <div className="text-sm font-medium mb-2">Lineage</div>
      {noParents && noChildren ? (
        <EmptyState message="Gen-0 seed strategy (no parent)" />
      ) : (
        <div className="flex flex-col gap-1">
          {data.ancestors.map((a) => <Node key={a.strategy_id} node={a} />)}
          <Node node={{ strategy_id: id, name: "THIS", generation: data.ancestors.length, mutator: null, accepted: null, sharpe: null }} marker="this" />
          {data.descendants.map((d) => <Node key={d.strategy_id} node={d} />)}
        </div>
      )}
    </div>
  );
}
