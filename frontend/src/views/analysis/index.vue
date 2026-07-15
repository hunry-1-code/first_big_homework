<template>
  <div class="analysis-container p-6 space-y-6">
    <!-- 头部横幅 -->
    <div class="flex justify-between items-center bg-white dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800/60 p-6 rounded-2xl shadow-sm">
      <div>
        <h1 class="text-2xl font-bold text-slate-800 dark:text-slate-100">🎯 事件定向分析</h1>
        <p class="text-sm text-slate-500 dark:text-slate-400 mt-1">
          输入关键词，选择监测平台，系统自动完成网络爬取、内容分析、事件聚合和情感分析全链路处理
        </p>
      </div>
      <el-button text @click="$router.push('/dashboard')" class="!text-gray-500 hover:!text-blue-500">
        ← 返回看板
      </el-button>
    </div>

    <!-- 分析配置表单 -->
    <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
      <template #header>
        <div class="font-bold text-slate-800 dark:text-slate-100">📋 分析配置</div>
      </template>

      <div class="space-y-6">
        <!-- 关键词 -->
        <div>
          <label class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
            事件关键词 <span class="text-red-500">*</span>
          </label>
          <el-input
            v-model="keyword"
            placeholder="输入要分析的事件关键词，例如：疫苗安全、AI监管..."
            size="large"
            clearable
            :disabled="state === 'running'"
            @keyup.enter="startAnalysis"
          >
            <template #prefix>
              <span class="text-slate-400">🔍</span>
            </template>
          </el-input>
        </div>

        <!-- 监测平台选择 -->
        <div>
          <label class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-3">
            监测平台 <span class="text-red-500">*</span>
            <span class="text-xs text-slate-400 font-normal ml-2">（不选则自动使用全部可用平台，共 {{ availablePlatforms.length }} 个）</span>
          </label>
          <!-- 社交平台 -->
          <div class="text-xs font-medium text-slate-400 mb-2 mt-1">社交平台</div>
          <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
            <div v-for="p in socialPlatforms" :key="p.id" class="platform-card relative flex flex-col items-center gap-2 p-4 rounded-xl border-2 cursor-pointer transition-all duration-200"
              :class="selectedPlatforms.includes(p.id) ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30 shadow-sm' : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-600'"
              :style="state === 'running' ? 'pointer-events:none;opacity:0.6' : ''"
              @click="togglePlatform(p.id)">
              <div v-if="selectedPlatforms.includes(p.id)" class="absolute top-2 right-2 w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center"><span class="text-white text-xs">✓</span></div>
              <IconifyIconOffline :icon="p.icon" class="text-2xl" :style="{ color: p.color }" />
              <span class="text-sm font-medium text-slate-700 dark:text-slate-200">{{ p.name }}</span>
            </div>
          </div>
          <!-- 搜索引擎 -->
          <div class="text-xs font-medium text-slate-400 mb-2 mt-4">搜索引擎</div>
          <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
            <div v-for="p in searchPlatforms" :key="p.id" class="platform-card relative flex flex-col items-center gap-2 p-4 rounded-xl border-2 cursor-pointer transition-all duration-200"
              :class="selectedPlatforms.includes(p.id) ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30 shadow-sm' : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-600'"
              :style="state === 'running' ? 'pointer-events:none;opacity:0.6' : ''"
              @click="togglePlatform(p.id)">
              <div v-if="selectedPlatforms.includes(p.id)" class="absolute top-2 right-2 w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center"><span class="text-white text-xs">✓</span></div>
              <IconifyIconOffline :icon="p.icon" class="text-2xl" :style="{ color: p.color }" />
              <span class="text-sm font-medium text-slate-700 dark:text-slate-200">{{ p.name }}</span>
            </div>
          </div>
          <!-- 新闻媒体 -->
          <div class="text-xs font-medium text-slate-400 mb-2 mt-4">新闻媒体 <span class="text-slate-300">（RSS订阅源，不支持关键词搜索，返回最新资讯）</span></div>
          <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <div v-for="p in newsPlatforms" :key="p.id" class="platform-card relative flex flex-col items-center gap-2 p-4 rounded-xl border-2 cursor-pointer transition-all duration-200"
              :class="selectedPlatforms.includes(p.id) ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30 shadow-sm' : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-600'"
              :style="state === 'running' ? 'pointer-events:none;opacity:0.6' : ''"
              @click="togglePlatform(p.id)">
              <div v-if="selectedPlatforms.includes(p.id)" class="absolute top-2 right-2 w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center"><span class="text-white text-xs">✓</span></div>
              <IconifyIconOffline :icon="p.icon" class="text-2xl" :style="{ color: p.color }" />
              <span class="text-sm font-medium text-slate-700 dark:text-slate-200">{{ p.name }}</span>
            </div>
          </div>
        </div>

        <!-- 采集数量 -->
        <div>
          <label class="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
            采集总量：<span class="text-blue-500 font-bold">{{ targetCount }}</span> 条（所有平台合计）
          </label>
          <el-slider
            v-model="targetCount"
            :min="10"
            :max="200"
            :step="10"
            :disabled="state === 'running'"
            show-stops
            :marks="{ 10: '10', 50: '50', 100: '100', 150: '150', 200: '200' }"
          />
        </div>

        <!-- 操作按钮 -->
        <div class="flex gap-3 pt-2 border-t border-slate-100 dark:border-slate-800/60 items-center">
          <el-button
            type="primary"
            size="large"
            :loading="state === 'running'"
            :disabled="!keyword.trim()"
            @click="startAnalysis"
          >
            <span v-if="state === 'running'" class="flex items-center gap-1.5">
              <el-icon class="animate-spin"><IconifyIconOffline icon="ep:loading" /></el-icon>
              分析中...
            </span>
            <span v-else class="flex items-center gap-1.5">
              🚀 开始定向分析
            </span>
          </el-button>
          <el-checkbox
            v-if="state !== 'running'"
            v-model="forceRefresh"
            :disabled="!keyword.trim()"
            class="!mr-0"
          >
            <span class="text-xs text-slate-400">强制刷新（跳过缓存）</span>
          </el-checkbox>
          <el-button
            v-if="state === 'completed' || state === 'failed'"
            size="large"
            @click="resetForm"
          >
            新建分析
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 分析进度（运行中） -->
    <el-card
      v-if="state === 'running'"
      shadow="never"
      class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl"
    >
      <template #header>
        <div class="font-bold text-slate-800 dark:text-slate-100">⏳ 分析进度</div>
      </template>

      <div class="overflow-x-auto pb-2">
      <el-steps :active="pipelineStage" align-center finish-status="success" class="min-w-[700px]">
        <el-step title="网络爬取" :description="stageDescription('crawl')">
          <template #icon>
            <span v-if="isStageDone('crawl')">✓</span>
            <span v-else-if="isStageRunning('crawl')" class="animate-pulse">🔍</span>
            <span v-else>🔍</span>
          </template>
        </el-step>
        <el-step title="文本预处理" :description="stageDescription('preprocess')">
          <template #icon>
            <span v-if="isStageDone('preprocess')">✓</span>
            <span v-else-if="isStageRunning('preprocess')" class="animate-pulse">🔄</span>
            <span v-else>🔄</span>
          </template>
        </el-step>
        <el-step title="内容分析" :description="stageDescription('content_analysis')">
          <template #icon>
            <span v-if="isStageDone('content_analysis')">✓</span>
            <span v-else-if="isStageRunning('content_analysis')" class="animate-pulse">📊</span>
            <span v-else>📊</span>
          </template>
        </el-step>
        <el-step title="事件聚合" :description="stageDescription('aggregation')">
          <template #icon>
            <span v-if="isStageDone('aggregation')">✓</span>
            <span v-else-if="isStageRunning('aggregation')" class="animate-pulse">🧩</span>
            <span v-else>🧩</span>
          </template>
        </el-step>
        <el-step title="情感分析" :description="stageDescription('sentiment')">
          <template #icon>
            <span v-if="isStageDone('sentiment')">✓</span>
            <span v-else-if="isStageRunning('sentiment')" class="animate-pulse">💚</span>
            <span v-else>💚</span>
          </template>
        </el-step>
        <el-step title="事件发布" :description="stageDescription('publish')">
          <template #icon>
            <span v-if="isStageDone('publish')">✓</span>
            <span v-else-if="isStageRunning('publish')" class="animate-pulse">📤</span>
            <span v-else>📤</span>
          </template>
        </el-step>
      </el-steps>
      </div>

      <div class="mt-6 px-4">
        <div class="flex justify-between text-sm mb-2">
          <span class="text-slate-500 dark:text-slate-400">总体进度</span>
          <span class="text-blue-500 font-bold">{{ taskProgress }}%</span>
        </div>
        <el-progress
          :percentage="taskProgress"
          :stroke-width="8"
          :color="taskProgress >= 95 ? '#22c55e' : '#3b82f6'"
        />
        <div class="mt-3 p-3 bg-slate-50 dark:bg-slate-800 rounded-lg flex items-start gap-2">
          <span class="animate-pulse text-blue-500 shrink-0">●</span>
          <span class="text-sm text-slate-600 dark:text-slate-300">{{ taskMessage }}</span>
        </div>
        <!-- 阶段详情列表 -->
        <div v-if="stageRecords.length > 0" class="mt-3 space-y-1 max-h-48 overflow-y-auto">
          <div
            v-for="(rec, idx) in stageRecords"
            :key="idx"
            class="flex items-center gap-2 text-xs px-2 py-1 rounded"
            :class="rec.status === 'done' ? 'text-emerald-600 bg-emerald-50 dark:bg-emerald-950/20' : 'text-blue-500 bg-blue-50 dark:bg-blue-950/20'"
          >
            <span>{{ rec.status === 'done' ? '✅' : '⏳' }}</span>
            <span class="font-medium">{{ stageLabel(rec.stage) }}</span>
            <span v-if="rec.message" class="text-slate-400">· {{ rec.message }}</span>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 分析结果（完成） -->
    <el-card
      v-if="state === 'completed'"
      shadow="never"
      class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl"
    >
      <el-result
        icon="success"
        title="分析完成！"
        :sub-title="`关键词「${keyword}」的全链路分析已完成`"
      >
        <template #extra>
          <div class="flex justify-center gap-3">
            <el-button type="primary" size="large" @click="$router.push('/dashboard')">
              查看舆情看板
            </el-button>
            <el-button size="large" @click="viewResults">
              查看分析事件
            </el-button>
          </div>
        </template>
      </el-result>

      <div class="mt-6 px-6">
        <el-descriptions :column="2" border size="large">
          <el-descriptions-item label="采集文章数">
            <span class="text-blue-500 font-bold text-lg">{{ taskResult?.collected || 0 }}</span> 篇
          </el-descriptions-item>
          <el-descriptions-item label="成功处理">
            <span class="text-emerald-500 font-bold text-lg">{{ taskResult?.processed || 0 }}</span> 篇
          </el-descriptions-item>
          <el-descriptions-item label="覆盖平台">
            {{ Object.keys(taskResult?.platform_counts || {}).join('、') || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="分析状态">
            <el-tag type="success" size="small">全链路完成</el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>

    <!-- 分析结果（失败） -->
    <el-card
      v-if="state === 'failed'"
      shadow="never"
      class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl"
    >
      <el-result
        icon="error"
        title="分析失败"
        :sub-title="taskMessage || '任务执行过程中出现错误，请重试'"
      >
        <template #extra>
          <div class="flex justify-center gap-3">
            <el-button type="primary" :loading="retrying" @click="doRetryAnalysis">
              🔄 复用数据重新分析
            </el-button>
            <el-button @click="resetForm">新建分析</el-button>
          </div>
        </template>
      </el-result>
    </el-card>

    <!-- 历史任务列表 -->
    <el-card
      v-if="myTasks.length > 0"
      shadow="never"
      class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl"
    >
      <template #header>
        <div class="flex justify-between items-center">
          <span class="font-bold text-slate-800 dark:text-slate-100">📋 我的分析任务历史</span>
          <el-button text size="small" @click="loadMyTasks">刷新</el-button>
        </div>
      </template>
      <TaskList :tasks="myTasks" :retrying-task-id="retryingTaskId" @retry="handleTaskListRetry" @select="viewTaskDetail" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, computed } from "vue";
import { useRouter, useRoute } from "vue-router";
import { searchCrawler } from "@/api/crawler";
import { getMyTasks, getTask, retryAnalysis } from "@/api/tasks";
import IconifyIconOffline from "@/components/ReIcon/src/iconifyIconOffline";
import TaskList from "@/components/TaskList.vue";
import { message } from "@/utils/message";
import { SEARCH_PLATFORMS } from "@/constants/platforms";
import { apiClient } from "@/api/client";

defineOptions({
  name: "EventAnalysis"
});

const router = useRouter();
const route = useRoute();

// 表单状态
const keyword = ref((route.query.keyword as string) || "");
const selectedPlatforms = ref<string[]>([]);
const targetCount = ref(50);
const forceRefresh = ref(false);
const availablePlatforms = ref(SEARCH_PLATFORMS);

const socialPlatforms = computed(() => availablePlatforms.value.filter(p => ['bilibili','weibo','zhihu','xiaohongshu','douyin'].includes(p.id)));
const searchPlatforms = computed(() => availablePlatforms.value.filter(p => ['baidu','baidu_news'].includes(p.id)));
const newsPlatforms = computed(() => availablePlatforms.value.filter(p => p.id.startsWith('news_')));

async function loadPlatforms() {
  try {
    const res = await apiClient.get("/crawler/platforms");
    const ids: string[] = res.data?.platforms || [];
    // RSS源去重：如果已有同名news_源则跳过（如news_36kr已覆盖rss_36kr）
    const rssIds: string[] = (res.data?.rss || []).filter((r: string) => !ids.includes(r.replace('rss_', 'news_')));
    const allIds = [...ids, ...rssIds];
    const matched = SEARCH_PLATFORMS.filter(p => allIds.includes(p.id));
    if (matched.length > 0) availablePlatforms.value = matched;
  } catch {}
}

// 任务状态
const state = ref<"idle" | "running" | "completed" | "failed">("idle");
const currentTaskId = ref<number | null>(null);
const taskProgress = ref(0);
const taskMessage = ref("");
const taskResult = ref<any>(null);
const pipelineStage = ref(0);
const myTasks = ref<any[]>([]);
const stageRecords = ref<Array<{stage: string; status: string; message: string}>>([]);
const retrying = ref(false);
const retryingTaskId = ref<number | null>(null);

// 6 阶段顺序
const STAGE_ORDER = ["crawl", "preprocess", "content_analysis", "aggregation", "sentiment", "publish"];

function stageLabel(stage: string): string {
  const labels: Record<string, string> = {
    crawl: "网络爬取", preprocess: "文本预处理", content_analysis: "内容分析",
    aggregation: "事件聚合", sentiment: "情感分析", publish: "事件发布",
    done: "完成"
  };
  return labels[stage] || stage;
}

function stageDescription(stage: string): string {
  const descs: Record<string, string> = {
    crawl: "从各平台采集数据",
    preprocess: "清洗去重+质量评估",
    content_analysis: "TF-IDF + BGE向量",
    aggregation: "多维聚类生成事件",
    sentiment: "LLM + SnowNLP",
    publish: "发布到舆情看板"
  };
  return descs[stage] || "";
}

function isStageDone(stage: string): boolean {
  return stageRecords.value.some(s => s.stage === stage && s.status === "done");
}

function isStageRunning(stage: string): boolean {
  return stageRecords.value.some(s => s.stage === stage && s.status === "running");
}

function inferPipelineStage(stages: any[], progress: number): number {
  if (progress >= 100) return 5; // all done
  if (!stages || stages.length === 0) return 0;
  // 找到最后一个有状态的阶段索引
  const latestStage = stages[stages.length - 1]?.stage;
  const idx = STAGE_ORDER.indexOf(latestStage);
  if (idx >= 0) return idx;
  // fallback
  const done = stages.filter((s: any) => s.status === 'done').map((s: any) => s.stage);
  if (done.length === 0) return 0;
  for (let i = STAGE_ORDER.length - 1; i >= 0; i--) {
    if (done.includes(STAGE_ORDER[i])) return Math.min(i + 1, 5);
  }
  return 0;
}

let pollTimer: ReturnType<typeof setInterval> | null = null;

// 平台切换
function togglePlatform(id: string) {
  const idx = selectedPlatforms.value.indexOf(id);
  if (idx >= 0) {
    selectedPlatforms.value.splice(idx, 1);
  } else {
    selectedPlatforms.value.push(id);
  }
}

function resetForm() {
  stopPolling();
  state.value = "idle";
  currentTaskId.value = null;
  taskProgress.value = 0;
  taskMessage.value = "";
  taskResult.value = null;
  pipelineStage.value = 0;
  stageRecords.value = [];
}

// 轮询任务状态
function startPolling(taskId: number) {
  stopPolling();
  pollTimer = setInterval(async () => {
    try {
      const res = await getTask(taskId);
      const task = res.data;
      if (!task) return;

      taskProgress.value = task.progress || 0;
      taskMessage.value = task.summary || task.message || "";
      stageRecords.value = task.stages || [];
      pipelineStage.value = inferPipelineStage(task.stages || [], task.progress || 0);

      if (task.status === "success") {
        taskResult.value = task.result || {};
        taskProgress.value = 100;
        pipelineStage.value = 5;
        stageRecords.value = task.stages || [];
        state.value = "completed";
        stopPolling();
        message("事件分析完成！", { type: "success" });
      } else if (task.status === "failed") {
        taskMessage.value = task.message || "任务执行失败";
        state.value = "failed";
        stopPolling();
        message("分析任务失败", { type: "error" });
      }
    } catch {
      // 轮询失败不影响继续
    }
  }, 2000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// 开始分析
async function startAnalysis() {
  const kw = keyword.value.trim();
  if (!kw) {
    message("请输入事件关键词", { type: "warning" });
    return;
  }

  state.value = "running";
  taskProgress.value = 0;
  taskMessage.value = "正在提交分析任务...";
  pipelineStage.value = 0;

  try {
    const platforms = selectedPlatforms.value.length > 0 ? selectedPlatforms.value : undefined;
    const res = await searchCrawler(kw, platforms, targetCount.value, forceRefresh.value);

    const data = res.data || res;
    const taskId = data.task_id;

    if (data.cached) {
      // 命中短期缓存（2h内），提示可强制刷新
      taskMessage.value = data.message || "近期已有相同分析结果";
      taskProgress.value = 100;
      pipelineStage.value = 5;
      state.value = "completed";
      message("命中近期缓存。如需最新数据，请勾选「强制刷新」后重新提交", { type: "success", duration: 5000 });
      return;
    }

    if (data.stale) {
      // 过期缓存 + 后台刷新中
      taskMessage.value = data.message || "已有过期缓存，后台正在增量刷新";
      taskProgress.value = 100;
      pipelineStage.value = 5;
      state.value = "completed";
      message("已返回近期结果，后台正在补充最新数据。如需完全重新采集请勾选「强制刷新」", { type: "info", duration: 5000 });
      if (taskId) {
        currentTaskId.value = taskId;
        startPolling(taskId);
      }
      return;
    }

    if (data.reused) {
      message("已存在相同的近期分析任务，正在追踪进度...", { type: "info" });
    }

    if (taskId) {
      currentTaskId.value = taskId;
      taskMessage.value = "任务已提交，正在准备采集...";
      startPolling(taskId);
    }
  } catch (err: any) {
    const errMsg = err?.response?.data?.message || err?.message || "提交分析任务失败";
    message(errMsg, { type: "error" });
    state.value = "failed";
    taskMessage.value = errMsg;
  }
}

// 查看结果 - 跳转到看板并自动筛选该事件分析的关键词
function viewResults() {
  router.push({ path: "/dashboard", query: { sk: keyword.value } });
}

// 复用已有数据重新分析
async function doRetryAnalysis() {
  if (!currentTaskId.value) return;
  await retryTask(currentTaskId.value);
}

async function retryTask(taskId: number) {
  retrying.value = true;
  retryingTaskId.value = taskId;
  try {
    const res = await retryAnalysis(taskId);
    const data = res.data || res;
    const newTaskId = data.task_id;
    if (newTaskId) {
      currentTaskId.value = newTaskId;
      state.value = "running";
      taskProgress.value = 0;
      taskMessage.value = "正在复用已采集数据，开始重新分析...";
      pipelineStage.value = 0;
      stageRecords.value = [];
      startPolling(newTaskId);
      message("重新分析任务已启动，复用已采集数据", { type: "success" });
    }
  } catch (err: any) {
    const errMsg = err?.response?.data?.message || err?.message || "重新分析失败";
    message(errMsg, { type: "error" });
    retryingTaskId.value = null;
  } finally {
    retrying.value = false;
  }
}

// TaskList 中的重试按钮
function handleTaskListRetry(taskId: number) {
  retryTask(taskId);
}

// 加载我的任务
async function loadMyTasks() {
  try {
    const res = await getMyTasks();
    myTasks.value = (res.data?.tasks || []).slice(0, 20);
  } catch {
    // 静默失败
  }
}

// 点击历史任务查看详情
async function viewTaskDetail(taskId: number) {
  try {
    const res = await getTask(taskId);
    const task = res.data;
    if (!task) return;
    currentTaskId.value = taskId;
    taskProgress.value = task.progress || 0;
    taskMessage.value = task.summary || task.message || "";
    stageRecords.value = task.stages || [];
    taskResult.value = task.result || {};
    pipelineStage.value = inferPipelineStage(task.stages || [], task.progress || 0);
    // 从任务 payload 恢复关键词
    const kw = task.payload?.keyword;
    if (kw) keyword.value = kw;

    if (task.status === "running") {
      state.value = "running";
      startPolling(taskId);
    } else if (task.status === "success" || task.status === "completed") {
      state.value = "completed";
      stopPolling();
    } else if (task.status === "failed") {
      state.value = "failed";
      stopPolling();
    }
  } catch { /* ignore */ }
}

onMounted(async () => {
  loadPlatforms();
  await loadMyTasks();
  // 自动恢复：如果有正在运行的任务，恢复轮询
  const running = myTasks.value.find((t: any) => t.status === 'running');
  if (running) {
    viewTaskDetail(running.id);
  }
});

onBeforeUnmount(() => {
  stopPolling();
});
</script>

<style scoped>
.analysis-container {
  min-height: calc(100vh - 120px);
}

.platform-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
