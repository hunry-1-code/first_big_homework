<script setup lang="ts">
import { onMounted, ref, watch, nextTick, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import * as echarts from "echarts";
import "echarts-wordcloud";
import { getEvent, exportEventReport } from "@/api/events";
import { useDark } from "@pureadmin/utils";
import { message } from "@/utils/message";
import PlusIcon from "~icons/ep/plus";
import MinusIcon from "~icons/ep/minus";
import RefreshRightIcon from "~icons/ep/refresh-right";

defineOptions({
  name: "EventDetail"
});

const route = useRoute();
const router = useRouter();
const eventData = ref<any>(null);
const loading = ref(true);

const { isDark } = useDark();
const currentZoom = ref(1.0);
const initialZoom = ref(1.0);
const currentShape = ref("circle");
const ZOOM_STEP = 0.12;
const ZOOM_MIN = 0.4;
const ZOOM_MAX = 2.5;

const shapeOptions = [
  { label: "圆形", value: "circle" },
  { label: "心形", value: "cardioid" },
  { label: "菱形", value: "diamond" },
  { label: "方形", value: "square" },
  { label: "三角", value: "triangle" },
  { label: "倒三角", value: "triangle-forward" },
  { label: "五边形", value: "pentagon" },
  { label: "星形", value: "star" }
];

const trendRef = ref<HTMLDivElement>();
const sentimentRef = ref<HTMLDivElement>();
const platformRef = ref<HTMLDivElement>();
const bubbleRef = ref<HTMLDivElement>();

let trendChart: echarts.ECharts | null = null;
let sentimentChart: echarts.ECharts | null = null;
let platformChart: echarts.ECharts | null = null;
let bubbleChart: echarts.ECharts | null = null;

onMounted(async () => {
  try {
    const response = await getEvent(Number(route.params.id));
    eventData.value = response.data;
    nextTick(() => {
      initCharts();
    });
  } catch (err) {
    message("加载事件详情失败", { type: "error" });
  } finally {
    loading.value = false;
  }
});

function initCharts() {
  if (!eventData.value) return;

  const dark = isDark.value;
  const textColor = dark ? "#cbd6df" : "#4a5568";
  const splitLineColor = dark ? "#2d3748" : "#edf2f7";

  // 1. 发展趋势折线图
  if (trendRef.value) {
    if (trendChart) trendChart.dispose();
    trendChart = echarts.init(trendRef.value);
    trendChart.setOption({
      grid: { top: 30, right: 20, bottom: 30, left: 40 },
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: eventData.value.trend?.dates || [],
        axisLabel: { color: textColor },
        axisLine: { lineStyle: { color: splitLineColor } }
      },
      yAxis: {
        type: "value",
        axisLabel: { color: textColor },
        splitLine: { lineStyle: { color: splitLineColor } }
      },
      series: [
        {
          name: "热度走势",
          data: eventData.value.trend?.counts || [],
          type: "line",
          smooth: true,
          lineStyle: { width: 3, color: "#409eff" },
          itemStyle: { color: "#409eff" },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(64,158,255,0.35)" },
              { offset: 1, color: "rgba(64,158,255,0)" }
            ])
          }
        }
      ]
    });
  }

  // 2. 情感极性分布环形图
  if (sentimentRef.value) {
    if (sentimentChart) sentimentChart.dispose();
    sentimentChart = echarts.init(sentimentRef.value);
    sentimentChart.setOption({
      tooltip: { trigger: "item", formatter: "{a} <br/>{b}: {c} ({d}%)" },
      legend: { bottom: "0%", textStyle: { color: textColor }, itemGap: 15 },
      series: [
        {
          name: "情感倾向",
          type: "pie",
          radius: ["45%", "70%"],
          center: ["50%", "45%"],
          avoidLabelOverlap: false,
          itemStyle: { borderRadius: 6, borderColor: dark ? "#111827" : "#fff", borderWidth: 2 },
          label: { show: false },
          data: [
            { value: eventData.value.sentiment_positive || 0, name: "正面", itemStyle: { color: "#67c23a" } },
            { value: eventData.value.sentiment_neutral || 0, name: "中性", itemStyle: { color: "#909399" } },
            { value: eventData.value.sentiment_negative || 0, name: "负面", itemStyle: { color: "#f56c6c" } }
          ]
        }
      ]
    });
  }

  // 3. 平台来源柱状图
  if (platformRef.value) {
    if (platformChart) platformChart.dispose();
    platformChart = echarts.init(platformRef.value);
    const platforms = eventData.value.platform?.platforms || [];
    platformChart.setOption({
      grid: { top: 30, right: 20, bottom: 30, left: 40 },
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: platforms.map((p: any) => p.platform || p.name),
        axisLabel: { color: textColor },
        axisLine: { lineStyle: { color: splitLineColor } }
      },
      yAxis: {
        type: "value",
        axisLabel: { color: textColor },
        splitLine: { lineStyle: { color: splitLineColor } }
      },
      series: [
        {
          name: "文章数",
          data: platforms.map((p: any) => p.count),
          type: "bar",
          barWidth: "35%",
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "#36b2f0" },
              { offset: 1, color: "#0066cc" }
            ]),
            borderRadius: [4, 4, 0, 0]
          }
        }
      ]
    });
  }

  initBubbleChart();
}

