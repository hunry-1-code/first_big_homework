export interface RiskRadarMetric {
  name: string;
  value: number;
  source: string; // 数据来源标注
}

function pct(value: number): number {
  return Math.round(Math.min(100, Math.max(0, value)));
}

function safeNum(v: any, fallback: number = 0): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

/**
 * 从真实后端数据构建六维舆情雷达指标。
 * 不再使用前端假数据，所有指标都对应实际分析结果。
 */
export function buildRiskRadarMetrics(eventData: any): RiskRadarMetric[] {
  const sentiment = eventData?.sentiment || {};
  const pubOp = eventData?.public_opinion || {};
  const report = eventData?.report || {};
  const risk = report?.risk_data || {};
  const articles = eventData?.articles?.articles || [];
  const totalArticles = safeNum(eventData?.articles?.total, articles.length);

  // 1. 情感极化度：越不中性越极化
  const pos = safeNum(eventData?.sentiment_positive);
  const neg = safeNum(eventData?.sentiment_negative);
  const neu = safeNum(eventData?.sentiment_neutral);
  const polarity = pct((1 - neu) * 100); // 中性越低=越极化

  // 2. 公众参与度：有评论的文章占比 + 评论密度
  const commentCount = safeNum(pubOp?.comment_count);
  const engagement = totalArticles > 0
    ? pct(Math.min(100, (commentCount / totalArticles) * 10))
    : 0;

  // 3. 传播广度：跨平台覆盖
  const platforms = safeNum(eventData?.platform_count)
    || safeNum(eventData?.platform?.platforms?.length);
  const spread = pct((platforms / 6) * 100); // 6 平台 = 满分

  // 4. 信息可信度：100 - 谣言风险（有 LLM 用 LLM，没有默认 85）
  const suspiciousScore = safeNum(risk?.score, 0);
  const credibility = pct(100 - Math.max(suspiciousScore, 0));

  // 5. 事件活跃度：最近 24h 文章占总文章比
  const trend = eventData?.trend || {};
  const counts: number[] = trend?.counts || [];
  const last24h = counts.length > 0 ? counts[counts.length - 1] : 1;
  const activity = pct(totalArticles > 0 ? (last24h / totalArticles) * 100 : 0);

  // 6. 公众意见分歧：评论情感不一致程度（0=一致 1=完全分歧）
  const divergence = safeNum(pubOp?.opinion_divergence, 0);
  const divergenceScore = pct(divergence * 100);

  return [
    { name: "情感极化度", value: polarity, source: "sentiment.weighted_ratios" },
    { name: "公众参与度", value: engagement, source: "public_opinion.comment_count" },
    { name: "传播广度", value: spread, source: "platform_count" },
    { name: "信息可信度", value: credibility, source: report?.risk_data ? "report.risk_data" : "rule_fallback" },
    { name: "事件活跃度", value: activity, source: "trend.counts" },
    { name: "意见分歧度", value: divergenceScore, source: "public_opinion.opinion_divergence" },
  ];
}
