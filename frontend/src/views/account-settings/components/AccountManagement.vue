<script setup lang="ts">
import { deviceDetection } from "@pureadmin/utils";
defineOptions({ name: "AccountManagement" });
</script>
<template>
  <div :class="['min-w-45', deviceDetection() ? 'max-w-full' : 'max-w-[70%]']">
    <h3 class="my-8!">账户管理</h3>
    <div class="flex flex-col items-center justify-center py-20 text-slate-400">
      <span class="text-4xl">🚧</span>
      <p class="mt-4 text-sm">账户管理功能即将上线</p>
    </div>
  </div>
</template>
