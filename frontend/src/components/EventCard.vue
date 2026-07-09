<template>
  <el-card shadow="hover">
    <template #header>
      <div style="display: flex; justify-content: space-between; gap: 12px">
        <strong>{{ event.title }}</strong>
        <el-tag type="warning">{{ event.lifecycle_stage }}</el-tag>
      </div>
    </template>
    <p class="muted">{{ event.summary }}</p>
    <el-progress :percentage="Math.min(100, Math.round(event.heat_index || 0))" />
    <div style="margin-top: 12px; display: flex; gap: 8px">
      <el-tag type="success">正面 {{ percent(event.sentiment_positive) }}</el-tag>
      <el-tag type="danger">负面 {{ percent(event.sentiment_negative) }}</el-tag>
      <el-tag>中性 {{ percent(event.sentiment_neutral) }}</el-tag>
    </div>
    <div style="margin-top: 14px">
      <el-button type="primary" text @click="$router.push(`/events/${event.id}`)">查看详情</el-button>
    </div>
  </el-card>
</template>

<script setup>
defineProps({
  event: {
    type: Object,
    required: true
  }
});

function percent(value) {
  return `${Math.round((value || 0) * 100)}%`;
}
</script>

