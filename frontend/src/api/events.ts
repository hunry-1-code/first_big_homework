import { apiClient } from "./client";

export function listEvents(params: any = {}) {
  return apiClient.get("/events", { params });
}

export function getEvent(id: number) {
  return apiClient.get(`/events/${id}`);
}

export function getEventReport(id: number) {
  return apiClient.get(`/events/${id}/report`);
}

export function exportEventReport(id: number, format: string = "html") {
  return apiClient.get(`/events/${id}/report/export`, { params: { format } });
}
export function getEventPropagation(id: number) {
  return apiClient.get(`/events/${id}/propagation`);
}
