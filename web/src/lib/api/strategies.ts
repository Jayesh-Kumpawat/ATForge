import { apiGet } from "./client";
import type { components } from "./types.gen";

export type StrategyListItem = components["schemas"]["StrategyListItem"];
export type StrategyListResponse = components["schemas"]["StrategyListResponse"];
export type StrategyDetail = components["schemas"]["StrategyDetail"];
export type BacktestListResponse = components["schemas"]["BacktestListResponse"];
export type EquityResponse = components["schemas"]["EquityResponse"];
export type SignalsResponse = components["schemas"]["SignalsResponse"];
export type LineageResponse = components["schemas"]["LineageResponse"];
export type ReasoningResponse = components["schemas"]["ReasoningResponse"];

export interface StrategyFilters {
  family?: string;
  minSharpe?: number;
  generation?: number;
  sort?: "sharpe_desc" | "sharpe_asc" | "name_asc" | "gen_desc";
  page?: number;
  pageSize?: number;
}

export async function fetchStrategies(filters: StrategyFilters = {}): Promise<StrategyListResponse> {
  const params = new URLSearchParams();
  if (filters.family) params.set("family", filters.family);
  if (filters.minSharpe !== undefined) params.set("min_sharpe", String(filters.minSharpe));
  if (filters.generation !== undefined) params.set("generation", String(filters.generation));
  if (filters.sort) params.set("sort", filters.sort);
  if (filters.page) params.set("page", String(filters.page));
  if (filters.pageSize) params.set("page_size", String(filters.pageSize));
  return apiGet<StrategyListResponse>(`/strategies?${params}`);
}

export async function fetchStrategy(id: number): Promise<StrategyDetail> {
  return apiGet<StrategyDetail>(`/strategies/${id}`);
}

export async function fetchStrategyBacktests(id: number): Promise<BacktestListResponse> {
  return apiGet<BacktestListResponse>(`/strategies/${id}/backtests`);
}

export async function fetchStrategyEquity(id: number, symbol: string, runId: string): Promise<EquityResponse> {
  return apiGet<EquityResponse>(
    `/strategies/${id}/equity?symbol=${encodeURIComponent(symbol)}&run_id=${encodeURIComponent(runId)}`,
  );
}

export async function fetchStrategySignals(id: number, symbol: string, runId: string): Promise<SignalsResponse> {
  return apiGet<SignalsResponse>(
    `/strategies/${id}/signals?symbol=${encodeURIComponent(symbol)}&run_id=${encodeURIComponent(runId)}`,
  );
}

export async function fetchStrategyLineage(id: number): Promise<LineageResponse> {
  return apiGet<LineageResponse>(`/strategies/${id}/lineage`);
}

export async function fetchStrategyReasoning(id: number): Promise<ReasoningResponse> {
  return apiGet<ReasoningResponse>(`/strategies/${id}/reasoning`);
}

export const strategiesQueryKeys = {
  all: ["strategies"] as const,
  list: (filters: StrategyFilters) => ["strategies", "list", filters] as const,
  detail: (id: number) => ["strategies", id] as const,
  backtests: (id: number) => ["strategies", id, "backtests"] as const,
  equity: (id: number, symbol: string, runId: string) =>
    ["strategies", id, "equity", symbol, runId] as const,
  signals: (id: number, symbol: string, runId: string) =>
    ["strategies", id, "signals", symbol, runId] as const,
  lineage: (id: number) => ["strategies", id, "lineage"] as const,
  reasoning: (id: number) => ["strategies", id, "reasoning"] as const,
};
