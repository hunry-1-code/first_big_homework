<script setup lang="ts">
import { deviceDetection } from "@pureadmin/utils";
defineOptions({ name: "SecurityLog" });
</script>
<template>
  <div :class="['min-w-45', deviceDetection() ? 'max-w-full' : 'max-w-[70%]']">
    <h3 class="my-8!">安全日志</h3>
    <div class="flex flex-col items-center justify-center py-20 text-slate-400">
      <span class="text-4xl">🚧</span>
      <p class="mt-4 text-sm">安全日志功能即将上线</p>
    </div>
  </div>
</template>
