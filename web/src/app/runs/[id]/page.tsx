"use client";

import { useParams } from "next/navigation";
import { RunHeader } from "./_components/RunHeader";
import { RunRankings } from "./_components/RunRankings";
import { RunEvolution } from "./_components/RunEvolution";
import { RunAgentActivity } from "./_components/RunAgentActivity";

export default function RunDetailPage() {
  const params = useParams();
  const runId = String(params.id);

  return (
    <div className="flex flex-col gap-5">
      <RunHeader runId={runId} />
      <RunRankings runId={runId} />
      <RunEvolution runId={runId} />
      <RunAgentActivity runId={runId} />
    </div>
  );
}
