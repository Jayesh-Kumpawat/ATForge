import { Inbox } from "lucide-react";

export function EmptyState({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-text-muted">
      <Inbox className="size-8" />
      <p className="text-sm text-text-secondary">{message}</p>
      {hint ? <p className="text-xs">{hint}</p> : null}
    </div>
  );
}
