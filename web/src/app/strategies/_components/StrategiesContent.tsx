"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchStats, statsQueryKey } from "@/lib/api/stats";
import {
  fetchStrategies,
  strategiesQueryKeys,
  type StrategyFilters,
  type StrategyListItem,
} from "@/lib/api/strategies";
import { FilterBar, Chip, DataTable, ValueText, type Column } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

const SORTS: { key: NonNullable<StrategyFilters["sort"]>; label: string }[] = [
  { key: "sharpe_desc", label: "Sharpe ↓" },
  { key: "sharpe_asc", label: "Sharpe ↑" },
  { key: "name_asc", label: "Name A–Z" },
  { key: "gen_desc", label: "Newest gen" },
];

export function StrategiesContent() {
  const router = useRouter();
  const params = useSearchParams();

  const family = params.get("family") ?? undefined;
  const sort = (params.get("sort") as StrategyFilters["sort"]) ?? "sharpe_desc";
  const minSharpe = params.get("min_sharpe") ? Number(params.get("min_sharpe")) : undefined;

  const filters: StrategyFilters = { family, sort, minSharpe, pageSize: 100 };

  const stats = useQuery({ queryKey: statsQueryKey, queryFn: fetchStats });
  const strategies = useQuery({
    queryKey: strategiesQueryKeys.list(filters),
    queryFn: () => fetchStrategies(filters),
  });

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params.toString());
    if (value === null) next.delete(key);
    else next.set(key, value);
    router.push(`/strategies?${next.toString()}`);
  };

  const columns: Column<StrategyListItem>[] = [
    { key: "name", label: "Name", render: (s) => <span className="text-primary">{s.name}</span> },
    { key: "family", label: "Family", render: (s) => <span className="text-text-secondary">{s.family}</span> },
    { key: "generation", label: "Gen", align: "right", render: (s) => <span className="tabular">{s.generation}</span> },
    {
      key: "parent",
      label: "Parent",
      align: "right",
      render: (s) => <span className="tabular text-text-muted">{s.parent_strategy_id ?? "—"}</span>,
    },
    { key: "best_sharpe", label: "Sharpe", align: "right", render: (s) => <ValueText value={s.best_sharpe} kind="sharpe" /> },
    { key: "best_sortino", label: "Sortino", align: "right", render: (s) => <ValueText value={s.best_sortino} /> },
    { key: "avg_win_rate", label: "Win%", align: "right", render: (s) => <ValueText value={s.avg_win_rate} kind="pct" /> },
    { key: "n_backtests", label: "Backtests", align: "right", render: (s) => <span className="tabular">{s.n_backtests}</span> },
  ];

  return (
    <div className="flex flex-col gap-4">
      <FilterBar>
        <span className="text-xs font-medium text-text-secondary">Family:</span>
        {(stats.data?.families ?? []).map((f) => (
          <Chip
            key={f.family}
            label={`${f.family} (${f.count})`}
            active={family === f.family}
            onClick={() => setParam("family", family === f.family ? null : f.family)}
          />
        ))}
        <span className="ml-3 text-xs font-medium text-text-secondary">Sort:</span>
        {SORTS.map((s) => (
          <Chip key={s.key} label={s.label} active={sort === s.key} onClick={() => setParam("sort", s.key)} />
        ))}
        <button
          type="button"
          onClick={() => router.push("/strategies")}
          className="ml-auto text-xs text-text-muted hover:text-foreground"
        >
          Clear all
        </button>
      </FilterBar>

      {strategies.isLoading ? (
        <Loading rows={6} />
      ) : strategies.error ? (
        <EmptyState message="Failed to load strategies" hint={(strategies.error as Error).message} />
      ) : !strategies.data || strategies.data.strategies.length === 0 ? (
        <EmptyState message="No strategies match these filters" hint="Adjust or clear the filters." />
      ) : (
        <DataTable
          columns={columns}
          rows={strategies.data.strategies}
          rowKey={(s) => s.strategy_id}
          onRowClick={(s) => router.push(`/strategies/${s.strategy_id}`)}
        />
      )}
    </div>
  );
}
