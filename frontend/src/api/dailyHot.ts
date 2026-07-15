import { apiClient } from "./client";
import type { DailyHotResponse } from "./types/opinion";

export function getTodayHotspots(limit: number = 20) {
  return apiClient.get<DailyHotResponse>("/hotspots/today", { params: { limit } });
}

export function enrichHotspotItem(itemId: number) {
  return apiClient.post(`/hotspots/today/items/${itemId}/enrich`);
}
