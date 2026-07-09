import { defineStore } from "pinia";

import { loginApi, meApi } from "../api/auth";

const TOKEN_KEY = "opinion_analysis_token";
const USER_KEY = "opinion_analysis_user";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || "",
    user: JSON.parse(localStorage.getItem(USER_KEY) || "null")
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.token),
    isAdmin: (state) => state.user?.role === "admin"
  },
  actions: {
    async login(credentials) {
      const response = await loginApi(credentials);
      this.token = response.data.token;
      this.user = response.data.user;
      localStorage.setItem(TOKEN_KEY, this.token);
      localStorage.setItem(USER_KEY, JSON.stringify(this.user));
    },
    async refreshMe() {
      const response = await meApi();
      this.user = response.data;
      localStorage.setItem(USER_KEY, JSON.stringify(this.user));
    },
    logout() {
      this.token = "";
      this.user = null;
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    }
  }
});

