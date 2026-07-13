<template>
  <div class="welcome-container p-6 space-y-6">
    <!-- 头部横幅 -->
    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-gradient-to-r from-blue-500/10 to-indigo-500/5 p-6 rounded-2xl border border-blue-500/10">
      <div>
        <h1 class="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
          <span>舆情事件看板</span>
        </h1>
        <p class="text-sm text-slate-500 dark:text-slate-400 mt-1">
          实时监测、清洗与智能分析全网舆情热点事件。
        </p>
      </div>
      <div class="flex gap-2">
        <el-button
          v-if="isAdmin"
          type="primary"
          size="large"
          @click="triggerCrawl"
        >手动触发全网采集</el-button>
        <el-button type="primary" size="large" plain @click="$router.push('/analysis')">
          新建事件分析 →
        </el-button>
      </div>
    </div>

    <!-- 日期导航条 -->
    <div class="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/60 dark:border-slate-800/60 shadow-sm p-3">
      <div class="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin">
        <span
          class="shrink-0 text-xs px-3 py-1.5 rounded-full cursor-pointer font-medium transition-colors"
          :class="activeDate === '' ? 'bg-blue-500 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'"
          @click="filterByDate('')"
        >全部 ({{ eventsStore.total }})</span>
        <span
          v-for="d in dateList"
          :key="d.date"
          class="shrink-0 text-xs px-3 py-1.5 rounded-full cursor-pointer transition-colors"
          :class="activeDate === d.date ? 'bg-blue-500 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'"
          @click="filterByDate(d.date)"
        >{{ formatDate(d.date) }} ({{ d.count }})</span>
      </div>
    </div>

    <!-- 今日热点 Top10 -->
    <div v-if="dailyHot.length > 0 && activeDate === ''" class="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/60 dark:border-slate-800/60 shadow-sm p-4">
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
          {{ item.title?.slice(0, 18) }}{{ (item.title || '').length > 18 ? '...' : '' }}
        </span>
        <span v-if="dailyHotLoading" class="text-xs text-slate-400">加载中...</span>
      </div>
    </div>

    <!-- 搜索 + 排序 + 清除 -->
    <div class="flex flex-col md:flex-row gap-3 items-stretch md:items-center bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200/60 dark:border-slate-800/60 shadow-sm">
      <div class="flex gap-2 flex-1">
        <el-input
          v-model="keyword"
          placeholder="输入事件关键词搜索"
          clearable
          size="large"
          @keyup.enter="handleSearch"
          @clear="clearFilter"
          class="max-w-[280px]"
        >
          <template #prefix><span class="text-slate-400">🔍</span></template>
        </el-input>
        <el-button type="primary" size="large" @click="handleSearch">搜索</el-button>
        <el-button v-if="keyword || activeDate" size="large" @click="clearFilter">清除筛选</el-button>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <span class="text-sm text-slate-400 whitespace-nowrap">排序:</span>
        <el-select v-model="sortBy" size="large" style="min-width: 160px">
          <el-option label="按综合热度" value="heat" />
          <el-option label="按发布时间" value="time" />
        </el-select>
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
        <p class="text-slate-400 mt-4 text-sm">{{ keyword ? '未找到匹配事件' : '暂无舆情事件，请输入关键词并点击搜索。' }}</p>
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
const activeDate = ref(""); // 空 = 全部
const allEvents = ref<any[]>([]); // 缓存全部事件用于日期提取

const isAdmin = computed(() => userStore.roles.includes("admin"));

const dailyHot = ref<any[]>([]);
const dailyHotLoading = ref(false);

// 从事件提取日期列表
const dateList = computed(() => {
  const map: Record<string, number> = {};
  for (const e of allEvents.value) {
    const d = (e.first_publish_time || "").slice(0, 10);
    if (d) map[d] = (map[d] || 0) + 1;
  }
  return Object.entries(map)
    .sort((a, b) => b[0].localeCompare(a[0]))
    .slice(0, 14)
    .map(([date, count]) => ({ date, count }));
});

function formatDate(iso: string) {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

async function loadDailyHot() {
  dailyHotLoading.value = true;
  try {
    const res = await getTodayHotspots(10);
    dailyHot.value = res.data?.items || res.data?.hotspots || [];
  } catch { dailyHot.value = []; }
  finally { dailyHotLoading.value = false; }
}

async function filterByDate(date: string) {
  activeDate.value = date;
  keyword.value = "";
  if (date) {
    // 用日期过滤（后端 API 支持 keyword 参数的模糊匹配不够精确，客户端过滤）
    await eventsStore.loadEvents({ size: 100 });
    allEvents.value = [...eventsStore.events];
    eventsStore.events = allEvents.value.filter(e =>
      (e.first_publish_time || "").startsWith(date)
    );
    eventsStore.total = eventsStore.events.length;
  } else {
    await eventsStore.loadEvents();
    allEvents.value = [...eventsStore.events];
  }
}

async function searchDailyHot(title: string) {
  keyword.value = title;
  activeDate.value = "";
  await eventsStore.loadEvents({ keyword: title });
  allEvents.value = [...eventsStore.events];
}

function clearFilter() {
  keyword.value = "";
  activeDate.value = "";
  eventsStore.loadEvents().then(() => { allEvents.value = [...eventsStore.events]; });
}

onMounted(async () => {
  await eventsStore.loadEvents({ size: 100 });
  allEvents.value = [...eventsStore.events];
  loadDailyHot();
});

async function handleSearch() {
  const kw = keyword.value.trim();
  activeDate.value = "";
  try {
    if (kw) {
      message(`已向系统提交「${kw}」采集任务...`, { type: "info" });
      await searchCrawler(kw);
    }
    await eventsStore.loadEvents({ keyword: kw, size: 100 });
    allEvents.value = [...eventsStore.events];
    message("事件看板刷新成功", { type: "success" });
  } catch { message("操作失败", { type: "error" }); }
}

async function triggerCrawl() {
  try {
    message("正在创建后台爬虫任务...", { type: "info" });
    const resp = await triggerCrawler({});
    message(`任务已启动 ID: ${resp.data.task_id}`, { type: "success" });
    await eventsStore.loadEvents({ size: 100 });
    allEvents.value = [...eventsStore.events];
  } catch { message("启动失败", { type: "error" }); }
}

const sortedEvents = computed(() => {
  const list = [...eventsStore.events];
  if (sortBy.value === "time") {
    return list.sort((a, b) => new Date(b.first_publish_time || 0).getTime() - new Date(a.first_publish_time || 0).getTime());
  }
  return list.sort((a, b) => (b.heat_index || 0) - (a.heat_index || 0));
});
</script>

<style scoped>
.welcome-container {
  min-height: calc(100vh - 120px);
}
</style>
