"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { fetchRunEvolution, runsQueryKeys, type ExperimentRow } from "@/lib/api/runs";
import { Card, SectionHeader, MetricTile, DataTable, ValueText, type Column } from "@/components/primitives";
import { Loading } from "@/components/common/Loading";
import { EmptyState } from "@/components/common/EmptyState";

export function RunEvolution({ runId }: { runId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: runsQueryKeys.evolution(runId),
    queryFn: () => fetchRunEvolution(runId),
  });

  const columns: Column<ExperimentRow>[] = [
    { key: "generation", label: "Gen", align: "right", render: (e) => <span className="tabular">{e.generation}</span> },
    { key: "mutator", label: "Mutator", render: (e) => e.mutator ?? "—" },
    {
      key: "lineage",
      label: "Parent → Child",
      render: (e) => (
        <span className="text-text-secondary">
          {e.parent_name ?? "—"} → {e.child_name ?? "—"}
        </span>
      ),
    },
    {
      key: "delta_sharpe",
      label: "ΔSharpe",
      align: "right",
      render: (e) => <ValueText value={e.delta_sharpe} kind="pnl" />,
    },
    {
      key: "accepted",
      label: "Verdict",
      render: (e) =>
        e.mutator === "critic_veto" ? (
          <span className="text-warn">⚖ vetoed</span>
        ) : e.accepted === 1 ? (
          <span className="text-up">✓ accepted</span>
        ) : (
          <span className="text-down">✗ rejected</span>
        ),
    },
  ];

  return (
    <Card className="p-4">
      <SectionHeader title="Evolution" hint="ratchet verdicts" />
      {isLoading ? (
        <Loading rows={4} />
      ) : error ? (
        <EmptyState message="Failed to load evolution data" />
      ) : !data || data.experiments.length === 0 ? (
        <EmptyState
          message="No evolution data for this run"
          hint="Single-pass run (max_generations=1). Run with --max-generations 2+ to see mutations."
        />
      ) : (
        <RunEvolutionBody
          experiments={data.experiments}
          progression={data.sharpe_progression}
          columns={columns}
        />
      )}
    </Card>
  );
}

function RunEvolutionBody({
  experiments,
  progression,
  columns,
}: {
  experiments: ExperimentRow[];
  progression: { generation: number; best_sharpe: number | null; n_backtests: number }[];
  columns: Column<ExperimentRow>[];
}) {
  const accepted = experiments.filter((e) => e.accepted === 1 && e.mutator !== "critic_veto").length;
  const rejected = experiments.filter((e) => e.accepted === 0 && e.mutator !== "critic_veto").length;
  const vetoed = experiments.filter((e) => e.mutator === "critic_veto").length;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        <MetricTile label="Accepted" value={accepted} />
        <MetricTile label="Rejected" value={rejected} />
        <MetricTile label="Vetoed" value={vetoed} />
      </div>

      {progression.length > 0 ? (
        <div>
          <div className="mb-2 text-[11px] uppercase tracking-wide text-text-muted">
            Best Sharpe per generation
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={progression}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="generation" stroke="var(--text-muted)" fontSize={11} />
              <YAxis stroke="var(--text-muted)" fontSize={11} />
              <Tooltip
                contentStyle={{
                  background: "var(--elevated)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Bar dataKey="best_sharpe" fill="var(--accent-teal)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : null}

      <div>
        <div className="mb-2 text-[11px] uppercase tracking-wide text-text-muted">Mutation log</div>
        <DataTable columns={columns} rows={experiments} rowKey={(e) => e.experiment_id} />
      </div>
    </div>
  );
}
