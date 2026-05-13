"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";

const FAMILIES = ["candle", "sma", "rsi", "composition"];

export function StrategyFilters() {
  const router = useRouter();
  const params = useSearchParams();

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params.toString());
    if (value === null || value === "") next.delete(key);
    else next.set(key, value);
    next.delete("page");
    router.push(`/strategies?${next.toString()}`);
  };

  const family = params.get("family") ?? "";
  const minSharpe = params.get("min_sharpe") ?? "";
  const sort = params.get("sort") ?? "sharpe_desc";
  const selectedFamilies = family ? family.split(",") : [];

  const toggleFamily = (f: string) => {
    const next = selectedFamilies.includes(f)
      ? selectedFamilies.filter((x) => x !== f)
      : [...selectedFamilies, f];
    setParam("family", next.join(",") || null);
  };

  return (
    <div className="rounded-lg border p-4 flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium mr-2">Family:</span>
        {FAMILIES.map((f) => {
          const active = selectedFamilies.includes(f);
          return (
            <Badge
              key={f}
              variant={active ? "default" : "outline"}
              className="cursor-pointer"
              onClick={() => toggleFamily(f)}
            >
              {f}
            </Badge>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Min Sharpe:</span>
          <Input
            className="w-24"
            type="number"
            step="0.1"
            value={minSharpe}
            onChange={(e) => setParam("min_sharpe", e.target.value || null)}
          />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Sort:</span>
          <Select value={sort} onValueChange={(v) => setParam("sort", v)}>
            <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="sharpe_desc">Sharpe (high → low)</SelectItem>
              <SelectItem value="sharpe_asc">Sharpe (low → high)</SelectItem>
              <SelectItem value="name_asc">Name (A → Z)</SelectItem>
              <SelectItem value="gen_desc">Generation (newest)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <Button variant="ghost" size="sm" onClick={() => router.push("/strategies")}>
          Clear all
        </Button>
      </div>
    </div>
  );
}
