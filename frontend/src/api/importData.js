import { apiClient } from "./client";

export function importJsonDocuments(documents) {
  return apiClient.post("/import/json", documents);
}

