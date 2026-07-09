<template>
  <AppShell>
    <div class="page-header">
      <div>
        <h1 class="page-title">智能问答</h1>
        <p class="muted">基于事件材料、报告和引用依据回答问题。</p>
      </div>
    </div>
    <div class="surface">
      <el-input v-model="question" type="textarea" :rows="4" placeholder="请输入问题，例如：这个事件目前公众态度如何？" />
      <el-button type="primary" :loading="loading" style="margin-top: 12px" @click="ask">提问</el-button>
      <el-divider />
      <div v-if="answer">
        <strong>回答</strong>
        <p>{{ answer }}</p>
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { ref } from "vue";

import { askQuestion } from "../api/qa";
import AppShell from "../components/AppShell.vue";

const question = ref("");
const answer = ref("");
const loading = ref(false);

async function ask() {
  loading.value = true;
  try {
    const response = await askQuestion({ question: question.value, event_id: 1 });
    answer.value = response.data.answer;
  } finally {
    loading.value = false;
  }
}
</script>

