"use client";

import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  fetchStrategyBacktests,
  fetchStrategyEquity,
  fetchStrategySignals,
  strategiesQueryKeys,
} from "@/lib/api/strategies";
import { ApiError } from "@/lib/api/client";
import { Card, SectionHeader } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

const EquityCurve = dynamic(() => import("@/components/charts/EquityCurve").then((m) => m.EquityCurve), { ssr: false });
const DrawdownArea = dynamic(() => import("@/components/charts/DrawdownArea").then((m) => m.DrawdownArea), { ssr: false });
const PriceWithSignals = dynamic(
  () => import("@/components/charts/PriceWithSignals").then((m) => m.PriceWithSignals),
  { ssr: false },
);

export function StrategyCharts({ id }: { id: number }) {
  const router = useRouter();
  const params = useSearchParams();

  const backtests = useQuery({
    queryKey: strategiesQueryKeys.backtests(id),
    queryFn: () => fetchStrategyBacktests(id),
  });

  const symbols = [...new Set((backtests.data?.backtests ?? []).map((b) => b.symbol))];
  const runs = [...new Set((backtests.data?.backtests ?? []).map((b) => b.run_id))];
  const symbol = params.get("symbol") ?? symbols[0] ?? "";
  const run = params.get("run") ?? runs[0] ?? "";

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    next.set(key, value);
    router.push(`/strategies/${id}?${next.toString()}`);
  };

  const equity = useQuery({
    queryKey: strategiesQueryKeys.equity(id, symbol, run),
    queryFn: () => fetchStrategyEquity(id, symbol, run),
    enabled: !!symbol && !!run,
    retry: false,
  });
  const signals = useQuery({
    queryKey: strategiesQueryKeys.signals(id, symbol, run),
    queryFn: () => fetchStrategySignals(id, symbol, run),
    enabled: !!symbol && !!run,
    retry: false,
  });

  const missing = (e: unknown) => e instanceof ApiError && e.code === "SIGNAL_DATA_MISSING";

  return (
    <Card className="p-4">
      <SectionHeader
        title="Charts"
        right={
          <div className="flex gap-2">
            <select
              value={symbol}
              onChange={(e) => setParam("symbol", e.target.value)}
              className="rounded-md border border-border bg-elevated px-2 py-1 text-xs"
            >
              {symbols.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <select
              value={run}
              onChange={(e) => setParam("run", e.target.value)}
              className="rounded-md border border-border bg-elevated px-2 py-1 text-xs"
            >
              {runs.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
        }
      />
      {backtests.isLoading ? (
        <Loading rows={4} />
      ) : !symbol || !run ? (
        <EmptyState message="No backtests for this strategy" />
      ) : (
        <div className="flex flex-col gap-4">
          <div>
            <div className="mb-2 text-[11px] uppercase tracking-wide text-text-muted">Price + Signals — {symbol}</div>
            {signals.isLoading ? (
              <Loading rows={3} />
            ) : missing(signals.error) ? (
              <EmptyState message="Signal data unavailable for this symbol/run" />
            ) : signals.error || !signals.data ? (
              <EmptyState message="Failed to load chart" />
            ) : (
              <PriceWithSignals bars={signals.data.bars} markers={signals.data.signals} />
            )}
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <div className="mb-2 text-[11px] uppercase tracking-wide text-text-muted">Equity</div>
              {equity.isLoading ? (
                <Loading rows={2} />
              ) : missing(equity.error) ? (
                <EmptyState message="Equity unavailable" />
              ) : equity.error || !equity.data ? (
                <EmptyState message="Failed to load equity" />
              ) : (
                <EquityCurve data={equity.data.points.map((p) => ({ t: p.t, equity: p.equity }))} />
              )}
            </div>
            <div>
              <div className="mb-2 text-[11px] uppercase tracking-wide text-text-muted">Drawdown</div>
              {equity.isLoading ? (
                <Loading rows={2} />
              ) : equity.error || !equity.data ? (
                <EmptyState message="Drawdown unavailable" />
              ) : (
                <DrawdownArea data={equity.data.points.map((p) => ({ t: p.t, drawdown: p.drawdown }))} />
              )}
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
