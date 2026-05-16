"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchRuns, runsQueryKeys, type RunSummary } from "@/lib/api/runs";
import { DataTable, StatusPill, type Column } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

type SortKey = "run_id" | "started_at" | "n_backtests" | "n_failures";

function sortRuns(rows: RunSummary[], key: SortKey, dir: "asc" | "desc"): RunSummary[] {
  const sorted = [...rows].sort((a, b) => {
    const av = a[key] ?? "";
    const bv = b[key] ?? "";
    if (av < bv) return -1;
    if (av > bv) return 1;
    return 0;
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

function RunsContent() {
  const router = useRouter();
  const params = useSearchParams();
  const sortKey = (params.get("sort") as SortKey) ?? "started_at";
  const sortDir = (params.get("dir") as "asc" | "desc") ?? "desc";

  const { data, isLoading, error } = useQuery({
    queryKey: runsQueryKeys.all,
    queryFn: () => fetchRuns(100, 0),
  });

  const onSort = (key: string) => {
    const next = new URLSearchParams(params.toString());
    if (sortKey === key) {
      next.set("dir", sortDir === "asc" ? "desc" : "asc");
    } else {
      next.set("sort", key);
      next.set("dir", "desc");
    }
    router.push(`/runs?${next.toString()}`);
  };

  const columns: Column<RunSummary>[] = [
    {
      key: "run_id",
      label: "Run ID",
      sortable: true,
      render: (r) => <span className="tabular text-primary">{r.run_id}</span>,
    },
    {
      key: "started_at",
      label: "Started",
      sortable: true,
      render: (r) => (
        <span className="tabular text-text-secondary">
          {r.started_at ? r.started_at.replace("T", " ").slice(0, 16) : "—"}
        </span>
      ),
    },
    { key: "status", label: "Status", render: (r) => <StatusPill status={r.status} /> },
    {
      key: "n_backtests",
      label: "Backtests",
      align: "right",
      sortable: true,
      render: (r) => <span className="tabular">{r.n_backtests}</span>,
    },
    {
      key: "n_failures",
      label: "Failures",
      align: "right",
      sortable: true,
      render: (r) => <span className="tabular text-down">{r.n_failures}</span>,
    },
    {
      key: "current_generation",
      label: "Gen",
      align: "right",
      render: (r) => <span className="tabular">{r.current_generation ?? "—"}</span>,
    },
  ];

  if (isLoading) return <Loading rows={6} />;
  if (error) return <EmptyState message="Failed to load runs" hint={(error as Error).message} />;
  if (!data || data.runs.length === 0) return <EmptyState message="No runs yet" hint="Run the pipeline to populate this." />;

  const rows = sortRuns(data.runs, sortKey, sortDir);

  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(r) => r.run_id}
      sortKey={sortKey}
      sortDir={sortDir}
      onSort={onSort}
      onRowClick={(r) => router.push(`/runs/${r.run_id}`)}
    />
  );
}

export default function RunsPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">Runs</h1>
      <Suspense fallback={<Loading rows={6} />}>
        <RunsContent />
      </Suspense>
    </div>
  );
}
