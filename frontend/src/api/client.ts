import axios from "axios";
import { getToken } from "@/utils/auth";
import { useUserStoreHook } from "@/store/modules/user";

export const apiClient = axios.create({
  baseURL: "/api",
  timeout: 60000
});

apiClient.interceptors.request.use((config) => {
  const tokenData = getToken();
  const token = tokenData?.accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      useUserStoreHook().logOut();
    }
    return Promise.reject(error);
  }
);
