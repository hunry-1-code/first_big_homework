<template>
  <div class="qa-container flex flex-col md:flex-row gap-6 p-6 h-[calc(100vh-120px)] overflow-hidden">
    <!-- 左侧/顶端：事件上下文选择 -->
    <div class="w-full md:w-80 shrink-0 flex flex-col bg-white dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800/60 rounded-xl p-4 shadow-sm">
      <h3 class="font-bold text-slate-800 dark:text-slate-200 mb-3 flex items-center gap-2">
        <span>💬 智能对话上下文</span>
      </h3>
      <p class="text-xs text-slate-400 dark:text-slate-500 mb-4 leading-relaxed">
        选择一个舆情事件作为AI对话的上下文背景，AI将围绕该事件的采集报道和AI研判报告为您解答。
      </p>

      <el-form label-position="top">
        <el-form-item label="当前讨论事件">
          <el-select
            v-model="selectedEventId"
            placeholder="请选择相关舆情事件"
            class="w-full"
            size="large"
            clearable
            @change="handleEventChange"
          >
            <el-option
              v-for="item in eventsStore.events"
              :key="item.id"
              :label="item.title"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="聚焦平台（可选）">
          <el-select
            v-model="selectedPlatform"
            placeholder="全部平台"
            class="w-full"
            size="large"
            clearable
          >
            <el-option
              v-for="p in availablePlatforms"
              :key="p.name"
              :label="p.name"
              :value="p.name"
            >
              <span class="inline-flex items-center gap-1.5">
                <span :style="{ color: p.color, display: 'inline-flex' }">
                  <IconifyIconOffline :icon="p.icon" style="font-size:16px" />
                </span>
                <span :style="{ color: p.color }">{{ p.name }}</span>
              </span>
            </el-option>
          </el-select>
        </el-form-item>
      </el-form>

      <div class="border-t border-slate-100 dark:border-slate-800/60 pt-4 mt-auto hidden md:block">
        <div class="text-xs text-slate-400 dark:text-slate-500 flex flex-col gap-1">
          <span>💡 提示：</span>
          <span>1. 可从「事件详情」顶部或 AI 研判卡片一键跳转至此。</span>
          <span>2. 选择平台后，AI 将聚焦该平台的报道进行分析。</span>
        </div>
      </div>
    </div>

    <!-- 右侧：ChatGPT 对话气泡窗 -->
    <div class="flex-1 flex flex-col bg-white dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800/60 rounded-xl shadow-sm overflow-hidden h-full">
      <!-- 聊天消息区域 -->
      <div ref="chatBoxRef" class="flex-1 p-6 overflow-y-auto space-y-4">
        <div v-if="messages.length === 0" class="flex flex-col items-center justify-center h-full text-slate-400">
          <span class="text-5xl">🤖</span>
          <p class="mt-4 text-sm font-medium">我是舆情事件智能AI助理，请在左侧选择讨论事件后向我提问。</p>
        </div>

        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          :class="['flex w-full items-start gap-3', msg.role === 'user' ? 'justify-end' : 'justify-start']"
        >
          <!-- AI 头像 -->
          <div v-if="msg.role === 'assistant'" class="size-8 rounded-full bg-blue-500 flex-c text-white font-bold shrink-0 shadow-sm text-sm">
            AI
          </div>

          <!-- 消息泡泡 -->
          <div
            :class="[
              'max-w-[75%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed shadow-sm',
              msg.role === 'user'
                ? 'bg-blue-600 text-white rounded-tr-none'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 rounded-tl-none border border-slate-200/40 dark:border-slate-700/30'
            ]"
          >
            <div class="whitespace-pre-wrap">{{ msg.content }}</div>
            <div v-if="msg.time" class="text-[10px] text-right mt-1.5 opacity-60">
              {{ msg.time }}
            </div>
          </div>

          <!-- 用户头像 -->
          <div v-if="msg.role === 'user'" class="size-8 rounded-full bg-slate-300 dark:bg-slate-700 flex-c text-slate-700 dark:text-slate-300 font-bold shrink-0 shadow-sm text-sm">
            我
          </div>
        </div>

        <!-- 思考中动画 -->
        <div v-if="thinking" class="flex w-full items-start gap-3 justify-start">
          <div class="size-8 rounded-full bg-blue-500 flex-c text-white font-bold shrink-0 shadow-sm text-sm animate-pulse">
            AI
          </div>
          <div class="bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 px-4 py-3 rounded-2xl rounded-tl-none border border-slate-200/40 dark:border-slate-700/30 text-sm shadow-sm flex items-center gap-1.5">
            <span class="font-medium animate-pulse">AI 正在思考中</span>
            <span class="flex gap-1">
              <span class="dot animate-bounce" style="animation-delay: 0ms">.</span>
              <span class="dot animate-bounce" style="animation-delay: 150ms">.</span>
              <span class="dot animate-bounce" style="animation-delay: 300ms">.</span>
            </span>
          </div>
        </div>
      </div>

      <!-- 输入栏 -->
      <div class="p-4 border-t border-slate-200/60 dark:border-slate-800/60 bg-slate-50/50 dark:bg-slate-900/50 shrink-0">
        <div class="flex gap-2">
          <el-input
            v-model="inputQuestion"
            type="textarea"
            :rows="2"
            resize="none"
            placeholder="请输入您的问题... (按 Enter 发送，Ctrl+Enter 换行)"
            size="large"
            @keydown="handleKeyDown"
            class="flex-1"
          />
          <el-button
            type="primary"
            size="large"
            class="h-auto px-6"
            :disabled="!inputQuestion.trim() || thinking"
            @click="sendQuestion"
          >
            发送
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, nextTick } from "vue";
import { useRoute } from "vue-router";
import { useEventsStore } from "@/store/modules/events";
import { askQuestion, getQaHistory } from "@/api/qa";
import { message } from "@/utils/message";
import { PLATFORMS } from "@/constants/platforms";
import IconifyIconOffline from "@/components/ReIcon/src/iconifyIconOffline";

