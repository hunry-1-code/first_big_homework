from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from app.analysis.trend_predictor import LifecyclePrediction, analyze_lifecycle


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def daily_counts_from_articles(articles) -> list[int]:
    counts = Counter()
    for article in articles:
        timestamp = getattr(article, "publish_time", None) or getattr(
            article, "first_crawled_at", None
        )
        if timestamp is not None:
            counts[timestamp.date().isoformat()] += 1
    return [counts[day] for day in sorted(counts)]


def daily_comment_counts(articles) -> list[int]:
    """按文章发布时间聚合每日评论数。"""
    from app.models.comment import Comment
    day_comments = Counter()
    for article in articles:
        ts = article.publish_time or article.first_crawled_at
        if ts is None:
            continue
        day = ts.date().isoformat()
        cnt = Comment.query.filter_by(article_id=article.id).count()
        day_comments[day] += cnt
    return [day_comments[day] for day in sorted(day_comments)]


def daily_sentiment_polarity(articles) -> list[float]:
    """按日计算情感极化度：|正面占比 - 负面占比|，越高越极化。"""
    from app.models.comment import Comment
    from collections import defaultdict
    day_labels = defaultdict(list)
    for article in articles:
        ts = article.publish_time or article.first_crawled_at
        if ts is None:
            continue
        day = ts.date().isoformat()
        for c in Comment.query.filter_by(article_id=article.id).all():
            if c.sentiment_label:
                day_labels[day].append(c.sentiment_label)

    result = []
    for day in sorted(day_labels):
        labels = day_labels[day]
        if not labels:
            result.append(0.0)
            continue
        c = Counter(labels)
        total = len(labels)
        pos_r = c.get("positive", 0) / total
        neg_r = c.get("negative", 0) / total
        result.append(round(abs(pos_r - neg_r), 4))
    return result


def update_event_lifecycle(
    event,
    daily_counts,
    *,
    now: datetime | None = None,
    daily_comments: list[int] | None = None,
    daily_sentiment: list[float] | None = None,
    crawl_mode: str = "search",
) -> LifecyclePrediction:
    """更新事件生命周期。

    - search 模式（单次搜索）：简化评估——活跃/衰减，不做四阶段伪拟合
    - monitor 模式（持续监控）：完整四阶段生命周期分析
    """
    now = now or _utcnow()

    if crawl_mode == "search":
        # 单次搜索：只看「当前活跃度」，不拟合四阶段
        return _assess_activity(event, daily_counts, daily_comments, daily_sentiment, now)

    prediction = analyze_lifecycle(
        daily_counts,
        previous_stage=getattr(event, "lifecycle_stage", None),
        daily_comments=daily_comments,
        daily_sentiment_polarity=daily_sentiment,
    )
    event.lifecycle_stage = prediction.stage
    event.lifecycle_status = prediction.status
    event.lifecycle_confidence = prediction.confidence
    event.lifecycle_evidence = dict(prediction.evidence)
    event.lifecycle_updated_at = now
    return prediction


def _assess_activity(event, daily_counts, daily_comments, daily_sentiment, now) -> LifecyclePrediction:
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

    evidence = {
        "mode": "search_snapshot",
        "total_articles": total_articles,
        "total_comments": total_comments,
        "recent_articles_24h": recent_articles,
        "recent_comments_24h": recent_comments,
        "comment_growing": comment_growing,
        "sentiment_polarizing": polarizing,
        "reason": "单次搜索截面数据，基于最近24h活跃度判断",
    }

    event.lifecycle_stage = stage
    event.lifecycle_status = "sufficient" if total_articles >= 3 else "data_insufficient"
    event.lifecycle_confidence = confidence
    event.lifecycle_evidence = evidence
    event.lifecycle_updated_at = now

    return LifecyclePrediction(
        stage=stage,
        status=event.lifecycle_status,
        confidence=confidence,
        evidence=evidence,
        momentum=0.0,
        next_stage_hint="",
    )


__all__ = [
    "daily_counts_from_articles",
    "daily_comment_counts",
    "daily_sentiment_polarity",
    "update_event_lifecycle",
]
