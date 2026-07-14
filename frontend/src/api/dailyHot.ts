import { apiClient } from "./client";
import type { DailyHotResponse } from "./types/opinion";

export function getTodayHotspots(limit: number = 10) {
  return apiClient.get<DailyHotResponse>("/hotspots/today", { params: { limit } });
}
