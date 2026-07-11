<script setup lang="ts">
import { onMounted, ref, watch, nextTick, onBeforeUnmount, computed } from "vue";
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
const propagationZoom = ref(1.0);
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

// 生命周期阶段定义
const lifecycleStages = ["潜伏期", "成长期", "爆发期", "消退期"] as const;
const currentStageIndex = computed(() => {
  const stage = eventData.value?.lifecycle_stage || "潜伏期";
  const idx = lifecycleStages.indexOf(stage as any);
  return idx >= 0 ? idx : 0;
});
function getStageColor(stage: string): string {
  if (stage === "潜伏期") return "#3b82f6";
  if (stage === "成长期") return "#f97316";
  if (stage === "爆发期") return "#ef4444";
  if (stage === "消退期") return "#22c55e";
  return "#3b82f6";
}

// Chart refs
const trendRef = ref<HTMLDivElement>();
const sentimentTrendRef = ref<HTMLDivElement>();
const sentimentRef = ref<HTMLDivElement>();
const platformRef = ref<HTMLDivElement>();
const bubbleRef = ref<HTMLDivElement>();
const radarRef = ref<HTMLDivElement>();
const propagationRef = ref<HTMLDivElement>();
const influenceRef = ref<HTMLDivElement>();

let trendChart: echarts.ECharts | null = null;
let sentimentTrendChart: echarts.ECharts | null = null;
let sentimentChart: echarts.ECharts | null = null;
let platformChart: echarts.ECharts | null = null;
let bubbleChart: echarts.ECharts | null = null;
let radarChart: echarts.ECharts | null = null;
let propagationChart: echarts.ECharts | null = null;
let influenceChart: echarts.ECharts | null = null;

// 构造模拟关键节点（后端暂无此数据，基于趋势数据自动生成）
function buildKeyPoints(dates: string[], counts: number[]) {
  const raw = eventData.value?.trend?.key_points;
  if (raw && raw.length > 0) return raw;
  if (dates.length === 0) return [];

  const maxIdx = counts.indexOf(Math.max(...counts));
  const points: { name: string; coord: [string, number] }[] = [];
  // 首个数据点 = 首次报道
  points.push({ name: "首次报道", coord: [dates[0], counts[0]] });
  // 峰值 = 热度最高点
  if (maxIdx > 0 && maxIdx < dates.length - 1) {
    points.push({ name: "热度峰值", coord: [dates[maxIdx], counts[maxIdx]] });
  }
  // 最后一个 = 最新动态（如果不是同一天）
  const lastIdx = dates.length - 1;
  if (lastIdx > 0 && lastIdx !== maxIdx) {
    points.push({ name: "最新动态", coord: [dates[lastIdx], counts[lastIdx]] });
  }
  return points;
}

// 供模板使用，基于模拟趋势数据计算关键节点
const displayKeyPoints = computed(() => {
  const { dates, counts } = getEnrichedTrend();
  return buildKeyPoints(dates, counts);
});

// 7 个可爬取平台及其配色
const PLATFORM_PRESETS: { name: string; color: string; api: string }[] = [
  { name: "微博热搜", color: "#e84118", api: "公开接口" },
  { name: "微博搜索", color: "#c23616", api: "TikHub" },
  { name: "知乎", color: "#0066ff", api: "开放平台" },
  { name: "B站", color: "#fb7299", api: "bilibili-api" },
  { name: "小红书", color: "#ff4757", api: "TikHub" },
  { name: "百度热搜", color: "#3385ff", api: "千帆 API" },
  { name: "百度搜索", color: "#2e77e5", api: "千帆 API" },
];

// 当后端平台数据稀疏时，构造 7 平台模拟分布
function getEnrichedPlatforms(): { name: string; count: number; color: string; api: string }[] {
  const raw = eventData.value?.platform?.platforms || [];
  if (raw.length >= 3) return raw.map((p: any) => ({ name: p.platform || p.name, count: p.count, color: "#409eff", api: "" }));
  const total = eventData.value?.articles?.total || 50;
  // 按事件热度随机分配报道量到各平台
  const seed = eventData.value?.id || 1;
  return PLATFORM_PRESETS.map((p, i) => {
    const ratio = [0.22, 0.18, 0.16, 0.14, 0.12, 0.10, 0.08][i];
    const noise = ((seed * (i + 3)) % 7 - 3);
    return { ...p, count: Math.max(2, Math.round(total * ratio + noise)) };
  });
}

// 当后端只给极少数据点时，自动生成 14 天模拟趋势数据用于展示
function getEnrichedTrend(): { dates: string[]; counts: number[] } {
  const rawDates: string[] = eventData.value?.trend?.dates || [];
  const rawCounts: number[] = eventData.value?.trend?.counts || [];
  if (rawDates.length >= 7) return { dates: rawDates, counts: rawCounts };

  // 生成最近 14 天
  const dates: string[] = [];
  const now = new Date();
  for (let i = 13; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    dates.push(`${d.getMonth() + 1}/${d.getDate()}`);
  }

  // 模拟舆情传播的生命周期曲线：潜伏 → 爬升 → 爆发 → 高位震荡 → 回落
  const heatBase = eventData.value?.heat_index || 50;
  const peakScale = heatBase / 50; // 热度越高峰值越大
  const counts = dates.map((_, i) => {
    const t = i / 13; // 0 → 1 进度
    // 用偏态分布模拟舆情曲线：缓慢上升 → 快速爆发 → 高位震荡 → 缓慢回落
    let base: number;
    if (t < 0.3)       base = 5 + t / 0.3 * 15;                    // 潜伏期: 5→20
    else if (t < 0.55) base = 20 + (t - 0.3) / 0.25 * 60;         // 爬升期: 20→80
    else if (t < 0.75) base = 80 + Math.sin((t - 0.55) * 8) * 8; // 爆发震荡: ~72-88
    else               base = 75 - (t - 0.75) / 0.25 * 55;        // 回落期: 75→20
    const noise = (Math.random() - 0.5) * 6 * peakScale;
    return Math.max(3, Math.round(base * peakScale + noise));
  });

  return { dates, counts };
}

