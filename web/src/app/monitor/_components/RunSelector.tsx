"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { fetchRuns, runsQueryKeys } from "@/lib/api/runs";

export function RunSelector() {
  const router = useRouter();
  const params = useSearchParams();
  const current = params.get("run") ?? "";

  const { data } = useQuery({
    queryKey: runsQueryKeys.all,
    queryFn: () => fetchRuns(20, 0),
    refetchInterval: 5000,
  });

  return (
    <Select
      value={current}
      onValueChange={(v) => {
        const next = new URLSearchParams(params.toString());
        next.set("run", v);
        router.push(`/monitor?${next.toString()}`);
      }}
    >
      <SelectTrigger className="w-80"><SelectValue placeholder="Select a run" /></SelectTrigger>
      <SelectContent>
        {(data?.runs ?? []).map((r) => (
          <SelectItem key={r.run_id} value={r.run_id}>
            {r.run_id} — {r.status} — {r.n_backtests} backtests
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
