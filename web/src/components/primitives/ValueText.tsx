import { cn } from "@/lib/utils";

type Kind = "sharpe" | "pnl" | "plain" | "pct";

function sharpeColor(v: number): string {
  if (v >= 2) return "text-up font-semibold";
  if (v >= 1) return "text-up";
  if (v >= 0) return "text-warn";
  return "text-down";
}

interface Props {
  value: number | null | undefined;
  kind?: Kind;
  className?: string;
}

export function ValueText({ value, kind = "plain", className }: Props) {
  if (value == null) return <span className={cn("tabular text-text-muted", className)}>—</span>;

  let color = "text-foreground";
  let text = value.toFixed(2);

  if (kind === "sharpe") color = sharpeColor(value);
  else if (kind === "pnl") {
    color = value >= 0 ? "text-up" : "text-down";
    text = `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
  } else if (kind === "pct") {
    color = value >= 0 ? "text-up" : "text-down";
    text = `${(value * 100).toFixed(1)}%`;
  }

  return <span className={cn("tabular", color, className)}>{text}</span>;
}
