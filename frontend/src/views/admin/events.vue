<template>
  <div class="events-mgr p-6 space-y-6">
    <div class="flex justify-between items-center bg-white dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800/60 p-6 rounded-2xl shadow-sm">
      <div>
        <h1 class="text-2xl font-bold text-slate-800 dark:text-slate-100">📋 事件管理中心</h1>
        <p class="text-sm text-slate-500 dark:text-slate-400 mt-1">管理正式事件、发布事件簇、审查合并候选</p>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="bg-white dark:bg-slate-900 rounded-xl border border-slate-200/60 dark:border-slate-800/60 p-4">
      <!-- 正式事件 -->
      <el-tab-pane label="正式事件" name="events">
        <div class="flex items-center gap-3 mb-4">
          <el-input v-model="eventKeyword" placeholder="搜索事件" size="default" clearable class="!w-[200px]" @keyup.enter="loadEvents" @clear="loadEvents" />
          <el-button size="default" @click="loadEvents">搜索</el-button>
          <span class="text-xs text-slate-400 ml-auto">共 {{ eventTotal }} 个事件</span>
        </div>
        <el-table :data="events" stripe size="default" v-loading="loading">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="text-xs" v-html="row.title?.replace(/<[^>]+>/g,'').slice(0,60) || '-'" />
            </template>
          </el-table-column>
          <el-table-column prop="heat_index" label="热度" width="80" align="center">
            <template #default="{ row }">{{ Math.round(row.heat_index || 0) }}</template>
          </el-table-column>
          <el-table-column prop="lifecycle_stage" label="阶段" width="80" align="center" />
          <el-table-column label="情感" width="140">
            <template #default="{ row }">
              <span class="text-xs text-emerald-500">+{{ Math.round((row.sentiment_positive||0)*100) }}%</span>
              <span class="text-xs text-red-400 mx-1">-{{ Math.round((row.sentiment_negative||0)*100) }}%</span>
              <span class="text-xs text-slate-400">{{ Math.round((row.sentiment_neutral||0)*100) }}%</span>
            </template>
          </el-table-column>
          <el-table-column prop="platform_count" label="平台数" width="70" align="center" />
          <el-table-column prop="independent_report_count" label="报道" width="70" align="center" />
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="$router.push(`/events/${row.id}`)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="flex justify-end mt-4">
          <el-pagination v-model:current-page="eventPage" v-model:page-size="eventSize"
            :total="eventTotal" :page-sizes="[10,20,50]" layout="total,sizes,prev,pager,next" small
            @current-change="loadEvents" @size-change="loadEvents" />
        </div>
      </el-tab-pane>

      <!-- 聚合运行 & 待发布事件簇 -->
      <el-tab-pane label="事件簇" name="clusters">
        <div class="space-y-4" v-loading="clusterLoading">
          <div v-for="run in aggRuns" :key="run.id" class="border border-slate-200 dark:border-slate-700 rounded-lg p-4">
            <div class="flex justify-between items-center mb-3">
              <div>
                <span class="font-medium text-slate-700 dark:text-slate-200">聚合运行 #{{ run.id }}</span>
                <span class="text-xs text-slate-400 ml-3">{{ run.created_at?.slice(0,16) }}</span>
                <el-tag size="small" class="ml-2" :type="run.status==='success'?'success':'info'">{{ run.status }}</el-tag>
              </div>
              <el-button size="small" @click="loadClusters(run.id)">刷新事件簇</el-button>
            </div>
            <div v-if="run._clusters">
              <el-table :data="run._clusters" size="small" stripe>
                <el-table-column prop="id" label="ID" width="50" />
                <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip>
                  <template #default="{ row }">
                    <span class="text-xs" v-html="(row.title||'').replace(/<[^>]+>/g,'').slice(0,80) || '-'" />
                  </template>
                </el-table-column>
                <el-table-column prop="article_count" label="文章数" width="70" align="center" />
                <el-table-column label="操作" width="140">
                  <template #default="{ row }">
                    <el-button v-if="!row._published" type="primary" size="small" @click="publishCluster(row)" :loading="row._publishing">
                      发布为事件
                    </el-button>
                    <el-tag v-else size="small" type="success">已发布</el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
          <div v-if="aggRuns.length===0" class="text-center py-10 text-slate-400 text-sm">暂无聚合运行记录</div>
        </div>
      </el-tab-pane>

      <!-- 合并候选 -->
      <el-tab-pane label="合并候选" name="merge">
        <div v-loading="mergeLoading">
          <el-table :data="mergeCandidates" stripe size="default">
            <el-table-column label="源事件" min-width="120">
              <template #default="{ row }">
                <span class="text-xs" v-html="(row.source_title||'-').replace(/<[^>]+>/g,'').slice(0,40)" />
              </template>
            </el-table-column>
            <el-table-column label="目标事件" min-width="120">
              <template #default="{ row }">
                <span class="text-xs" v-html="(row.target_title||'-').replace(/<[^>]+>/g,'').slice(0,40)" />
              </template>
            </el-table-column>
            <el-table-column prop="score" label="相似度" width="80" align="center">
              <template #default="{ row }">{{ Math.round((row.similarity_score||0)*100) }}%</template>
            </el-table-column>
            <el-table-column label="操作" width="160">
              <template #default="{ row }">
                <el-button type="success" size="small" @click="confirmMerge(row)" :loading="row._merging">确认合并</el-button>
                <el-button type="danger" size="small" @click="rejectMerge(row)">拒绝</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="mergeCandidates.length===0" class="text-center py-10 text-slate-400 text-sm">暂无合并候选</div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { http } from "@/utils/http";
