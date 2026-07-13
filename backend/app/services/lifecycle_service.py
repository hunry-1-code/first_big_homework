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


def update_event_lifecycle(
    event,
    daily_counts,
    *,
    now: datetime | None = None,
) -> LifecyclePrediction:
    prediction = analyze_lifecycle(
        daily_counts,
        previous_stage=getattr(event, "lifecycle_stage", None),
    )
    event.lifecycle_stage = prediction.stage
    event.lifecycle_status = prediction.status
    event.lifecycle_confidence = prediction.confidence
    event.lifecycle_evidence = dict(prediction.evidence)
    event.lifecycle_updated_at = now or _utcnow()
    return prediction


__all__ = ["daily_counts_from_articles", "update_event_lifecycle"]
