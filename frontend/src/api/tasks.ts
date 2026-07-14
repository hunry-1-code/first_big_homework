import { apiClient } from "./client";

export function getTask(id: number) {
  return apiClient.get(`/tasks/${id}`);
}

export function getMyTasks() {
  return apiClient.get("/tasks/my");
}

export function getAllTasks() {
  return apiClient.get("/tasks");
}

export function retryAnalysis(taskId: number) {
  return apiClient.post(`/tasks/${taskId}/retry-analysis`);
}
