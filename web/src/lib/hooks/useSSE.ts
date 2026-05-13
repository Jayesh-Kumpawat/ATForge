"use client";

import { useEffect, useRef, useState } from "react";
import { sseUrl } from "@/lib/api/client";
import type { EventEnvelope } from "@/lib/api/runs";

interface UseSSEOptions {
  path: string;
  enabled?: boolean;
  bufferSize?: number;
}

interface UseSSEReturn {
  events: EventEnvelope[];
  isConnected: boolean;
  error: string | null;
  clear: () => void;
  pause: () => void;
  resume: () => void;
  isPaused: boolean;
}

export function useSSE({ path, enabled = true, bufferSize = 1000 }: UseSSEOptions): UseSSEReturn {
  const [events, setEvents] = useState<EventEnvelope[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPaused, setIsPaused] = useState(false);
  const lastEventIdRef = useRef(0);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!enabled || isPaused) return;

    const url = sseUrl(`${path}${path.includes("?") ? "&" : "?"}after_event_id=${lastEventIdRef.current}`);
    const es = new EventSource(url);
    sourceRef.current = es;

    es.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    es.addEventListener("pipeline_event", (msg) => {
      const envelope = JSON.parse((msg as MessageEvent).data) as EventEnvelope;
      lastEventIdRef.current = envelope.event_id;
      setEvents((prev) => {
        const next = [...prev, envelope];
        return next.length > bufferSize ? next.slice(-bufferSize) : next;
      });
    });

    es.addEventListener("heartbeat", () => {
      // Connection alive; nothing to do.
    });

    es.onerror = () => {
      setIsConnected(false);
      setError("Connection lost. Retrying…");
    };

    return () => {
      es.close();
      setIsConnected(false);
    };
  }, [path, enabled, isPaused, bufferSize]);

  return {
    events,
    isConnected,
    error,
    clear: () => setEvents([]),
    pause: () => setIsPaused(true),
    resume: () => setIsPaused(false),
    isPaused,
  };
}
