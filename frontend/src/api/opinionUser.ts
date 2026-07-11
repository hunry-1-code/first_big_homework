import { apiClient } from "./client";

export function getUserProfile() {
  return apiClient.get("/user/profile");
}

export function saveUserProfile(payload: any) {
  return apiClient.put("/user/profile", payload);
}

export function getUserConfig() {
  return apiClient.get("/user/config");
}

export function saveUserConfig(payload: any) {
  return apiClient.put("/user/config", payload);
}

export function getUserSources() {
  return apiClient.get("/user/sources");
}