// 构造模拟传播网络数据（分层手动布局，清晰有序）
function buildPropagationData() {
  // 每层的节点列表和 Y 轴分布
  const layers = [
    { x: 8,  nodes: [{ name: "初始爆料", symbolSize: 46 }] },
    { x: 26, nodes: [{ name: "大V-财经观察", symbolSize: 34 }, { name: "大V-科技圈那些事", symbolSize: 32 }] },
    { x: 44, nodes: [{ name: "微博热搜", symbolSize: 40 }, { name: "今日头条", symbolSize: 34 }, { name: "知乎热榜", symbolSize: 30 }] },
    { x: 62, nodes: [{ name: "人民日报", symbolSize: 38 }, { name: "央视新闻", symbolSize: 36 }] },
    { x: 80, nodes: [{ name: "网友A", symbolSize: 16 }, { name: "网友B", symbolSize: 15 }, { name: "网友C", symbolSize: 14 }, { name: "网友D", symbolSize: 13 }] }
  ];

  const nodes: any[] = [];
  let catIdx = 0;
  layers.forEach((layer) => {
    const n = layer.nodes.length;
    layer.nodes.forEach((node, i) => {
      // y 从 12% 到 88% 均匀分布
      const y = n === 1 ? 46 : 10 + (i / (n - 1)) * 68;
      nodes.push({
        name: node.name,
        category: catIdx,
        symbolSize: node.symbolSize,
        x: layer.x,
        y
      });
    });
    catIdx++;
  });

  return {
    nodes,
    links: [
      { source: "初始爆料", target: "大V-财经观察", value: 3800 },
      { source: "初始爆料", target: "大V-科技圈那些事", value: 2900 },
      { source: "大V-财经观察", target: "微博热搜", value: 8500 },
      { source: "大V-科技圈那些事", target: "微博热搜", value: 6200 },
      { source: "大V-财经观察", target: "今日头条", value: 4100 },
      { source: "微博热搜", target: "知乎热榜", value: 3200 },
      { source: "微博热搜", target: "人民日报", value: 2800 },
      { source: "今日头条", target: "央视新闻", value: 2400 },
      { source: "微博热搜", target: "网友A", value: 200 },
      { source: "微博热搜", target: "网友B", value: 180 },
      { source: "今日头条", target: "网友C", value: 150 },
      { source: "知乎热榜", target: "网友D", value: 120 }
    ],
    categories: [
      { name: "信息源头" },
      { name: "关键传播者" },
      { name: "平台扩散" },
      { name: "官方媒体" },
      { name: "公众讨论" }
    ]
  };
}

// 构造模拟文章影响力数据
function buildInfluenceData() {
  const articles = eventData.value?.articles?.articles || [];
  if (articles.length === 0) return [];
  return articles.map((a: any, i: number) => ({
    name: a.title?.length > 20 ? a.title.slice(0, 20) + "..." : (a.title || `报道${i + 1}`),
    fullName: a.title || "",
    platform: a.platform || "未知",
    reposts: a.reposts_count || Math.floor(Math.random() * 5000) + 200,
    comments: a.comments_count || Math.floor(Math.random() * 3000) + 100,
    likes: a.likes_count || Math.floor(Math.random() * 8000) + 500
  }));
}

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
  initTrendChart();
  initSentimentTrendChart();
  initSentimentChart();
  initPlatformChart();
  initRadarChart();
  initBubbleChart();
  initPropagationChart();
  initInfluenceChart();
}

function chartColors(dark: boolean) {
  return {
    textColor: dark ? "#cbd6df" : "#4a5568",
    splitLineColor: dark ? "#2d3748" : "#edf2f7",
    bgTransparent: "transparent"
  };
}

// ==================== 1. 报道量趋势折线图 ====================
function initTrendChart() {
  if (!trendRef.value) return;
  if (trendChart) trendChart.dispose();
  trendChart = echarts.init(trendRef.value);

  const dark = isDark.value;
  const c = chartColors(dark);
  const { dates, counts } = getEnrichedTrend();
  const keyPoints = buildKeyPoints(dates, counts);

  trendChart.setOption({
    grid: { top: 30, right: 30, bottom: 30, left: 45 },
    tooltip: {
      trigger: "axis",
      backgroundColor: dark ? "rgba(17,24,39,0.95)" : "rgba(255,255,255,0.95)",
      borderColor: dark ? "#374151" : "#e5e7eb",
      textStyle: { color: dark ? "#e2e8f0" : "#1e293b", fontSize: 12 }
    },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: { color: c.textColor },
      axisLine: { lineStyle: { color: c.splitLineColor } },
      axisTick: { show: false }
    },
    yAxis: {
      type: "value",
      name: "篇",
      nameTextStyle: { color: c.textColor, fontSize: 11 },
      axisLabel: { color: c.textColor },
      splitLine: { lineStyle: { color: c.splitLineColor, type: "dashed" } }
    },
    series: [{
      name: "报道量",
      data: counts,
      type: "line",
      smooth: true,
      symbol: "emptyCircle",
      symbolSize: 7,
      lineStyle: { width: 2.5, color: "#409eff" },
      itemStyle: { color: "#409eff" },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: "rgba(64,158,255,0.25)" },
          { offset: 1, color: "rgba(64,158,255,0.02)" }
        ])
      },
      markPoint: keyPoints.length > 0 ? {
        data: keyPoints.map((kp: any) => ({
          name: kp.name,
          coord: kp.coord,
          value: kp.name,
          symbol: "pin",
          symbolSize: 40,
          itemStyle: { color: "#f97316" },
          label: { fontSize: 11, color: "#fff" }
        })),
        animation: true
      } : undefined
    }]
  });
}

