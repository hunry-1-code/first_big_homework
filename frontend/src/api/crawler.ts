import { apiClient } from "./client";

export function triggerCrawler(payload: any = {}) {
  return apiClient.post("/crawler/trigger", payload);
}

export function searchCrawler(keyword: string, platforms?: string[], targetCount?: number, force?: boolean) {
  const payload: Record<string, any> = { keyword };
  if (platforms && platforms.length > 0) {
    payload.platforms = platforms;
  }
  if (targetCount !== undefined && targetCount >= 1 && targetCount <= 200) {
    payload.target_count = targetCount;
  }
  if (force) {
    payload.force = true;
  }
  return apiClient.post("/crawler/search", payload);
}

export function getCrawlerStatus() {
  return apiClient.get("/crawler/status");
}
