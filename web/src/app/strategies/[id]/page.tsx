"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { StrategyHeader } from "./_components/StrategyHeader";
import { StrategyCharts } from "./_components/StrategyCharts";
import { StrategyLineage } from "./_components/StrategyLineage";
import { StrategyBacktests } from "./_components/StrategyBacktests";
import { Loading } from "@/components/common/Loading";

export default function StrategyDetailPage() {
  const params = useParams();
  const id = Number(params.id);

  return (
    <Suspense fallback={<Loading rows={4} />}>
      <div className="flex flex-col gap-5">
        <StrategyHeader id={id} />
        <StrategyCharts id={id} />
        <StrategyLineage id={id} />
        <StrategyBacktests id={id} />
      </div>
    </Suspense>
  );
}