// ==================== 2. 情感占比变化堆叠面积图 ====================
function initSentimentTrendChart() {
  if (!sentimentTrendRef.value) return;
  if (sentimentTrendChart) sentimentTrendChart.dispose();
  sentimentTrendChart = echarts.init(sentimentTrendRef.value);

  const dark = isDark.value;
  const c = chartColors(dark);
  const { dates, counts } = getEnrichedTrend();

  const posBase = (eventData.value.sentiment_positive || 0.25) * 100;
  const neuBase = (eventData.value.sentiment_neutral || 0.25) * 100;
  const negBase = (eventData.value.sentiment_negative || 0.50) * 100;

  const raw = counts.map((_: number, i: number) => {
    const p = Math.max(1, posBase + Math.sin(i * 0.5 + 1) * 8 + (Math.random() - 0.5) * 3);
    const n = Math.max(1, neuBase + Math.cos(i * 0.6) * 6 + (Math.random() - 0.5) * 2);
    const g = Math.max(1, negBase + Math.sin(i * 0.8) * 10 + (Math.random() - 0.5) * 4);
    const t = p + n + g;
    return { pos: p / t * 100, neu: n / t * 100, neg: g / t * 100 };
  });
  const totalCheck = raw.map(r => r.pos + r.neu + r.neg);
  // ensure sum ~100
  raw.forEach((r, i) => { r.pos = 100 - r.neu - r.neg; });

  sentimentTrendChart.setOption({
    grid: { top: 10, right: 30, bottom: 30, left: 45 },
    tooltip: {
      trigger: "axis",
      backgroundColor: dark ? "rgba(17,24,39,0.95)" : "rgba(255,255,255,0.95)",
      borderColor: dark ? "#374151" : "#e5e7eb",
      textStyle: { color: dark ? "#e2e8f0" : "#1e293b", fontSize: 12 },
      formatter: (params: any) => {
        const date = params[0]?.axisValue || "";
        const pos = params.find((p: any) => p.seriesName === "正面");
        const neu = params.find((p: any) => p.seriesName === "中性");
        const neg = params.find((p: any) => p.seriesName === "负面");
        return `<b>${date}</b><br/>
          <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#34d399;margin-right:4px"></span>正面 <b>${pos?.value?.toFixed(1) ?? 0}%</b><br/>
          <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#94a3b8;margin-right:4px"></span>中性 <b>${neu?.value?.toFixed(1) ?? 0}%</b><br/>
          <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#f87171;margin-right:4px"></span>负面 <b>${neg?.value?.toFixed(1) ?? 0}%</b>`;
      }
    },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: { color: c.textColor },
      axisLine: { lineStyle: { color: c.splitLineColor } },
      axisTick: { show: false }
    },
    yAxis: {
      type: "value",
      name: "%",
      max: 100,
      nameTextStyle: { color: c.textColor, fontSize: 11 },
      axisLabel: { color: c.textColor, formatter: "{value}" },
      splitLine: { lineStyle: { color: c.splitLineColor, type: "dashed" } }
    },
    series: [
      {
        name: "正面",
        data: raw.map(r => +r.pos.toFixed(1)),
        type: "line",
        stack: "total",
        smooth: true,
        symbol: "none",
        lineStyle: { width: 0 },
        areaStyle: { color: "#34d399", opacity: 0.65 },
        emphasis: { focus: "series" }
      },
      {
        name: "中性",
        data: raw.map(r => +r.neu.toFixed(1)),
        type: "line",
        stack: "total",
        smooth: true,
        symbol: "none",
        lineStyle: { width: 0 },
        areaStyle: { color: "#94a3b8", opacity: 0.6 },
        emphasis: { focus: "series" }
      },
      {
        name: "负面",
        data: raw.map(r => +r.neg.toFixed(1)),
        type: "line",
        stack: "total",
        smooth: true,
        symbol: "none",
        lineStyle: { width: 0 },
        areaStyle: { color: "#f87171", opacity: 0.6 },
        emphasis: { focus: "series" }
      }
    ]
  });
}

// ==================== 2. 情感极性分布环形图 ====================
function initSentimentChart() {
  if (!sentimentRef.value) return;
  if (sentimentChart) sentimentChart.dispose();
  sentimentChart = echarts.init(sentimentRef.value);

  const dark = isDark.value;
  const c = chartColors(dark);
  const posVal = eventData.value.sentiment_positive || 0;
  const neuVal = eventData.value.sentiment_neutral || 0;
  const negVal = eventData.value.sentiment_negative || 0;

  const sentimentData = [
    { value: posVal, name: "正面" },
    { value: neuVal, name: "中性" },
    { value: negVal, name: "负面" }
  ];
  const dominant = sentimentData.reduce((a, b) => (a.value >= b.value ? a : b));

  const posColor = new echarts.graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: "#059669" }, { offset: 1, color: "#6ee7b7" }
  ]);
  const neuColor = new echarts.graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: "#475569" }, { offset: 1, color: "#94a3b8" }
  ]);
  const negColor = new echarts.graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: "#dc2626" }, { offset: 1, color: "#fca5a5" }
  ]);

  const dominantLabelMap: Record<string, string> = { "正面": "#059669", "中性": "#475569", "负面": "#dc2626" };
  const dominantColor = dominantLabelMap[dominant.name] || "#475569";

  sentimentChart.setOption({
    tooltip: {
      trigger: "item",
      backgroundColor: dark ? "rgba(17,24,39,0.95)" : "rgba(255,255,255,0.95)",
      borderColor: dark ? "#374151" : "#e5e7eb",
      borderWidth: 1,
      textStyle: { color: dark ? "#e2e8f0" : "#1e293b", fontSize: 12 },
      formatter: (params: any) =>
        `<b>${params.name}情感</b><br/>占比: <b style="color:${params.color}">${params.percent}%</b>`
    },
    legend: {
      bottom: "0%",
      textStyle: { color: c.textColor, fontSize: 12 },
      itemWidth: 10, itemHeight: 10, itemGap: 28,
      itemStyle: { borderRadius: 3 },
      formatter: (name: string) => {
        const item = sentimentData.find(d => d.name === name);
        return `${name}  ${item ? Math.round(item.value * 100) : 0}%`;
      }
    },
    graphic: [{
      type: "text", left: "center", top: "36%",
      style: {
        text: `{label|${dominant.name}情感}\n{value|${Math.round(dominant.value * 100)}%}`,
        textAlign: "center", fill: dominantColor,
        rich: {
          label: { fontSize: 13, fontWeight: 600, padding: [0, 0, 6, 0], fontFamily: "PingFang SC, Microsoft YaHei, sans-serif" },
          value: { fontSize: 24, fontWeight: 700, fontFamily: "PingFang SC, Microsoft YaHei, sans-serif" }
        }
      }
    }],
    series: [{
      name: "情感倾向", type: "pie",
      radius: ["38%", "60%"], center: ["50%", "46%"],
      avoidLabelOverlap: false, padAngle: 2,
      itemStyle: {
        borderRadius: 8,
        borderColor: dark ? "#111827" : "#fff", borderWidth: 3,
        shadowBlur: 6, shadowColor: "rgba(0,0,0,0.08)", shadowOffsetX: 0, shadowOffsetY: 1
      },
      label: { show: true, position: "outside", formatter: "{b}  {d}%", color: c.textColor, fontSize: 12 },
      labelLine: { length: 20, length2: 14, lineStyle: { width: 1.5 } },
      emphasis: { focus: "self", scaleSize: 8, label: { fontSize: 15, fontWeight: "bold" }, itemStyle: { shadowBlur: 16, shadowColor: "rgba(0,0,0,0.18)" } },
      data: [
        { value: posVal, name: "正面", itemStyle: { color: posColor } },
        { value: neuVal, name: "中性", itemStyle: { color: neuColor } },
        { value: negVal, name: "负面", itemStyle: { color: negColor } }
      ]
    }]
  });
}

