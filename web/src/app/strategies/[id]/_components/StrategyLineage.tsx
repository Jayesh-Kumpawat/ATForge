"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  fetchStrategyLineage,
  fetchStrategyReasoning,
  strategiesQueryKeys,
} from "@/lib/api/strategies";
import { Card, SectionHeader, ValueText } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

export function StrategyLineage({ id }: { id: number }) {
  const lineage = useQuery({
    queryKey: strategiesQueryKeys.lineage(id),
    queryFn: () => fetchStrategyLineage(id),
  });
  const reasoning = useQuery({
    queryKey: strategiesQueryKeys.reasoning(id),
    queryFn: () => fetchStrategyReasoning(id),
  });

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card className="p-4">
        <SectionHeader title="Lineage" />
        {lineage.isLoading ? (
          <Loading rows={3} />
        ) : !lineage.data ||
          (lineage.data.ancestors.length === 0 && lineage.data.descendants.length === 0) ? (
          <EmptyState message="Gen-0 seed — no lineage" />
        ) : (
          <div className="flex flex-col gap-1 font-mono text-xs">
            {[...lineage.data.ancestors,
              { strategy_id: id, name: "THIS", generation: -1, mutator: null, accepted: null, sharpe: null },
              ...lineage.data.descendants,
            ].map((n) => (
              <div key={`${n.strategy_id}-${n.name}`} className="flex items-center gap-2">
                {n.name === "THIS" ? (
                  <span className="font-semibold text-primary">#{n.strategy_id} {n.name}</span>
                ) : (
                  <Link href={`/strategies/${n.strategy_id}`} className="text-primary hover:underline">
                    #{n.strategy_id} {n.name}
                  </Link>
                )}
                {n.mutator ? <span className="text-text-muted">[{n.mutator}]</span> : null}
                {n.sharpe != null ? <ValueText value={n.sharpe} kind="sharpe" /> : null}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card className="p-4">
        <SectionHeader title="LLM Reasoning" />
        {reasoning.isLoading ? (
          <Loading rows={2} />
        ) : !reasoning.data || reasoning.data.entries.length === 0 ? (
          <EmptyState message="No reasoning recorded" hint="Likely a gen-0 seed." />
        ) : (
          <div className="flex flex-col gap-3">
            {reasoning.data.entries.map((e, i) => (
              <div key={i} className="border-l-2 border-border pl-3">
                <div className="text-[10px] text-text-muted">
                  gen {e.generation} · {e.mutator} · {e.accepted ? "accepted" : "rejected"}
                </div>
                <p className="mt-0.5 whitespace-pre-wrap text-xs text-text-secondary">{e.reasoning}</p>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
