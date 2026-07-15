from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from app.analysis.trend_predictor import LifecyclePrediction, analyze_lifecycle


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def build_daily_lifecycle_series(articles) -> dict:
    articles = list(articles)
    dated_articles = []
    article_day = {}
    for article in articles:
        timestamp = getattr(article, "publish_time", None) or getattr(
            article, "first_crawled_at", None
        )
        if timestamp is None:
            continue
        day = timestamp.date()
        dated_articles.append((article, day))
        article_day[int(article.id)] = day
    if not dated_articles:
        return {
            "dates": [],
            "articles": [],
            "comments": [],
            "sentiment_polarity": [],
            "platforms": [],
        }

    start = min(day for _article, day in dated_articles)
    end = max(day for _article, day in dated_articles)
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)

    article_counts = Counter()
    day_platforms = defaultdict(set)
    for article, day in dated_articles:
        article_counts[day] += 1
        platform = str(getattr(article, "platform", "") or "").strip()
        if platform:
            day_platforms[day].add(platform)

    from app.models.comment import Comment

    comment_counts = Counter()
    sentiment_counts = defaultdict(Counter)
    article_ids = list(article_day)
    comments = (
        Comment.query.filter(Comment.article_id.in_(article_ids)).all()
        if article_ids
        else []
    )
    for comment in comments:
        day = article_day.get(int(comment.article_id))
        if day is None:
            continue
        comment_counts[day] += 1
        if comment.sentiment_label:
            sentiment_counts[day][str(comment.sentiment_label)] += 1

    polarity = []
    for day in days:
        labels = sentiment_counts[day]
        total = sum(labels.values())
        if not total:
            polarity.append(0.0)
            continue
        positive = labels.get("positive", 0) / total
        negative = labels.get("negative", 0) / total
        polarity.append(round(abs(positive - negative), 4))

    return {
        "dates": [day.isoformat() for day in days],
        "articles": [article_counts[day] for day in days],
        "comments": [comment_counts[day] for day in days],
        "sentiment_polarity": polarity,
        "platforms": [len(day_platforms[day]) for day in days],
    }


def daily_counts_from_articles(articles) -> list[int]:
    return build_daily_lifecycle_series(articles)["articles"]


def daily_comment_counts(articles) -> list[int]:
    """按文章发布时间聚合每日评论数。"""
    return build_daily_lifecycle_series(articles)["comments"]


def daily_sentiment_polarity(articles) -> list[float]:
    """按日计算情感极化度：|正面占比 - 负面占比|，越高越极化。"""
    return build_daily_lifecycle_series(articles)["sentiment_polarity"]


def update_event_lifecycle(
    event,
    daily_counts,
    *,
    now: datetime | None = None,
    daily_comments: list[int] | None = None,
    daily_sentiment: list[float] | None = None,
    daily_platforms: list[int] | None = None,
    dates: list[str] | None = None,
    crawl_mode: str = "search",
) -> LifecyclePrediction:
    """更新事件生命周期。

    - search 模式（单次搜索）：简化评估——活跃/衰减，不做四阶段伪拟合
    - monitor 模式（持续监控）：完整四阶段生命周期分析
    """
    now = now or _utcnow()

    if crawl_mode == "search":
        # 单次搜索：只看「当前活跃度」，不拟合四阶段
        prediction = _assess_activity(
            event,
            daily_counts,
            daily_comments,
            daily_sentiment,
            now,
            daily_platforms=daily_platforms,
            dates=dates,
        )
        return prediction

    prediction = analyze_lifecycle(
        daily_counts,
        previous_stage=getattr(event, "lifecycle_stage", None),
        daily_comments=daily_comments,
        daily_sentiment_polarity=daily_sentiment,
        daily_platform_count=daily_platforms,
    )
    event.lifecycle_stage = prediction.stage
    event.lifecycle_status = prediction.status
    event.lifecycle_confidence = prediction.confidence
    event.lifecycle_evidence = _enhanced_evidence(
        event,
        prediction,
        dates=dates,
        daily_counts=daily_counts,
        daily_comments=daily_comments,
        daily_sentiment=daily_sentiment,
        daily_platforms=daily_platforms,
    )
    event.lifecycle_updated_at = now
    return prediction