import { message } from "@/utils/message";

defineOptions({ name: "AdminEvents" });

const activeTab = ref("events");
const loading = ref(false);
const events = ref<any[]>([]);
const eventTotal = ref(0);
const eventPage = ref(1);
const eventSize = ref(20);
const eventKeyword = ref("");

const clusterLoading = ref(false);
const aggRuns = ref<any[]>([]);
const mergeLoading = ref(false);
const mergeCandidates = ref<any[]>([]);

async function loadEvents() {
  loading.value = true;
  try {
    const res = await http.request<any>("get", "/api/events", {
      params: { page: eventPage.value, size: eventSize.value, keyword: eventKeyword.value || undefined }
    });
    events.value = res.data.events || [];
    eventTotal.value = res.data.total || 0;
  } catch { events.value = []; }
  finally { loading.value = false; }
}

async function loadAggRuns() {
  clusterLoading.value = true;
  try {
    const res = await http.request<any>("get", "/api/aggregation/runs", { params: { size: 20 } });
    aggRuns.value = res.data.runs || [];
  } catch { aggRuns.value = []; }
  finally { clusterLoading.value = false; }
}

async function loadClusters(runId: number) {
  try {
    const res = await http.request<any>("get", `/api/aggregation/runs/${runId}/clusters`);
    const run = aggRuns.value.find(r => r.id === runId);
    if (run) run._clusters = res.data.clusters || [];
  } catch { message("加载失败", { type: "error" }); }
}

async function publishCluster(cluster: any) {
  cluster._publishing = true;
  try {
    await http.request("post", `/api/aggregation/clusters/${cluster.id}/publish`);
    cluster._published = true;
    message("发布成功", { type: "success" });
    loadEvents();
  } catch { message("发布失败", { type: "error" }); }
  finally { cluster._publishing = false; }
}

async function loadMergeCandidates() {
  mergeLoading.value = true;
  try {
    const res = await http.request<any>("get", "/api/aggregation/merge-candidates");
    mergeCandidates.value = res.data.candidates || [];
  } catch { mergeCandidates.value = []; }
  finally { mergeLoading.value = false; }
}

async function confirmMerge(row: any) {
  row._merging = true;
  try {
    await http.request("post", `/api/aggregation/merge-candidates/${row.id}/confirm`);
    message("合并成功", { type: "success" });
    loadMergeCandidates(); loadEvents();
  } catch { message("合并失败", { type: "error" }); }
  finally { row._merging = false; }
}

async function rejectMerge(row: any) {
  try {
    await http.request("post", `/api/aggregation/merge-candidates/${row.id}/reject`);
    message("已拒绝", { type: "success" });
    loadMergeCandidates();
  } catch { message("操作失败", { type: "error" }); }
}

onMounted(() => { loadEvents(); loadAggRuns(); loadMergeCandidates(); });
</script>

<style scoped>
.events-mgr { min-height: calc(100vh - 120px); }
</style>
