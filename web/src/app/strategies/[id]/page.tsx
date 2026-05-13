import { StrategyHeader } from "./_components/StrategyHeader";
import { AggregateMetricsCard } from "./_components/AggregateMetricsCard";
import { SymbolRunSelector } from "./_components/SymbolRunSelector";
import { BacktestPerSymbolTable } from "./_components/BacktestPerSymbolTable";

export default function StrategyDetailPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  return (
    <div className="flex flex-col gap-4">
      <StrategyHeader id={id} />
      <AggregateMetricsCard id={id} />
      <SymbolRunSelector id={id} />
      <BacktestPerSymbolTable id={id} />
    </div>
  );
}
