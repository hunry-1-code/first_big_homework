<template>
  <div class="admin-dashboard-container p-6 space-y-6">
    <!-- 头部 -->
    <div class="bg-white dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800/60 p-6 rounded-2xl shadow-sm">
      <h1 class="text-2xl font-bold text-slate-800 dark:text-slate-100">⚙️ 运维管理</h1>
      <p class="text-sm text-slate-500 dark:text-slate-400 mt-1">全链路进程监控 · 每日热点调度</p>
    </div>

    <!-- 每日热点调度控制 -->
    <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
      <template #header>
        <div class="flex justify-between items-center">
          <span class="font-bold text-slate-800 dark:text-slate-100">🔥 每日热点定时调度</span>
          <div class="flex items-center gap-2">
            <el-switch v-model="dhEnabled" :loading="dhLoading" active-text="启用" inactive-text="停用"
              @change="(v:boolean) => { dhEnabled = !v; toggleDH(v) }" />
            <el-popconfirm title="确认立即执行一次每日热点采集？会调用爬虫API。" @confirm="triggerDH">
              <template #reference>
                <el-button size="small" type="primary" :loading="dhRunning">手动触发</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </template>
      <div class="flex items-center gap-6 text-sm">
        <div class="flex items-center gap-2">
          <span class="text-slate-400">采集间隔：</span>
          <el-select v-model="dhInterval" size="small" style="width:120px" @change="setDHInterval">
            <el-option :value="30" label="30 分钟" />
            <el-option :value="60" label="1 小时" />
            <el-option :value="120" label="2 小时" />
            <el-option :value="360" label="6 小时" />
            <el-option :value="720" label="12 小时" />
          </el-select>
        </div>
        <div v-if="dhLastRun" class="text-slate-400">
          上次：{{ dhLastRun }}
        </div>
        <div v-if="dhNextRun" class="text-slate-400">
          下次：{{ dhNextRun }}
        </div>
      </div>
    </el-card>

    <!-- 底部：全链路进程管理器 -->
    <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
      <template #header>
        <div class="flex justify-between items-center">
          <div class="flex items-center gap-4">
            <span class="font-bold text-slate-800 dark:text-slate-100">⚙️ 全链路进程管理器</span>
            <div class="flex items-center gap-3 text-xs">
              <span class="text-slate-400">总计 <b class="text-slate-600">{{ allTasks.length }}</b></span>
              <span class="text-blue-500">运行中 <b>{{ runningCount }}</b></span>
              <span class="text-emerald-500">完成 <b>{{ doneCount }}</b></span>
              <span class="text-red-500">失败 <b>{{ failedCount }}</b></span>
            </div>
          </div>
          <div class="flex gap-2">
            <el-button size="small" @click="loadData" :loading="tasksLoading">刷新</el-button>
            <el-popconfirm title="清理所有失败任务？" @confirm="cleanFailed">
              <template #reference>
                <el-button size="small" type="danger" plain>清理失败</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </template>

      <div v-loading="tasksLoading">
        <TaskList :tasks="allTasks" />
        <div v-if="allTasks.length === 0" class="flex flex-col items-center justify-center py-10 text-slate-400 text-sm">
          <span class="text-4xl mb-2">📭</span>
          <p>暂无进程记录</p>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { getAllTasks } from "@/api/tasks";
import TaskList from "@/components/TaskList.vue";
import { message } from "@/utils/message";
import { http } from "@/utils/http";

defineOptions({ name: "OpinionAdmin" });

const allTasks = ref<any[]>([]);
const tasksLoading = ref(false);
const runningCount = computed(() => allTasks.value.filter(t => t.status === 'running').length);
const doneCount = computed(() => allTasks.value.filter(t => t.status === 'success' || t.status === 'completed').length);
const failedCount = computed(() => allTasks.value.filter(t => t.status === 'failed').length);

async function loadData() {
  tasksLoading.value = true;
  try {
    const res = await getAllTasks();
    allTasks.value = res.data?.tasks || [];
  } catch { allTasks.value = []; }
  finally { tasksLoading.value = false; }
}

async function cleanFailed() {
  let ok = 0;
  for (const t of allTasks.value.filter(t => t.status === 'failed')) {
    try { await http.request('delete', '/api/tasks/' + t.id); ok++; } catch {}
  }
  message(`清理完成：${ok} 个`, { type: 'success' });
  loadData();
}

const dhEnabled = ref(false);
const dhInterval = ref(60);
const dhLoading = ref(false);
const dhRunning = ref(false);
const dhLastRun = ref('');
const dhNextRun = ref('');

async function loadDHStatus() {
  try {
    const r = await http.request<any>('get', '/api/admin/daily-hot/status');
    dhEnabled.value = r.data?.enabled ?? false;
    dhInterval.value = r.data?.interval_minutes ?? 60;
    dhLastRun.value = r.data?.last_run?.replace('T',' ').slice(0,16) || '';
    dhNextRun.value = r.data?.next_run?.replace('T',' ').slice(0,16) || '';
  } catch {}
}
async function toggleDH(v: boolean) {
  dhLoading.value = true;
  try { await http.request('post', '/api/admin/daily-hot/toggle', { data: { enabled: v } }); dhEnabled.value = v; }
  catch { dhEnabled.value = !v; message('操作失败', { type: 'error' }); }
  finally { dhLoading.value = false; }
}
async function setDHInterval(v: number) {
  try { await http.request('post', '/api/admin/daily-hot/interval', { data: { minutes: v } }); }
  catch { message('设置失败', { type: 'error' }); }
}
async function triggerDH() {
  dhRunning.value = true;
  try {
    const r = await http.request<any>('post', '/api/admin/daily-hot/run');
    message(`已触发 #${r.data?.task_id}`, { type: 'success' });
    setTimeout(loadData, 3000);
  } catch { message('触发失败', { type: 'error' }); }
  finally { dhRunning.value = false; }
}

onMounted(() => { loadData(); loadDHStatus(); });
</script>

<style scoped>
.admin-dashboard-container {
  min-height: calc(100vh - 120px);
}
</style>