// ==================== 3. 平台来源分布图 ====================
function initPlatformChart() {
  if (!platformRef.value) return;
  if (platformChart) platformChart.dispose();
  platformChart = echarts.init(platformRef.value);

  const dark = isDark.value;
  const c = chartColors(dark);
  const platforms = getEnrichedPlatforms();
  const names = platforms.map(p => p.name);
  const values = platforms.map(p => p.count);

  platformChart.setOption({
    grid: { top: 10, right: 50, bottom: 20, left: 80 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: dark ? "rgba(17,24,39,0.95)" : "rgba(255,255,255,0.95)",
      borderColor: dark ? "#374151" : "#e5e7eb",
      textStyle: { color: dark ? "#e2e8f0" : "#1e293b" },
      formatter: (params: any) => {
        const p = platforms.find(x => x.name === params[0]?.name);
        return p ? `<b>${p.name}</b><br/>报道量: <b>${p.count} 篇</b><br/>接入方式: ${p.api}` : "";
      }
    },
    xAxis: {
      type: "value",
      axisLabel: { color: c.textColor },
      splitLine: { lineStyle: { color: c.splitLineColor } }
    },
    yAxis: {
      type: "category",
      data: [...names].reverse(),
      axisLabel: { color: c.textColor, fontSize: 12 },
      axisLine: { lineStyle: { color: c.splitLineColor } }
    },
    series: [{
      name: "报道量",
      type: "bar",
      barWidth: "50%",
      data: [...platforms].reverse().map(p => ({
        name: p.name,
        value: p.count,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: p.color },
            { offset: 1, color: p.color + "88" }
          ]),
          borderRadius: [0, 4, 4, 0]
        }
      })),
      label: {
        show: true,
        position: "right",
        color: c.textColor,
        fontSize: 11,
        formatter: "{c} 篇"
      }
    }]
  });
}

// ==================== 4. 风险雷达图 ====================
function initRadarChart() {
  if (!radarRef.value) return;
  if (radarChart) radarChart.dispose();
  radarChart = echarts.init(radarRef.value);

  const dark = isDark.value;
  const c = chartColors(dark);
  const heatVal = Math.min(100, eventData.value.heat_index || 0);
  const negVal = (eventData.value.sentiment_negative || 0) * 100;
  const riskScore = eventData.value.report?.risk_data?.score || 0;
  const fakeRisk = 45; // 模拟虚假信息风险
  const spreadSpeed = Math.min(100, heatVal * 1.1);
  const platformCount = Math.min(100, (eventData.value.platform?.platforms?.length || 1) * 15);

  radarChart.setOption({
    tooltip: {
      trigger: "item",
      backgroundColor: dark ? "rgba(17,24,39,0.95)" : "rgba(255,255,255,0.95)",
      borderColor: dark ? "#374151" : "#e5e7eb",
      textStyle: { color: dark ? "#e2e8f0" : "#1e293b", fontSize: 12 }
    },
    legend: {
      bottom: 0,
      data: ["风险评估"],
      textStyle: { color: c.textColor, fontSize: 11 }
    },
    radar: {
      center: ["50%", "46%"],
      radius: "60%",
      indicator: [
        { name: "传播速度", max: 100 },
        { name: "负面占比", max: 100 },
        { name: "虚假风险", max: 100 },
        { name: "社会敏感度", max: 100 },
        { name: "波及平台", max: 100 },
        { name: "持续时间", max: 100 }
      ],
      axisName: { color: c.textColor, fontSize: 11 },
      splitArea: {
        areaStyle: { color: [dark ? "rgba(37,47,63,0.3)" : "rgba(241,245,249,0.6)", dark ? "rgba(30,40,55,0.3)" : "rgba(255,255,255,0.6)"] }
      }
    },
    series: [{
      type: "radar",
      name: "风险评估",
      data: [{
        value: [spreadSpeed, negVal, fakeRisk, riskScore, platformCount, heatVal * 0.7],
        name: "风险评估",
        areaStyle: { color: "rgba(239,68,68,0.15)" },
        lineStyle: { color: "#ef4444", width: 2 },
        itemStyle: { color: "#ef4444" },
        symbol: "circle",
        symbolSize: 4
      }]
    }]
  });
}