defineOptions({
  name: "OpinionQa"
});

const route = useRoute();
const eventsStore = useEventsStore();

const selectedEventId = ref<number | undefined>(undefined);
const selectedPlatform = ref<string>("");
const inputQuestion = ref("");
const thinking = ref(false);
const chatBoxRef = ref<HTMLDivElement>();

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  time?: string;
}

const messages = ref<ChatMessage[]>([]);

onMounted(async () => {
  // 加载事件下拉列表
  await eventsStore.loadEvents();

  // 如果路由携带了 event_id 参数，则自动选择
  if (route.query.event_id) {
    selectedEventId.value = Number(route.query.event_id);
  }
  if (route.query.platform) {
    selectedPlatform.value = String(route.query.platform);
  }

  // 加载历史提问记录
  await loadHistory();
});

// 加载历史提问记录
async function loadHistory() {
  try {
    const response = await getQaHistory();
    // 接口返回历史记录列表映射到消息流
    if (response.data && response.data.history) {
      const historyList: ChatMessage[] = [];
      response.data.history.forEach((item: any) => {
        // 如果当前选择了某个事件，只过滤出该事件的历史提问；如果未选事件，展示所有历史
        if (!selectedEventId.value || item.event_id === selectedEventId.value) {
          historyList.push({
            role: "user",
            content: item.question,
            time: item.created_at
          });
          historyList.push({
            role: "assistant",
            content: item.answer,
            time: item.created_at
          });
        }
      });
      messages.value = historyList;
      scrollToBottom();
    }
  } catch (err) {
    message("加载对话历史记录失败", { type: "error" });
  }
}

// 切换事件上下文
// 只显示选中事件实际涉及的信源平台
const availablePlatforms = computed(() => {
  if (!selectedEventId.value) return PLATFORMS; // 未选事件时显示全部
  const event = eventsStore.events.find((e: any) => e.id === selectedEventId.value);
  if (!event?.platforms?.length) return PLATFORMS;
  return PLATFORMS.filter(p => event.platforms.includes(p.name));
});

function handleEventChange() {
  selectedPlatform.value = ""; // 切换事件时重置平台选择
  messages.value = [];
  loadHistory();
}

// 发送消息
async function sendQuestion() {
  const q = inputQuestion.value.trim();
  if (!q) return;

  // 新增用户消息到流中
  messages.value.push({
    role: "user",
    content: q,
    time: formatTime(new Date())
  });
  inputQuestion.value = "";
  scrollToBottom();

  thinking.value = true;

  try {
    // 如果选了平台，将平台上下文注入问题
    const contextualQuestion = selectedPlatform.value
      ? `[聚焦平台：${selectedPlatform.value}] ${q}`
      : q;
    const response = await askQuestion({
      question: contextualQuestion,
      event_id: selectedEventId.value
    });

    messages.value.push({
      role: "assistant",
      content: response.data.answer,
      time: formatTime(new Date())
    });
  } catch (err: any) {
    messages.value.push({
      role: "assistant",
      content: err.response?.data?.message || "AI 应答失败，请稍后重试。"
    });
  } finally {
    thinking.value = false;
    scrollToBottom();
  }
}

// 辅助方法：自动滚动到底部
function scrollToBottom() {
  nextTick(() => {
    if (chatBoxRef.value) {
      chatBoxRef.value.scrollTop = chatBoxRef.value.scrollHeight;
    }
  });
}

// 辅助方法：处理回车发送
function handleKeyDown(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.ctrlKey && !e.shiftKey) {
    e.preventDefault();
    sendQuestion();
  }
}

// 格式化时间显示
function formatTime(d: Date): string {
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
</script>

<style scoped>
.dot {
  display: inline-block;
}
</style>
