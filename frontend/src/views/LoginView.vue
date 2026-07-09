<template>
  <div class="login-page">
    <el-card class="login-card">
      <h1>网络舆情事件智能分析系统</h1>
      <p class="muted">登录后进入事件看板、问答和个人中心。</p>
      <el-form :model="form" label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名">
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" autocomplete="current-password" show-password />
        </el-form-item>
        <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
        <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%; margin-top: 14px">
          登录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";

import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const loading = ref(false);
const error = ref("");
const form = reactive({ username: "admin", password: "admin123" });

async function submit() {
  loading.value = true;
  error.value = "";
  try {
    await auth.login(form);
    router.push("/");
  } catch (err) {
    error.value = err.response?.data?.message || "登录失败";
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #f4f6f8 0%, #dde7ef 100%);
}

.login-card {
  width: min(420px, calc(100vw - 32px));
}
</style>

