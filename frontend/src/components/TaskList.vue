<template>
  <el-table :data="tasks" size="default" class="w-full border border-slate-100 dark:border-slate-800 rounded-lg overflow-hidden shadow-sm">
    <el-table-column prop="id" label="ID" width="70" align="center" />
    <el-table-column prop="task_type" label="类型" width="100">
      <template #default="{ row }">
        <el-tag :type="getTypeTag(row.task_type)" size="small">
          {{ formatType(row.task_type) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="status" label="状态" width="100">
      <template #default="{ row }">
        <el-tag :type="getStatusTag(row.status)" size="small" effect="dark">
          {{ formatStatus(row.status) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="progress" label="进度" width="140">
      <template #default="{ row }">
        <div class="flex items-center gap-2">
          <el-progress
            :percentage="row.progress || 0"
            :status="row.status === 'failed' ? 'exception' : (row.status === 'completed' ? 'success' : undefined)"
            :stroke-width="5"
            class="flex-1"
          />
        </div>
      </template>
    </el-table-column>
    <el-table-column prop="message" label="系统说明" min-width="180">
      <template #default="{ row }">
        <span class="text-sm text-slate-600 dark:text-slate-400 font-mono">{{ row.message || "-" }}</span>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
defineProps<{
  tasks: Array<{
    id: number;
    task_type: string;
    status: string;
    progress: number;
    message: string;
  }>;
}>();

function formatType(type: string) {
  if (type === "crawl") return "网络爬虫";
  if (type === "import") return "数据导入";
  if (type === "analysis") return "智能分析";
  return type;
}

function getTypeTag(type: string): any {
  if (type === "crawl") return "primary";
  if (type === "import") return "warning";
  return "info";
}

function formatStatus(status: string) {
  if (status === "pending") return "等待中";
  if (status === "running") return "进行中";
  if (status === "completed") return "已完成";
  if (status === "failed") return "已失败";
  return status;
}

function getStatusTag(status: string): any {
  if (status === "pending") return "info";
  if (status === "running") return "warning";
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  return "info";
}
</script>
