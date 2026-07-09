import { apiClient } from "./client";

export function listEvents(params = {}) {
  return apiClient.get("/events", { params });
}

export function getEvent(id) {
  return apiClient.get(`/events/${id}`);
}

export function getEventReport(id) {
  return apiClient.get(`/events/${id}/report`);
}

export function exportEventReport(id, format = "html") {
  return apiClient.get(`/events/${id}/report/export`, { params: { format } });
}

