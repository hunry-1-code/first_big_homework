import { apiClient } from "./client";

export function getTask(id) {
  return apiClient.get(`/tasks/${id}`);
}

export function getMyTasks() {
  return apiClient.get("/tasks/my");
}

export function getAllTasks() {
  return apiClient.get("/tasks");
}