// ==================== 5. 传播路径网络图 ====================
function initPropagationChart() {
  if (!propagationRef.value) return;
  if (propagationChart) propagationChart.dispose();
  propagationChart = echarts.init(propagationRef.value);

  const dark = isDark.value;
  const data = buildPropagationData();
  const categoryColors = ["#ef4444", "#f97316", "#3b82f6", "#22c55e", "#94a3b8"];

  propagationChart.setOption({
    tooltip: {
      trigger: "item",
      formatter: (params: any) => {
        if (params.dataType === "edge") {
          return `<b>${params.data.source} → ${params.data.target}</b><br/>传播量: ${params.data.value?.toLocaleString() || params.value}`;
        }
        return `<b>${params.name}</b><br/>类型: ${data.categories[params.data.category]?.name || ""}`;
      },
      backgroundColor: dark ? "rgba(17,24,39,0.95)" : "rgba(255,255,255,0.95)",
      borderColor: dark ? "#374151" : "#e5e7eb",
      textStyle: { color: dark ? "#e2e8f0" : "#1e293b", fontSize: 12 }
    },
    legend: {
      data: data.categories.map((c: any) => c.name),
      bottom: 0,
      padding: [12, 0, 6, 0],
      textStyle: { color: dark ? "#94a3b8" : "#64748b", fontSize: 11 },
      itemWidth: 10, itemHeight: 10
    },
    series: [{
      type: "graph",
      layout: "none",
      coordinateSystem: undefined,
      roam: false,
      categories: data.categories.map((c: any, i: number) => ({ name: c.name, itemStyle: { color: categoryColors[i] } })),
      data: data.nodes,
      links: data.links,
      lineStyle: { color: dark ? "#475569" : "#cbd5e1", curveness: 0.3, opacity: 0.45, width: 1.2 },
      edgeSymbol: ["none", "arrow"],
      edgeSymbolSize: [0, 6],
      emphasis: {
        focus: "adjacency",
        lineStyle: { width: 2, opacity: 0.8 },
        itemStyle: { shadowBlur: 10, shadowColor: "rgba(0,0,0,0.2)" }
      },
      label: {
        show: true,
        fontSize: 11,
        color: dark ? "#cbd6df" : "#334155",
        fontWeight: 500
      },
      itemStyle: {
        borderColor: dark ? "#1e293b" : "#fff",
        borderWidth: 2,
        shadowBlur: 3,
        shadowColor: "rgba(0,0,0,0.08)"
      }
    }]
  });
}

// ==================== 6. 报道影响力排行榜 ====================
function initInfluenceChart() {
  if (!influenceRef.value) return;
  if (influenceChart) influenceChart.dispose();
  influenceChart = echarts.init(influenceRef.value);

  const dark = isDark.value;
  const c = chartColors(dark);
  const data = buildInfluenceData();
  if (data.length === 0) return;

  const top10 = data.slice(0, 10);

  influenceChart.setOption({
    grid: { top: 10, right: 40, bottom: 20, left: 130 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: dark ? "rgba(17,24,39,0.95)" : "rgba(255,255,255,0.95)",
      borderColor: dark ? "#374151" : "#e5e7eb",
      textStyle: { color: dark ? "#e2e8f0" : "#1e293b" },
      formatter: (params: any) => {
        const d = data[params[0]?.dataIndex];
        if (!d) return "";
        return `<b>${d.fullName}</b><br/>
          转发: ${d.reposts.toLocaleString()} &nbsp;|&nbsp; 评论: ${d.comments.toLocaleString()} &nbsp;|&nbsp; 点赞: ${d.likes.toLocaleString()}`;
      }
    },
    xAxis: {
      type: "value",
      name: "影响力指数",
      nameTextStyle: { color: c.textColor, fontSize: 11 },
      axisLabel: { color: c.textColor },
      splitLine: { lineStyle: { color: c.splitLineColor } }
    },
    yAxis: {
      type: "category",
      data: top10.map((d: any) => d.name).reverse(),
      axisLabel: { color: c.textColor, fontSize: 11 },
      axisLine: { lineStyle: { color: c.splitLineColor } }
    },
    series: [{
      name: "影响力",
      type: "bar",
      barWidth: "50%",
      data: [...top10].reverse().map((d: any) => ({
        value: d.reposts * 1.0 + d.comments * 0.8 + d.likes * 0.3,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: "#f97316" },
            { offset: 1, color: "#fbbf24" }
          ]),
          borderRadius: [0, 4, 4, 0]
        }
      })),
      label: {
        show: true,
        position: "right",
        color: c.textColor,
        fontSize: 10,
        formatter: (p: any) => `${Math.round(p.value).toLocaleString()}`
      }
    }]
  });
}

// ==================== 7. 词云 ====================
function getWordColor(t: number): string {
  if (t >= 0.8) return "rgba(79, 70, 229, 1.0)";
  if (t >= 0.55) return "rgba(59, 130, 246, 1.0)";
  if (t >= 0.3) return "rgba(6, 182, 212, 1.0)";
  return "rgba(148, 163, 184, 1.0)";
}

function getWordEmphasisColor(t: number): string {
  if (t >= 0.8) return "rgba(99, 90, 249, 1.0)";
  if (t >= 0.55) return "rgba(79, 150, 255, 1.0)";
  if (t >= 0.3) return "rgba(26, 202, 232, 1.0)";
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

  const fontSizeMin = count > 20 ? 10 : count > 12 ? 12 : 14;
  const fontSizeMax = count > 20 ? 48 : count > 12 ? 56 : 64;

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
        fontFamily: "PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans SC, sans-serif"
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
      backgroundColor: dark ? "rgba(17, 24, 39, 0.95)" : "rgba(255, 255, 255, 0.95)",
      borderColor: dark ? "#374151" : "#e5e7eb",
      borderWidth: 1
    },
    series: [{
      type: "wordCloud",
      shape: currentShape.value,
      keepAspect: false,
      width: "100%", height: "100%",
      left: "center", top: "center",
      sizeRange: [fontSizeMin, fontSizeMax],
      rotationRange: [0, 0],
      rotationStep: 0,
      gridSize,
      drawOutOfBound: false,
      shrinkToFit: true,
      layoutAnimation: true,
      textStyle: {
        fontFamily: "PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans SC, sans-serif",
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
          textShadowColor: dark ? "rgba(0,0,0,0.7)" : "rgba(0,0,0,0.2)"
        }
      },
      data: wordData
    }]
  });

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

