<script setup lang="ts">
import { onMounted, ref, watch, nextTick, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import * as echarts from "echarts";
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

function initBubbleChart() {
  if (!eventData.value || !bubbleRef.value) return;

  const dark = isDark.value;
  const list = eventData.value.keywords?.keywords || [];
  if (list.length === 0) return;

  // 1. 动态归一化算法，自适应词数规模
  const weights = list.map((kw: any) => kw.weight || 0);
  const maxW = Math.max(...weights, 1);
  const minW = Math.min(...weights, 0);
  const range = maxW - minW || 1;

  // 词数较多时自动缩小，防止拥堵溢出
  const count = list.length;
  // 🌟 使用平滑缩放公式，自动根据关键词数量按比例推导最合宜的视口大小，杜绝大图溢出
  const initialZoomVal = Math.min(1.2, Math.max(0.55, 12 / count));
  initialZoom.value = initialZoomVal;
  currentZoom.value = initialZoomVal;
  const minSize = count > 15 ? 32 : 55;
  const maxSize = count > 15 ? 65 : 100;

  const bubbleData = list.map((kw: any, idx: number) => {
    // 线性归一化映射
    const t = ((kw.weight || 0) - minW) / range;
    const size = Math.round(minSize + t * (maxSize - minSize));

    // 🌟 根据归一化热度 t 动态分配色温梯度（大词靛蓝耀眼，中等科技蓝，小词灰蓝温和，完美契合冷调科技背景）
    let color;
    if (t >= 0.8) {
      color = { light: "rgba(79, 70, 229, 0.08)", main: "rgba(79, 70, 229, 0.65)", border: "rgba(79, 70, 229, 0.95)", shadow: "rgba(79, 70, 229, 0.2)" }; // 核心超高热度：深邃靛蓝
    } else if (t >= 0.55) {
      color = { light: "rgba(59, 130, 246, 0.08)", main: "rgba(59, 130, 246, 0.65)", border: "rgba(59, 130, 246, 0.95)", shadow: "rgba(59, 130, 246, 0.15)" }; // 中高热度：标准科技蓝
    } else if (t >= 0.3) {
      color = { light: "rgba(6, 182, 212, 0.08)", main: "rgba(6, 182, 212, 0.65)", border: "rgba(6, 182, 212, 0.95)", shadow: "rgba(6, 182, 212, 0.12)" };  // 中等热度：冰川青绿
    } else {
      color = { light: "rgba(148, 163, 184, 0.06)", main: "rgba(148, 163, 184, 0.55)", border: "rgba(148, 163, 184, 0.85)", shadow: "rgba(148, 163, 184, 0.1)" }; // 低热度：温和灰蓝色
    }

    // 3. 造型多样化设计 (100% 全云朵气泡图，交替使用三种不同轮廓的云朵造型)
    let symbol = "";
    const cloudStyles = [
      "path://M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96z", // 经典云
      "path://M12 6c-2.62 0-4.88 1.86-5.39 4.43C4.3 10.74 2.5 12.89 2.5 15.5c0 3.04 2.46 5.5 5.5 5.5h11c2.48 0 4.5-2.02 4.5-4.5 0-2.31-1.74-4.22-4.03-4.47C18.89 8.61 15.74 6 12 6z",  // 扁平宽云
      "path://M12 6c-3 0-5.5 2.24-5.92 5.15C4.28 11.53 2.5 13.56 2.5 16c0 2.76 2.24 5 5 5h12c2.21 0 4-1.79 4-4 0-2.05-1.54-3.74-3.53-3.97C19.46 8.91 16.08 6 12 6z"   // 紧凑圆云
    ];
    symbol = cloudStyles[idx % cloudStyles.length];
    const symbolSize: [number, number] = [size * 1.5, size * 1.05];

    // 4. 文字辨识度与描边优化 (浅色底用深色字，深色底用白字，描边厚度调为 1.0px 防发虚锯齿)
    const labelColor = dark ? "#ffffff" : "#1e293b";
    const labelBorder = dark ? color.border : "#ffffff";
    const labelBorderWidth = 1.0;

    return {
      name: kw.word,
      value: kw.weight,
      symbol: symbol,
      symbolSize: symbolSize,
      draggable: true,
      itemStyle: {
        color: new echarts.graphic.RadialGradient(0.4, 0.3, 0.9, [
          { offset: 0, color: color.light },
          { offset: 0.8, color: color.main },
          { offset: 1, color: color.border }
        ]),
        borderColor: color.border,
        borderWidth: 1.2,
        shadowBlur: dark ? 12 : 6,
        shadowColor: color.shadow
      },
      label: {
        show: true,
        formatter: kw.word,
        fontSize: Math.round(14 + t * 7), // 🌟 字号调大：范围扩大到 14px - 21px
        fontWeight: 600, // 🌟 中粗体呈现设计感
        fontFamily: '"Outfit", "Cabinet Grotesk", "Inter", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif', // 🌟 高质感科技感无衬线字体栈
        color: labelColor,
        textBorderColor: labelBorder,
        textBorderWidth: labelBorderWidth
      }
    };
  });

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
      backgroundColor: dark ? "rgba(17, 24, 39, 0.95)" : "rgba(255, 255, 255, 0.95)",
      borderColor: dark ? "#374151" : "#e5e7eb",
      borderWidth: 1
    },
    series: [
      {
        type: "graph",
        layout: "force",
        force: {
          repulsion: count > 15 ? 70 : 110, // 减弱排斥力，让节点能够更加亲密地发生碰撞贴合
          gravity: 0.11, // 增加向中心收拢的重力，形成紧凑的“云状星团”分布
          edgeLength: 10,
          friction: 0.45 // 增加运动阻尼（摩擦力），防止气泡无休止晃动
        },
        roam: "move", // 仅拖拽平移，关闭滚轮缩放，防止阻碍页面滚动
        zoom: currentZoom.value,
        draggable: true,
        data: bubbleData,
        links: [],
        lineStyle: {
          width: 0
        }
      }
    ]
  });
}