def _assess_activity(
    event,
    daily_counts,
    daily_comments,
    daily_sentiment,
    now,
    *,
    daily_platforms=None,
    dates=None,
) -> LifecyclePrediction:
    """单次搜索模式下的活跃度评估。不假装知道事件全生命周期，只看当前是否有活跃讨论。"""
    total_articles = sum(daily_counts) if daily_counts else 0
    total_comments = sum(daily_comments) if daily_comments else 0

    # 最近24h内有新文章 → 活跃
    recent_articles = daily_counts[-1] if len(daily_counts) > 0 else 0
    recent_comments = daily_comments[-1] if daily_comments and len(daily_comments) > 0 else 0

    # 评论是否还在增长
    comment_growing = False
    if daily_comments and len(daily_comments) >= 2:
        comment_growing = daily_comments[-1] > daily_comments[-2]

    # 情感是否还在极化（讨论未平息）
    polarizing = False
    if daily_sentiment and len(daily_sentiment) >= 2:
        polarizing = daily_sentiment[-1] > daily_sentiment[-2]

    # 判断：活跃 vs 趋于平静
    if recent_articles >= 3 and (recent_comments > 50 or comment_growing or polarizing):
        stage = "成长期"
        confidence = 0.65
    elif total_articles >= 10 and (comment_growing or polarizing):
        stage = "成长期"
        confidence = 0.55
    elif recent_articles >= 1:
        stage = "潜伏期"
        confidence = 0.50
    else:
        stage = "消退期"
        confidence = 0.45

    trend = analyze_lifecycle(
        daily_counts,
        daily_comments=daily_comments,
        daily_sentiment_polarity=daily_sentiment,
        daily_platform_count=daily_platforms,
    )
    evidence = {
        "mode": "search_snapshot",
        "total_articles": total_articles,
        "total_comments": total_comments,
        "recent_articles_24h": recent_articles,
        "recent_comments_24h": recent_comments,
        "comment_growing": comment_growing,
        "sentiment_polarizing": polarizing,
        "momentum": trend.momentum,
        "next_stage_hint": trend.next_stage_hint,
        "reason": "单次搜索截面数据，基于最近24h活跃度判断",
    }

    event.lifecycle_stage = stage
    event.lifecycle_status = "sufficient" if total_articles >= 3 else "data_insufficient"
    if event.lifecycle_status == "data_insufficient":
        confidence = min(confidence, 0.40)
        prediction = LifecyclePrediction(
            stage=stage,
            status=event.lifecycle_status,
            confidence=confidence,
            evidence=evidence,
            momentum=trend.momentum,
            next_stage_hint=trend.next_stage_hint,
        )
        event.lifecycle_confidence = confidence
    event.lifecycle_confidence = confidence
    if event.lifecycle_status != "data_insufficient":
        prediction = LifecyclePrediction(
            stage=stage,
            status=event.lifecycle_status,
            confidence=confidence,
            evidence=evidence,
            momentum=trend.momentum,
            next_stage_hint=trend.next_stage_hint,
        )
    event.lifecycle_evidence = _enhanced_evidence(
        event,
        prediction,
        dates=dates,
        daily_counts=daily_counts,
        daily_comments=daily_comments,
        daily_sentiment=daily_sentiment,
        daily_platforms=daily_platforms,
    )
    event.lifecycle_updated_at = now
    return prediction


def _enhanced_evidence(
    event,
    prediction,
    *,
    dates,
    daily_counts,
    daily_comments,
    daily_sentiment,
    daily_platforms,
) -> dict:
    from app.services.lifecycle_explanation_service import explain_lifecycle

    evidence = dict(prediction.evidence)
    evidence["momentum"] = prediction.momentum
    evidence["next_stage_hint"] = prediction.next_stage_hint
    series = {
        "dates": list(dates or []),
        "articles": list(daily_counts or []),
        "comments": list(daily_comments or []),
        "sentiment_polarity": list(daily_sentiment or []),
        "platforms": list(daily_platforms or []),
    }
    explanation = explain_lifecycle(
        event_title=getattr(event, "title", "") or "",
        stage=prediction.stage,
        confidence=prediction.confidence,
        momentum=prediction.momentum,
        next_stage_hint=prediction.next_stage_hint,
        series=series,
    )
    evidence.update(
        {
            "dates": series["dates"],
            "llm_status": explanation["status"],
            "llm_model": explanation.get("model"),
            "trend_explanation": explanation.get("trend_explanation", ""),
            "next_stage_reason": explanation.get("next_stage_reason", ""),
            "trend_risks": explanation.get("risks", []),
        }
    )
    return evidence


__all__ = [
    "daily_counts_from_articles",
    "build_daily_lifecycle_series",
    "daily_comment_counts",
    "daily_sentiment_polarity",
    "update_event_lifecycle",
]
