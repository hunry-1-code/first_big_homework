<template>
  <div class="user-profile-container p-6 space-y-6">
    <!-- 头部 -->
    <div class="flex justify-between items-center bg-white dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800/60 p-6 rounded-2xl shadow-sm">
      <div class="flex items-center gap-4">
        <div class="size-14 rounded-full bg-gradient-to-tr from-blue-500 to-indigo-600 flex items-center justify-center text-white text-xl font-bold shadow-md">
          {{ userStore.username.substring(0, 2).toUpperCase() }}
        </div>
        <div>
          <h2 class="text-xl font-bold text-slate-800 dark:text-slate-100">{{ userStore.username }}</h2>
          <div class="flex items-center gap-2 mt-1.5">
            <el-tag size="small" :type="isAdmin ? 'danger' : 'success'" effect="dark" class="rounded-full">
              {{ isAdmin ? "系统管理员" : "普通用户" }}
            </el-tag>
          </div>
        </div>
      </div>
      <el-button type="danger" plain @click="handleLogout">退出登录</el-button>
    </div>

    <el-row :gutter="24">
      <!-- 快捷分析关键词 -->
      <el-col :xs="24" :lg="12" class="mb-6">
        <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
          <template #header>
            <div class="font-bold text-slate-800 dark:text-slate-100">🎯 快捷分析</div>
          </template>
          <p class="text-xs text-slate-400 mb-4">预设关键词，点击即可跳转分析页面自动填入，省去重复输入。</p>

          <div class="flex gap-2 mb-4">
            <el-input v-model="keywordInput" placeholder="输入关键词，回车添加" size="default"
              @keyup.enter="addKeyword" class="flex-1">
              <template #suffix><span class="text-xs text-slate-400">Enter</span></template>
            </el-input>
          </div>

          <div class="flex flex-wrap gap-2 mb-4">
            <span
              v-for="kw in myKeywords"
              :key="kw"
              class="group inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-sm cursor-pointer bg-blue-50 text-blue-600 dark:bg-blue-950/30 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
              @click="goAnalyze(kw)"
            >
              {{ kw }}
              <span class="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-600 ml-0.5"
                @click.stop="removeKeyword(kw)">×</span>
            </span>
            <span v-if="myKeywords.length === 0" class="text-xs text-slate-400">添加关键词后点击即可快速分析</span>
          </div>

          <div class="flex gap-2">
            <el-button size="small" type="primary" plain @click="saveKeywords" :loading="saving">保存关键词</el-button>
            <el-button size="small" type="success" plain @click="monitorAll" :loading="monitoring" :disabled="myKeywords.length === 0">🔍 一键监控全部</el-button>
          </div>
        </el-card>
      </el-col>

      <!-- 我的分析任务 -->
      <el-col :xs="24" :lg="12" class="mb-6">
        <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
          <template #header>
            <div class="font-bold text-slate-800 dark:text-slate-100 flex justify-between items-center">
              <span>📋 我的分析记录</span>
              <el-button size="small" @click="loadMyTasks">刷新</el-button>
            </div>
          </template>

          <div v-loading="tasksLoading">
            <TaskList :tasks="myTasks" />
            <div v-if="myTasks.length === 0" class="text-center py-8 text-slate-400 text-sm">
              <span class="text-3xl block mb-2">📭</span>暂无分析记录，去 <router-link to="/analysis" class="text-blue-500">事件分析</router-link> 开始第一条吧
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="24">
      <!-- 分析统计 -->
      <el-col :xs="24" :md="8" class="mb-6">
        <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
          <template #header><span class="font-bold text-slate-800 dark:text-slate-100">📊 分析统计</span></template>
          <div class="grid grid-cols-2 gap-3 text-center">
            <div class="bg-blue-50 dark:bg-blue-950/30 rounded-lg p-3">
              <div class="text-2xl font-bold text-blue-600">{{ myTasks.length }}</div>
              <div class="text-xs text-slate-500 mt-1">分析任务</div>
            </div>
            <div class="bg-emerald-50 dark:bg-emerald-950/30 rounded-lg p-3">
              <div class="text-2xl font-bold text-emerald-600">{{ doneCount }}</div>
              <div class="text-xs text-slate-500 mt-1">已完成</div>
            </div>
            <div class="bg-orange-50 dark:bg-orange-950/30 rounded-lg p-3">
              <div class="text-2xl font-bold text-orange-600">{{ runningCount }}</div>
              <div class="text-xs text-slate-500 mt-1">运行中</div>
            </div>
            <div class="bg-red-50 dark:bg-red-950/30 rounded-lg p-3">
              <div class="text-2xl font-bold text-red-500">{{ failedCount }}</div>
              <div class="text-xs text-slate-500 mt-1">失败</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 搜索历史 -->
      <el-col :xs="24" class="mb-6">
        <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
          <template #header>
            <div class="flex justify-between items-center">
              <span class="font-bold text-slate-800 dark:text-slate-100">🕐 搜索历史</span>
              <el-button size="small" @click="loadSearchHistory">刷新</el-button>
            </div>
          </template>
          <div v-loading="historyLoading">
            <div v-if="searchHistory.length > 0" class="space-y-2">
              <div v-for="h in searchHistory" :key="h.id"
                class="flex items-center justify-between gap-3 p-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                <span class="text-sm text-blue-600 dark:text-blue-400 font-medium min-w-0 truncate cursor-pointer"
                  @click="goAnalyze(h.keyword)">{{ h.keyword }}</span>
                <span class="text-xs text-slate-400 shrink-0">{{ h.platforms?.join('、') || '全部平台' }} · {{ h.target_count }}篇</span>
                <span class="text-[10px] text-slate-400 shrink-0">{{ formatHistoryTime(h.created_at) }}</span>
                <el-button size="small" text type="primary" class="shrink-0" @click="repeatHistorySearch(h.id)">再次搜索</el-button>
                <el-button size="small" text type="danger" class="shrink-0" @click="removeHistory(h.id)">×</el-button>
              </div>
            </div>
            <div v-else class="text-xs text-slate-400 py-4 text-center">暂无搜索历史</div>
          </div>
        </el-card>
      </el-col>

      <!-- 平台目录：展示系统支持的数据源及其能力 -->
      <el-col :xs="24" class="mb-6">
        <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
          <template #header>
            <div class="flex justify-between items-center">
              <div>
                <span class="font-bold text-slate-800 dark:text-slate-100">📡 数据源平台</span>
                <span class="text-xs text-slate-400 ml-2">系统支持采集和评论分析的平台，共 {{ platformSources.length }} 个</span>
              </div>
              <el-button size="small" @click="loadPlatformSources" :loading="sourcesLoading">刷新</el-button>
            </div>
          </template>
          <div v-loading="sourcesLoading">
            <div v-if="platformSources.length > 0" class="space-y-1">
              <div v-for="p in platformSources" :key="p.code"
                class="flex items-center gap-4 px-3 py-2.5 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                <!-- 图标 -->
                <img :src="p._favicon" class="w-5 h-5 shrink-0 rounded" :alt="p._name"
                  @error="($event.target as HTMLImageElement).style.display='none'" />
                <IconifyIconOffline v-if="!p._favicon" :icon="p._icon" class="text-lg shrink-0" :style="{ color: p._color }" />
                <!-- 名称 -->
                <span class="text-sm font-medium text-slate-700 dark:text-slate-200 w-24 shrink-0">{{ p._name }}</span>
                <!-- 类型 -->
                <el-tag size="small" :type="p.type === 'social' ? 'danger' : p.type === 'news' ? 'success' : 'info'" effect="plain" class="shrink-0">
                  {{ p.type === 'social' ? '社交' : p.type === 'news' ? '新闻' : p.type === 'search' ? '搜索' : p.type === 'news_group' ? '聚合' : p.type }}
                </el-tag>
                <!-- 能力 -->
                <span class="flex items-center gap-1 shrink-0">
                  <span v-if="p.crawler_supported" class="text-[10px] text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30 px-1.5 py-0.5 rounded font-medium">采集</span>
                  <span v-if="p.comment_supported" class="text-[10px] text-purple-600 bg-purple-50 dark:bg-purple-950/30 px-1.5 py-0.5 rounded font-medium">评论</span>
                </span>
                <!-- 官网链接 -->
                <a :href="p.official_url" target="_blank" class="text-xs text-blue-500 hover:text-blue-600 shrink-0 hidden md:inline">官网</a>
                <!-- 搜索链接 -->
                <a :href="p.search_url?.replace('{keyword}','')" target="_blank" class="text-xs text-slate-400 hover:text-slate-600 shrink-0 hidden md:inline">搜索</a>
                <!-- 关注按钮 -->
                <el-button
                  size="small"
                  :type="p.followed ? 'primary' : 'default'"
                  :plain="!p.followed"
                  class="shrink-0 ml-auto"
                  @click.stop="p.followed ? unfollowSource(p.code) : followSource(p.code)">
                  {{ p.followed ? '已关注' : '+ 关注' }}
                </el-button>
              </div>
            </div>
            <div v-else class="text-xs text-slate-400 py-8 text-center">加载中...</div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useRouter } from "vue-router";
