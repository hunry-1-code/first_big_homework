<template>
  <AppShell>
    <div class="page-header">
      <div>
        <h1 class="page-title">个人中心</h1>
        <p class="muted">管理关键词、数据源、问答历史和任务记录。</p>
      </div>
      <el-button @click="logout">退出登录</el-button>
    </div>

    <div class="grid">
      <section class="surface">
        <h2>用户信息</h2>
        <p>用户名：{{ auth.user?.username }}</p>
        <p>角色：{{ auth.user?.role }}</p>
      </section>
      <section class="surface">
        <h2>关注配置</h2>
        <el-select v-model="config.followed_sources" multiple placeholder="选择数据源" style="width: 100%">
          <el-option v-for="source in sources" :key="source.code" :label="source.platform" :value="source.code" />
        </el-select>
        <el-input v-model="keywordInput" placeholder="输入关键词后回车" style="margin-top: 12px" @keyup.enter="addKeyword" />
        <div style="margin-top: 10px">
          <el-tag v-for="word in config.keywords" :key="word" closable style="margin: 4px" @close="removeKeyword(word)">
            {{ word }}
          </el-tag>
        </div>
        <el-button type="primary" style="margin-top: 12px" @click="save">保存配置</el-button>
      </section>
      <section class="surface">
        <h2>任务记录</h2>
        <TaskList :tasks="tasks" />
      </section>
    </div>
  </AppShell>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";

import { getMyTasks } from "../api/tasks";
import { getUserConfig, getUserSources, saveUserConfig } from "../api/user";
import AppShell from "../components/AppShell.vue";
import TaskList from "../components/TaskList.vue";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const keywordInput = ref("");
const sources = ref([]);
const tasks = ref([]);
const config = reactive({ followed_sources: [], keywords: [] });

onMounted(async () => {
  const [sourceResp, configResp, taskResp] = await Promise.all([getUserSources(), getUserConfig(), getMyTasks()]);
  sources.value = sourceResp.data.presets;
  Object.assign(config, configResp.data);
  tasks.value = taskResp.data.tasks;
});

function addKeyword() {
  const word = keywordInput.value.trim();
  if (word && !config.keywords.includes(word)) {
    config.keywords.push(word);
  }
  keywordInput.value = "";
}

function removeKeyword(word) {
  config.keywords = config.keywords.filter((item) => item !== word);
}

async function save() {
  await saveUserConfig(config);
}

function logout() {
  auth.logout();
  router.push("/login");
}
</script>

