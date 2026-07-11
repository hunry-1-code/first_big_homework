from __future__ import annotations

import unicodedata
from datetime import datetime

from flask import current_app

from app.analysis.event_similarity import cosine_similarity, entity_similarity, set_similarity
from app.extensions import db
from app.models import Event, EventMergeRecord, EventRepresentation


def _normalized(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def _compatible_representation(event_id: int):
    return EventRepresentation.query.filter_by(
        event_id=event_id,
        model_name=current_app.config.get("BGE_MODEL", "BAAI/bge-small-zh-v1.5"),
        model_version=current_app.config.get("BGE_MODEL_VERSION", "default"),
        preprocess_version=current_app.config.get("BGE_PREPROCESS_VERSION", "v1"),
    ).first()


def _related_score(source_event, source_representation, candidate, representation):
    signals = {
        "bge": cosine_similarity(source_representation.vector, representation.vector),
        "keyword": set_similarity(
            source_representation.keywords or [], representation.keywords or []
        ),
        "entity": entity_similarity(
            source_representation.entities or {}, representation.entities or {}
        ),
        "topic": (
            1.0
            if source_event.topic_category
            and source_event.topic_category == candidate.topic_category
            else 0.0
        ),
    }
    weights = {"bge": 0.65, "keyword": 0.15, "entity": 0.15, "topic": 0.05}
    available = {key: value for key, value in signals.items() if value is not None}
    total = sum(weights[key] for key in available)
    score = sum(available[key] * weights[key] / total for key in available) if total else 0.0
    reasons = []
    if available.get("bge", 0) >= 0.70:
        reasons.append("BGE语义相似")
    if available.get("keyword", 0) > 0:
        reasons.append("关键词相似")
    if available.get("entity", 0) > 0:
        reasons.append("实体证据相似")
    if available.get("topic", 0) > 0:
        reasons.append("主题分类一致")
    return round(score, 6), signals, reasons


def find_similar_events(
    event_id: int,
    *,
    limit: int | None = None,
    before: datetime | None = None,
    after: datetime | None = None,
) -> list[dict]:
    source = db.session.get(Event, int(event_id))
    if source is None:
        raise KeyError(f"event not found: {event_id}")
    source_representation = _compatible_representation(source.id)
    if source_representation is None:
        return []
    merged_alias_ids = {
        item.source_event_id
        for item in EventMergeRecord.query.filter_by(status="confirmed").all()
    }
    query = Event.query.filter(Event.id != source.id)
    if before is not None:
        query = query.filter(Event.first_publish_time < before)
    if after is not None:
        query = query.filter(Event.first_publish_time >= after)
    rows = []
    for candidate in query.all():
        if candidate.id in merged_alias_ids:
            continue
        representation = _compatible_representation(candidate.id)
        if representation is None:
            continue
        score, signals, reasons = _related_score(
            source, source_representation, candidate, representation
        )
        rows.append(
            {
                "event_id": candidate.id,
                "title": candidate.title,
                "topic_category": candidate.topic_category,
                "first_publish_time": candidate.first_publish_time.isoformat()
                if candidate.first_publish_time
                else None,
                "similarity": score,
                "match_reasons": reasons,
                "score_details": signals,
                "representation_version": {
                    "model_name": representation.model_name,
                    "model_version": representation.model_version,
                    "preprocess_version": representation.preprocess_version,
                },
            }
        )
    effective_limit = limit or current_app.config.get("EVENT_RELATED_LIMIT", 5)
    return sorted(rows, key=lambda item: (-item["similarity"], item["event_id"]))[
        : max(1, min(20, int(effective_limit)))
    ]


def _query_match_score(keyword: str, event: Event, representation) -> tuple[float, list[str]]:
    query = _normalized(keyword)
    if not query:
        return 0.0, []
    reasons = []
    score = 0.0
    if query in _normalized(event.title) or query in _normalized(event.topic_name or ""):
        score += 1.0
        reasons.append("标题或主题名称匹配")
    matched_terms = [
        term
        for term in (representation.keywords or [] if representation else [])
        if _normalized(term) and _normalized(term) in query
    ]
    if matched_terms:
        score += min(1.0, len(matched_terms) / 2)
        reasons.append("关键词匹配")
    if event.summary and query in _normalized(event.summary):
        score += 0.5
        reasons.append("事件概述匹配")
    return score, reasons


def search_historical_events(keyword: str, *, limit: int = 20) -> list[dict]:
    merged_alias_ids = {
        item.source_event_id
        for item in EventMergeRecord.query.filter_by(status="confirmed").all()
    }
    rows = []
    for event in Event.query.all():
        if event.id in merged_alias_ids:
            continue
        representation = _compatible_representation(event.id)
        score, reasons = _query_match_score(keyword, event, representation)
        if score <= 0:
            continue
        rows.append(
            {
                "event_id": event.id,
                "title": event.title,
                "topic_category": event.topic_category,
                "topic_name": event.topic_name,
                "first_publish_time": event.first_publish_time.isoformat()
                if event.first_publish_time
                else None,
                "similarity": round(score, 6),
                "match_reasons": reasons,
            }
        )
    return sorted(rows, key=lambda item: (-item["similarity"], item["event_id"]))[
        : max(1, min(100, int(limit)))
    ]


__all__ = ["find_similar_events", "search_historical_events"]
