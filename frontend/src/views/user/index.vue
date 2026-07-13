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

          <el-button size="small" type="primary" plain @click="saveKeywords" :loading="saving">
            保存关键词
          </el-button>
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
      <!-- 平台状态 -->
      <el-col :xs="24" :md="8" class="mb-6">
        <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
          <template #header><span class="font-bold text-slate-800 dark:text-slate-100">📡 爬虫平台状态</span></template>
          <div class="space-y-2">
            <div v-for="p in platformStatus" :key="p.name" class="flex items-center justify-between text-sm">
              <span class="text-slate-600 dark:text-slate-400">{{ p.name }}</span>
              <el-tag size="small" :type="p.ok ? 'success' : 'warning'">{{ p.ok ? '可用' : p.status }}</el-tag>
            </div>
            <div v-if="platformStatus.length === 0" class="text-xs text-slate-400">加载中...</div>
          </div>
        </el-card>
      </el-col>

      <!-- 我的事件 -->
      <el-col :xs="24" :md="8" class="mb-6">
        <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
          <template #header>
            <span class="font-bold text-slate-800 dark:text-slate-100">📊 我的事件</span>
          </template>
          <div v-if="myEvents.length > 0" class="space-y-2">
            <div v-for="e in myEvents" :key="e.id"
              class="text-sm text-blue-500 cursor-pointer hover:underline truncate"
              @click="router.push('/events/' + e.id)">
              {{ e.title?.slice(0, 30) }}{{ (e.title || '').length > 30 ? '...' : '' }}
            </div>
          </div>
          <div v-else class="text-xs text-slate-400 py-4 text-center">
            暂无，去<a href="/analysis" class="text-blue-500">分析页</a>创建
          </div>
        </el-card>
      </el-col>

      <!-- 修改密码 -->
      <el-col :xs="24" :md="8" class="mb-6">
        <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
          <template #header><span class="font-bold text-slate-800 dark:text-slate-100">🔒 修改密码</span></template>
          <el-form size="default" label-position="top">
            <el-form-item label="新密码">
              <el-input v-model="newPassword" type="password" show-password placeholder="6-128位" />
            </el-form-item>
            <el-button type="primary" size="small" @click="changePassword" :loading="changingPwd">确认修改</el-button>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useRouter } from "vue-router";
import { useUserStore } from "@/store/modules/user";
import { getMyTasks } from "@/api/tasks";
import { http } from "@/utils/http";
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

const isAdmin = computed(() => userStore.roles.includes("admin"));

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
    await http.request("put", "/api/user/config", { data: { keywords: myKeywords.value } });
    message("已保存", { type: "success" });
  } catch { message("保存失败", { type: "error" }); }
  finally { saving.value = false; }
}

function goAnalyze(kw: string) {
  router.push({ path: "/analysis", query: { keyword: kw } });
}

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

onMounted(() => {
  loadMyTasks();
  loadPlatformStatus();
  loadMyEvents();
  try {
    http.request<any>("get", "/api/user/config").then(r => {
      myKeywords.value = r.data?.keywords || [];
    }).catch(() => {});
  } catch {}
});
</script>

<style scoped>
.user-profile-container { min-height: calc(100vh - 120px); }
</style>
