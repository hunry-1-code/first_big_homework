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
) -> LifecyclePrediction:
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
    event.lifecycle_updated_at = now or _utcnow()
    return prediction


__all__ = [
    "daily_counts_from_articles",
    "daily_comment_counts",
    "daily_sentiment_polarity",
    "update_event_lifecycle",
]
