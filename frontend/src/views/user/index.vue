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

    <!-- 统一双列网格 -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- ===== 左列 ===== -->
      <div class="space-y-6">
        <!-- 快捷分析 -->
        <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
          <template #header>
            <span class="font-bold text-slate-800 dark:text-slate-100">🎯 快捷分析</span>
          </template>
          <p class="text-sm text-slate-400 mb-4">预设关键词，点击即可跳转分析页面自动填入。</p>
          <div class="flex gap-2 mb-4">
            <el-input v-model="keywordInput" placeholder="输入关键词，回车添加" size="default"
              @keyup.enter="addKeyword" class="flex-1">
              <template #suffix><span class="text-xs text-slate-400">Enter</span></template>
            </el-input>
          </div>
          <div class="flex flex-wrap gap-2 mb-4">
            <span v-for="kw in myKeywords" :key="kw"
              class="group inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-sm cursor-pointer bg-blue-50 text-blue-600 dark:bg-blue-950/30 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
              @click="goAnalyze(kw)">
              {{ kw }}
              <span class="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-600 ml-0.5" @click.stop="removeKeyword(kw)">×</span>
            </span>
            <span v-if="myKeywords.length === 0" class="text-sm text-slate-400">添加关键词后点击即可快速分析</span>
          </div>
          <el-button size="small" type="primary" plain @click="saveKeywords" :loading="saving">保存关键词</el-button>
        </el-card>

        <!-- 搜索历史 -->
        <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
          <template #header>
            <div class="flex justify-between items-center">
              <div class="flex items-center gap-2">
                <span class="font-bold text-slate-800 dark:text-slate-100">🕐 搜索历史</span>
                <el-tag v-if="searchHistory.length" size="small" type="info" effect="plain" round>{{ searchHistory.length }} 条</el-tag>
              </div>
              <el-button size="small" @click="loadSearchHistory" :loading="historyLoading">刷新</el-button>
            </div>
          </template>
          <div v-loading="historyLoading">
            <div v-if="searchHistory.length > 0" class="grid grid-cols-1 gap-2">
              <div v-for="h in searchHistory" :key="h.id"
                class="group flex items-center gap-4 p-3 rounded-xl border border-transparent hover:border-blue-200 dark:hover:border-blue-800/40 hover:bg-blue-50/30 dark:hover:bg-blue-950/10 transition-all cursor-pointer"
                @click="goAnalyze(h.keyword)">
                <div class="flex-1 min-w-0">
                  <div class="text-base font-semibold text-slate-800 dark:text-slate-200 truncate">{{ h.keyword }}</div>
                  <div class="flex items-center gap-3 mt-1">
                    <span class="text-xs text-slate-400">{{ formatHistoryTime(h.created_at) }}</span>
                    <span class="text-xs text-slate-400">{{ h.target_count }} 篇</span>
                    <span v-if="h.platforms?.length" class="text-xs text-slate-400">{{ h.platforms.length }} 个平台</span>
                  </div>
                </div>
                <div class="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                  <el-button size="small" type="primary" @click.stop="repeatHistorySearch(h.id)">再次搜索</el-button>
                  <el-button size="small" type="danger" text @click.stop="removeHistory(h.id)">删除</el-button>
                </div>
              </div>
            </div>
            <div v-else class="text-sm text-slate-400 py-8 text-center">
              <span class="text-3xl block mb-2">🕐</span>暂无搜索历史
            </div>
          </div>
        </el-card>
      </div>

      <!-- ===== 右列 ===== -->
      <div class="space-y-6">
        <!-- 我的分析记录 -->
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
              <span class="text-3xl block mb-2">📭</span>暂无分析记录
            </div>
          </div>
        </el-card>

        <!-- 数据源概览 -->
        <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
          <template #header><span class="font-bold text-slate-800 dark:text-slate-100">📡 数据源概览</span></template>
          <div class="text-sm text-slate-500 space-y-3">
            <div class="flex items-baseline gap-2">
              <span class="text-2xl font-bold text-slate-700 dark:text-slate-200">12</span>
              <span>个数据平台可用</span>
            </div>
            <div class="flex flex-wrap gap-1.5">
              <span class="text-xs px-2 py-1 rounded-full bg-blue-50 text-blue-600 dark:bg-blue-950/30 font-medium">社交平台 6</span>
              <span class="text-xs px-2 py-1 rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-950/30 font-medium">新闻媒体 5</span>
              <span class="text-xs px-2 py-1 rounded-full bg-amber-50 text-amber-600 dark:bg-amber-950/30 font-medium">搜索引擎 1</span>
            </div>
            <div class="text-xs text-slate-400 pt-1 border-t border-slate-100 dark:border-slate-800">具体平台和采集能力见 <router-link to="/analysis" class="text-blue-500">事件分析页</router-link></div>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useRouter } from "vue-router";
import { useUserStore } from "@/store/modules/user";
import { getMyTasks } from "@/api/tasks";
import { getSearchHistory, deleteSearchHistory, repeatSearch, getUserConfig, saveUserConfig } from "@/api/user";
import TaskList from "@/components/TaskList.vue";
import { message } from "@/utils/message";

defineOptions({ name: "OpinionUser" });

const router = useRouter();
const userStore = useUserStore();

const keywordInput = ref("");
const myKeywords = ref<string[]>([]);
const myTasks = ref<any[]>([]);
const tasksLoading = ref(false);
const saving = ref(false);
const searchHistory = ref<any[]>([]);
const historyLoading = ref(false);

const isAdmin = computed(() => userStore.roles.includes("admin"));

async function loadConfig() {
  try {
    const r = await getUserConfig();
    myKeywords.value = r.data?.keywords || [];
  } catch {}
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
      const q: Record<string, string> = { keyword: payload.keyword };
      if (payload.target_count) q.target = String(payload.target_count);
      if (payload.platforms?.length) q.platforms = payload.platforms.join(',');
      router.push({ path: "/analysis", query: q });
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

onMounted(() => { loadConfig(); loadSearchHistory(); loadMyTasks(); });

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
</script>

<style scoped>
.user-profile-container { min-height: calc(100vh - 120px); }
</style>
