"use client";

import { createChart, ColorType, CandlestickSeries, createSeriesMarkers, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";
import { useTheme } from "next-themes";

interface Bar { t: number; o: number; h: number; l: number; c: number; v: number; }
interface Marker { t: number; type: "entry" | "exit"; price: number; }

export function PriceWithSignals({ bars, markers }: { bars: Bar[]; markers: Marker[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    if (!containerRef.current) return;

    const isDark = resolvedTheme === "dark";
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 400,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: isDark ? "#e5e7eb" : "#374151",
      },
      grid: {
        vertLines: { color: isDark ? "#374151" : "#e5e7eb" },
        horzLines: { color: isDark ? "#374151" : "#e5e7eb" },
      },
      timeScale: { timeVisible: true },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e", downColor: "#ef4444",
      borderUpColor: "#22c55e", borderDownColor: "#ef4444",
      wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    });

    candleSeries.setData(
      bars.map((b) => ({
        time: Math.floor(b.t / 1000) as UTCTimestamp,
        open: b.o, high: b.h, low: b.l, close: b.c,
      })),
    );

    createSeriesMarkers(
      candleSeries,
      markers.map((m) => ({
        time: Math.floor(m.t / 1000) as UTCTimestamp,
        position: m.type === "entry" ? "belowBar" : "aboveBar",
        color: m.type === "entry" ? "#22c55e" : "#ef4444",
        shape: m.type === "entry" ? "arrowUp" : "arrowDown",
        text: m.type,
      })),
    );

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [bars, markers, resolvedTheme]);

  return <div ref={containerRef} className="w-full" />;
}
