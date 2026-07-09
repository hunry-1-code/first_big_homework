import { apiClient } from "./client";

export function loginApi(payload) {
  return apiClient.post("/auth/login", payload);
}

export function meApi() {
  return apiClient.get("/auth/me");
}

