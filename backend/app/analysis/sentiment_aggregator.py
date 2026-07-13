from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from app.analysis.sentiment_config import SentimentConfig


LABELS = ("positive", "negative", "neutral")


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


@dataclass(frozen=True, slots=True)
class SentimentAggregateItem:
    article_id: int
    label: str
    score: float
    platform: str
    publish_time: datetime | None = None
    observed_time: datetime | None = None
    is_representative: bool = True
    nlp_weight: float = 1.0
    spam_weight: float = 1.0
    duplicate_weight: float = 1.0
    heat_contribution: float | None = None


def article_sentiment_weight(
    item: SentimentAggregateItem, *, event_max_heat: float
) -> tuple[float, dict]:
    quality = _clamp(item.nlp_weight)
    spam = _clamp(item.spam_weight)
    duplicate = 1.0 if item.is_representative else _clamp(item.duplicate_weight)
    heat = max(0.0, float(item.heat_contribution or 0.0))
    spread = 1.0
    if event_max_heat > 0 and heat > 0:
        normalized_log_heat = math.log1p(heat) / math.log1p(event_max_heat)
        spread = min(1.5, 1.0 + normalized_log_heat * 0.5)
    weight = quality * spam * duplicate * spread
    return weight, {
        "quality_weight": quality,
        "spam_weight": spam,
        "duplicate_factor": duplicate,
        "spread_factor": spread,
        "final_weight": weight,
    }


def summarize_sentiment(
    items: Iterable[SentimentAggregateItem],
    config: SentimentConfig,
    *,
    representative_reasons: Iterable[str] | None = None,
) -> dict:
    rows = [item for item in items if item.label in LABELS]
    raw_counts = {label: 0 for label in LABELS}
    weighted = {label: 0.0 for label in LABELS}
    max_heat = max((float(item.heat_contribution or 0.0) for item in rows), default=0.0)
    score_total = 0.0
    total_weight = 0.0
    representative_count = 0
    for item in rows:
        raw_counts[item.label] += 1
        representative_count += int(item.is_representative)
        weight, _details = article_sentiment_weight(item, event_max_heat=max_heat)
        weighted[item.label] += weight
        score_total += _clamp(item.score, -1.0, 1.0) * weight
        total_weight += weight
    ratios = {
        label: weighted[label] / total_weight if total_weight else 0.0
        for label in LABELS
    }
    dominant = max(LABELS, key=lambda label: (ratios[label], -LABELS.index(label))) if rows else None
    average_score = score_total / total_weight if total_weight else 0.0
    return {
        "article_count": len(rows),
        "representative_count": representative_count,
        "raw_counts": raw_counts,
        "weighted_ratios": ratios,
        "average_score": average_score,
        "dominant_label": dominant,
        "effective_weight": total_weight,
        "summary": _generate_sentiment_summary(
            ratios,
            dominant,
            len(rows),
            average_score=average_score,
            representative_reasons=representative_reasons,
        ),
    }


def _generate_sentiment_summary(
    ratios: dict,
    dominant: str | None,
    total: int,
    *,
    average_score: float = 0.0,
    representative_reasons: Iterable[str] | None = None,
) -> str:
    """Build a deterministic, persistable summary without another model call."""
    label_names = {
        "positive": "正面",
        "negative": "负面",
        "neutral": "中立",
    }
    dominant_name = label_names.get(dominant, "暂无")
    positive = round(float(ratios.get("positive", 0.0)) * 100, 1)
    negative = round(float(ratios.get("negative", 0.0)) * 100, 1)
    neutral = round(float(ratios.get("neutral", 0.0)) * 100, 1)
    summary = (
        f"共分析{int(total)}篇文章，主导情感为{dominant_name}；"
        f"正面{positive}%、负面{negative}%、中立{neutral}%，"
        f"加权平均分{float(average_score):.3f}。"
    )
    reasons = []
    for reason in representative_reasons or []:
        cleaned = " ".join(str(reason or "").split())
        if cleaned and cleaned not in reasons:
            reasons.append(cleaned[:120])
        if len(reasons) >= 3:
            break
    if reasons:
        summary += "代表性判断依据：" + "；".join(reasons) + "。"
    return summary


def build_daily_sentiment(
    items: Iterable[SentimentAggregateItem], config: SentimentConfig
) -> list[dict]:
    grouped: dict[str, list[SentimentAggregateItem]] = defaultdict(list)
    sources: dict[str, dict[str, int]] = defaultdict(
        lambda: {"publish_time": 0, "observed_at": 0}
    )
    for item in items:
        effective_time = item.publish_time or item.observed_time
        if effective_time is None:
            continue
        key = effective_time.date().isoformat()
        grouped[key].append(item)
        sources[key]["publish_time" if item.publish_time is not None else "observed_at"] += 1
    output = []
    for key in sorted(grouped):
        summary = summarize_sentiment(grouped[key], config)
        warnings = ["TIME_SOURCE_DEGRADED"] if sources[key]["observed_at"] else []
        output.append(
            {
                "date": key,
                **summary,
                "time_source_counts": sources[key],
                "warnings": warnings,
            }
        )
    return output


def build_platform_sentiment(
    items: Iterable[SentimentAggregateItem], config: SentimentConfig
) -> list[dict]:
    grouped: dict[str, list[SentimentAggregateItem]] = defaultdict(list)
    for item in items:
        grouped[str(item.platform or "unknown")].append(item)
    output = []
    for platform in sorted(grouped):
        summary = summarize_sentiment(grouped[platform], config)
        insufficient = (
            summary["article_count"] < config.platform_min_articles
            or summary["representative_count"] < config.platform_min_representatives
        )
        output.append(
            {
                "platform": platform,
                **summary,
                "sample_insufficient": insufficient,
                "warnings": ["PLATFORM_SAMPLE_INSUFFICIENT"] if insufficient else [],
            }
        )
    return output


__all__ = [
    "SentimentAggregateItem",
    "article_sentiment_weight",
    "build_daily_sentiment",
    "build_platform_sentiment",
    "summarize_sentiment",
]
