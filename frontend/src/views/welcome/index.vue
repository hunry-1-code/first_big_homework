<template>
  <div class="welcome-container p-6 space-y-6">
    <!-- 头部横幅 -->
    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 p-6 rounded-2xl border"
      :class="activeSearchKw ? 'bg-gradient-to-r from-emerald-500/10 to-teal-500/5 border-emerald-500/20' : 'bg-gradient-to-r from-blue-500/10 to-indigo-500/5 border-blue-500/10'">
      <div>
        <h1 class="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
          <span v-if="activeSearchKw">🎯 事件分析</span>
          <span v-else>舆情事件看板</span>
        </h1>
        <p class="text-sm text-slate-500 dark:text-slate-400 mt-1">
          <template v-if="activeSearchKw">
            关键词「<b class="text-emerald-600">{{ activeSearchKw }}</b>」的分析结果，共 {{ realTotal }} 个事件
          </template>
          <template v-else>
            实时监测、清洗与智能分析全网舆情热点事件。共 {{ realTotal }} 个事件
          </template>
        </p>
      </div>
      <el-button type="primary" size="large" plain @click="$router.push('/analysis')">
        新建事件分析 →
      </el-button>
    </div>

    <!-- 事件分析来源 -->
    <div v-if="searchKeywordList.length > 0" class="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/60 dark:border-slate-800/60 shadow-sm p-3">
      <div class="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin">
        <span class="shrink-0 text-xs font-bold text-slate-500">🎯 事件分析</span>
        <span
          class="shrink-0 text-xs px-3 py-1.5 rounded-full cursor-pointer font-medium transition-colors"
          :class="activeSearchKw === '' ? 'bg-emerald-500 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'"
          @click="filterBySearchKw('')"
        >全部</span>
        <span
          v-for="kw in searchKeywordList"
          :key="kw.keyword"
          class="shrink-0 text-xs px-3 py-1.5 rounded-full cursor-pointer transition-colors"
          :class="activeSearchKw === kw.keyword ? 'bg-emerald-500 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'"
          @click="filterBySearchKw(kw.keyword)"
        >{{ kw.keyword }} ({{ kw.count }})</span>
      </div>
    </div>

    <!-- 日期导航条 -->
    <div class="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/60 dark:border-slate-800/60 shadow-sm p-3">
      <div class="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin">
        <span class="shrink-0 text-xs font-bold text-slate-500">📅 时间</span>
        <span
          class="shrink-0 text-xs px-3 py-1.5 rounded-full cursor-pointer font-medium transition-colors"
          :class="activeDate === '' ? 'bg-blue-500 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'"
          @click="filterByDate('')"
        >全部</span>
        <span
          v-for="d in dateList"
          :key="d.date"
          class="shrink-0 text-xs px-3 py-1.5 rounded-full cursor-pointer transition-colors"
          :class="activeDate === d.date ? 'bg-blue-500 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'"
          @click="filterByDate(d.date)"
        >{{ formatDate(d.date) }} ({{ d.count }})</span>
      </div>
    </div>

    <!-- 搜索 + 排序 -->
    <div class="flex flex-col md:flex-row gap-3 items-stretch md:items-center bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200/60 dark:border-slate-800/60 shadow-sm">
      <div class="flex gap-2 flex-1">
        <el-input v-model="keyword" placeholder="搜索事件标题或摘要" clearable size="large"
          @keyup.enter="doSearch" @clear="clearFilter" class="max-w-[300px]">
          <template #prefix><span class="text-slate-400">🔍</span></template>
        </el-input>
        <el-button type="primary" size="large" @click="doSearch">搜索</el-button>
        <el-button v-if="keyword || activeDate" size="large" @click="clearFilter">清除</el-button>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <span class="text-sm text-slate-500 self-center">{{ keyword ? '搜索结果' : '共 ' + realTotal + ' 个事件' }}</span>
        <span class="text-sm text-slate-400 ml-2">排序:</span>
        <el-select v-model="sortBy" size="large" style="min-width: 140px">
          <el-option label="按热度" value="heat" />
          <el-option label="按时间" value="time" />
        </el-select>
      </div>
    </div>

    <!-- 事件列表：按来源关键词分组 -->
    <div v-loading="eventsStore.loading" class="space-y-6">
      <!-- 按来源关键词分组展示 -->
      <template v-if="groupedEvents.length > 0">
        <div v-for="group in groupedEvents" :key="group.keyword || '__ungrouped__'">
          <!-- 分组头 -->
          <div v-if="!activeSearchKw && group.keyword" class="flex items-center gap-3 mb-3 pl-1">
            <span class="text-lg font-bold text-slate-700 dark:text-slate-200">🎯 {{ group.keyword }}</span>
            <span class="text-xs text-slate-400">{{ group.events.length }} 个事件</span>
            <el-button size="small" text type="primary" class="!text-xs" @click="filterBySearchKw(group.keyword)">
              只看此项 →
            </el-button>
          </div>
          <!-- 事件卡片网格 -->
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <EventCard v-for="event in group.events" :key="event.id" :event="event" />
          </div>
        </div>
      </template>
      <div v-else class="flex flex-col items-center justify-center py-20 bg-white dark:bg-slate-900 rounded-xl border border-slate-200/60 dark:border-slate-800/60">
        <span class="text-4xl">📭</span>
        <p class="text-slate-400 mt-4 text-sm">{{ keyword ? '未找到匹配事件' : '暂无舆情事件，请新建事件分析。' }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed, watch } from "vue";
