"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchStrategyEquity, strategiesQueryKeys } from "@/lib/api/strategies";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { ApiError } from "@/lib/api/client";

const DrawdownArea = dynamic(() => import("@/components/charts/DrawdownArea").then((m) => m.DrawdownArea), { ssr: false });

export function DrawdownCard({ id }: { id: number }) {
  const params = useSearchParams();
  const symbol = params.get("symbol") ?? "";
  const run = params.get("run") ?? "";

  const { data, isLoading, error } = useQuery({
    queryKey: strategiesQueryKeys.equity(id, symbol, run),
    queryFn: () => fetchStrategyEquity(id, symbol, run),
    enabled: !!symbol && !!run,
    retry: false,
  });

  if (!symbol || !run) return <EmptyState message="Select symbol + run for drawdown" />;
  if (isLoading) return <Loading />;
  if (error instanceof ApiError && error.code === "SIGNAL_DATA_MISSING")
    return <EmptyState message="Drawdown unavailable" />;
  if (error || !data) return <EmptyState message="Failed to load drawdown" />;

  return (
    <div className="rounded-lg border p-4">
      <div className="text-sm font-medium mb-2">Drawdown — {symbol}</div>
      <DrawdownArea data={data.points.map((p) => ({ t: p.t, drawdown: p.drawdown }))} />
    </div>
  );
}
