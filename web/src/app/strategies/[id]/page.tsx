import { StrategyHeader } from "./_components/StrategyHeader";
import { AggregateMetricsCard } from "./_components/AggregateMetricsCard";
import { SymbolRunSelector } from "./_components/SymbolRunSelector";
import { PriceSignalChart } from "./_components/PriceSignalChart";
import { EquityCurveCard } from "./_components/EquityCurveCard";
import { DrawdownCard } from "./_components/DrawdownCard";
import { BacktestPerSymbolTable } from "./_components/BacktestPerSymbolTable";
import { LineageTree } from "./_components/LineageTree";
import { ReasoningCard } from "./_components/ReasoningCard";
import { ExperimentHistoryTable } from "./_components/ExperimentHistoryTable";

export default function StrategyDetailPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  return (
    <div className="flex flex-col gap-4">
      <StrategyHeader id={id} />
      <AggregateMetricsCard id={id} />
      <SymbolRunSelector id={id} />
      <PriceSignalChart id={id} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <EquityCurveCard id={id} />
        <DrawdownCard id={id} />
      </div>
      <BacktestPerSymbolTable id={id} />
      <LineageTree id={id} />
      <ReasoningCard id={id} />
      <div>
        <h2 className="text-sm font-medium mb-2">Experiment History</h2>
        <ExperimentHistoryTable id={id} />
      </div>
    </div>
  );
}
