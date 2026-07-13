<template>
  <div class="task-process-list space-y-3">
    <div
      v-for="task in tasks"
      :key="task.id"
      class="bg-white dark:bg-slate-900 border rounded-xl shadow-sm overflow-hidden transition-all"
      :class="task.status === 'running' ? 'border-blue-300 dark:border-blue-700' : task.status === 'failed' ? 'border-red-200 dark:border-red-900' : 'border-slate-200 dark:border-slate-800'"
    >
      <!-- 进程头部 -->
      <div class="flex items-center gap-4 p-4 cursor-pointer" @click="task._expanded = !task._expanded">
        <span class="text-xs font-mono text-slate-400 w-12">#{{ task.id }}</span>
        <el-tag :type="getTypeTag(task.task_type)" size="small" class="shrink-0">
          {{ formatType(task.task_type) }}
        </el-tag>
        <span class="text-sm text-slate-600 dark:text-slate-300 flex-1 truncate">
          {{ task.payload?.keyword || task.summary || task.message || '-' }}
        </span>
        <el-tag :type="getStatusTag(task.status)" size="small" effect="dark" class="shrink-0">
          {{ formatStatus(task.status) }}
        </el-tag>
        <el-progress
          :percentage="task.progress || 0"
          :status="task.status === 'failed' ? 'exception' : (['success','completed'].includes(task.status) ? 'success' : undefined)"
          :stroke-width="6"
          class="!w-[120px] shrink-0"
        />
        <span class="text-[11px] text-slate-400 shrink-0 w-16 text-right">
          {{ timeAgo(task.created_at) }}
        </span>
      </div>

      <!-- 展开：流水线阶段 -->
      <div v-if="task._expanded" class="border-t border-slate-100 dark:border-slate-800 px-4 py-3 bg-slate-50 dark:bg-slate-950/50">
        <div v-if="task.stages && task.stages.length > 0" class="flex items-center gap-1 flex-wrap">
          <template v-for="(s, i) in task.stages" :key="i">
            <span v-if="i > 0" class="text-slate-300 dark:text-slate-600 mx-1">→</span>
            <span
              class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full"
              :class="s.status === 'done' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400' : s.status === 'failed' ? 'bg-red-50 text-red-600 dark:bg-red-950/30 dark:text-red-400' : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'"
            >
              <span class="font-medium">{{ stageName(s.stage) }}</span>
              <span v-if="s.detail" class="opacity-70">({{ s.detail }})</span>
            </span>
          </template>
        </div>
        <div v-else class="text-xs text-slate-400">暂无阶段详情</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatTaskStatus, getTaskStatusTag, taskKeyword } from "./taskPresentation";

defineProps<{ tasks: any[] }>();

function formatType(t: string) {
  const m: Record<string,string> = { crawl:'网络爬虫', daily_hot:'每日热点', daily_hot_enrichment:'热点补全', import:'数据导入', analysis:'智能分析', hotspot:'热点分析', aggregation:'事件聚合', sentiment:'情感分析' };
  return m[t] || t;
}
function getTypeTag(t: string): any { return t === 'crawl' ? 'primary' : t === 'daily_hot' ? 'warning' : 'info'; }
function getStatusTag(s: string): any { return s === 'pending' ? 'info' : s === 'running' ? 'warning' : (s === 'success' || s === 'completed') ? 'success' : s === 'failed' ? 'danger' : 'info'; }
function formatStatus(s: string) { return s === 'pending' ? '等待' : s === 'running' ? '运行中' : (s === 'success' || s === 'completed') ? '完成' : s === 'failed' ? '失败' : s; }
function stageName(s: string) {
  const m: Record<string,string> = { crawl:'采集', preprocess:'预处理', content_analysis:'内容分析', aggregation:'事件聚合', sentiment:'情感分析', publish:'发布', dedup:'LLM去重', enrich:'热点补全', done:'完成' };
  return m[s] || s;
}
function timeAgo(ts: string) {
  if (!ts) return '';
  const d = (Date.now() - new Date(ts).getTime()) / 1000;
  if (d < 60) return '刚刚';
  if (d < 3600) return Math.floor(d/60) + '分钟前';
  if (d < 86400) return Math.floor(d/3600) + '小时前';
  return Math.floor(d/86400) + '天前';
}
</script>
