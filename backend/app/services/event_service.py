from __future__ import annotations

from collections import Counter

from sqlalchemy import or_

from app.extensions import db
from app.models import Article, Event, EventHeatSnapshot, Report
from app.services.event_similarity_service import search_historical_events


def _event_item(event: Event) -> dict:
    snapshot = (
        db.session.get(EventHeatSnapshot, event.current_heat_snapshot_id)
        if event.current_heat_snapshot_id
        else None
    )
    return {
        "id": event.id,
        "title": event.title,
        "summary": event.summary,
        "topic_category": event.topic_category,
        "topic_name": event.topic_name,
        "heat_index": float(event.heat_index or 0),
        "core_heat": float(event.core_heat or 0),
        "spread_heat": event.spread_heat,
        "is_hot": bool(event.is_hot),
        "hot_rank": event.hot_rank,
        "lifecycle_stage": event.lifecycle_stage,
        "sentiment_positive": float(event.sentiment_positive or 0),
        "sentiment_negative": float(event.sentiment_negative or 0),
        "sentiment_neutral": float(event.sentiment_neutral or 0),
        "independent_report_count": int(event.independent_report_count or 0),
        "platform_count": int(event.platform_count or 0),
        "time_confidence": event.time_confidence,
        "first_publish_time": event.first_publish_time.isoformat()
        if event.first_publish_time
        else None,
        "last_activity_time": event.last_activity_time.isoformat()
        if event.last_activity_time
        else None,
        "calculated_at": snapshot.calculated_at.isoformat() if snapshot else None,
        "formula_version": snapshot.formula_version if snapshot else None,
        "warnings": (snapshot.calculation_details or {}).get("warnings", [])
        if snapshot
        else ["HEAT_SNAPSHOT_UNAVAILABLE"],
    }


def list_events(args) -> dict:
    page = max(1, int(args.get("page", 1)))
    size = max(1, min(100, int(args.get("size", 20))))
    query = Event.query
    keyword = str(args.get("keyword") or "").strip()
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                Event.title.like(pattern),
                Event.topic_name.like(pattern),
                Event.summary.like(pattern),
            )
        )
    hot_value = str(args.get("hot") or "").strip().casefold()
    if hot_value in {"1", "true", "yes"}:
        query = query.filter(Event.is_hot.is_(True))
    total = query.count()
    events = (
        query.order_by(Event.is_hot.desc(), Event.hot_rank.asc(), Event.heat_index.desc(), Event.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "events": [_event_item(event) for event in events],
        "total": total,
        "page": page,
        "size": size,
    }


def get_event_detail(event_id: int) -> dict | None:
    event = Event.query.get(event_id)
    if event is None:
        return None
    articles = Article.query.filter_by(event_id=event.id).order_by(Article.publish_time.desc()).all()
    snapshots = (
        EventHeatSnapshot.query.filter_by(event_id=event.id)
        .order_by(EventHeatSnapshot.calculated_at)
        .all()
    )
    platform_counts = Counter(article.platform for article in articles)
    total_articles = sum(platform_counts.values())
    report = Report.query.filter_by(event_id=event.id).order_by(Report.id.desc()).first()
    from app.services.sentiment_analysis_service import get_event_sentiment

    sentiment = get_event_sentiment(event.id)
    data = _event_item(event)
    data.update(
        report={
            "overview_text": report.overview_text if report else event.summary,
            "risk_data": report.risk_data if report else {},
        },
        trend={
            "dates": [item.calculated_at.isoformat() for item in snapshots],
            "counts": [
                (item.raw_statistics or {}).get("independent_report_count_7d", 0)
                for item in snapshots
            ],
            "heat": [item.final_heat for item in snapshots],
            "key_points": [],
        },
        sentiment=sentiment,
        platform={
            "platforms": [
                {
                    "name": platform,
                    "count": count,
                    "percentage": count / total_articles if total_articles else 0,
                }
                for platform, count in sorted(platform_counts.items())
            ]
        },
        keywords={"keywords": []},
        articles={
            "articles": [
                {
                    "id": article.id,
                    "platform": article.platform,
                    "title": article.title,
                    "clean_content": article.clean_content,
                    "sentiment_label": article.sentiment_label,
                    "publish_time": article.publish_time.isoformat()
                    if article.publish_time
                    else None,
                }
                for article in articles
            ],
            "total": len(articles),
        },
    )
    return data


def search_events(keyword: str) -> list[dict]:
    semantic = search_historical_events(keyword, limit=20)
    if not semantic:
        return list_events({"keyword": keyword, "page": 1, "size": 20})["events"]
    output = []
    for item in semantic:
        event = db.session.get(Event, item["event_id"])
        if event is None:
            continue
        value = _event_item(event)
        value["similarity"] = item["similarity"]
        value["match_reasons"] = item["match_reasons"]
        output.append(value)
    return output
