import axios from "axios";

import { useAuthStore } from "../stores/auth";

export const apiClient = axios.create({
  baseURL: "/api",
  timeout: 15000
});

apiClient.interceptors.request.use((config) => {
  const auth = useAuthStore();
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore().logout();
    }
    return Promise.reject(error);
  }
);