// 监听暗黑模式切换重新渲染图表
watch(isDark, () => {
  nextTick(() => initCharts());
});

const handleResize = () => {
  trendChart?.resize();
  sentimentChart?.resize();
  platformChart?.resize();
  bubbleChart?.resize();
};

window.addEventListener("resize", handleResize);
onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  trendChart?.dispose();
  sentimentChart?.dispose();
  platformChart?.dispose();
  bubbleChart?.dispose();
});

async function handleExport() {
  try {
    const res = await exportEventReport(Number(route.params.id), "html");
    message(`报告导出成功！导出格式: ${res.data.format}。${res.data.message}`, {
      type: "success"
    });
  } catch (err) {
    message("报告导出失败", { type: "error" });
  }
}

function percent(value: number) {
  return `${Math.round((value || 0) * 100)}%`;
}

function getWordColor(t: number): string {
  // 根据归一化权重 t (0~1) 分配四档色温梯度
  if (t >= 0.8)  return "rgba(79, 70, 229, 1.0)";   // 核心高热: 深邃靛蓝
  if (t >= 0.55) return "rgba(59, 130, 246, 1.0)";  // 中高热度: 标准科技蓝
  if (t >= 0.3)  return "rgba(6, 182, 212, 1.0)";   // 中等热度: 冰川青绿
  return "rgba(148, 163, 184, 1.0)";                  // 低热: 温和灰蓝
}

function getWordEmphasisColor(t: number): string {
  if (t >= 0.8)  return "rgba(99, 90, 249, 1.0)";
  if (t >= 0.55) return "rgba(79, 150, 255, 1.0)";
  if (t >= 0.3)  return "rgba(26, 202, 232, 1.0)";
  return "rgba(168, 183, 204, 1.0)";
}

