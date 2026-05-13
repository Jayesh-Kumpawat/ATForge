"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchStrategySignals, strategiesQueryKeys } from "@/lib/api/strategies";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { ApiError } from "@/lib/api/client";

const PriceWithSignals = dynamic(
  () => import("@/components/charts/PriceWithSignals").then((m) => m.PriceWithSignals),
  { ssr: false },
);

export function PriceSignalChart({ id }: { id: number }) {
  const params = useSearchParams();
  const symbol = params.get("symbol") ?? "";
  const run = params.get("run") ?? "";

  const { data, isLoading, error } = useQuery({
    queryKey: strategiesQueryKeys.signals(id, symbol, run),
    queryFn: () => fetchStrategySignals(id, symbol, run),
    enabled: !!symbol && !!run,
    retry: false,
  });

  if (!symbol || !run) return <EmptyState message="Select symbol + run for chart" />;
  if (isLoading) return <Loading />;
  if (error instanceof ApiError && error.code === "SIGNAL_DATA_MISSING")
    return <EmptyState message="Signal data unavailable for this strategy/run combination" />;
  if (error || !data) return <EmptyState message="Failed to load chart" />;

  return (
    <div className="rounded-lg border p-4">
      <div className="text-sm font-medium mb-2">Price + Signals — {symbol}</div>
      <PriceWithSignals bars={data.bars} markers={data.signals} />
    </div>
  );
}
