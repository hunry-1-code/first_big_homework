<script setup lang="ts">
import { onMounted, ref, watch, nextTick, onBeforeUnmount, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import * as echarts from "echarts";
import "echarts-wordcloud";
import { getEvent, exportEventReport, getEventPropagation } from "@/api/events";
import { useDark } from "@pureadmin/utils";
import { message } from "@/utils/message";
import { PLATFORMS, platformColor, platformBg, getPlatform, resolvePlatformName, type PlatformInfo } from "@/constants/platforms";
import IconifyIconOffline from "@/components/ReIcon/src/iconifyIconOffline";
import PlusIcon from "~icons/ep/plus";
import MinusIcon from "~icons/ep/minus";
import RefreshRightIcon from "~icons/ep/refresh-right";
import { buildRiskRadarMetrics } from "./riskRadar";
import { buildPropagationNotice } from "./propagationPresentation";
import { buildLifecycleNote } from "./lifecyclePresentation";
import type { PublicOpinionSnapshot } from "@/api/types/opinion";

defineOptions({
  name: "EventDetail"
});

const route = useRoute();
const router = useRouter();
const eventData = ref<any>(null);
const propagationData = ref<any>(null);
const loading = ref(true);
const propagationNotice = computed(() =>
  buildPropagationNotice(propagationData.value)
);
const lifecycleNote = computed(() => buildLifecycleNote(eventData.value));
const publicOpinion = computed<PublicOpinionSnapshot | null>(() => eventData.value?.public_opinion || null);
const opinionModeLabel = computed(() => publicOpinion.value?.analysis_mode === "narrative_gap" ? "机构叙事与公众意见对照" : publicOpinion.value?.analysis_mode === "public_opinion_only" ? "仅公众意见分析" : "数据不足");
const rate = (value: number | null | undefined) => value == null ? "--" : `${Math.round(value * 100)}%`;

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
const lifecycleStages = ["潜伏期", "成长期", "高潮期", "消退期"] as const;
const currentStageIndex = computed(() => {
  const stage = eventData.value?.lifecycle_stage || "潜伏期";
  const idx = lifecycleStages.indexOf(stage as any);
  return idx >= 0 ? idx : 0;
});
function getStageColor(stage: string): string {
  if (stage === "潜伏期") return "#3b82f6";
  if (stage === "成长期") return "#f97316";
  if (stage === "高潮期") return "#ef4444";
  if (stage === "消退期") return "#22c55e";
  return "#3b82f6";
}

// 轻量背景（已完成阶段用）
function getStageLightBg(stage: string): string {
  const c = getStageColor(stage);
  if (c === "#3b82f6") return "#dbeafe";
  if (c === "#f97316") return "#ffedd5";
  if (c === "#ef4444") return "#fee2e2";
  if (c === "#22c55e") return "#dcfce7";
  return "#dbeafe";
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

// 关键传播节点时间轴 — 用趋势拐点数据（propagation key_nodes 当前质量不足以展示）
const displayKeyPoints = computed(() => {
  const { dates, counts } = getEnrichedTrend();
  return buildKeyPoints(dates, counts).map(kp => ({
    name: kp.name,
    time: kp.coord?.[0] || "",
    desc: ""
  }));
});

// 仅返回该事件实际涉及的平台（后端有数据用后端，无数据从 articles 推断）
function getEnrichedPlatforms(): PlatformInfo[] {
  const raw = eventData.value?.platform?.platforms || [];
  if (raw.length >= 2) {
    return raw
      .map((p: any) => PLATFORMS.find(x => x.name === (p.platform || p.name)))
      .filter(Boolean) as PlatformInfo[];
  }
  // 从 articles 中提取出现过的平台并去重（支持后端英文代码自动转换）
  const articles = eventData.value?.articles?.articles || [];
  const seen = new Set<string>();
  const result: PlatformInfo[] = [];
  for (const a of articles) {
    const cn = resolvePlatformName(a.platform);
    const p = PLATFORMS.find(x => x.name === cn);
    if (p && !seen.has(p.name)) { seen.add(p.name); result.push(p); }
  }
  return result.length >= 2 ? result : PLATFORMS.slice(0, 4);
}

// 当后端只给极少数据点时，自动生成 14 天模拟趋势数据用于展示
function getEnrichedTrend(): { dates: string[]; counts: number[] } {
  const rawDates: string[] = eventData.value?.trend?.dates || [];
  const rawCounts: number[] = eventData.value?.trend?.counts || [];
  return { dates: rawDates, counts: rawCounts };
}

// 构造传播网络数据——使用后端真实数据 + force 自动布局
function getNodeBg(idx: number, total: number): string {
  const colors = ["#fee2e2", "#ffedd5", "#dbeafe", "#dcfce7", "#f3e8ff", "#fce7f3"];
  return colors[idx % colors.length];
}
function getNodeColor(idx: number): string {
  const colors = ["#dc2626", "#ea580c", "#2563eb", "#16a34a", "#9333ea", "#db2777"];
  return colors[idx % colors.length];
}

function buildPropagationData() {
  const raw = propagationData.value;
  if (!raw || !raw.graph || !raw.graph.nodes || raw.graph.nodes.length === 0) {
    return { nodes: [], links: [], categories: [] };
  }

  const g = raw.graph;
  // 将后端字符串 category 映射为数字索引
  const catMap: Record<string, number> = {
    "origin_candidate": 0,
    "influencer_amplification": 1,
    "media_intervention": 2,
    "official_response": 2,
    "peak_content": 1,
    "ordinary": 3
  };
  const catNames = ["信息源头", "关键传播者", "官方媒体", "普通讨论"];
  const usedCats = new Set<number>();

  const nodes = g.nodes.map((n: any) => {
    const cat = catMap[n.category] ?? 3;
    usedCats.add(cat);
    return {
      id: n.id,
      name: (n.name || "匿名").slice(0, 8),
      category: cat,
      symbolSize: (n.symbolSize || 15) + 5,
      platform: n.platform,
      title: n.title
    };
  });

  const categories = catNames.map((name, i) => ({ name })).filter((_, i) => usedCats.has(i));

  return {
    nodes,
    links: g.links.map((l: any) => ({
      source: String(l.source),
      target: String(l.target),
      value: l.confidence ? Math.round(l.confidence * 100) : 1
    })),
    categories
  };
}

// 构造模拟文章影响力数据
function buildInfluenceData() {
  const articles = eventData.value?.articles?.articles || [];
  if (articles.length === 0) return [];
  const withInteractions = articles.filter((a: any) =>
    (a.reposts_count ?? 0) + (a.comments_count ?? 0) + (a.likes_count ?? 0) > 0
  );
  // 如果全无互动数据，返回空（不显示全0的假排行）
  if (withInteractions.length === 0) return [];
  return withInteractions.map((a: any, i: number) => ({
    name: a.title?.length > 20 ? a.title.slice(0, 20) + "..." : (a.title || `报道${i + 1}`),
    fullName: a.title || "",
    platform: a.platform || "未知",
    reposts: a.reposts_count ?? 0,
    comments: a.comments_count ?? 0,
    likes: a.likes_count ?? 0
  }));
}

onMounted(async () => {
  try {
    // 先加载事件主体数据，传播数据单独加载（可能慢），不阻塞页面
    const eventResp = await getEvent(Number(route.params.id));
    eventData.value = eventResp.data;
    await nextTick();
    initCharts();
    // 传播数据异步加载，到达后重绘传播图
    getEventPropagation(Number(route.params.id)).then(async r => {
      propagationData.value = r?.data || r;
      await nextTick();
      initPropagationChart();
    }).catch(err => { console.warn('[prop] fetch failed:', err); });
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
    grid: { top: 40, right: 30, bottom: 40, left: 55 },
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
          symbol: "roundRect",
          symbolSize: [Math.min(140, kp.name.length * 12 + 16), 26],
          itemStyle: { color: "#f97316", borderRadius: 6 },
          label: { show: true, fontSize: 11, color: "#fff", fontWeight: "bold" }
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
  const { dates } = getEnrichedTrend();

  const daily = eventData.value?.sentiment?.daily || eventData.value?.sentiment?.daily_trend || [];
  if (daily.length === 0) {
    // fallback: 用基础比例生成单点
    const pos = (eventData.value.sentiment_positive || 0) * 100;
    const neu = (eventData.value.sentiment_neutral || 0) * 100;
    const neg = (eventData.value.sentiment_negative || 0) * 100;
    sentimentTrendChart.setOption(getSentimentAreaOption(dark, c, dates, [
      { pos, neu, neg }
    ]));
    return;
  }

  const raw = daily.map((d: any) => ({
    pos: (d.positive || d.weighted_ratios?.positive || 0) * 100,
    neu: (d.neutral || d.weighted_ratios?.neutral || 0) * 100,
    neg: (d.negative || d.weighted_ratios?.negative || 0) * 100
  }));
  // ensure sum ~100 for each day
  raw.forEach((r: any) => {
    const total = r.pos + r.neu + r.neg;
    if (total > 0) { r.pos = (r.pos / total) * 100; r.neu = (r.neu / total) * 100; r.neg = (r.neg / total) * 100; }
  });

  const dailyDates = daily.map((d: any) => {
    if (d.date) { const m = d.date.slice(5, 7).replace(/^0/, ''); const day = d.date.slice(8, 10).replace(/^0/, ''); return m + '/' + day; }
    if (d.calculated_at) return d.calculated_at.slice(5, 10);
    return "";
  }).filter(Boolean);

  sentimentTrendChart.setOption(getSentimentAreaOption(dark, c, dailyDates.length ? dailyDates : dates.slice(0, raw.length), raw));
}

function getSentimentAreaOption(dark: boolean, c: any, dates: string[], raw: any[]) {
  return {
    grid: { top: 30, right: 30, bottom: 35, left: 55 },
    tooltip: {
      trigger: "axis",
      backgroundColor: dark ? "rgba(17,24,39,0.95)" : "rgba(255,255,255,0.95)",
      borderColor: dark ? "#374151" : "#e5e7eb",
      textStyle: { color: dark ? "#e2e8f0" : "#1e293b", fontSize: 12 },
      formatter: (params: any) => {
        const date = params[0]?.axisValue || "";
        const pos = params.find((p: any) => p.seriesName === "正面");
        const neu = params.find((p: any) => p.seriesName === "中立");
        const neg = params.find((p: any) => p.seriesName === "负面");
        return `<b>${date}</b><br/>
          <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#34d399;margin-right:4px"></span>正面 <b>${pos?.value?.toFixed(1) ?? 0}%</b><br/>
          <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#94a3b8;margin-right:4px"></span>中立 <b>${neu?.value?.toFixed(1) ?? 0}%</b><br/>
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
        name: "中立",
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
  };
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
    { value: neuVal, name: "中立" },
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

  const dominantLabelMap: Record<string, string> = { "正面": "#059669", "中立": "#475569", "负面": "#dc2626" };
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
        { value: neuVal, name: "中立", itemStyle: { color: neuColor } },
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
  if (platforms.length === 0) return;

  // 用 articles 里的实际报道量计算每个平台的 count
  const articles = eventData.value?.articles?.articles || [];
  const countMap: Record<string, number> = {};
  articles.forEach((a: any) => { countMap[a.platform] = (countMap[a.platform] || 0) + 1; });
  const list = platforms.map(p => ({ ...p, count: countMap[p.name] || 1 }));

  const yData = [...list].reverse();

  platformChart.setOption({
    grid: { top: 10, right: 55, bottom: 20, left: 85 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: dark ? "rgba(17,24,39,0.95)" : "rgba(255,255,255,0.95)",
      borderColor: dark ? "#374151" : "#e5e7eb",
      textStyle: { color: dark ? "#e2e8f0" : "#1e293b" },
      formatter: (params: any) => {
        const p = list.find(x => x.name === params[0]?.name);
        return p ? `<b>${p.name}</b><br/>报道量: <b>${p.count} 篇</b><br/>接入方式: ${p.api}</b>` : "";
      }
    },
    xAxis: {
      type: "value",
      axisLabel: { color: c.textColor },
      splitLine: { lineStyle: { color: c.splitLineColor } }
    },
    yAxis: {
      type: "category",
      data: yData.map(p => p.name),
      axisLabel: {
        fontSize: 12,
        formatter: (name: string) => name,
        color: (name: string) => {
          const p = PLATFORMS.find(x => x.name === name);
          return p ? p.color : (dark ? "#cbd6df" : "#4a5568");
        }
      },
      axisLine: { lineStyle: { color: c.splitLineColor } }
    },
    series: [{
      name: "报道量",
      type: "bar",
      barWidth: "50%",
      data: yData.map(p => ({
        name: p.name,
        value: p.count,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: p.color },
            { offset: 1, color: p.color + "66" }
          ]),
          borderRadius: [0, 4, 4, 0]
        }
      })),
      label: { show: true, position: "right", color: c.textColor, fontSize: 11, formatter: "{c} 篇" }
    }]
  });
}

// ==================== 4. 舆情风险画像 ====================
function initRadarChart() {
  if (!radarRef.value) return;
  if (radarChart) radarChart.dispose();
  radarChart = echarts.init(radarRef.value);

  const dark = isDark.value;
  const c = chartColors(dark);
  const metrics = buildRiskRadarMetrics(eventData.value);

  radarChart.setOption({
    tooltip: {
      trigger: "item",
      backgroundColor: dark ? "rgba(17,24,39,0.95)" : "rgba(255,255,255,0.95)",
      borderColor: dark ? "#374151" : "#e5e7eb",
      textStyle: { color: dark ? "#e2e8f0" : "#1e293b", fontSize: 12 }
    },
    legend: {
      bottom: 0,
      data: ["舆情画像"],
      textStyle: { color: c.textColor, fontSize: 11 }
    },
    radar: {
      center: ["50%", "46%"],
      radius: "60%",
      indicator: metrics.map(metric => ({ name: metric.name, max: 100 })),
      axisName: { color: c.textColor, fontSize: 11 },
      splitArea: {
        areaStyle: { color: [dark ? "rgba(37,47,63,0.3)" : "rgba(241,245,249,0.6)", dark ? "rgba(30,40,55,0.3)" : "rgba(255,255,255,0.6)"] }
      }
    },
    series: [{
      type: "radar",
      name: "舆情画像",
      data: [{
        value: metrics.map(metric => metric.value),
        name: "舆情画像",
        areaStyle: { color: "rgba(239,68,68,0.15)" },
        lineStyle: { color: "#ef4444", width: 2 },
        itemStyle: { color: "#ef4444" },
        symbol: "circle",
        symbolSize: 4
      }]
    }]
  });
}

// ==================== 5. 传播路径（已改为列表展示） ====================

// ==================== 6. 报道影响力排行榜 ====================
function initInfluenceChart() {
  const el = influenceRef.value;
  if (!el) return;
  // 确保容器有尺寸（echarts 需要明确的宽高）
  if (el.clientHeight === 0) {
    el.style.height = "320px";
    el.style.width = el.clientWidth > 0 ? `${el.clientWidth}px` : "100%";
  }
  if (influenceChart) influenceChart.dispose();
  influenceChart = echarts.init(el);

  const dark = isDark.value;
  const c = chartColors(dark);
  const data = buildInfluenceData();
  if (data.length === 0) {
    influenceChart.setOption({
      title: { text: '暂无互动数据', left: 'center', top: 'center', textStyle: { color: c.textColor, fontSize: 13 } }
    });
    return;
  }

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
  if (!eventData.value || !bubbleRef.value) {
    console.warn('[wordcloud] container not ready');
    return;
  }

  const dark = isDark.value;
  const list = eventData.value.keywords?.keywords || [];
  if (list.length === 0) {
    console.warn('[wordcloud] no keywords');
    return;
  }
  console.log('[wordcloud] rendering', list.length, 'keywords', list.slice(0,3));

  const count = list.length;
  // 金字塔字号映射：顶部词巨大醒目，中部中等，底部微小环绕
  const sorted = [...list]
    .map((kw: any) => ({ ...kw }))
    .sort((a: any, b: any) => (b.weight || 0) - (a.weight || 0));

  const fontSizeMin = 12;
  const fontSizeMax = 64;

  const wordData = sorted.map((kw: any, idx: number) => {
    // 用 rank 位置做陡峭映射：顶部词吞噬大部分字号空间
    const rankRatio = sorted.length > 1 ? idx / (sorted.length - 1) : 0;
    const t = 1.0 - Math.pow(rankRatio, 0.35); // pow < 1 → 顶部拉开差距
    const fontSize = Math.round(fontSizeMin + t * (fontSizeMax - fontSizeMin));
    const isTop = idx < Math.min(6, sorted.length * 0.2);
    const isMid = !isTop && idx < Math.min(15, sorted.length * 0.5);

    // 情感着色：负面红、正面绿、中性灰蓝，透明度随字号衰减
    const sentiment = kw.sentiment || "neutral";
    const isComment = kw.source === "comment";
    let color: string;
    const alpha = isTop ? 1.0 : isMid ? 0.75 : 0.45;
    if (isComment) {
      color = dark
        ? `rgba(216,180,254,${alpha})`
        : `rgba(147,51,234,${(alpha * 0.85).toFixed(2)})`;
    } else if (sentiment === "negative") {
      color = dark
        ? `rgba(252,165,165,${alpha})`
        : `rgba(220,38,38,${(alpha * 0.9).toFixed(2)})`;
    } else if (sentiment === "positive") {
      color = dark
        ? `rgba(134,239,172,${alpha})`
        : `rgba(5,150,105,${(alpha * 0.9).toFixed(2)})`;
    } else {
      color = dark
        ? `rgba(148,163,184,${(alpha * 0.7).toFixed(2)})`
        : `rgba(30,64,175,${(alpha * 0.8).toFixed(2)})`;
    }

    return {
      name: kw.word,
      value: kw.weight,
      textStyle: {
        color,
        fontSize,
        fontWeight: isTop ? "bold" : "normal",
        fontFamily: "PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans SC, sans-serif"
      },
      emphasis: {
        textStyle: {
          color: dark ? "#e2e8f0" : "#1e293b",
          textShadowBlur: 6,
          textShadowColor: dark ? "rgba(0,0,0,0.6)" : "rgba(0,0,0,0.12)"
        }
      }
    };
  });

  const gridSize = 4;

  if (bubbleChart) bubbleChart.dispose();
  try {
    bubbleChart = echarts.init(bubbleRef.value);
  } catch(e) {
    console.error('[wordcloud] init failed:', e);
    return;
  }
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
          const idx = sorted.findIndex((k: any) => k.word === v.name);
          if (idx < 0) return dark ? "#94a3b8" : "#64748b";
          if (idx < 6) return dark ? "#93c5fd" : "#1e40af";
          if (idx < 15) return dark ? "#94a3b8" : "#3b82f6";
          return dark ? "rgba(148,163,184,0.35)" : "rgba(148,163,184,0.5)";
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
                <!-- 已完成 -->
                <span v-if="idx < currentStageIndex"
                  class="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-medium transition-all duration-300"
                  :style="{ backgroundColor: getStageLightBg(stage), color: getStageColor(stage), border: '1px solid ' + getStageColor(stage) + '40' }"
                >
                  <span class="w-1.5 h-1.5 rounded-full shrink-0" :style="{ backgroundColor: getStageColor(stage) }" />
                  {{ stage }}
                </span>
                <!-- 当前 -->
                <span v-else-if="idx === currentStageIndex"
                  class="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold text-white transition-all duration-300"
                  :style="{ backgroundColor: getStageColor(stage) }"
                >
                  <span class="w-1.5 h-1.5 rounded-full shrink-0 bg-white/70" />
                  {{ stage }}
                </span>
                <!-- 未到达 -->
                <span v-else
                  class="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-medium text-slate-400 dark:text-slate-500 transition-all duration-300"
                >
                  <span class="w-1.5 h-1.5 rounded-full shrink-0 bg-slate-300 dark:bg-slate-600" />
                  {{ stage }}
                </span>
                <span
                  v-if="idx < lifecycleStages.length - 1"
                  class="text-[10px] mx-0.5"
                  :style="{ color: idx < currentStageIndex ? getStageColor(lifecycleStages[idx + 1]) + '80' : '#cbd5e1' }"
                >▸</span>
              </template>
            </div>
            <span
              v-if="lifecycleNote"
              class="text-[11px] text-slate-400 dark:text-slate-500"
            >
              {{ lifecycleNote }}
            </span>
            <span v-if="eventData?.prediction?.confidence" class="text-[10px] text-slate-400">
              置信度 {{ (eventData.prediction.confidence * 100).toFixed(0) }}%
              <template v-if="eventData.prediction.trend_direction"> · {{ eventData.prediction.trend_direction }}</template>
              <template v-if="eventData.prediction.next_stage"> · 预测→{{ eventData.prediction.next_stage }}</template>
            </span>
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
              {{ eventData.heat_index > 0 ? Math.round(eventData.heat_index) : '--' }}
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

      <!-- ===== 公众意见与叙事张力 ===== -->
      <el-card v-if="publicOpinion" shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl mb-6">
        <template #header>
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div class="text-base font-bold text-slate-800 dark:text-slate-100">公众意见与叙事张力</div>
              <div class="text-sm text-slate-400 mt-1">评论独立分析，不计入事件聚类与报道数量</div>
            </div>
            <el-tag :type="publicOpinion.narrative_gap_available ? 'warning' : 'info'" effect="plain">{{ opinionModeLabel }}</el-tag>
          </div>
        </template>

        <!-- 机构数据缺失提示 -->
        <div v-if="publicOpinion.coverage_warning" class="mb-5 px-4 py-3 rounded-lg bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300 text-sm">当前未采集到机构侧数据，不计算叙事张力；这不代表机构没有公开回应。</div>

        <!-- 核心指标：2x2 大卡片 -->
        <div class="grid grid-cols-2 gap-4 mb-6">
          <div class="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50">
            <div class="text-sm text-slate-500 mb-1">评论样本</div>
            <div class="text-3xl font-bold text-slate-700 dark:text-slate-200">{{ publicOpinion.comment_count }}</div>
            <div class="text-xs text-slate-400 mt-1">条公众评论</div>
          </div>
          <div class="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/20">
            <div class="text-sm text-rose-600 mb-1">公众负面率</div>
            <div class="text-3xl font-bold text-rose-600">{{ rate(publicOpinion.negative_rate) }}</div>
            <div class="text-xs text-rose-400 mt-1">情感校正 {{ publicOpinion.sentiment_corrected_count ?? 0 }} 条</div>
          </div>
          <div class="p-4 rounded-xl bg-amber-50 dark:bg-amber-950/20">
            <div class="text-sm text-amber-600 mb-1">意见分歧度</div>
            <div class="text-3xl font-bold text-amber-600">{{ rate(publicOpinion.opinion_divergence) }}</div>
            <div class="text-xs text-amber-400 mt-1">观点一致性指标</div>
          </div>
          <div class="p-4 rounded-xl bg-blue-50 dark:bg-blue-950/20">
            <div class="text-sm text-blue-600 mb-1">加权情感分布</div>
            <div class="text-sm font-medium space-x-3" v-if="publicOpinion.weighted_sentiment">
              <span class="text-emerald-600">正面 {{ rate(publicOpinion.weighted_sentiment.positive) }}</span>
              <span class="text-rose-600">负面 {{ rate(publicOpinion.weighted_sentiment.negative) }}</span>
              <span class="text-slate-500">中性 {{ rate(publicOpinion.weighted_sentiment.neutral) }}</span>
            </div>
            <div class="text-xs text-blue-400 mt-1">长度+点赞质量加权</div>
          </div>
        </div>

        <!-- AI 公众关注主题 -->
        <div v-if="publicOpinion.opinion_themes && publicOpinion.opinion_themes.length" class="mb-5">
          <h4 class="text-sm font-bold text-slate-600 dark:text-slate-400 mb-3">AI 识别公众关注主题</h4>
          <div class="flex flex-wrap gap-2">
            <span v-for="(t, i) in publicOpinion.opinion_themes" :key="i"
              class="inline-flex items-center gap-2 text-sm px-3 py-1.5 rounded-full"
              :class="t.sentiment === 'negative' ? 'bg-red-50 text-red-700 dark:bg-red-950/30' : t.sentiment === 'positive' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30' : 'bg-slate-100 text-slate-600 dark:bg-slate-800'">
              {{ t.theme }}
              <span class="opacity-50 text-xs">{{ t.example?.slice(0, 30) }}</span>
            </span>
          </div>
        </div>

        <!-- 媒体vs公众叙事差异 -->
        <div v-if="publicOpinion.narrative_gap_analysis" class="mb-5 p-4 rounded-xl bg-purple-50 dark:bg-purple-950/20 text-sm">
          <div class="font-bold text-purple-700 dark:text-purple-300 mb-2">媒体与公众叙事差异</div>
          <div class="text-slate-600 dark:text-slate-300 space-y-2">
            <div><span class="font-medium">媒体强调：</span>{{ publicOpinion.narrative_gap_analysis.media_focus }}</div>
            <div><span class="font-medium">公众关注：</span>{{ publicOpinion.narrative_gap_analysis.public_focus }}</div>
            <div><span class="font-medium">核心差异：</span>{{ publicOpinion.narrative_gap_analysis.gap }}</div>
            <el-tag size="small" :type="publicOpinion.narrative_gap_analysis.intensity === 'high' ? 'danger' : 'warning'">
              差异强度: {{ publicOpinion.narrative_gap_analysis.intensity }}
            </el-tag>
          </div>
        </div>

        <!-- 三列：关键词 + 诉求 -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div>
            <h4 class="text-sm font-bold text-slate-600 dark:text-slate-400 mb-2">机构侧关键词</h4>
            <div class="flex flex-wrap gap-2">
              <el-tag v-for="item in publicOpinion.official_keywords" :key="item.word" type="primary" effect="plain">{{ item.word }} {{ item.count }}</el-tag>
              <span v-if="!publicOpinion.official_keywords.length" class="text-sm text-slate-400">暂无机构数据</span>
            </div>
          </div>
          <div>
            <h4 class="text-sm font-bold text-slate-600 dark:text-slate-400 mb-2">公众高频表达</h4>
            <div class="flex flex-wrap gap-2">
              <el-tag v-for="item in publicOpinion.public_keywords" :key="item.word" type="danger" effect="plain">{{ item.word }} {{ item.count }}</el-tag>
              <span v-if="!publicOpinion.public_keywords.length" class="text-sm text-slate-400">暂无评论数据</span>
            </div>
          </div>
          <div>
            <h4 class="text-sm font-bold text-slate-600 dark:text-slate-400 mb-2">公众诉求</h4>
            <div class="space-y-2">
              <div v-for="item in publicOpinion.public_demands" :key="item.demand" class="flex justify-between text-sm text-slate-600 dark:text-slate-300">
                <span>{{ item.demand }}</span><b>{{ item.count }}</b>
              </div>
              <span v-if="!publicOpinion.public_demands.length" class="text-sm text-slate-400">暂未识别出明确诉求</span>
            </div>
          </div>
        </div>

        <!-- 核心判断 -->
        <div v-if="publicOpinion.gap_interpretation" class="mt-5 pt-4 border-t border-slate-100 dark:border-slate-800 text-sm text-slate-600 dark:text-slate-300">
          核心判断：{{ publicOpinion.gap_interpretation }}；公众意见分歧度 {{ rate(publicOpinion.opinion_divergence) }}
        </div>
      </el-card>

      <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl mb-6">
        <template #header>
          <div class="font-bold text-slate-800 dark:text-slate-100">
            📈 舆情传播趋势与情感变化
          </div>
        </template>
        <div class="border-b border-slate-100 dark:border-slate-800/60 pb-4 mb-4">
          <div class="text-xs text-slate-400 dark:text-slate-500 mb-2">报道量趋势</div>
          <div ref="trendRef" class="w-full h-[260px]" />
        </div>
        <div>
          <div class="text-xs text-slate-400 dark:text-slate-500 mb-2">情感分布变化（正面 · 中立 · 负面）</div>
          <div ref="sentimentTrendRef" class="w-full h-[260px]" />
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
            <div class="flex flex-wrap gap-1.5 mb-3">
              <span
                v-for="p in getEnrichedPlatforms()"
                :key="p.name"
                class="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full font-medium"
                :style="{ color: p.color, background: p.bg }"
              >
                <IconifyIconOffline :icon="p.icon" class="text-sm" />
                {{ p.name }}
              </span>
            </div>
            <div ref="platformRef" class="w-full h-[280px]" />
          </el-card>
        </el-col>
        <el-col :xs="24" :md="8" class="mb-4">
          <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl">
            <template #header>
              <div>
                <div class="font-bold text-slate-800 dark:text-slate-100">🛡️ 多维舆情画像</div>
                <div class="text-xs text-slate-400 mt-1">归一化指标，均由当前事件真实采集数据计算</div>
              </div>
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
              <div><span class="text-gray-400">时间:</span>
                <span class="font-medium ml-1 text-gray-700 dark:text-gray-300">{{ eventData.time_code || '-' }}</span></div>
              <div><span class="text-gray-400">地点:</span>
                <span class="font-medium ml-1 text-gray-700 dark:text-gray-300">{{ eventData.location || '-' }}</span></div>
              <div class="col-span-2"><span class="text-gray-400">人物/机构:</span>
                <span class="font-medium ml-1 text-gray-700 dark:text-gray-300">{{ eventData.key_figures || '-' }}</span></div>
              <div class="col-span-2"><span class="text-gray-400">起因:</span>
                <span class="font-medium ml-1 text-gray-700 dark:text-gray-300 line-clamp-1" :title="eventData.cause">{{ eventData.cause || '-' }}</span></div>
            </div>
            <p class="text-sm text-gray-600 dark:text-gray-300 leading-relaxed mb-2">
              {{ eventData.report?.overview_text || '暂无研判摘要' }}
            </p>
            <div v-if="eventData.report?.risk_data?.factors?.length" class="text-xs text-gray-400 mt-2">
              <span class="font-medium text-orange-500">风险因素：</span>
              {{ eventData.report.risk_data.factors.join('；') }}
            </div>
            <div class="mt-3 pt-3 border-t border-gray-100 dark:border-gray-800">
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

      <!-- ===== 事件溯源与关键传播路径 ===== -->
      <el-card shadow="never" class="!border-slate-200/60 dark:!border-slate-800/60 rounded-xl mb-6">
        <template #header>
          <div class="font-bold text-slate-800 dark:text-slate-100">事件溯源与关键传播路径</div>
        </template>
        <div v-if="propagationNotice" class="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-800/60 dark:bg-amber-950/30 dark:text-amber-300">{{ propagationNotice }}</div>

        <!-- 关键词传播链 -->
        <div v-if="propagationData?.graph?.nodes?.length" class="mb-4">
          <div class="text-xs text-slate-400 mb-2">关键词传播演化链</div>
          <div class="flex items-center gap-2 flex-wrap">
            <template v-for="(node, idx) in propagationData.graph.nodes" :key="node.id">
              <span class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium"
                :style="{ backgroundColor: getNodeBg(idx, propagationData.graph.nodes.length), color: getNodeColor(idx) }">
                {{ node.name }}
                <span class="text-[10px] opacity-60">({{ Math.round((node.symbolSize || 0) / 40 * 100) }}%)</span>
              </span>
              <span v-if="idx < propagationData.graph.nodes.length - 1" class="text-slate-300 text-lg">&rarr;</span>
            </template>
          </div>
        </div>

        <!-- 溯源信息 -->
        <div v-if="propagationData?.origin_analysis" class="text-xs text-slate-500 space-y-1">
          <div v-if="propagationData.origin_analysis.status === 'completed' && propagationData.origin_analysis.origin">
            <span class="font-medium">疑似源头:</span>
            {{ propagationData.origin_analysis.origin.title }}
            <span v-if="propagationData.origin_analysis.origin.source">({{ propagationData.origin_analysis.origin.source }})</span>
          </div>
          <div v-else-if="propagationData?.coverage_status === 'partial'">
            <span class="text-amber-500">溯源状态: 部分完成，待豆包联网复核</span>
          </div>
          <div v-else>
            <span class="text-slate-400">溯源分析将在后台计算完成后更新</span>
          </div>
          <div v-if="propagationData?.summary?.coverage_notice">{{ propagationData.summary.coverage_notice }}</div>
        </div>

        <div v-if="!propagationData" class="text-xs text-slate-400 py-4 text-center">传播数据加载中...</div>
        <div v-else-if="!propagationData.graph?.nodes?.length" class="text-xs text-slate-400 py-4 text-center">暂无传播路径数据</div>
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
                  <span class="absolute -left-[29px] top-0.5 w-3.5 h-3.5 rounded-full border-2 border-white dark:border-slate-900 shadow-sm"
                    :class="idx === 0 ? 'bg-blue-500' : idx === displayKeyPoints.length - 1 ? 'bg-orange-500' : 'bg-red-500'" />
                  <div class="text-xs text-slate-400 dark:text-slate-500 mb-0.5">{{ kp.time || '' }}</div>
                  <div class="text-sm font-semibold text-slate-700 dark:text-slate-200">{{ kp.name }}</div>
                  <div class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    {{ idx === 0 ? '当前采集数据中的最早报道节点。' : idx === displayKeyPoints.length - 1 ? '当前采集窗口中的最新报道节点。' : '报道量出现阶段性变化的关键时间点。' }}
                  </div>
                </div>
                <div v-if="displayKeyPoints.length === 0" class="text-sm text-slate-400 dark:text-slate-500 py-4 text-center">
                  暂无数据，等待后端分析引擎填充。
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
            <div ref="influenceRef" class="w-full h-[320px]">
              <div v-if="!eventData?.articles?.articles?.length" class="flex items-center justify-center h-full text-sm text-slate-400">暂无报道数据</div>
            </div>
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
          <el-table-column prop="platform" label="来源平台" width="120">
            <template #default="{ row }">
              <span
                class="inline-flex items-center gap-1 text-[11px] px-1.5 py-px rounded font-medium"
                :style="{ color: platformColor(row.platform), background: platformBg(row.platform) }"
              >
                <IconifyIconOffline :icon="getPlatform(row.platform)?.icon || ''" class="text-sm" />
                {{ row.platform }}
              </span>
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
                {{ row.sentiment_label || '中立' }}
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
          <el-table-column label="关键词" min-width="180">
            <template #default="{ row }">
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="k in (row.keywords || [])"
                  :key="k.word"
                  class="inline-block text-[11px] px-1.5 py-0.5 rounded font-medium cursor-pointer hover:opacity-80"
                  :class="{
                    'bg-red-50 text-red-600 dark:bg-red-950/30 dark:text-red-400': k.sentiment === 'negative',
                    'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/30 dark:text-emerald-400': k.sentiment === 'positive',
                    'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400': k.sentiment === 'neutral'
                  }"
                >
                  {{ k.word }}
                </span>
                <span v-if="!row.keywords || row.keywords.length === 0" class="text-xs text-slate-400">-</span>
              </div>
            </template>
          </el-table-column>
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
.opinion-panel {
  background-image: radial-gradient(circle at 90% 0%, rgb(245 158 11 / 8%), transparent 34%);
}
.opinion-metric {
  padding: 12px 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: rgb(248 250 252 / 55%);
  span { display: block; color: #94a3b8; font-size: 12px; margin-bottom: 4px; }
  strong { font-size: 20px; }
}
.opinion-column {
  padding: 14px;
  border-radius: 10px;
  border: 1px solid var(--el-border-color-lighter);
  h4 { margin-bottom: 10px; font-size: 13px; font-weight: 700; color: var(--el-text-color-primary); }
}
</style>
