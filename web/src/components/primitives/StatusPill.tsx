import { cn } from "@/lib/utils";

export type RunStatus = "running" | "done" | "failed" | "pending" | "unknown";

const STYLE: Record<RunStatus, string> = {
  running: "bg-primary/12 text-primary border-primary/30",
  done: "bg-up/12 text-up border-up/30",
  failed: "bg-down/12 text-down border-down/30",
  pending: "bg-muted text-text-muted border-border",
  unknown: "bg-muted text-text-muted border-border",
};

const ICON: Record<RunStatus, string> = {
  running: "●",
  done: "✓",
  failed: "✗",
  pending: "○",
  unknown: "○",
};

export function StatusPill({ status, className }: { status: RunStatus; className?: string }) {
  const s = (STYLE[status] ?? STYLE.unknown);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium",
        s,
        className,
      )}
    >
      <span>{ICON[status] ?? ICON.unknown}</span>
      {status}
    </span>
  );
}
