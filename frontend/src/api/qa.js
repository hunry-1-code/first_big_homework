import { apiClient } from "./client";

export function askQuestion(payload) {
  return apiClient.post("/qa/ask", payload);
}

export function getQaHistory(params = {}) {
  return apiClient.get("/qa/history", { params });
}

