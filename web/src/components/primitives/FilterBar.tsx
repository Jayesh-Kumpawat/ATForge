import { cn } from "@/lib/utils";

export function FilterBar({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2 rounded-lg border border-border bg-elevated p-3", className)}>
      {children}
    </div>
  );
}
