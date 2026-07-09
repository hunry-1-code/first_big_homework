import { apiClient } from "./client";

export function triggerCrawler(payload = {}) {
  return apiClient.post("/crawler/trigger", payload);
}

export function searchCrawler(keyword) {
  return apiClient.post("/crawler/search", { keyword });
}

export function getCrawlerStatus() {
  return apiClient.get("/crawler/status");
}

