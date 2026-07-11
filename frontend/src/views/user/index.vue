<template>
  <div class="user-profile-container p-6 space-y-6">
    <!-- 头部模块 -->
    <div class="flex justify-between items-center bg-white dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800/60 p-6 rounded-2xl shadow-sm">
      <div class="flex items-center gap-4">
        <div class="size-14 rounded-full bg-gradient-to-tr from-blue-500 to-indigo-600 flex-c text-white text-xl font-bold shadow-md">
          {{ userStore.username.substring(0, 2).toUpperCase() }}
        </div>
        <div>
          <h2 class="text-xl font-bold text-slate-800 dark:text-slate-100">{{ userStore.username }}</h2>
          <div class="flex items-center gap-2 mt-1.5">
            <el-tag size="small" type="success" effect="dark" class="rounded-full">
              {{ isAdmin ? "系统管理员" : "普通用户" }}
            </el-tag>
            <span class="text-xs text-slate-400">系统角色权限：{{ userStore.roles.join(', ') }}</span>
          </div>
        </div>
      </div>
      <el-button type="danger" plain @click="handleLogout">退出登录</el-button>
    </div>

    <!-- 主配置网格 -->
    <el-row :gutter="24">
      <!-- 关注配置项 -->
      <el-col :xs="24" :lg="12" class="mb-6">
        <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl h-full flex flex-col">
          <template #header>
            <div class="font-bold text-slate-800 dark:text-slate-100 flex items-center gap-1.5">
              <span>⚙️ 监控敏感关注配置</span>
            </div>
          </template>

          <el-form label-position="top" class="space-y-4">
            <!-- 关注的数据源 -->
            <el-form-item label="关注的数据源平台">
              <el-select
                v-model="config.followed_sources"
                multiple
                placeholder="请选择要监控的源头平台"
                size="large"
                class="w-full"
              >
                <el-option
                  v-for="source in sources"
                  :key="source.code"
                  :label="source.platform"
                  :value="source.code"
                />
              </el-select>
            </el-form-item>

            <!-- 关注的敏感词 -->
            <el-form-item label="关注的监控关键词（回车生成标签）">
              <el-input
                v-model="keywordInput"
                placeholder="输入关键词后按回车(Enter)添加..."
                size="large"
                @keyup.enter="addKeyword"
              >
                <template #suffix>
                  <span class="text-xs text-slate-400">Enter</span>
                </template>
              </el-input>

              <!-- 关键词 Tag 胶囊 -->
              <div class="flex flex-wrap gap-2 mt-3">
                <el-tag
                  v-for="word in config.keywords"
                  :key="word"
                  closable
                  size="default"
                  type="warning"
                  @close="removeKeyword(word)"
                  class="rounded-full px-3"
                >
                  {{ word }}
                </el-tag>
                <span v-if="config.keywords.length === 0" class="text-xs text-slate-400">暂无关注敏感词，请输入添加。</span>
              </div>
            </el-form-item>

            <!-- 保存按钮 -->
            <div class="pt-4 border-t border-slate-100 dark:border-slate-800/60 flex justify-end">
              <el-button type="primary" size="large" @click="saveConfigAction">
                保存监控配置
              </el-button>
            </div>
          </el-form>
        </el-card>
      </el-col>

      <!-- 个人任务运行流水 -->
      <el-col :xs="24" :lg="12" class="mb-6">
        <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl h-full flex flex-col">
          <template #header>
            <div class="font-bold text-slate-800 dark:text-slate-100 flex justify-between items-center">
              <span>📋 我的异步任务流水</span>
              <el-button size="small" @click="loadTasks">刷新记录</el-button>
            </div>
          </template>

          <div v-loading="tasksLoading" class="flex-1">
            <TaskList :tasks="tasks" />
            <div v-if="tasks.length === 0" class="flex flex-col items-center justify-center py-10 text-slate-400 text-sm">
              <span>📭</span>
              <p class="mt-2">暂无任何任务流水记录</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, computed } from "vue";
import { useRouter } from "vue-router";
import { useUserStore } from "@/store/modules/user";
import { getUserSources, getUserConfig, saveUserConfig } from "@/api/opinionUser";
import { getMyTasks } from "@/api/tasks";
import TaskList from "@/components/TaskList.vue";
import { message } from "@/utils/message";

defineOptions({
  name: "OpinionUser"
});

const router = useRouter();
const userStore = useUserStore();

const keywordInput = ref("");
const sources = ref<Array<{ code: string; platform: string }>>([]);
const tasks = ref<any[]>([]);
const tasksLoading = ref(false);

const config = reactive<{
  followed_sources: string[];
  keywords: string[];
}>({
  followed_sources: [],
  keywords: []
});

const isAdmin = computed(() => {
  return userStore.roles.includes("admin");
});

onMounted(async () => {
  try {
    const [sourceResp, configResp] = await Promise.all([
      getUserSources(),
      getUserConfig()
    ]);
    sources.value = sourceResp.data.presets;
    Object.assign(config, configResp.data);
  } catch (err) {
    message("获取配置元数据失败", { type: "error" });
  }

  await loadTasks();
});

// 加载任务
async function loadTasks() {
  tasksLoading.value = true;
  try {
    const taskResp = await getMyTasks();
    tasks.value = taskResp.data.tasks;
  } catch (err) {
    message("加载任务流水失败", { type: "error" });
  } finally {
    tasksLoading.value = false;
  }
}

// 添加敏感词
function addKeyword() {
  const word = keywordInput.value.trim();
  if (word && !config.keywords.includes(word)) {
    config.keywords.push(word);
  }
  keywordInput.value = "";
}

// 移除敏感词
function removeKeyword(word: string) {
  config.keywords = config.keywords.filter(item => item !== word);
}

// 保存配置
async function saveConfigAction() {
  try {
    await saveUserConfig(config);
    message("敏感关注配置保存成功！", { type: "success" });
  } catch (err) {
    message("配置保存失败", { type: "error" });
  }
}

// 退出登录
function handleLogout() {
  userStore.logOut();
  message("您已安全退出系统", { type: "success" });
}
</script>

<style scoped>
.user-profile-container {
  min-height: calc(100vh - 120px);
}
</style>
