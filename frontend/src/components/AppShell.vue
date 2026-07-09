<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">网络舆情事件<br />智能分析系统</div>
      <el-menu :default-active="$route.path" router background-color="#17202a" text-color="#cbd6df" active-text-color="#ffffff">
        <el-menu-item index="/">舆情看板</el-menu-item>
        <el-menu-item index="/qa">智能问答</el-menu-item>
        <el-menu-item index="/user">个人中心</el-menu-item>
        <el-menu-item v-if="auth.isAdmin" index="/admin">系统管理</el-menu-item>
      </el-menu>
    </aside>
    <main class="main-area">
      <slot />
    </main>
  </div>
</template>

<script setup>
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
</script>
