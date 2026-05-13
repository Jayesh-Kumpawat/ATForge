"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { fetchStrategy, strategiesQueryKeys } from "@/lib/api/strategies";
import { Loading } from "@/components/common/Loading";
import { Badge } from "@/components/ui/badge";

export function StrategyHeader({ id }: { id: number }) {
  const { data, isLoading, error } = useQuery({
    queryKey: strategiesQueryKeys.detail(id),
    queryFn: () => fetchStrategy(id),
  });

  if (isLoading) return <Loading rows={2} />;
  if (error || !data) return <div className="text-red-500">{(error as Error)?.message ?? "Strategy not found"}</div>;

  return (
    <div className="flex flex-col gap-2 rounded-lg border p-4">
      <div className="flex items-center gap-3">
        <Link href="/strategies" className="text-sm text-muted-foreground underline">← Library</Link>
        <h1 className="text-2xl font-semibold">{data.name}</h1>
        <Badge variant="outline">{data.family}</Badge>
      </div>
      <div className="text-sm text-muted-foreground flex flex-wrap gap-x-4">
        <span>#{data.strategy_id}</span>
        <span>Family: {data.family}</span>
        {data.parent_strategy_id ? (
          <span>
            Parent: <Link href={`/strategies/${data.parent_strategy_id}`} className="underline">
              #{data.parent_strategy_id}
            </Link>
          </span>
        ) : (
          <span>Parent: — (gen-0 seed)</span>
        )}
      </div>
      <pre className="text-xs bg-muted rounded p-2 overflow-x-auto">{JSON.stringify(data.params, null, 2)}</pre>
    </div>
  );
}
