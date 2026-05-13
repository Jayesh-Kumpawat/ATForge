"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchStrategyReasoning, strategiesQueryKeys } from "@/lib/api/strategies";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

export function ReasoningCard({ id }: { id: number }) {
  const { data, isLoading } = useQuery({
    queryKey: strategiesQueryKeys.reasoning(id),
    queryFn: () => fetchStrategyReasoning(id),
  });

  if (isLoading) return <Loading rows={2} />;
  if (!data || data.entries.length === 0)
    return <EmptyState message="No LLM reasoning recorded" hint="Likely a gen-0 seed strategy." />;

  return (
    <div className="rounded-lg border p-4 flex flex-col gap-3">
      <div className="text-sm font-medium">LLM Reasoning</div>
      {data.entries.map((e, i) => (
        <div key={i} className="border-l-2 border-muted pl-3 flex flex-col gap-1">
          <div className="text-xs text-muted-foreground">
            run: {e.run_id.slice(0, 8)}… · gen: {e.generation} · mutator: {e.mutator} · {e.accepted ? "accepted" : "rejected"} · ΔSharpe: {e.delta_sharpe?.toFixed(2) ?? "—"}
          </div>
          <p className="text-sm whitespace-pre-wrap">{e.reasoning}</p>
        </div>
      ))}
    </div>
  );
}
