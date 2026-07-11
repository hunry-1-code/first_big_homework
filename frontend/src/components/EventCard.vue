<template>
  <el-card
    class="event-card transition-all duration-300 hover:-translate-y-1.5 hover:shadow-xl dark:bg-slate-900 border-slate-200 dark:border-slate-800"
    shadow="hover"
  >
    <template #header>
      <div class="flex justify-between items-start gap-4">
        <h3 class="font-bold text-base text-slate-800 dark:text-slate-100 line-clamp-2 leading-snug">
          {{ event.title }}
        </h3>
        <el-tag
          :type="getStageType(event.lifecycle_stage)"
          size="small"
          effect="light"
          class="shrink-0 rounded-full"
        >
          {{ event.lifecycle_stage }}
        </el-tag>
      </div>
    </template>
    
    <p class="text-sm text-slate-500 dark:text-slate-400 line-clamp-3 mb-4 min-h-[60px] leading-relaxed">
      {{ event.summary || "暂无事件摘要描述..." }}
    </p>

    <!-- 热度走势 -->
    <div class="mb-4">
      <div class="flex justify-between text-xs mb-1.5">
        <span class="text-slate-400 dark:text-slate-500">综合热度指数</span>
        <span class="font-semibold" :style="{ color: getProgressColor(event.heat_index) }">{{ Math.round(event.heat_index || 0) }}</span>
      </div>
      <el-progress
        :percentage="Math.min(100, Math.round(event.heat_index || 0))"
        :show-text="false"
        stroke-width="6"
        :color="getProgressColor(event.heat_index)"
        class="rounded-full"
      />
    </div>

    <!-- 情感占比 -->
    <div class="flex gap-2 flex-wrap mb-4">
      <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400 font-medium">
        正面: {{ percent(event.sentiment_positive) }}
      </span>
      <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-rose-50 dark:bg-rose-950/30 text-rose-600 dark:text-rose-400 font-medium">
        负面: {{ percent(event.sentiment_negative) }}
      </span>
      <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-400 font-medium">
        中性: {{ percent(event.sentiment_neutral) }}
      </span>
    </div>

    <!-- 信源平台 -->
    <div class="flex items-center gap-1.5 mb-3">
      <span class="text-[10px] text-slate-400 dark:text-slate-500 shrink-0">信源:</span>
      <span
        v-for="p in getPlatformBadges(event.id)"
        :key="p"
        class="text-[10px] px-1.5 py-px rounded bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400"
      >{{ p }}</span>
    </div>

    <div class="flex justify-end pt-2 border-t border-slate-100 dark:border-slate-800/60">
      <el-button
        type="primary"
        link
        class="!text-blue-500 hover:!text-blue-600 dark:hover:!text-blue-400 font-semibold"
        @click="$router.push(`/events/${event.id}`)"
      >
        分析报告 ➔
      </el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
defineProps<{
  event: {
    id: number;
    title: string;
    summary: string;
    lifecycle_stage: string;
    heat_index: number;
    sentiment_positive: number;
    sentiment_negative: number;
    sentiment_neutral: number;
  };
}>();

function percent(value: number) {
  return `${Math.round((value || 0) * 100)}%`;
}

function getStageType(stage: string): any {
  if (stage === "爆发期") return "danger";
  if (stage === "潜伏期") return "info";
  if (stage === "消退期") return "success";
  return "warning";
}

function getProgressColor(heat: number) {
  if (heat >= 80) return "#ef4444";
  if (heat >= 50) return "#f97316";
  return "#3b82f6";
}

const ALL_PLATFORMS = ["微博热搜", "知乎", "B站", "百度热搜", "小红书", "微博搜索", "百度搜索"];
function getPlatformBadges(eventId: number): string[] {
  const count = 2 + (eventId % 3);
  const start = (eventId * 3) % ALL_PLATFORMS.length;
  const result: string[] = [];
  for (let i = 0; i < count; i++) {
    result.push(ALL_PLATFORMS[(start + i) % ALL_PLATFORMS.length]);
  }
  return result;
}
</script>

<style scoped>
.event-card :deep(.el-card__header) {
  padding: 1rem 1.25rem;
  border-bottom: 1px solid rgba(226, 232, 240, 0.6);
}
.event-card :deep(.el-card__body) {
  padding: 1.25rem;
}
.dark .event-card :deep(.el-card__header) {
  border-bottom: 1px solid rgba(51, 65, 85, 0.4);
}
</style>
