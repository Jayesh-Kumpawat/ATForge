import { cn } from "@/lib/utils";

interface Props {
  label: string;
  value: string | number;
  delta?: number | null;
  accent?: boolean;
  className?: string;
}

export function MetricTile({ label, value, delta, accent, className }: Props) {
  return (
    <div
      className={cn(
        "rounded-md border bg-elevated px-3 py-2.5 min-w-[120px]",
        accent ? "border-primary/30" : "border-border",
        className,
      )}
    >
      <div
        className={cn(
          "text-[10px] uppercase tracking-wide",
          accent ? "text-primary" : "text-text-muted",
        )}
      >
        {label}
      </div>
      <div
        className={cn(
          "tabular text-2xl font-semibold mt-0.5",
          accent ? "text-primary" : "text-foreground",
        )}
      >
        {value}
      </div>
      {delta != null ? (
        <div className={cn("tabular text-xs mt-0.5", delta >= 0 ? "text-up" : "text-down")}>
          {delta >= 0 ? "+" : ""}
          {delta.toFixed(2)}
        </div>
      ) : null}
    </div>
  );
}