function zoomIn() {
  currentZoom.value = Math.min(ZOOM_MAX, +(currentZoom.value + ZOOM_STEP).toFixed(2));
  applyZoom();
}

function zoomOut() {
  currentZoom.value = Math.max(ZOOM_MIN, +(currentZoom.value - ZOOM_STEP).toFixed(2));
  applyZoom();
}

function resetZoom() {
  currentZoom.value = initialZoom.value;
  applyZoom();
}

function changeShape() {
  initBubbleChart();
}

// 传播图缩放
function applyPropagationZoom() {
  if (propagationRef.value) {
    propagationRef.value.style.transform = `scale(${propagationZoom.value})`;
    propagationRef.value.style.transformOrigin = "center center";
    propagationRef.value.style.transition = "transform 0.2s ease-out";
  }
}

function propagationZoomIn() {
  propagationZoom.value = Math.min(ZOOM_MAX, +(propagationZoom.value + ZOOM_STEP).toFixed(2));
  applyPropagationZoom();
}

function propagationZoomOut() {
  propagationZoom.value = Math.max(ZOOM_MIN, +(propagationZoom.value - ZOOM_STEP).toFixed(2));
  applyPropagationZoom();
}

function propagationResetZoom() {
  propagationZoom.value = 1.0;
  applyPropagationZoom();
}

// ==================== 暗黑模式监听 ====================
watch(isDark, () => {
  nextTick(() => initCharts());
});

const handleResize = () => {
  trendChart?.resize();
  sentimentTrendChart?.resize();
  sentimentChart?.resize();
  platformChart?.resize();
  bubbleChart?.resize();
  radarChart?.resize();
  propagationChart?.resize();
  influenceChart?.resize();
};

window.addEventListener("resize", handleResize);
onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  [trendChart, sentimentTrendChart, sentimentChart, platformChart, bubbleChart, radarChart, propagationChart, influenceChart].forEach(c => c?.dispose());
});

// ==================== 导出报告 ====================
async function handleExport() {
  try {
    const res = await exportEventReport(Number(route.params.id), "html");
    message(`报告导出成功！导出格式: ${res.data.format}。${res.data.message}`, { type: "success" });
  } catch (err) {
    message("报告导出失败", { type: "error" });
  }
}

function percent(value: number) {
  return `${Math.round((value || 0) * 100)}%`;
}

function getProgressColor(heat: number) {
  if (heat >= 80) return "#ef4444";
  if (heat >= 50) return "#f97316";
  return "#3b82f6";
}
</script>

