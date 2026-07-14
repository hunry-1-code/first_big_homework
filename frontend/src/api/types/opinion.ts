export interface PublicOpinionSnapshot {
  comment_count: number;
  sentiment_distribution: { positive: number; neutral: number; negative: number };
  negative_rate: number | null;
  institutional_article_count: number;
  institutional_response_rate: number | null;
  analysis_mode: "narrative_gap" | "public_opinion_only" | "insufficient_data";
  narrative_gap_available: boolean;
  narrative_gap_score: number | null;
  gap_interpretation: string | null;
  coverage_warning: string | null;
  opinion_divergence: number | null;
  public_keywords: Array<{ word: string; count: number }>;
  official_keywords: Array<{ word: string; count: number }>;
  public_demands: Array<{ demand: string; count: number }>;
}

export interface DailyHotItem {
  id: number;
  rank: number;
  title: string;
  fused_score: number;
  source_ranks: Record<string, number>;
  source_urls: Record<string, string>;
  enrichment_status: string;
  event_id: number | null;
  analysis_task_id: number | null;
  category: string | null;
  topic_name: string | null;
  topic_keywords: string[];
}

export interface DailyHotResponse {
  status: string;
  stale: boolean;
  items: DailyHotItem[];
  total: number;
  category_counts: Record<string, number>;
}