import { useUserStore } from "@/store/modules/user";
import { resolvePlatformName, getPlatform, PLATFORMS } from "@/constants/platforms";
import IconifyIconOffline from "@/components/ReIcon/src/iconifyIconOffline";
import { getMyTasks } from "@/api/tasks";
import { getSearchHistory, deleteSearchHistory, repeatSearch, getUserConfig, saveUserConfig } from "@/api/user";
import { http } from "@/utils/http";
import TaskList from "@/components/TaskList.vue";
import { message } from "@/utils/message";

defineOptions({ name: "OpinionUser" });

const router = useRouter();
const userStore = useUserStore();

const keywordInput = ref("");
const myKeywords = ref<string[]>([]);
const myTasks = ref<any[]>([]);
const crawlerPlatforms = ref<Array<{code: string; name: string; status: string}>>([]);
const platformSources = ref<any[]>([]);
const sourcesLoading = ref(false);
const tasksLoading = ref(false);
const saving = ref(false);
const monitoring = ref(false);
const searchHistory = ref<any[]>([]);
const historyLoading = ref(false);

const isAdmin = computed(() => userStore.roles.includes("admin"));

async function loadConfig() {
  try {
    const r = await getUserConfig();
    myKeywords.value = r.data?.keywords || [];
  } catch {}
}

