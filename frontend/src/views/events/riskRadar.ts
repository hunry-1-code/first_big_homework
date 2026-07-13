export interface RiskRadarMetric {
  name: string;
  value: number;
}

const SUPPORTED_PLATFORM_COUNT = 8;
const ACTIVITY_HALF_SATURATION_PER_DAY = 10;
const INTERACTION_REFERENCE = 500;

function finiteNumber(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function percentage(value: number): number {
  return Math.round(Math.min(100, Math.max(0, value)));
}

function articleCount(data: any): number {
  return Math.max(0, finiteNumber(data?.articles?.total));
}

function activityScore(data: any): number {
  const first = Date.parse(data?.first_publish_time || "");
  const last = Date.parse(data?.last_activity_time || "");
  if (!Number.isFinite(first) || !Number.isFinite(last) || last <= first) return 0;

  const spanDays = (last - first) / 86_400_000;
  const reportsPerDay = articleCount(data) / spanDays;
  return percentage(
    (reportsPerDay / (reportsPerDay + ACTIVITY_HALF_SATURATION_PER_DAY)) * 100
  );
}

function interactionScore(data: any): number {
  const articles = Array.isArray(data?.articles?.articles)
    ? data.articles.articles
    : [];
  // 只计有互动数据的文章，避免无数据文章（百度新闻）拉低均值
  const withData = articles.filter((a: any) =>
    finiteNumber(a?.likes_count) + finiteNumber(a?.comments_count) + finiteNumber(a?.reposts_count) > 0
  );
  if (withData.length === 0) return 0;

  const total = withData.reduce(
    (sum: number, article: any) =>
      sum +
      Math.max(0, finiteNumber(article?.likes_count)) +
      Math.max(0, finiteNumber(article?.comments_count)) +
      Math.max(0, finiteNumber(article?.reposts_count)),
    0
  );
  const average = total / withData.length;
  return percentage(
    (Math.log1p(average) / Math.log1p(INTERACTION_REFERENCE)) * 100
  );
}

export function buildRiskRadarMetrics(data: any): RiskRadarMetric[] {
  const risk = data?.report?.risk_data || {};
  const suspiciousTotal = Math.max(0, finiteNumber(risk.total_count));
  const suspiciousCount = Math.max(0, finiteNumber(risk.suspicious_count));
  const platformCount = Array.isArray(data?.platform?.platforms)
    ? data.platform.platforms.length
    : 0;

  return [
    { name: "传播活跃度", value: activityScore(data) },
    {
      name: "负面占比",
      value: percentage(finiteNumber(data?.sentiment_negative) * 100)
    },
    { name: "可疑风险", value: percentage(finiteNumber(risk.score)) },
    {
      name: "可疑报道率",
      value: percentage(
        suspiciousTotal > 0 ? (suspiciousCount / suspiciousTotal) * 100 : 0
      )
    },
    {
      name: "平台覆盖",
      value: percentage((platformCount / SUPPORTED_PLATFORM_COUNT) * 100)
    },
    { name: "互动强度", value: interactionScore(data) }
  ];
}