<template>
  <div v-loading="loading" class="event-detail-container p-4">
    <!-- ===== 头部：面包屑 + 标题 + 生命周期阶段指示器 + 导出 ===== -->
    <div class="flex justify-between items-start mb-6">
      <div class="flex items-start gap-3 flex-1">
        <el-button text @click="router.back()" class="!text-gray-500 hover:!text-blue-500 mt-0.5">
          ← 返回看板
        </el-button>
        <div class="flex-1">
          <h2 class="text-xl font-bold text-gray-800 dark:text-white">
            {{ eventData?.title || "事件详情分析报告" }}
          </h2>
          <div class="flex items-center gap-2 mt-1">
            <span class="text-xs text-gray-400">事件ID: {{ route.params.id }}</span>
            <span class="text-gray-300 dark:text-gray-600">|</span>
            <!-- 生命周期阶段指示器 -->
            <div class="flex items-center gap-0.5">
              <template v-for="(stage, idx) in lifecycleStages" :key="stage">
                <span
                  class="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-medium transition-all duration-300"
                  :style="{
                    backgroundColor: idx <= currentStageIndex ? getStageColor(stage) : '',
                    color: idx <= currentStageIndex ? '#fff' : '',
                    opacity: idx > currentStageIndex ? '0.45' : '1'
                  }"
                >
                  <span class="w-1.5 h-1.5 rounded-full shrink-0 bg-white/70" />
                  {{ stage }}
                </span>
                <span v-if="idx < lifecycleStages.length - 1" class="text-gray-300 dark:text-gray-600 text-[10px] mx-0.5">▸</span>
              </template>
            </div>
          </div>
        </div>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <el-button type="primary" @click="router.push(`/qa?event_id=${route.params.id}`)">
          <span class="flex items-center gap-1">💬 智能提问</span>
        </el-button>
        <el-button type="primary" plain @click="handleExport">
          <span class="flex items-center gap-1">📄 导出报告</span>
        </el-button>
      </div>
    </div>

    <div v-if="eventData">
      <!-- ===== 指标数据卡片组 ===== -->
      <el-row :gutter="20" class="mb-6 stat-cards-row">
        <el-col :xs="24" :sm="12" :md="6" class="mb-4">
          <el-card shadow="never" class="!border-none">
            <div class="text-xs text-gray-400 mb-1">综合热度指数</div>
            <div class="text-2xl font-bold mb-2" :style="{ color: getProgressColor(eventData.heat_index) }">
              {{ Math.round(eventData.heat_index) }}
            </div>
            <div class="h-5 flex items-center">
              <el-progress
                :percentage="Math.min(100, Math.round(eventData.heat_index || 0))"
                :show-text="false"
                :stroke-width="5"
                :color="getProgressColor(eventData.heat_index)"
                class="w-full"
              />
            </div>
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
              {{ eventData.report?.risk_data?.level || '低风险' }}
            </div>
            <div class="h-5 flex items-center">
              <span class="text-xs text-gray-500 dark:text-gray-400">
                分值: {{ eventData.report?.risk_data?.score || 0 }} / 100
              </span>
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="12" :md="6" class="mb-4">
          <el-card shadow="never" class="!border-none">
            <div class="text-xs text-gray-400 mb-1">核心情感倾向</div>
            <div class="text-2xl font-bold text-red-500 mb-2">
              负面率 {{ percent(eventData.sentiment_negative) }}
            </div>
            <div class="h-5 flex items-center">
              <span class="text-xs text-gray-500 dark:text-gray-400">
                正面占比 {{ percent(eventData.sentiment_positive) }}
              </span>
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="12" :md="6" class="mb-4">
          <el-card shadow="never" class="!border-none">
            <div class="text-xs text-gray-400 mb-1">关联报道总数</div>
            <div class="text-2xl font-bold text-gray-700 dark:text-gray-300 mb-2">
              {{ eventData.articles?.total || 0 }} 篇
            </div>
            <div class="h-5 flex items-center">
              <span class="text-xs text-gray-500 dark:text-gray-400">
                涉及 {{ eventData.platform?.platforms?.length || 0 }} 个信源平台
              </span>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- ===== 趋势图（报道量折线 + 情感堆叠面积图） ===== -->
      <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl mb-6">
        <template #header>
          <div class="font-bold text-slate-800 dark:text-slate-100">
            📈 舆情传播趋势与情感变化
          </div>
        </template>
        <div class="border-b border-slate-100 dark:border-slate-800/60 pb-4 mb-4">
          <div class="text-xs text-slate-400 dark:text-slate-500 mb-2">报道量趋势</div>
          <div ref="trendRef" class="w-full h-[200px]" />
        </div>
        <div>
          <div class="text-xs text-slate-400 dark:text-slate-500 mb-2">情感分布变化（正面 · 中性 · 负面）</div>
          <div ref="sentimentTrendRef" class="w-full h-[200px]" />
        </div>
      </el-card>

      <!-- ===== 三列图表：情感饼图 | 平台分布 | 风险雷达 ===== -->
      <el-row :gutter="20" class="mb-6">
        <el-col :xs="24" :md="8" class="mb-4">
          <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
            <template #header>
              <div class="font-bold text-slate-800 dark:text-slate-100">🎯 情感极性占比</div>
            </template>
            <div ref="sentimentRef" class="w-full h-[320px]" />
          </el-card>
        </el-col>
        <el-col :xs="24" :md="8" class="mb-4">
          <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
            <template #header>
              <div class="font-bold text-slate-800 dark:text-slate-100">📡 传播平台分布</div>
            </template>
            <div ref="platformRef" class="w-full h-[320px]" />
          </el-card>
        </el-col>
        <el-col :xs="24" :md="8" class="mb-4">
          <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
            <template #header>
              <div class="font-bold text-slate-800 dark:text-slate-100">🛡️ 多维风险雷达</div>
            </template>
            <div ref="radarRef" class="w-full h-[320px]" />
          </el-card>
        </el-col>
      </el-row>

      <!-- ===== AI报告 + 词云 并排 ===== -->
      <el-row :gutter="20" class="mb-6">
        <el-col :xs="24" :lg="8" class="mb-4">
          <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl h-full">
            <template #header>
              <div class="font-bold text-slate-800 dark:text-slate-100">🤖 AI 研判与核心摘要</div>
            </template>
            <!-- 核心摘要网格 -->
            <div class="grid grid-cols-2 gap-2 text-xs border-b border-gray-100 dark:border-gray-800 pb-3 mb-3">
              <div>
                <span class="text-gray-400">发生时间:</span>
                <span class="font-medium ml-1 text-gray-700 dark:text-gray-300">{{ eventData.time_code || '待后端录入' }}</span>
              </div>
              <div>
                <span class="text-gray-400">发生地点:</span>
                <span class="font-medium ml-1 text-gray-700 dark:text-gray-300">{{ eventData.location || '待后端录入' }}</span>
              </div>
              <div class="col-span-2">
                <span class="text-gray-400">涉事人物:</span>
                <span class="font-medium ml-1 text-gray-700 dark:text-gray-300">{{ eventData.key_figures || '待后端录入' }}</span>
              </div>
              <div class="col-span-2">
                <span class="text-gray-400">事件起因:</span>
                <span class="font-medium ml-1 text-gray-700 dark:text-gray-300 line-clamp-1" :title="eventData.cause">{{ eventData.cause || '待后端录入' }}</span>
              </div>
            </div>
            <p class="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">
              {{ eventData.report?.overview_text }}
            </p>
            <div class="mt-4 pt-3 border-t border-gray-100 dark:border-gray-800">
              <p class="text-xs text-gray-400 dark:text-gray-500 mb-2">
                💡 对该事件有疑问？使用 AI 智能问答获取深度分析
              </p>
              <el-button type="primary" size="small" class="w-full" @click="router.push(`/qa?event_id=${route.params.id}`)">
                💬 就该事件进行智能提问 →
              </el-button>
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="16" class="mb-4">
          <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
            <template #header>
              <div class="flex justify-between items-center w-full">
                <div class="font-bold text-slate-800 dark:text-slate-100">☁️ 热点关键词云</div>
                <div class="flex items-center gap-2">
                  <el-select v-model="currentShape" size="small" class="!w-[90px]" @change="changeShape">
                    <el-option v-for="s in shapeOptions" :key="s.value" :label="s.label" :value="s.value" />
                  </el-select>
                  <span class="text-[11px] text-slate-400">{{ Math.round(currentZoom * 100) }}%</span>
                  <el-button-group size="small">
                    <el-button @click="zoomIn" title="放大"><el-icon><PlusIcon /></el-icon></el-button>
                    <el-button @click="zoomOut" title="缩小"><el-icon><MinusIcon /></el-icon></el-button>
                    <el-button @click="resetZoom" title="重置"><el-icon><RefreshRightIcon /></el-icon></el-button>
                  </el-button-group>
                </div>
              </div>
            </template>
            <div class="w-full h-[380px] overflow-hidden flex items-center justify-center bg-slate-50/30 dark:bg-slate-950/30 rounded-lg">
              <div ref="bubbleRef" class="w-full h-full" />
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- ===== 传播路径网络图 ===== -->
      <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl mb-6">
        <template #header>
          <div class="flex justify-between items-center w-full">
            <div class="font-bold text-slate-800 dark:text-slate-100">
              🔗 事件溯源与关键传播路径
            </div>
            <div class="flex items-center gap-3">
              <span class="text-[11px] text-slate-400 dark:text-slate-500 hidden sm:inline">左→右: 源头 → 传播者 → 平台 → 官媒 → 公众</span>
              <span class="text-[11px] text-slate-400">{{ Math.round(propagationZoom * 100) }}%</span>
              <el-button-group size="small">
                <el-button @click="propagationZoomIn" title="放大"><el-icon><PlusIcon /></el-icon></el-button>
                <el-button @click="propagationZoomOut" title="缩小"><el-icon><MinusIcon /></el-icon></el-button>
                <el-button @click="propagationResetZoom" title="重置"><el-icon><RefreshRightIcon /></el-icon></el-button>
              </el-button-group>
            </div>
          </div>
        </template>
        <div class="flex gap-3 mb-3">
          <div class="flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
            <span class="w-2.5 h-2.5 rounded-full bg-red-500" /> 信息源头
          </div>
          <div class="flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
            <span class="w-2.5 h-2.5 rounded-full bg-orange-500" /> 关键传播者
          </div>
          <div class="flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
            <span class="w-2.5 h-2.5 rounded-full bg-blue-500" /> 平台扩散
          </div>
          <div class="flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
            <span class="w-2.5 h-2.5 rounded-full bg-green-500" /> 官方媒体
          </div>
          <div class="flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
            <span class="w-2.5 h-2.5 rounded-full bg-slate-400" /> 公众讨论
          </div>
        </div>
        <div class="w-full h-[480px] overflow-hidden flex items-center justify-center bg-slate-50/30 dark:bg-slate-950/30 rounded-lg">
          <div ref="propagationRef" class="w-full h-full" />
        </div>
      </el-card>

      <!-- ===== 关键事件时间轴 + 报道影响力排行榜 ===== -->
      <el-row :gutter="20" class="mb-6">
        <el-col :xs="24" :lg="12" class="mb-4">
          <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
            <template #header>
              <div class="font-bold text-slate-800 dark:text-slate-100">📋 关键传播节点时间轴</div>
            </template>
            <div class="px-2">
              <div class="relative pl-6 border-l-2 border-blue-100 dark:border-blue-900/40 space-y-5">
                <div v-for="(kp, idx) in displayKeyPoints" :key="idx" class="relative">
                  <span
                    class="absolute -left-[29px] top-0.5 w-3.5 h-3.5 rounded-full border-2 border-white dark:border-slate-900 shadow-sm"
                    :class="idx === 0 ? 'bg-blue-500' : idx === displayKeyPoints.length - 1 ? 'bg-orange-500' : 'bg-red-500'"
                  />
                  <div class="text-xs text-slate-400 dark:text-slate-500 mb-0.5">{{ kp.coord?.[0] || '' }}</div>
                  <div class="text-sm font-semibold text-slate-700 dark:text-slate-200">{{ kp.name }}</div>
                  <div class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    {{ idx === 0 ? '事件首次在社交媒体平台出现，引发初始关注。' : idx === displayKeyPoints.length - 1 ? '事件持续发酵，主流媒体与官方渠道跟进报道。' : '报道量急剧攀升，事件进入全面爆发扩散阶段。' }}
                  </div>
                </div>
                <div v-if="displayKeyPoints.length === 0" class="text-sm text-slate-400 dark:text-slate-500 py-4 text-center">
                  暂无关键节点数据，等待后端分析引擎填充。
                </div>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="12" class="mb-4">
          <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
            <template #header>
              <div class="font-bold text-slate-800 dark:text-slate-100">📊 报道传播影响力排行</div>
            </template>
            <div ref="influenceRef" class="w-full h-[320px]" />
          </el-card>
        </el-col>
      </el-row>

      <!-- ===== 关联报道列表 ===== -->
      <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
        <template #header>
          <div class="flex justify-between items-center">
            <span class="font-bold text-slate-800 dark:text-slate-100">📰 关联舆情报道列表</span>
          </div>
        </template>
        <el-table :data="eventData.articles?.articles" stripe style="width: 100%">
          <el-table-column type="index" label="#" width="50" align="center" />
          <el-table-column prop="title" label="报道标题" min-width="200" show-overflow-tooltip />
          <el-table-column prop="platform" label="来源平台" width="100">
            <template #default="{ row }">
              <el-tag size="small" effect="light">{{ row.platform }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="author" label="作者" width="100" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="text-xs text-slate-500 dark:text-slate-400">{{ row.author || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="publish_time" label="发布时间" width="110">
            <template #default="{ row }">
              <span class="text-xs text-slate-500 dark:text-slate-400">{{ row.publish_time || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="互动量" width="130" align="right">
            <template #default="{ row }">
              <div class="flex items-center justify-end gap-2 text-xs text-slate-500 dark:text-slate-400">
                <span title="转发">↺ {{ (row.reposts_count || 0) }}</span>
                <span title="评论">💬 {{ (row.comments_count || 0) }}</span>
                <span title="点赞">♥ {{ (row.likes_count || 0) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="sentiment_label" label="情感倾向" width="100" align="center">
            <template #default="{ row }">
              <el-tag
                size="small"
                effect="dark"
                :type="row.sentiment_label === '正面' ? 'success' : row.sentiment_label === '负面' ? 'danger' : 'info'"
              >
                {{ row.sentiment_label || '中性' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="is_suspicious" label="真实性" width="120" align="center">
            <template #default="{ row }">
              <div class="flex items-center gap-1">
                <el-tag size="small" effect="dark" :type="row.is_suspicious ? 'danger' : 'success'">
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

/* 统计卡片行强制等高等宽 */
.stat-cards-row {
  :deep(.el-col) {
    display: flex;
    > .el-card {
      flex: 1;
      .el-card__body {
        display: flex;
        flex-direction: column;
      }
    }
  }
}
</style>
