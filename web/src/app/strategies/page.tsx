import { Suspense } from "react";
import { StrategyFilters } from "./_components/StrategyFilters";
import { StrategyTable } from "./_components/StrategyTable";
import { Loading } from "@/components/common/Loading";

export default function StrategyLibraryPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Strategy Library</h1>
      <Suspense fallback={<Loading />}>
        <StrategyFilters />
        <StrategyTable />
      </Suspense>
    </div>
  );
}
