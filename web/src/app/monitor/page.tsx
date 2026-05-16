"use client";

import { Suspense } from "react";
import { MonitorContent } from "./_components/MonitorContent";
import { Loading } from "@/components/common/Loading";

export default function MonitorPage() {
  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-xl font-semibold">Pipeline Monitor</h1>
      <Suspense fallback={<Loading rows={4} />}>
        <MonitorContent />
      </Suspense>
    </div>
  );
}
