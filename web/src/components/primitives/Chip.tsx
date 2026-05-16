"use client";

import { cn } from "@/lib/utils";

interface Props {
  label: string;
  active?: boolean;
  onClick?: () => void;
  className?: string;
}

export function Chip({ label, active, onClick, className }: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-md border px-2.5 py-1 text-xs transition-colors",
        active
          ? "border-primary/30 bg-primary/12 text-primary"
          : "border-border bg-elevated text-text-secondary hover:border-border-strong hover:text-foreground",
        className,
      )}
    >
      {label}
    </button>
  );
}
