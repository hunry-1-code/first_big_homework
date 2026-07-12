<template>
  <div class="admin-dashboard-container p-6 space-y-6">
    <!-- 头部横幅 -->
    <div class="flex justify-between items-center bg-white dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800/60 p-6 rounded-2xl shadow-sm">
      <div>
        <h1 class="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
          <span>⚙️ 系统管理中心</span>
        </h1>
        <p class="text-sm text-slate-500 dark:text-slate-400 mt-1">
          管理系统底座的网络爬虫节点、进行模拟事件导入及全局异步任务流水监控。
        </p>
      </div>
      <el-button type="primary" size="large" @click="loadData">
        刷新所有状态
      </el-button>
    </div>

    <!-- 中间运行网格 -->
    <el-row :gutter="24">
      <!-- 爬虫底座监控 -->
      <el-col :xs="24" :lg="12" class="mb-6">
        <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl h-full flex flex-col">
          <template #header>
            <div class="font-bold text-slate-800 dark:text-slate-100 flex justify-between items-center">
              <span>🕷️ 爬虫运行底座状态监控</span>
              <el-button type="warning" size="small" @click="handleManualTrigger">
                手动触发全网爬取
              </el-button>
            </div>
          </template>

          <div v-loading="statusLoading" class="flex-1 flex flex-col">
            <div class="bg-slate-950 dark:bg-black rounded-lg p-4 font-mono text-xs text-emerald-400 overflow-auto flex-1 min-h-[250px] shadow-inner border border-slate-900 leading-relaxed">
              <pre class="whitespace-pre-wrap">{{ JSON.stringify(crawlerStatus, null, 2) }}</pre>
            </div>
            <p class="text-xs text-slate-400 dark:text-slate-500 mt-3 leading-snug">
              提示：上图展示了后台系统在各大数据源平台（如微博、今日头条、知乎等）监控到的总条目计数、上次同步时间及任务健康指数。
            </p>
          </div>
        </el-card>
      </el-col>

      <!-- 样例数据智能导入 -->
      <el-col :xs="24" :lg="12" class="mb-6">
        <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl h-full flex flex-col">
          <template #header>
            <div class="font-bold text-slate-800 dark:text-slate-100 flex justify-between items-center">
              <span>📥 舆情样例数据导入</span>
              <el-button type="success" size="small" @click="handleLoadDemo">
                载入模版样例
              </el-button>
            </div>
          </template>

          <div class="flex-1 flex flex-col space-y-4">
            <p class="text-xs text-slate-400 dark:text-slate-500 leading-normal">
              粘贴事件的 JSON 数组结构。系统会自动校验数据模型（包含标题、热度指数、涉事属性及情感比例等），校验成功后将拉起后台导入异步任务进行批量导入。
            </p>

            <el-input
              v-model="jsonText"
              type="textarea"
              :rows="11"
              resize="none"
              placeholder="请输入标准的 JSON 数组，例如: [{ 'title': '舆情事件', 'summary': '...' }]"
              class="font-mono text-sm"
            />

            <div class="flex justify-end pt-2 border-t border-slate-100 dark:border-slate-800/60">
              <el-button
                type="primary"
                size="large"
                :loading="importing"
                :disabled="!jsonText.trim() || jsonText.trim() === '[]'"
                @click="handleImport"
              >
                开始校验并导入
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 底部：系统全局异步任务列表 -->
    <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
      <template #header>
        <div class="font-bold text-slate-800 dark:text-slate-100">
          ⚙️ 系统全局异步任务调度中心 (Global Task Scheduler)
        </div>
      </template>

      <div v-loading="tasksLoading">
        <TaskList :tasks="allTasks" />
        <div v-if="allTasks.length === 0" class="flex flex-col items-center justify-center py-10 text-slate-400 text-sm">
          <span>📭</span>
          <p class="mt-2">系统当前没有任何后台任务调度记录</p>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { getCrawlerStatus, triggerCrawler } from "@/api/crawler";
import { importJsonDocuments } from "@/api/importData";
import { getAllTasks } from "@/api/tasks";
import TaskList from "@/components/TaskList.vue";
import { message } from "@/utils/message";

defineOptions({
  name: "OpinionAdmin"
});

const crawlerStatus = ref<any>({});
const allTasks = ref<any[]>([]);
const jsonText = ref("[]");

const statusLoading = ref(false);
const tasksLoading = ref(false);
const importing = ref(false);

onMounted(() => {
  loadData();
});

// 加载全局状态
async function loadData() {
  statusLoading.value = true;
  tasksLoading.value = true;
  try {
    const [statusResp, taskResp] = await Promise.all([
      getCrawlerStatus(),
      getAllTasks()
    ]);
    crawlerStatus.value = statusResp.data;
    allTasks.value = taskResp.data.tasks;
  } catch (err) {
    message("获取系统后台状态失败", { type: "error" });
  } finally {
    statusLoading.value = false;
    tasksLoading.value = false;
  }
}

// 手动触发采集
async function handleManualTrigger() {
  try {
    message("正在创建全网后台采集任务...", { type: "info" });
    const response = await triggerCrawler({});
    message(`采集任务已启动！任务ID: ${response.data.task_id}`, { type: "success" });
    await loadData();
  } catch (err) {
    message("触发爬虫任务失败", { type: "error" });
  }
}

// 载入 Demo 样例模版
function handleLoadDemo() {
  const demoData = [
    {
      title: "某地网络产品数据泄露舆情事件",
      summary: "某科技公司近期被曝光存在严重的用户隐私数据泄露，引起社交媒体平台网友的大量讨论和声讨。",
      heat_index: 82.3,
      lifecycle_stage: "高潮期",
      sentiment_positive: 0.12,
      sentiment_neutral: 0.28,
      sentiment_negative: 0.60
    }
  ];
  jsonText.value = JSON.stringify(demoData, null, 2);
  message("已载入事件 JSON 模版数据", { type: "info" });
}

// 开始导入校验并导入
async function handleImport() {
  importing.value = true;
  try {
    const docs = JSON.parse(jsonText.value);
    if (!Array.isArray(docs)) {
      message("输入格式错误：必须是一个 JSON 数组形式", { type: "error" });
      importing.value = false;
      return;
    }
    const response = await importJsonDocuments(docs);
    message(`数据校验通过，批量导入异步任务创建成功！任务ID: ${response.data.task_id}`, { type: "success" });
    jsonText.value = "[]";
    await loadData();
  } catch (err: any) {
    const errMsg = err.response?.data?.message || err.message || "JSON 校验解析失败，请检查格式";
    message(errMsg, { type: "error" });
  } finally {
    importing.value = false;
  }
}
</script>

<style scoped>
.admin-dashboard-container {
  min-height: calc(100vh - 120px);
}
</style>
