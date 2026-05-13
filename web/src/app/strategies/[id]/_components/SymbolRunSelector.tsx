"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { fetchStrategyBacktests, strategiesQueryKeys } from "@/lib/api/strategies";

export function SymbolRunSelector({ id }: { id: number }) {
  const router = useRouter();
  const params = useSearchParams();

  const { data } = useQuery({
    queryKey: strategiesQueryKeys.backtests(id),
    queryFn: () => fetchStrategyBacktests(id),
  });

  const symbols = Array.from(new Set((data?.backtests ?? []).map((b) => b.symbol)));
  const runs = Array.from(new Set((data?.backtests ?? []).map((b) => b.run_id)));

  const symbol = params.get("symbol") ?? symbols[0] ?? "";
  const run = params.get("run") ?? runs[0] ?? "";

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    next.set(key, value);
    router.push(`/strategies/${id}?${next.toString()}`);
  };

  return (
    <div className="flex flex-wrap gap-3">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">Symbol:</span>
        <Select value={symbol} onValueChange={(v) => setParam("symbol", v)}>
          <SelectTrigger className="w-44"><SelectValue placeholder="Select symbol" /></SelectTrigger>
          <SelectContent>
            {symbols.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">Run:</span>
        <Select value={run} onValueChange={(v) => setParam("run", v)}>
          <SelectTrigger className="w-72"><SelectValue placeholder="Select run" /></SelectTrigger>
          <SelectContent>
            {runs.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
