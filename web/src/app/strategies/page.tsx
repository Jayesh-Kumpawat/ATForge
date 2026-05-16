"use client";

import { Suspense } from "react";
import { StrategiesContent } from "./_components/StrategiesContent";
import { Loading } from "@/components/common/Loading";

export default function StrategiesPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">Strategies</h1>
      <Suspense fallback={<Loading rows={6} />}>
        <StrategiesContent />
      </Suspense>
    </div>
  );
}