async function monitorAll() {
  monitoring.value = true;
  try {
    for (const kw of myKeywords.value) {
      await http.request("post", "/api/crawler/search", { data: { keyword: kw, target_count: 30 } });
    }
    message(`已提交 ${myKeywords.value.length} 个关键词的监控任务`, { type: "success" });
  } catch { message("提交失败", { type: "error" }); }
  finally { monitoring.value = false; }
}

function addKeyword() {
  const w = keywordInput.value.trim();
  if (w && !myKeywords.value.includes(w)) myKeywords.value.push(w);
  keywordInput.value = "";
}

function removeKeyword(w: string) {
  myKeywords.value = myKeywords.value.filter(k => k !== w);
}

async function saveKeywords() {
  saving.value = true;
  try {
    await saveUserConfig({ keywords: myKeywords.value });
    message("已保存", { type: "success" });
  } catch { message("保存失败", { type: "error" }); }
  finally { saving.value = false; }
}

function goAnalyze(kw: string) {
  router.push({ path: "/analysis", query: { keyword: kw } });
}

async function loadSearchHistory() {
  historyLoading.value = true;
  try {
    const r = await getSearchHistory(1, 20);
    searchHistory.value = r.data?.records || r.data?.items || [];
  } catch { searchHistory.value = []; }
  finally { historyLoading.value = false; }
}

async function removeHistory(id: number) {
  try { await deleteSearchHistory(id); loadSearchHistory(); }
  catch { message("删除失败", { type: "error" }); }
}

async function repeatHistorySearch(id: number) {
  try {
    const r = await repeatSearch(id);
    const payload = r.data?.search_payload;
    if (payload) {
      router.push({ path: "/analysis", query: { keyword: payload.keyword } });
    }
  } catch { message("复用搜索失败", { type: "error" }); }
}

function formatHistoryTime(ts: string) {
  if (!ts) return "";
  const d = (Date.now() - new Date(ts).getTime()) / 1000;
  if (d < 60) return "刚刚";
  if (d < 3600) return Math.floor(d / 60) + "分钟前";
  if (d < 86400) return Math.floor(d / 3600) + "小时前";
  return Math.floor(d / 86400) + "天前";
}

const FAVICON_DOMAINS: Record<string, string> = {
  bilibili: "bilibili.com", weibo: "weibo.com", zhihu: "zhihu.com",
  xiaohongshu: "xiaohongshu.com", douyin: "douyin.com", baidu: "baidu.com",
  news_people: "people.com.cn", news_36kr: "36kr.com", news_thepaper: "thepaper.cn",
  news_infoq: "infoq.cn", news_sspai: "sspai.com",
};

