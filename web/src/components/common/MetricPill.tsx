import { cn } from "@/lib/utils";

interface Props {
  label: string;
  value: string | number | null | undefined;
  delta?: number | null;
  valueClassName?: string;
}

export function MetricPill({ label, value, delta, valueClassName }: Props) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border p-4 min-w-[140px]">
      <span className="text-xs text-muted-foreground uppercase tracking-wide">{label}</span>
      <span className={cn("text-2xl font-semibold", valueClassName)}>
        {value === null || value === undefined ? "—" : value}
      </span>
      {delta !== undefined && delta !== null ? (
        <span className={cn("text-xs", delta >= 0 ? "text-green-500" : "text-red-500")}>
          {delta >= 0 ? "+" : ""}{delta.toFixed(2)} vs parent
        </span>
      ) : null}
    </div>
  );
}
