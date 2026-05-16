import { apiGet } from "./client";
import type { components } from "./types.gen";

export type RunSummary = components["schemas"]["RunSummary"];
export type RunListResponse = components["schemas"]["RunListResponse"];
export type EventEnvelope = components["schemas"]["EventEnvelope"];
export type RunRankingsResponse = components["schemas"]["RunRankingsResponse"];
export type RankingRow = components["schemas"]["RankingRow"];
export type RunEvolutionResponse = components["schemas"]["RunEvolutionResponse"];
export type ExperimentRow = components["schemas"]["ExperimentRow"];
export type TimelineResponse = components["schemas"]["TimelineResponse"];

export async function fetchRuns(limit = 20, offset = 0): Promise<RunListResponse> {
  return apiGet<RunListResponse>(`/runs?limit=${limit}&offset=${offset}`);
}

export async function fetchRun(runId: string): Promise<RunSummary> {
  return apiGet<RunSummary>(`/runs/${encodeURIComponent(runId)}`);
}

export async function fetchRunRankings(runId: string): Promise<RunRankingsResponse> {
  return apiGet<RunRankingsResponse>(`/runs/${encodeURIComponent(runId)}/rankings`);
}

export async function fetchRunEvolution(runId: string): Promise<RunEvolutionResponse> {
  return apiGet<RunEvolutionResponse>(`/runs/${encodeURIComponent(runId)}/evolution`);
}

export async function fetchRunTimeline(runId: string): Promise<TimelineResponse> {
  return apiGet<TimelineResponse>(`/runs/${encodeURIComponent(runId)}/timeline`);
}

export const runsQueryKeys = {
  all: ["runs"] as const,
  detail: (runId: string) => ["runs", runId] as const,
  rankings: (runId: string) => ["runs", runId, "rankings"] as const,
  evolution: (runId: string) => ["runs", runId, "evolution"] as const,
  timeline: (runId: string) => ["runs", runId, "timeline"] as const,
};
