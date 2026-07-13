<template>
  <div class="welcome-container p-6 space-y-6">
    <!-- 头部横幅与手动采集 -->
    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-gradient-to-r from-blue-500/10 to-indigo-500/5 p-6 rounded-2xl border border-blue-500/10">
      <div>
        <h1 class="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
          <span>舆情事件看板</span>
        </h1>
        <p class="text-sm text-slate-500 dark:text-slate-400 mt-1">
          实时监测、清洗与智能分析全网舆情热点事件。
        </p>
      </div>
      <el-button
        v-if="isAdmin"
        type="primary"
        size="large"
        class="shadow-md shadow-blue-500/20"
        @click="triggerCrawl"
      >
        <span class="flex items-center gap-1.5">
          <span>手动触发全网采集</span>
        </span>
      </el-button>
    </div>

    <!-- 搜索与排序工具栏 -->
    <div class="flex flex-col md:flex-row gap-4 items-stretch md:items-center bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200/60 dark:border-slate-800/60 shadow-sm">
      <div class="flex gap-2">
        <el-input
          v-model="keyword"
          placeholder="输入事件关键词搜索"
          clearable
          size="large"
          @keyup.enter="handleSearch"
          class="w-[280px]"
        >
          <template #prefix>
            <span class="text-slate-400">🔍</span>
          </template>
        </el-input>
        <el-button type="primary" size="large" @click="handleSearch">
          搜索 / 采集
        </el-button>
        <el-button
          type="primary"
          size="large"
          plain
          @click="$router.push('/analysis')"
        >
          新建事件分析 →
        </el-button>
      </div>

      <div class="flex items-center gap-2 shrink-0">
        <span class="text-sm text-slate-400 dark:text-slate-500 whitespace-nowrap">排序依据:</span>
        <el-select v-model="sortBy" size="large" style="min-width: 180px">
          <el-option label="按发布时间" value="time" />
          <el-option label="按综合热度" value="heat" />
        </el-select>
      </div>
    </div>

    <!-- 今日热点 Top10 -->
    <div v-if="dailyHot.length > 0" class="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/60 dark:border-slate-800/60 shadow-sm p-4">
      <div class="flex items-center gap-2 mb-3">
        <span class="font-bold text-slate-800 dark:text-slate-100">🔥 今日热点</span>
        <span class="text-xs text-slate-400">实时热榜 Top10</span>
      </div>
      <div class="flex flex-wrap gap-2">
        <span
          v-for="(item, idx) in dailyHot"
          :key="idx"
          class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full cursor-pointer transition-colors"
          :class="idx < 3 ? 'bg-orange-50 text-orange-600 dark:bg-orange-950/30 dark:text-orange-400 font-medium' : 'bg-slate-50 text-slate-500 dark:bg-slate-800 dark:text-slate-400'"
          @click="searchDailyHot(item.title)"
        >
          <span class="font-bold">{{ idx + 1 }}</span>
          {{ item.title?.slice(0, 20) }}{{ (item.title || '').length > 20 ? '...' : '' }}
        </span>
        <span v-if="dailyHotLoading" class="text-xs text-slate-400">加载中...</span>
      </div>
    </div>

    <!-- 事件网格列表 -->
    <div v-loading="eventsStore.loading">
      <div v-if="sortedEvents.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <EventCard
          v-for="event in sortedEvents"
          :key="event.id"
          :event="event"
        />
      </div>
      
      <div v-else class="flex flex-col items-center justify-center py-20 bg-white dark:bg-slate-900 rounded-xl border border-slate-200/60 dark:border-slate-800/60">
        <span class="text-4xl">📭</span>
        <p class="text-slate-400 mt-4 text-sm">暂无舆情事件，请输入关键词并点击搜索/采集。</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useEventsStore } from "@/store/modules/events";
import { useUserStore } from "@/store/modules/user";
import { searchCrawler, triggerCrawler } from "@/api/crawler";
import { getTodayHotspots } from "@/api/dailyHot";
import EventCard from "@/components/EventCard.vue";
import { message } from "@/utils/message";

defineOptions({
  name: "OpinionBoard"
});

const eventsStore = useEventsStore();
const userStore = useUserStore();

const keyword = ref("");
const sortBy = ref<"time" | "heat">("heat");

const isAdmin = computed(() => {
  return userStore.roles.includes("admin");
});

const dailyHot = ref<any[]>([]);
const dailyHotLoading = ref(false);

async function loadDailyHot() {
  dailyHotLoading.value = true;
  try {
    const res = await getTodayHotspots(10);
    dailyHot.value = res.data?.items || res.data?.hotspots || [];
  } catch { dailyHot.value = []; }
  finally { dailyHotLoading.value = false; }
}

function searchDailyHot(title: string) {
  keyword.value = title;
  handleSearch();
}

onMounted(() => {
  eventsStore.loadEvents();
  loadDailyHot();
});

// 搜索/采集
async function handleSearch() {
  const kw = keyword.value.trim();
  try {
    if (kw) {
      message(`已向系统提交「${kw}」敏感词采集任务...`, { type: "info" });
      await searchCrawler(kw);
    }
    await eventsStore.loadEvents({ keyword: kw });
    message("事件看板刷新成功", { type: "success" });
  } catch (err) {
    message("操作失败，请重试", { type: "error" });
  }
}

// 手动采集
async function triggerCrawl() {
  try {
    message("正在创建后台网络爬虫采集任务...", { type: "info" });
    const response = await triggerCrawler({});
    message(`采集任务启动成功！任务ID: ${response.data.task_id}`, { type: "success" });
    await eventsStore.loadEvents();
  } catch (err) {
    message("启动采集任务失败", { type: "error" });
  }
}

// 排序逻辑
const sortedEvents = computed(() => {
  const list = [...eventsStore.events];
  if (sortBy.value === "time") {
    // 越新的ID越靠前（表示最新时间）
    return list.sort((a, b) => b.id - a.id);
  } else {
    // 综合热度降序
    return list.sort((a, b) => (b.heat_index || 0) - (a.heat_index || 0));
  }
});
</script>

<style scoped>
.welcome-container {
  min-height: calc(100vh - 120px);
}
</style>
