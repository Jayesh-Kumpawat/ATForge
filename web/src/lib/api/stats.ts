import { apiGet } from "./client";
import type { components } from "./types.gen";

export type StatsResponse = components["schemas"]["StatsResponse"];

export async function fetchStats(): Promise<StatsResponse> {
  return apiGet<StatsResponse>("/stats");
}

export const statsQueryKey = ["stats"] as const;
