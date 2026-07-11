import { apiClient } from "./client";

export function triggerCrawler(payload: any = {}) {
  return apiClient.post("/crawler/trigger", payload);
}

export function searchCrawler(keyword: string) {
  return apiClient.post("/crawler/search", { keyword });
}

export function getCrawlerStatus() {
  return apiClient.get("/crawler/status");
}
