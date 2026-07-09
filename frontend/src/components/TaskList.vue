<template>
  <el-table :data="tasks" size="small">
    <el-table-column prop="id" label="ID" width="70" />
    <el-table-column prop="task_type" label="类型" />
    <el-table-column prop="status" label="状态" />
    <el-table-column prop="progress" label="进度" width="90" />
    <el-table-column prop="message" label="说明" />
  </el-table>
</template>

<script setup>
defineProps({
  tasks: {
    type: Array,
    default: () => []
  }
});
</script>

