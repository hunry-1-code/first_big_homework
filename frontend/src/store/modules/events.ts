import { defineStore } from "pinia";
import { listEvents } from "@/api/events";

export const useEventsStore = defineStore("events", {
  state: () => ({
    events: [] as any[],
    total: 0,
    loading: false
  }),
  actions: {
    async loadEvents(params: any = {}) {
      this.loading = true;
      try {
        const response = await listEvents(params);
        this.events = response.data.events;
        this.total = response.data.total;
      } finally {
        this.loading = false;
      }
    }
  }
});
