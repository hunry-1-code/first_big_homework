<template>
  <AppShell>
    <div class="page-header">
      <div>
        <h1 class="page-title">系统管理</h1>
        <p class="muted">采集、导入和后台任务。</p>
      </div>
      <el-button type="primary" @click="load">刷新</el-button>
    </div>

    <div class="grid">
      <section class="surface">
        <h2>爬虫状态</h2>
        <pre>{{ status }}</pre>
        <el-button type="primary" @click="trigger">手动采集</el-button>
      </section>

      <section class="surface">
        <h2>JSON 样例导入</h2>
        <el-input v-model="jsonText" type="textarea" :rows="8" />
        <el-button type="primary" style="margin-top: 12px" @click="importJson">导入</el-button>
      </section>

      <section class="surface">
        <h2>系统任务</h2>
        <TaskList :tasks="tasks" />
      </section>
    </div>
  </AppShell>
</template>

<script setup>
import { onMounted, ref } from "vue";

import { getCrawlerStatus, triggerCrawler } from "../api/crawler";
import { importJsonDocuments } from "../api/importData";
import { getAllTasks } from "../api/tasks";
import AppShell from "../components/AppShell.vue";
import TaskList from "../components/TaskList.vue";

const status = ref({});
const tasks = ref([]);
const jsonText = ref("[]");

onMounted(load);

async function load() {
  const [statusResp, taskResp] = await Promise.all([getCrawlerStatus(), getAllTasks()]);
  status.value = statusResp.data;
  tasks.value = taskResp.data.tasks;
}

async function trigger() {
  await triggerCrawler({});
  await load();
}

async function importJson() {
  const documents = JSON.parse(jsonText.value || "[]");
  await importJsonDocuments(documents);
  await load();
}
</script>