import { useEventsStore } from "@/store/modules/events";
import { getTodayHotspots } from "@/api/dailyHot";
import EventCard from "@/components/EventCard.vue";
import { useRouter, useRoute } from "vue-router";
import type { DailyHotItem } from "@/api/types/opinion";

defineOptions({
  name: "OpinionBoard"
});

const eventsStore = useEventsStore();
const router = useRouter();
const route = useRoute();

const keyword = ref((route.query.keyword as string) || "");
const sortBy = ref<"time" | "heat">("time");
const activeDate = ref((route.query.date as string) || "");
const activeSearchKw = ref((route.query.sk as string) || ""); // 按来源搜索关键词筛选
const allEvents = ref<any[]>([]); // 缓存全部事件用于日期提取
const realTotal = ref(0); // 后端真实总数，不受客户端筛选影响

const dailyHot = ref<DailyHotItem[]>([]);
const dailyHotCategoryCounts = ref<Record<string, number>>({});
const activeHotCategory = ref("");
const dailyHotLoading = ref(false);
const dailyHotCategories = computed(() => Object.entries(dailyHotCategoryCounts.value).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count));
const visibleDailyHot = computed(() => activeHotCategory.value ? dailyHot.value.filter(item => item.category === activeHotCategory.value) : dailyHot.value);

// 从事件提取日期列表
const dateList = computed(() => {
  const map: Record<string, number> = {};
  for (const e of allEvents.value) {
    const first = (e.first_publish_time || "").slice(0, 10);
    const last = (e.last_activity_time || e.first_publish_time || "").slice(0, 10);
    if (!first) continue;
    // 事件覆盖的每一天都计数
    const start = new Date(first);
    const end = new Date(last);
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      const key = d.toISOString().slice(0, 10);
      map[key] = (map[key] || 0) + 1;
    }
  }
  return Object.entries(map)
    .sort((a, b) => b[0].localeCompare(a[0]))
    .slice(0, 14)
    .map(([date, count]) => ({ date, count }));
});

// 从全部事件中提取搜索关键词
const searchKeywordList = computed(() => {
  const map: Record<string, number> = {};
  for (const e of allEvents.value) {
    const kw = e.search_keyword;
    if (kw) map[kw] = (map[kw] || 0) + 1;
  }
  return Object.entries(map)
    .sort((a, b) => b[1] - a[1])
    .map(([keyword, count]) => ({ keyword, count }));
});

