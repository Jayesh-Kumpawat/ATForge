"use client";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { EventEnvelope } from "@/lib/api/runs";
import { EVENT_COLORS } from "@/lib/constants";

interface Props {
  events: EventEnvelope[];
  isPaused: boolean;
  onPauseToggle: () => void;
  onClear: () => void;
  error: string | null;
  isConnected: boolean;
}

export function LiveEventStream({ events, isPaused, onPauseToggle, onClear, error, isConnected }: Props) {
  const recent = events.slice(-200).reverse();

  return (
    <div className="rounded-lg border flex flex-col h-[400px]">
      <div className="flex items-center justify-between px-4 py-2 border-b">
        <div className="flex items-center gap-2 text-sm font-medium">
          Event Stream
          <span className={isConnected ? "text-green-500" : "text-red-500"}>
            {isConnected ? "● live" : "○ disconnected"}
          </span>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={onPauseToggle}>
            {isPaused ? "Resume" : "Pause"}
          </Button>
          <Button variant="ghost" size="sm" onClick={onClear}>Clear</Button>
        </div>
      </div>
      {error ? <div className="bg-red-500/10 text-red-500 text-xs px-4 py-1">{error}</div> : null}
      <ScrollArea className="flex-1">
        <div className="font-mono text-xs">
          {recent.map((e) => (
            <div key={e.event_id} className="px-4 py-1 border-b last:border-0 flex gap-2">
              <span className="text-muted-foreground">{new Date(e.ts_ms).toLocaleTimeString()}</span>
              <span className={EVENT_COLORS[e.event_type] ?? ""}>{e.event_type}</span>
              <span className="text-muted-foreground truncate">
                {JSON.stringify(e.payload).slice(0, 120)}
              </span>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
