import { apiGet } from "./client";
import type { components } from "./types.gen";

export type RunSummary = components["schemas"]["RunSummary"];
export type RunListResponse = components["schemas"]["RunListResponse"];
export type EventEnvelope = components["schemas"]["EventEnvelope"];

export async function fetchRuns(limit = 20, offset = 0): Promise<RunListResponse> {
  return apiGet<RunListResponse>(`/runs?limit=${limit}&offset=${offset}`);
}

export async function fetchRun(runId: string): Promise<RunSummary> {
  return apiGet<RunSummary>(`/runs/${encodeURIComponent(runId)}`);
}

export const runsQueryKeys = {
  all: ["runs"] as const,
  detail: (runId: string) => ["runs", runId] as const,
};
