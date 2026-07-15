import { apiClient } from "./client";

export function askQuestion(payload: { question: string; event_id?: number }) {
  return apiClient.post("/qa/ask", payload);
}

export function getQaHistory(params: any = {}) {
  return apiClient.get("/qa/history", { params });
}

export function clearQaHistory(eventId?: number) {
  return apiClient.delete("/qa/history", { params: eventId ? { event_id: eventId } : {} });
}
