export const EVENT_COLORS: Record<string, string> = {
  EvtPipelineStart: "text-blue-500",
  EvtPipelineDone: "text-green-500",
  EvtNodeStart: "text-indigo-500",
  EvtNodeDone: "text-emerald-500",
  EvtBacktestDone: "text-cyan-500",
  EvtMutationProposed: "text-violet-500",
  EvtRatchetVerdict: "text-amber-500",
  EvtCriticVerdict: "text-orange-500",
  EvtGenerationDone: "text-pink-500",
  EvtAgentToolCall: "text-fuchsia-500",
};

export const SHARPE_COLOR = (s: number | null | undefined): string => {
  if (s == null) return "text-muted-foreground";
  if (s >= 2.0) return "text-green-500 font-semibold";
  if (s >= 1.0) return "text-green-400";
  if (s >= 0) return "text-yellow-500";
  return "text-red-500";
};

export const FAMILY_LABELS: Record<string, string> = {
  candle: "Candlestick",
  sma: "SMA",
  rsi: "RSI",
  composition: "Composition",
};