function formatDate(iso: string) {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

async function loadDailyHot() {
  dailyHotLoading.value = true;
  try {
    const res = await getTodayHotspots(20);
    dailyHot.value = res.data?.items || [];
    dailyHotCategoryCounts.value = res.data?.category_counts || {};
  } catch { dailyHot.value = []; }
  finally { dailyHotLoading.value = false; }
}

function openDailyHot(item: DailyHotItem) {
  if (item.event_id) router.push(`/events/${item.event_id}`);
  else filterByKeyword(item.title);
}

function filterBySearchKw(kw: string) {
  activeSearchKw.value = kw;
  router.replace({ query: { ...route.query, sk: kw || undefined } });
  applyLocalFilters();
}

async function filterByDate(date: string) {
  activeDate.value = date;
  // 同步到 URL，刷新不丢失
  router.replace({ query: { ...route.query, date: date || undefined } });
  applyLocalFilters();
}

function applyLocalFilters() {
  let filtered = [...allEvents.value];
  // 日期筛选
  if (activeDate.value) {
    filtered = filtered.filter(e => {
      const first = e.first_publish_time || "";
      const last = e.last_activity_time || first;
      return first.slice(0, 10) <= activeDate.value && last.slice(0, 10) >= activeDate.value;
    });
  }
  // 来源关键词筛选
  if (activeSearchKw.value) {
    filtered = filtered.filter(e => e.search_keyword === activeSearchKw.value);
  }
  eventsStore.events = filtered;
}

function filterByKeyword(title: string) {
  keyword.value = title;
  activeDate.value = "";
  eventsStore.loadEvents({ keyword: title, size: 200 }).then(() => {
    allEvents.value = [...eventsStore.events];
    realTotal.value = eventsStore.total;
  });
}

async function doSearch() {
  activeDate.value = "";
  const kw = keyword.value.trim();
  router.replace({ query: { ...route.query, keyword: kw || undefined, date: undefined } });
  await eventsStore.loadEvents(kw ? { keyword: kw, size: 200 } : { size: 200 });
  allEvents.value = [...eventsStore.events];
  realTotal.value = eventsStore.total;
}

function clearFilter() {
  keyword.value = "";
  activeDate.value = "";
  activeSearchKw.value = "";
  router.replace({ query: {} });
  eventsStore.loadEvents({ size: 200 }).then(() => {
    allEvents.value = [...eventsStore.events];
    realTotal.value = eventsStore.total;
  });
}

onMounted(async () => {
  const queryKeyword = route.query.keyword as string | undefined;
  const queryDate = route.query.date as string | undefined;
  if (queryKeyword) keyword.value = queryKeyword;
  if (queryDate) activeDate.value = queryDate;

  const params: any = { size: 200 };
  if (queryKeyword) params.keyword = queryKeyword;
  await eventsStore.loadEvents(params);
  allEvents.value = [...eventsStore.events];
  realTotal.value = eventsStore.total;

  // 如果 URL 带日期，客户端过滤
  if (queryDate && allEvents.value.length > 0) {
    eventsStore.events = allEvents.value.filter(e => {
      const first = e.first_publish_time || "";
      const last = e.last_activity_time || first;
      return first.slice(0, 10) <= queryDate && last.slice(0, 10) >= queryDate;
    });
  }

  loadDailyHot();
});

// 按来源关键词分组 + 排序
const groupedEvents = computed(() => {
  let list = [...eventsStore.events];
  // 来源关键词筛选
  if (activeSearchKw.value) {
    list = list.filter(e => e.search_keyword === activeSearchKw.value);
  }
  // 排序
  const sortFn = sortBy.value === "time"
    ? (a: any, b: any) => new Date(b.first_publish_time || 0).getTime() - new Date(a.first_publish_time || 0).getTime()
    : (a: any, b: any) => (b.heat_index || 0) - (a.heat_index || 0);
  list.sort(sortFn);

  // 选中单个关键词时不分组
  if (activeSearchKw.value) {
    return [{ keyword: activeSearchKw.value, events: list }];
  }

  // 按 search_keyword 分组
  const groups: Record<string, any[]> = {};
  const ungrouped: any[] = [];
  for (const e of list) {
    const kw = e.search_keyword;
    if (kw) {
      if (!groups[kw]) groups[kw] = [];
      groups[kw].push(e);
    } else {
      ungrouped.push(e);
    }
  }
  const result = Object.entries(groups)
    .sort((a, b) => {
      const aTime = Math.max(...a[1].map((e: any) => new Date(e.created_at || 0).getTime()));
      const bTime = Math.max(...b[1].map((e: any) => new Date(e.created_at || 0).getTime()));
      return bTime - aTime;
    })
    .map(([keyword, events]) => ({ keyword, events }));
  if (ungrouped.length > 0) {
    result.push({ keyword: "", events: ungrouped });
  }
  return result;
});
</script>

<style scoped>
.welcome-container {
  min-height: calc(100vh - 120px);
}
</style>
