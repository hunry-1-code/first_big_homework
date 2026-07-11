import { apiClient } from "./client";

export function importJsonDocuments(documents: any[]) {
  return apiClient.post("/import/json", documents);
}
