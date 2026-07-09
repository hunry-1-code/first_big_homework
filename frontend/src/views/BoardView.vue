<template>
  <AppShell>
    <div class="page-header">
      <div>
        <h1 class="page-title">舆情事件看板</h1>
        <p class="muted">展示已采集和分析完成的热点事件。</p>
      </div>
      <el-button v-if="auth.isAdmin" type="primary" @click="trigger">手动采集</el-button>
    </div>

    <div class="surface" style="margin-bottom: 16px">
      <el-input v-model="keyword" placeholder="搜索事件或触发关键词采集" clearable @keyup.enter="search" />
      <el-button style="margin-top: 10px" @click="search">搜索/采集</el-button>
    </div>

    <div class="grid cols-3">
      <EventCard v-for="event in events.events" :key="event.id" :event="event" />
    </div>
  </AppShell>
</template>

<script setup>
import { onMounted, ref } from "vue";

import { searchCrawler, triggerCrawler } from "../api/crawler";
import AppShell from "../components/AppShell.vue";
import EventCard from "../components/EventCard.vue";
import { useAuthStore } from "../stores/auth";
import { useEventsStore } from "../stores/events";

const auth = useAuthStore();
const events = useEventsStore();
const keyword = ref("");

onMounted(() => events.loadEvents());

async function search() {
  if (keyword.value.trim()) {
    await searchCrawler(keyword.value.trim());
  }
  await events.loadEvents({ keyword: keyword.value.trim() });
}

async function trigger() {
  await triggerCrawler({});
}
</script>

