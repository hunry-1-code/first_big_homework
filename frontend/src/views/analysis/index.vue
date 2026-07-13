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
            <span class="text-xs text-slate-400 font-normal ml-2">（不选则自动使用全部可用平台）</span>
          </label>
          <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <div
              v-for="p in SEARCH_PLATFORMS"
              :key="p.id"
              :class="[
                'platform-card relative flex flex-col items-center gap-2 p-4 rounded-xl border-2 cursor-pointer transition-all duration-200',
                selectedPlatforms.includes(p.id)
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30 shadow-sm'
                  : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-600',
                state === 'running' ? 'pointer-events-none opacity-60' : ''
              ]"
              @click="togglePlatform(p.id)"
            >
              <div
                v-if="selectedPlatforms.includes(p.id)"
                class="absolute top-2 right-2 w-5 h-5 rounded-full bg-blue-500 flex items-center justify-center"
              >
                <span class="text-white text-xs">✓</span>
              </div>
              <IconifyIconOffline :icon="p.icon" class="text-2xl" :style="{ color: p.color }" />
              <span class="text-sm font-medium text-slate-700 dark:text-slate-200">{{ p.name }}</span>
              <span
                v-if="!p.always"
                class="text-[10px] px-1.5 py-0.5 rounded text-slate-400 bg-slate-100 dark:bg-slate-800"
                :title="'需要配置 ' + p.needKey"
              >
                {{ p.needKey }}
              </span>
              <span v-else class="text-[10px] px-1.5 py-0.5 rounded text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30">
                直接可用
              </span>
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
        <div class="flex gap-3 pt-2 border-t border-slate-100 dark:border-slate-800/60">
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
          <el-button
            v-if="state === 'running' || state === 'completed' || state === 'failed'"
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

      <el-steps :active="pipelineStage" align-center finish-status="success">
        <el-step title="网络爬取" description="从各平台采集数据">
          <template #icon>
            <span v-if="pipelineStage > 0">✓</span>
            <span v-else-if="pipelineStage === 0" class="animate-pulse">🔍</span>
            <span v-else>🔍</span>
          </template>
        </el-step>
        <el-step title="内容分析" description="TF-IDF + BGE向量">
          <template #icon>
            <span v-if="pipelineStage > 1">✓</span>
            <span v-else-if="pipelineStage === 1" class="animate-pulse">📊</span>
            <span v-else>📊</span>
          </template>
        </el-step>
        <el-step title="事件聚合" description="多维聚类生成事件">
          <template #icon>
            <span v-if="pipelineStage > 2">✓</span>
            <span v-else-if="pipelineStage === 2" class="animate-pulse">🧩</span>
            <span v-else>🧩</span>
          </template>
        </el-step>
        <el-step title="情感分析" description="LLM + SnowNLP">
          <template #icon>
            <span v-if="pipelineStage > 3">✓</span>
            <span v-else-if="pipelineStage === 3" class="animate-pulse">💚</span>
            <span v-else>💚</span>
          </template>
        </el-step>
      </el-steps>

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
        <div class="mt-3 p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
          <span class="text-sm text-slate-600 dark:text-slate-300">{{ taskMessage }}</span>
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
          <el-button type="primary" @click="resetForm">重新分析</el-button>
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
      <TaskList :tasks="myTasks" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, computed } from "vue";
import { useRouter } from "vue-router";
import { searchCrawler } from "@/api/crawler";
import { getMyTasks, getTask } from "@/api/tasks";
import IconifyIconOffline from "@/components/ReIcon/src/iconifyIconOffline";
import TaskList from "@/components/TaskList.vue";
import { message } from "@/utils/message";
import { SEARCH_PLATFORMS } from "@/constants/platforms";

defineOptions({
  name: "EventAnalysis"
});

const router = useRouter();

// 表单状态
const keyword = ref("");
const selectedPlatforms = ref<string[]>([]);
const targetCount = ref(100);

// 任务状态
const state = ref<"idle" | "running" | "completed" | "failed">("idle");
const currentTaskId = ref<number | null>(null);
const taskProgress = ref(0);
const taskMessage = ref("");
const taskResult = ref<any>(null);
const pipelineStage = ref(0);
const myTasks = ref<any[]>([]);

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
}

function inferPipelineStage(stages: any[], progress: number): number {
  if (progress >= 100) return 4;
  if (!stages || stages.length === 0) return 0;
  const done = stages.filter((s: any) => s.status === 'done').map((s: any) => s.stage);
  if (done.includes('sentiment') || done.includes('publish')) return 3;
  if (done.includes('aggregation')) return 2;
  if (done.includes('content_analysis')) return 1;
  if (done.includes('crawl') || done.includes('preprocess')) return 0;
  return 0;
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
      pipelineStage.value = inferPipelineStage(task.stages || [], task.progress || 0);

      if (task.status === "success") {
        taskResult.value = task.result || {};
        taskProgress.value = 100;
        pipelineStage.value = 4;
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
    const res = await searchCrawler(kw, platforms, targetCount.value);

    const data = res.data || res;
    const taskId = data.task_id;

    if (data.cached) {
      // 命中24h缓存，直接完成
      taskMessage.value = "已复用 24 小时内相同关键词的分析结果";
      taskProgress.value = 100;
      pipelineStage.value = 4;
      state.value = "completed";
      message("命中缓存，直接返回已有分析结果", { type: "success" });
      return;
    }

    if (data.reused) {
      message("已存在相同的近期分析任务，正在追踪进度...", { type: "info" });
    }

    if (taskId) {
      currentTaskId.value = taskId;
      taskMessage.value = "任务已提交，正在准备采集...";
      startPolling(taskId);
    } else if (data.stale) {
      // 过期缓存，后台刷新中
      taskMessage.value = "返回过期缓存结果，后台正在增量刷新";
      taskProgress.value = 100;
      pipelineStage.value = 4;
      state.value = "completed";
      message("已返回近期结果，后台正在更新", { type: "info" });
    }
  } catch (err: any) {
    const errMsg = err?.response?.data?.message || err?.message || "提交分析任务失败";
    message(errMsg, { type: "error" });
    state.value = "failed";
    taskMessage.value = errMsg;
  }
}

// 查看结果 - 跳转到看板用关键词筛选
function viewResults() {
  router.push({ path: "/dashboard", query: { keyword: keyword.value } });
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

onMounted(() => {
  loadMyTasks();
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
