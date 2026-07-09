<template>
  <AppShell>
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ detail?.title || "事件详情" }}</h1>
        <p class="muted">趋势、情感、平台、关键词和报告在线展示。</p>
      </div>
      <el-button @click="reserveExport">导出报告</el-button>
    </div>

    <el-tabs v-if="detail" class="surface">
      <el-tab-pane label="事件概述">
        <p>{{ detail.report.overview_text }}</p>
      </el-tab-pane>
      <el-tab-pane label="发展趋势">
        <pre>{{ detail.trend }}</pre>
      </el-tab-pane>
      <el-tab-pane label="情感分布">
        <pre>{{ detail.sentiment }}</pre>
      </el-tab-pane>
      <el-tab-pane label="平台分布">
        <pre>{{ detail.platform }}</pre>
      </el-tab-pane>
      <el-tab-pane label="高频关键词">
        <el-tag v-for="item in detail.keywords.keywords" :key="item.word" style="margin: 4px">
          {{ item.word }} {{ item.weight }}
        </el-tag>
      </el-tab-pane>
      <el-tab-pane label="关联报道">
        <el-table :data="detail.articles.articles">
          <el-table-column prop="title" label="标题" />
          <el-table-column prop="platform" label="平台" width="120" />
          <el-table-column prop="sentiment_label" label="情感" width="120" />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </AppShell>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import { exportEventReport, getEvent } from "../api/events";
import AppShell from "../components/AppShell.vue";

const route = useRoute();
const detail = ref(null);

onMounted(async () => {
  const response = await getEvent(route.params.id);
  detail.value = response.data;
});

async function reserveExport() {
  await exportEventReport(route.params.id, "html");
}
</script>

