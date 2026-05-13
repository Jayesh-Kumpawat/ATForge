"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchStrategyEquity, strategiesQueryKeys } from "@/lib/api/strategies";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";
import { ApiError } from "@/lib/api/client";

const EquityCurve = dynamic(() => import("@/components/charts/EquityCurve").then((m) => m.EquityCurve), { ssr: false });

export function EquityCurveCard({ id }: { id: number }) {
  const params = useSearchParams();
  const symbol = params.get("symbol") ?? "";
  const run = params.get("run") ?? "";

  const { data, isLoading, error } = useQuery({
    queryKey: strategiesQueryKeys.equity(id, symbol, run),
    queryFn: () => fetchStrategyEquity(id, symbol, run),
    enabled: !!symbol && !!run,
    retry: false,
  });

  if (!symbol || !run) return <EmptyState message="Select a symbol and run to view equity" />;
  if (isLoading) return <Loading />;
  if (error instanceof ApiError && error.code === "SIGNAL_DATA_MISSING")
    return <EmptyState message="Equity unavailable" hint="Signal/OHLCV cache missing for this symbol/run" />;
  if (error || !data) return <EmptyState message="Failed to load equity" hint={(error as Error)?.message} />;

  return (
    <div className="rounded-lg border p-4">
      <div className="text-sm font-medium mb-2">Equity Curve — {symbol}</div>
      <EquityCurve data={data.points.map((p) => ({ t: p.t, equity: p.equity }))} />
    </div>
  );
}