function updateZoom() {
  if (bubbleChart) {
    bubbleChart.setOption({
      series: [{ zoom: currentZoom.value }]
    });
  }
}

function zoomIn() {
  currentZoom.value = Math.min(3.0, currentZoom.value + 0.15);
  updateZoom();
}

function zoomOut() {
  currentZoom.value = Math.max(0.3, currentZoom.value - 0.15);
  updateZoom();
}

function resetZoom() {
  currentZoom.value = initialZoom.value;
  updateZoom();
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

      <!-- 中间内容区域：物理力导向气泡词云 (满宽) -->
      <el-row class="mb-6">
        <el-col :span="24">
          <el-card shadow="never" class="!border-none">
            <template #header>
              <div class="flex justify-between items-center w-full">
                <div class="font-bold">热点舆情气泡词云堆积图 (Force Bubble Cloud)</div>
                <!-- 放大缩小重置按钮组 (右上角，保证清晰显示) -->
                <el-button-group>
                  <el-button size="small" @click="zoomIn" title="放大">
                    <el-icon><PlusIcon /></el-icon>
                  </el-button>
                  <el-button size="small" @click="zoomOut" title="缩小">
                    <el-icon><MinusIcon /></el-icon>
                  </el-button>
                  <el-button size="small" @click="resetZoom" title="重置">
                    <el-icon><RefreshRightIcon /></el-icon>
                  </el-button>
                </el-button-group>
              </div>
            </template>
            <div ref="bubbleRef" class="w-full h-[360px]" />
          </el-card>
        </el-col>
      </el-row>

      <!-- 底部列表：关联报道 -->
      <el-card shadow="never" class="!border-none">
        <template #header>
          <div class="flex justify-between items-center">
            <span class="font-bold">关联舆情报道列表</span>
            <el-button type="primary" link @click="router.push(`/qa?event_id=${route.params.id}`)">
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
