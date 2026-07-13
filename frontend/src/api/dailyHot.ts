import { apiClient } from "./client";

export function getTodayHotspots(limit: number = 10) {
  return apiClient.get("/hotspots/today", { params: { limit } });
}
