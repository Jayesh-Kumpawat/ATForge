import { cn } from "@/lib/utils";

interface Props {
  title: string;
  hint?: string;
  right?: React.ReactNode;
  className?: string;
}

export function SectionHeader({ title, hint, right, className }: Props) {
  return (
    <div className={cn("flex items-center justify-between border-b border-border pb-2 mb-3", className)}>
      <div className="flex items-baseline gap-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-text-secondary">{title}</h2>
        {hint ? <span className="text-xs text-text-muted">{hint}</span> : null}
      </div>
      {right}
    </div>
  );
}