function initBubbleChart() {
  if (!eventData.value || !bubbleRef.value) return;

  const dark = isDark.value;
  const list = eventData.value.keywords?.keywords || [];
  if (list.length === 0) return;

  const count = list.length;
  const weights = list.map((kw: any) => kw.weight || 0);
  const maxW = Math.max(...weights, 1);
  const minW = Math.min(...weights, 0);
  const range = maxW - minW || 1;

  // 动态字号范围: 词多时收窄，词少时放大
  const fontSizeMin = count > 20 ? 10 : count > 12 ? 12 : 14;
  const fontSizeMax = count > 20 ? 48 : count > 12 ? 56 : 64;

  // 排序: 大权重优先放置，布局更稳定
  const sorted = [...list]
    .map((kw: any) => ({ ...kw }))
    .sort((a: any, b: any) => (b.weight || 0) - (a.weight || 0));

  const wordData = sorted.map((kw: any) => {
    const t = ((kw.weight || 0) - minW) / range;
    const fontSize = Math.round(fontSizeMin + t * (fontSizeMax - fontSizeMin));
    return {
      name: kw.word,
      value: kw.weight,
      textStyle: {
        color: getWordColor(t),
        fontSize,
        fontWeight: t >= 0.55 ? "bold" : "normal",
        fontFamily:
          "PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans SC, sans-serif"
      },
      emphasis: {
        textStyle: {
          color: getWordEmphasisColor(t),
          textShadowBlur: 8,
          textShadowColor: dark ? "rgba(0,0,0,0.6)" : "rgba(0,0,0,0.15)"
        }
      }
    };
  });

  // 自适应 gridSize: 词越少、网格越细，堆积越密
  const gridSize = count > 20 ? 8 : count > 12 ? 6 : 4;

  if (bubbleChart) bubbleChart.dispose();
  bubbleChart = echarts.init(bubbleRef.value);
  bubbleChart.setOption({
    backgroundColor: "transparent",
    tooltip: {
      show: true,
      formatter: (params: any) => {
        return `<div class="p-1.5 font-sans text-xs">
          <span class="font-bold text-gray-700 dark:text-gray-200">${params.name}</span><br/>
          <span class="text-gray-400">词汇热度: </span>
          <span class="font-bold text-blue-500">${Math.round((params.value || 0) * 100)}</span>
        </div>`;
      },
      backgroundColor: dark
        ? "rgba(17, 24, 39, 0.95)"
        : "rgba(255, 255, 255, 0.95)",
      borderColor: dark ? "#374151" : "#e5e7eb",
      borderWidth: 1
    },
    series: [
      {
        type: "wordCloud",
        shape: currentShape.value,
        keepAspect: false,
        width: "100%",
        height: "100%",
        left: "center",
        top: "center",
        sizeRange: [fontSizeMin, fontSizeMax],
        rotationRange: [0, 0],
        rotationStep: 0,
        gridSize,
        drawOutOfBound: false,
        shrinkToFit: true,
        layoutAnimation: true,
        textStyle: {
          fontFamily:
            "PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans SC, sans-serif",
          fontWeight: "normal",
          color: (v: any) => {
            const t = ((v.value || 0) - minW) / range;
            return getWordColor(t);
          }
        },
        emphasis: {
          focus: "self",
          textStyle: {
            textShadowBlur: 10,
            textShadowColor: dark
              ? "rgba(0,0,0,0.7)"
              : "rgba(0,0,0,0.2)"
          }
        },
        data: wordData
      }
    ]
  });

  // 重置缩放
  initialZoom.value = 1.0;
  currentZoom.value = 1.0;
  applyZoom();
}

function applyZoom() {
  if (bubbleRef.value) {
    bubbleRef.value.style.transform = `scale(${currentZoom.value})`;
    bubbleRef.value.style.transformOrigin = "center center";
    bubbleRef.value.style.transition = "transform 0.2s ease-out";
  }
}

function updateZoom() {
  applyZoom();
}

function zoomIn() {
  currentZoom.value = Math.min(ZOOM_MAX, +(currentZoom.value + ZOOM_STEP).toFixed(2));
  updateZoom();
}

function zoomOut() {
  currentZoom.value = Math.max(ZOOM_MIN, +(currentZoom.value - ZOOM_STEP).toFixed(2));
  updateZoom();
}

function resetZoom() {
  currentZoom.value = initialZoom.value;
  updateZoom();
}

function changeShape() {
  initBubbleChart();
}
</script>

