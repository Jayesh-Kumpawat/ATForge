import { Inbox } from "lucide-react";

export function EmptyState({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-muted-foreground">
      <Inbox className="size-10" />
      <p className="text-sm">{message}</p>
      {hint ? <p className="text-xs">{hint}</p> : null}
    </div>
  );
}