async function loadPlatformSources() {
  sourcesLoading.value = true;
  try {
    const r = await http.request<any>("get", "/api/user/sources");
    const raw = r.data?.presets || [];
    platformSources.value = raw.map((p: any) => {
      const cn = resolvePlatformName(p.code);
      const info = getPlatform(cn);
      const domain = FAVICON_DOMAINS[p.code];
      return {
        ...p,
        followed: p.followed ?? false,
        _name: cn,
        _icon: info?.icon || "ri:question-line",
        _color: info?.color || "#94a3b8",
        _favicon: domain ? `https://www.google.com/s2/favicons?domain=${domain}&sz=32` : null,
      };
    });
  } catch { platformSources.value = []; }
  finally { sourcesLoading.value = false; }
}

async function followSource(code: string) {
  try {
    await http.request("post", `/api/user/sources/${code}/follow`);
    loadPlatformSources();
    message("已关注", { type: "success" });
  } catch { message("操作失败", { type: "error" }); }
}

async function unfollowSource(code: string) {
  try {
    await http.request("delete", `/api/user/sources/${code}/follow`);
    loadPlatformSources();
    message("已取消关注", { type: "success" });
  } catch { message("操作失败", { type: "error" }); }
}

onMounted(() => { loadConfig(); loadSearchHistory(); loadMyTasks(); loadCrawlerPlatforms(); loadPlatformSources(); });

async function loadMyTasks() {
  tasksLoading.value = true;
  try {
    const r = await getMyTasks();
    myTasks.value = r.data?.tasks || [];
  } catch {}
  finally { tasksLoading.value = false; }
}

function handleLogout() {
  userStore.logOut();
  message("已退出", { type: "success" });
}

// 平台状态
const platformStatus = ref<Array<{name:string,ok:boolean,status:string}>>([]);
async function loadPlatformStatus() {
  try {
    const r = await http.request<any>("get", "/api/crawler/status");
    const data = r.data || {};
    const list = [];
    // 从 crawler status 提取各平台状态
    for (const [name, info] of Object.entries(data)) {
      if (typeof info === 'object' && info !== null) {
        const s = info as any;
        list.push({ name, ok: s.error_count === 0 || s.total_count > 0, status: s.error_count > 0 ? '异常' : '正常' });
      }
    }
    if (list.length === 0) {
      // fallback: hardcoded status based on earlier tests
      list.push({ name: 'B站', ok: true, status: '正常' });
      list.push({ name: '知乎', ok: true, status: '正常' });
      list.push({ name: '微博', ok: true, status: '正常' });
      list.push({ name: '百度', ok: false, status: '限流' });
      list.push({ name: '抖音', ok: false, status: '缺Key' });
    }
    platformStatus.value = list;
  } catch { platformStatus.value = []; }
}

// 我的事件
const myEvents = ref<any[]>([]);
async function loadMyEvents() {
  try {
    const r = await http.request<any>("get", "/api/events", { params: { size: 10 } });
    myEvents.value = r.data?.events || [];
  } catch {}
}

// 修改密码
const newPassword = ref("");
const changingPwd = ref(false);
async function changePassword() {
  if (!newPassword.value || newPassword.value.length < 6) {
    message("密码至少6位", { type: "warning" }); return;
  }
  changingPwd.value = true;
  try {
    await http.request("put", "/api/user/profile", { data: { password: newPassword.value } });
    message("密码已修改", { type: "success" });
    newPassword.value = "";
  } catch { message("修改失败", { type: "error" }); }
  finally { changingPwd.value = false; }
}

async function loadCrawlerPlatforms() {
  try {
    const r = await http.request<any>("get", "/api/crawler/platforms");
    const codes: string[] = r.data?.platforms || [];
    const rssCodes: string[] = r.data?.rss || [];
    const rateLimited: string[] = r.data?.rate_limited || [];
    crawlerPlatforms.value = [...codes, ...rssCodes].map(code => ({
      code,
      name: resolvePlatformName(code),
      status: rateLimited.includes(code) ? "rate_limited" : "active",
    }));
  } catch { crawlerPlatforms.value = []; }
}
</script>

<style scoped>
.user-profile-container { min-height: calc(100vh - 120px); }
</style>