<template>
  <div v-loading="loading" class="event-detail-container p-4">
    <!-- 面包屑与返回按钮 -->
    <div class="flex justify-between items-center mb-6">
      <div class="flex items-center gap-3">
        <el-button circle @click="router.back()">
          <IconifyIconOffline icon="ep:arrow-left" />
        </el-button>
        <div>
          <h2 class="text-xl font-bold text-gray-800 dark:text-white">
            {{ eventData?.title || "事件详情分析报告" }}
          </h2>
          <div class="flex gap-2 items-center mt-1">
            <el-tag size="small" type="warning">{{ eventData?.lifecycle_stage }}</el-tag>
            <span class="text-xs text-gray-400">事件ID: {{ route.params.id }}</span>
          </div>
        </div>
      </div>
      <el-button type="primary" plain @click="handleExport">
        <IconifyIconOffline icon="ep:download" class="mr-1" />
        导出报告
      </el-button>
    </div>

    <div v-if="eventData">
      <!-- 指标数据卡片组 -->
      <el-row :gutter="20" class="mb-6">
        <el-col :xs="24" :sm="12" :md="6" class="mb-4">
          <el-card shadow="never" class="!border-none">
            <div class="text-xs text-gray-400 mb-1">综合热度指数</div>
            <div class="text-2xl font-bold text-blue-500 mb-2">
              {{ Math.round(eventData.heat_index) }}
            </div>
            <el-progress
              :percentage="Math.min(100, Math.round(eventData.heat_index || 0))"
              :show-text="false"
              stroke-width="5"
              color="#3b82f6"
            />
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="12" :md="6" class="mb-4">
          <el-card shadow="never" class="!border-none">
            <div class="text-xs text-gray-400 mb-1">风险评估等级</div>
            <div
              :class="[
                'text-2xl font-bold mb-2',
                eventData.report?.risk_data?.level === '高风险'
                  ? 'text-red-500'
                  : eventData.report?.risk_data?.level === '中风险'
                    ? 'text-orange-500'
                    : 'text-green-500'
              ]"
            >
              {{ eventData.report?.risk_data?.level || "低风险" }}
            </div>
            <div class="text-xs text-gray-500 dark:text-gray-400">
              分值: {{ eventData.report?.risk_data?.score || 0 }} / 100
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="12" :md="6" class="mb-4">
          <el-card shadow="never" class="!border-none">
            <div class="text-xs text-gray-400 mb-1">核心情感倾向</div>
            <div class="text-2xl font-bold text-red-500 mb-2">
              负面率 {{ percent(eventData.sentiment_negative) }}
            </div>
            <div class="text-xs text-gray-500 dark:text-gray-400">
              正面占比 {{ percent(eventData.sentiment_positive) }}
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="12" :md="6" class="mb-4">
          <el-card shadow="never" class="!border-none">
            <div class="text-xs text-gray-400 mb-1">关联报道总数</div>
            <div class="text-2xl font-bold text-gray-700 dark:text-gray-300 mb-2">
              {{ eventData.articles?.total || 0 }} 篇
            </div>
            <div class="text-xs text-gray-500 dark:text-gray-400">
              涉及 {{ eventData.platform?.platforms?.length || 0 }} 个信源平台
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 中间内容区域：图表与事件报告 -->
      <el-row :gutter="20" class="mb-6">
        <!-- 统计图表区域 -->
        <el-col :xs="24" :lg="16" class="mb-6">
          <el-card shadow="never" class="!border-none mb-6">
            <template #header>
              <div class="font-bold">舆情传播趋势 (Daily Trend)</div>
            </template>
            <div ref="trendRef" class="w-full h-[280px]" />
          </el-card>

          <el-row :gutter="20">
            <el-col :xs="24" :sm="12">
              <el-card shadow="never" class="!border-none">
                <template #header>
                  <div class="font-bold">情感极性占比</div>
                </template>
                <div ref="sentimentRef" class="w-full h-[220px]" />
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-card shadow="never" class="!border-none">
                <template #header>
                  <div class="font-bold">传播平台分布</div>
                </template>
                <div ref="platformRef" class="w-full h-[220px]" />
              </el-card>
            </el-col>
          </el-row>
        </el-col>

        <!-- AI报告与词云区域 -->
        <el-col :xs="24" :lg="8" class="mb-6">
          <el-card shadow="never" class="!border-none mb-6 h-[590px] flex flex-col">
            <template #header>
              <div class="font-bold">AI 研判与核心摘要</div>
            </template>
            <!-- 核心摘要网格 -->
            <div class="grid grid-cols-2 gap-2 text-xs border-b border-gray-100 dark:border-gray-800 pb-3 mb-3 shrink-0">
              <div>
                <span class="text-gray-400">发生时间:</span>
                <span class="font-medium ml-1 text-gray-700 dark:text-gray-300">{{ eventData.time_code || '未录入' }}</span>
              </div>
              <div>
                <span class="text-gray-400">发生地点:</span>
                <span class="font-medium ml-1 text-gray-700 dark:text-gray-300">{{ eventData.location || '未录入' }}</span>
              </div>
              <div class="col-span-2">
                <span class="text-gray-400">涉事人物:</span>
                <span class="font-medium ml-1 text-gray-700 dark:text-gray-300">{{ eventData.key_figures || '未录入' }}</span>
              </div>
              <div class="col-span-2">
                <span class="text-gray-400">事件起因:</span>
                <span class="font-medium ml-1 text-gray-700 dark:text-gray-300 line-clamp-1" :title="eventData.cause">{{ eventData.cause || '未录入' }}</span>
              </div>
            </div>
            <el-scrollbar class="flex-1">
              <p class="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">
                {{ eventData.report?.overview_text }}
              </p>
            </el-scrollbar>
          </el-card>
        </el-col>
      </el-row>

      <!-- 底部：热点词云图 (满宽) -->
      <el-row class="mb-6">
        <el-col :span="24">
          <el-card shadow="never" class="!border-none">
            <template #header>
              <div class="flex justify-between items-center w-full">
                <div class="font-bold">热点关键词云 (Word Cloud)</div>
                <div class="flex items-center gap-2">
                  <el-select v-model="currentShape" size="small" class="!w-[90px]" @change="changeShape">
                    <el-option v-for="s in shapeOptions" :key="s.value" :label="s.label" :value="s.value" />
                  </el-select>
                  <span class="text-[11px] text-slate-400">{{ Math.round(currentZoom * 100) }}%</span>
                  <el-button-group size="small">
                    <el-button @click="zoomIn" title="放大">
                      <el-icon><PlusIcon /></el-icon>
                    </el-button>
                    <el-button @click="zoomOut" title="缩小">
                      <el-icon><MinusIcon /></el-icon>
                    </el-button>
                    <el-button @click="resetZoom" title="重置">
                      <el-icon><RefreshRightIcon /></el-icon>
                    </el-button>
                  </el-button-group>
                </div>
              </div>
            </template>
            <div class="w-full h-[440px] overflow-hidden flex items-center justify-center bg-slate-50/30 dark:bg-slate-950/30 rounded-lg">
              <div ref="bubbleRef" class="w-full h-full" />
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 底部列表：关联报道 -->
      <el-card shadow="never" class="!border-none">
        <template #header>
          <div class="flex justify-between items-center">
            <span class="font-bold">关联舆情报道列表</span>
            <el-button type="primary" link @click="router.push(`/opinion/qa?event_id=${route.params.id}`)">
              <IconifyIconOffline icon="ri:question-answer-line" class="mr-1" />
              就该事件进行智能提问
            </el-button>
          </div>
        </template>
        <el-table :data="eventData.articles?.articles" stripe style="width: 100%">
          <el-table-column type="index" label="序号" width="60" />
          <el-table-column prop="title" label="报道标题" min-width="250" show-overflow-tooltip />
          <el-table-column prop="platform" label="来源平台" width="120">
            <template #default="{ row }">
              <el-tag size="small">{{ row.platform }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="sentiment_label" label="情感倾向" width="120">
            <template #default="{ row }">
              <el-tag
                size="small"
                :type="
                  row.sentiment_label === '正面'
                    ? 'success'
                    : row.sentiment_label === '负面'
                      ? 'danger'
                      : 'info'
                "
              >
                {{ row.sentiment_label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="is_suspicious" label="真实性检测" width="130">
            <template #default="{ row }">
              <div class="flex items-center gap-1">
                <el-tag
                  size="small"
                  :type="row.is_suspicious ? 'danger' : 'success'"
                >
                  {{ row.is_suspicious ? '可疑谣言' : '真实信源' }}
                </el-tag>
                <span v-if="row.is_suspicious && row.suspicious_score" class="text-[11px] text-red-500 font-bold">
                  {{ Math.round(row.suspicious_score * 100) }}%
                </span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="clean_content" label="正文摘要" min-width="200" show-overflow-tooltip />
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.event-detail-container {
  :deep(.el-card__header) {
    padding: 14px 20px;
    border-bottom: 1px solid var(--el-border-color-extra-light);
  }
}
</style>
