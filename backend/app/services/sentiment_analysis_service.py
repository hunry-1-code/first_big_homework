from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from threading import RLock

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.analysis.sentiment_aggregator import (
    SentimentAggregateItem,
    article_sentiment_weight,
    build_daily_sentiment,
    build_platform_sentiment,
    summarize_sentiment,
)
from app.analysis.sentiment_analyzer import (
    SentimentAnalysisError,
    analyze_sentiment,
    analyze_with_snownlp,
)
from app.analysis.sentiment_config import SentimentConfig
from app.extensions import db
from app.llm.client import LLMClient
from app.models import (
    AggregationAssignment,
    AggregationCluster,
    AggregationRun,
    Article,
    ArticleSentimentResult,
    Event,
    EventArticleMembership,
    EventSentimentSnapshot,
    SentimentRun,
)
from app.services.task_service import StaleTaskLeaseError, assert_task_lease


_CREATION_LOCK = RLock()
_EXECUTION_LOCK = RLock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _content_identity(article: Article) -> str:
    if article.latest_snapshot_id:
        return f"snapshot:{article.latest_snapshot_id}:v{article.content_version or 1}"
    return f"article:{article.id}:v{article.content_version or 1}"


def _config_from_app() -> SentimentConfig:
    return SentimentConfig(
        text_limit=current_app.config.get("SENTIMENT_TEXT_LIMIT", 500),
        neutral_score_min=current_app.config.get("SENTIMENT_NEUTRAL_SCORE_MIN", -0.20),
        neutral_score_max=current_app.config.get("SENTIMENT_NEUTRAL_SCORE_MAX", 0.20),
        llm_max_concurrency=current_app.config.get("SENTIMENT_LLM_MAX_CONCURRENCY", 3),
        llm_retry_count=current_app.config.get("SENTIMENT_LLM_RETRY_COUNT", 3),
        minimum_success_ratio=current_app.config.get("SENTIMENT_MIN_SUCCESS_RATIO", 0.80),
        platform_min_articles=current_app.config.get("SENTIMENT_PLATFORM_MIN_ARTICLES", 3),
        platform_min_representatives=current_app.config.get(
            "SENTIMENT_PLATFORM_MIN_REPRESENTATIVES", 2
        ),
        snownlp_positive_threshold=current_app.config.get(
            "SNOWNLP_POSITIVE_THRESHOLD", 0.60
        ),
        snownlp_negative_threshold=current_app.config.get(
            "SNOWNLP_NEGATIVE_THRESHOLD", 0.40
        ),
        snownlp_confidence_cap=current_app.config.get("SNOWNLP_CONFIDENCE_CAP", 0.75),
        algorithm_version=current_app.config.get(
            "SENTIMENT_ALGORITHM_VERSION", "sentiment-v1"
        ),
        prompt_version=current_app.config.get(
            "SENTIMENT_PROMPT_VERSION", "sentiment-prompt-v1"
        ),
        preprocess_version=current_app.config.get(
            "SENTIMENT_PREPROCESS_VERSION", "sentiment-text-v1"
        ),
    )


def _valid_article(article: Article) -> bool:
    return bool(
        article.clean_status == "success"
        and (str(article.title or "").strip() or str(article.clean_content or "").strip())
        and float(article.nlp_weight or 0) > 0
        and not bool(article.is_advertisement)
        and str(article.source_type or "") != "hotlist"
    )


def _load_targets(aggregation: AggregationRun) -> list[dict]:
    targets = []
    clusters = AggregationCluster.query.filter_by(
        aggregation_run_id=aggregation.id
    ).order_by(AggregationCluster.cluster_index).all()
    for cluster in clusters:
        rows = []
        if aggregation.scope == "global" and cluster.resolved_event_id is not None:
            memberships = EventArticleMembership.query.filter_by(
                event_id=cluster.resolved_event_id, is_active=True
            ).order_by(EventArticleMembership.article_id).all()
            for membership in memberships:
                article = db.session.get(Article, membership.article_id)
                if article is not None and _valid_article(article):
                    rows.append(
                        {
                            "article": article,
                            "is_representative": not bool(article.is_duplicate),
                            "frozen_identity": _content_identity(article),
                        }
                    )
        else:
            assignments = AggregationAssignment.query.filter_by(
                aggregation_cluster_id=cluster.id
            ).order_by(AggregationAssignment.article_id).all()
            for assignment in assignments:
                article = db.session.get(Article, assignment.article_id)
                if article is not None and _valid_article(article):
                    rows.append(
                        {
                            "article": article,
                            "is_representative": bool(assignment.is_representative),
                            "frozen_identity": assignment.content_identity,
                        }
                    )
        if rows:
            targets.append(
                {
                    "cluster": cluster,
                    "event": db.session.get(Event, cluster.resolved_event_id)
                    if cluster.resolved_event_id is not None
                    else None,
                    "rows": rows,
                }
            )
    return targets


def _dataset_hash(targets: list[dict]) -> str:
    payload = []
    for target in targets:
        for row in target["rows"]:
            payload.append(
                (
                    int(target["cluster"].id),
                    int(target["event"].id) if target["event"] else None,
                    int(row["article"].id),
                    str(row["frozen_identity"]),
                    bool(row["is_representative"]),
                )
            )
    encoded = json.dumps(sorted(payload), ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _versions(config: SentimentConfig) -> dict:
    return {
        "algorithm": config.algorithm_version,
        "llm_model": current_app.config.get("LLM_MODEL_NAME", "deepseek-chat"),
        "llm_model_version": current_app.config.get("LLM_MODEL_VERSION", "default"),
        "prompt_version": config.prompt_version,
        "preprocess_version": config.preprocess_version,
        "snownlp_version": "0.12.3",
    }


def create_sentiment_run(
    aggregation_run_id: int,
    *,
    source_task_id: int | None = None,
    user_id: int | None = None,
    config: SentimentConfig | None = None,
) -> tuple[SentimentRun, bool]:
    config = config or _config_from_app()
    aggregation = db.session.get(AggregationRun, int(aggregation_run_id))
    if aggregation is None:
        raise KeyError(f"aggregation run not found: {aggregation_run_id}")
    if aggregation.status != "success":
        raise ValueError("只有成功的事件聚合运行才能创建情感分析")
    targets = _load_targets(aggregation)
    if not targets:
        raise ValueError("NO_VALID_DOCUMENT")
    dataset_hash = _dataset_hash(targets)
    with _CREATION_LOCK:
        latest = (
            SentimentRun.query.filter_by(
                aggregation_run_id=aggregation.id,
                scope=aggregation.scope,
                mode=aggregation.mode,
                config_hash=config.config_hash(),
            )
            .order_by(SentimentRun.attempt.desc())
            .first()
        )
        if latest is not None and latest.status != "failed":
            return latest, True
        attempt = int(latest.attempt or 1) + 1 if latest else 1
        run = SentimentRun(
            aggregation_run_id=aggregation.id,
            source_task_id=source_task_id,
            user_id=user_id if user_id is not None else aggregation.user_id,
            scope=aggregation.scope,
            mode=aggregation.mode,
            attempt=attempt,
            dataset_hash=dataset_hash,
            config_hash=config.config_hash(),
            config=config.as_dict(),
            versions=_versions(config),
            statistics={},
            status="pending",
            warnings=[],
        )
        db.session.add(run)
        try:
            db.session.commit()
            return run, False
        except IntegrityError:
            db.session.rollback()
            winner = SentimentRun.query.filter_by(
                aggregation_run_id=aggregation.id,
                scope=aggregation.scope,
                mode=aggregation.mode,
                config_hash=config.config_hash(),
                attempt=attempt,
            ).first()
            if winner is None:
                raise
            return winner, True


def _default_client() -> LLMClient:
    return LLMClient(
        api_key=current_app.config.get("LLM_API_KEY", ""),
        base_url=current_app.config.get("LLM_BASE_URL", ""),
        model_name=current_app.config.get("LLM_MODEL_NAME", ""),
        timeout=current_app.config.get("LLM_REQUEST_TIMEOUT", 30),
    )


def _compatible_cached_result(article: Article, run: SentimentRun):
    versions = run.versions or {}
    return (
        ArticleSentimentResult.query.join(
            SentimentRun, ArticleSentimentResult.sentiment_run_id == SentimentRun.id
        )
        .filter(
            SentimentRun.status == "success",
            ArticleSentimentResult.article_id == article.id,
            ArticleSentimentResult.content_identity == _content_identity(article),
            ArticleSentimentResult.prompt_version == versions.get("prompt_version"),
            ArticleSentimentResult.preprocess_version == versions.get("preprocess_version"),
            ArticleSentimentResult.model_version == versions.get("llm_model_version"),
            ArticleSentimentResult.method.in_(["llm", "snownlp"]),
        )
        .order_by(ArticleSentimentResult.id.desc())
        .first()
    )


def _result_values(result: dict, run: SentimentRun) -> dict:
    versions = run.versions or {}
    return {
        "label": result["label"],
        "score": float(result["score"]),
        "confidence": float(result["confidence"]),
        "dimension": result["dimension"],
        "target": str(result["target"])[:200],
        "reason": str(result["reason"])[:500],
        "method": result["method"],
        "model_name": result.get("model_name"),
        "model_version": versions.get("llm_model_version"),
        "prompt_version": versions.get("prompt_version"),
        "preprocess_version": versions.get("preprocess_version"),
        "raw_response": result.get("raw_response"),
        "warnings": list(result.get("warnings") or []),
    }


def _serialize_snapshot(snapshot: EventSentimentSnapshot) -> dict:
    daily_trend = snapshot.daily_trend or []
    calculation_details = snapshot.calculation_details or {}
    sentiment_summary = calculation_details.get("summary")

    return {
        "snapshot_id": snapshot.id,
        "sentiment_run_id": snapshot.sentiment_run_id,
        "event_id": snapshot.event_id,
        "aggregation_cluster_id": snapshot.aggregation_cluster_id,
        "calculated_at": snapshot.calculated_at.isoformat()
        if snapshot.calculated_at
        else None,
        "article_count": snapshot.article_count,
        "representative_count": snapshot.representative_count,
        "raw_counts": snapshot.raw_counts or {},
        "weighted_ratios": snapshot.weighted_ratios or {},
        "summary": sentiment_summary,
        "positive": float((snapshot.weighted_ratios or {}).get("positive", 0)),
        "negative": float((snapshot.weighted_ratios or {}).get("negative", 0)),
        "neutral": float((snapshot.weighted_ratios or {}).get("neutral", 0)),
        "dominant_label": snapshot.dominant_label,
        "average_score": float(snapshot.average_score or 0),
        "daily_trend": daily_trend,
        "daily": daily_trend,
        "platform_distribution": snapshot.platform_distribution or [],
        "time_confidence": snapshot.time_confidence,
        "calculation_details": calculation_details,
        "algorithm_version": snapshot.algorithm_version,
        "warnings": snapshot.warnings or [],
    }


def run_sentiment_analysis(
    sentiment_run_id: int,
    *,
    task_id: int | None = None,
    config: SentimentConfig | None = None,
    llm_analyzer=None,
    fallback_analyzer=None,
    now: datetime | None = None,
) -> dict:
    config = config or _config_from_app()
    now = now or _utcnow()
    run = db.session.get(SentimentRun, int(sentiment_run_id))
    if run is None:
        raise KeyError(f"sentiment run not found: {sentiment_run_id}")
    if run.status == "success":
        return {"sentiment_run_id": run.id, "status": run.status, **(run.statistics or {})}
    run.status = "running"
    run.started_at = now
    db.session.commit()
    llm_analyzer = llm_analyzer or analyze_sentiment
    fallback_analyzer = fallback_analyzer or analyze_with_snownlp
    try:
        with _EXECUTION_LOCK:
            aggregation = db.session.get(AggregationRun, run.aggregation_run_id)
            if aggregation is None or aggregation.status != "success":
                raise ValueError("上游事件聚合运行不存在或未成功")
            targets = _load_targets(aggregation)
            if _dataset_hash(targets) != run.dataset_hash:
                raise ValueError("DATASET_CHANGED")
            for target in targets:
                for row in target["rows"]:
                    if _content_identity(row["article"]) != row["frozen_identity"]:
                        raise ValueError("DATASET_CHANGED")
            ArticleSentimentResult.query.filter_by(sentiment_run_id=run.id).delete()
            EventSentimentSnapshot.query.filter_by(sentiment_run_id=run.id).delete()
            db.session.flush()
            counters = Counter()
            run_warnings = set()
            created_by_article = {}
            target_by_article = {}
            for target in targets:
                for row in target["rows"]:
                    target_by_article[row["article"].id] = (target, row)
            client = None
            for article_id in sorted(target_by_article):
                target, row = target_by_article[article_id]
                article = row["article"]
                if not row["is_representative"]:
                    continue
                cached = _compatible_cached_result(article, run)
                if cached is not None:
                    values = {
                        "label": cached.label,
                        "score": cached.score,
                        "confidence": cached.confidence,
                        "dimension": cached.dimension,
                        "target": cached.target,
                        "reason": cached.reason,
                        "method": cached.method,
                        "model_name": cached.model_name,
                        "model_version": cached.model_version,
                        "prompt_version": cached.prompt_version,
                        "preprocess_version": cached.preprocess_version,
                        "raw_response": cached.raw_response,
                        "warnings": list(cached.warnings or []) + ["SENTIMENT_RESULT_REUSED"],
                    }
                    counters["reused_count"] += 1
                else:
                    context = {
                        "topic_category": target["cluster"].topic_category,
                        "topic_name": target["cluster"].topic_name,
                        "event_title": target["cluster"].title,
                        "article_title": article.title,
                    }
                    text = f"{article.title or ''}\n{article.clean_content or ''}"
                    llm_error = None
                    result = None
                    for _attempt in range(config.llm_retry_count + 1):
                        try:
                            if llm_analyzer is analyze_sentiment:
                                client = client or _default_client()
                                result = llm_analyzer(
                                    text, context=context, client=client, config=config
                                )
                            else:
                                result = llm_analyzer(text, context=context, config=config)
                            counters["llm_count"] += 1
                            llm_error = None
                            break
                        except Exception as exc:
                            llm_error = exc
                    if llm_error is not None:
                        exc = llm_error
                        run_warnings.add(type(exc).__name__.upper())
                        try:
                            result = fallback_analyzer(
                                text, context=context, config=config
                            )
                            counters["snownlp_count"] += 1
                        except Exception as fallback_exc:
                            counters["failed_count"] += 1
                            run_warnings.add(type(fallback_exc).__name__.upper())
                            continue
                    values = _result_values(result, run)
                result_row = ArticleSentimentResult(
                    sentiment_run_id=run.id,
                    article_id=article.id,
                    content_identity=_content_identity(article),
                    aggregation_cluster_id=target["cluster"].id,
                    event_id=target["event"].id if target["event"] else None,
                    **values,
                )
                db.session.add(result_row)
                db.session.flush()
                created_by_article[article.id] = result_row
            for article_id in sorted(target_by_article):
                target, row = target_by_article[article_id]
                article = row["article"]
                if row["is_representative"]:
                    continue
                source = created_by_article.get(article.duplicate_of_id)
                if source is None:
                    counters["skipped_count"] += 1
                    run_warnings.add("DUPLICATE_SENTIMENT_SOURCE_MISSING")
                    continue
                inherited = ArticleSentimentResult(
                    sentiment_run_id=run.id,
                    article_id=article.id,
                    content_identity=_content_identity(article),
                    aggregation_cluster_id=target["cluster"].id,
                    event_id=target["event"].id if target["event"] else None,
                    label=source.label,
                    score=source.score,
                    confidence=source.confidence,
                    dimension=source.dimension,
                    target=source.target,
                    reason=source.reason,
                    method="inherited",
                    model_name=source.model_name,
                    model_version=source.model_version,
                    prompt_version=source.prompt_version,
                    preprocess_version=source.preprocess_version,
                    raw_response=None,
                    inherited_from_result_id=source.id,
                    warnings=["DUPLICATE_SENTIMENT_INHERITED"],
                )
                db.session.add(inherited)
                db.session.flush()
                created_by_article[article.id] = inherited
                counters["inherited_count"] += 1
            analyzable = len(target_by_article)
            successful = len(created_by_article)
            if not analyzable or successful / analyzable < config.minimum_success_ratio:
                raise ValueError("SENTIMENT_SUCCESS_RATIO_TOO_LOW")
            summary_targets = []
            event_targets = {}
            for target in targets:
                event = target["event"]
                if event is None:
                    summary_targets.append(target)
                    continue
                existing = event_targets.get(event.id)
                if existing is None:
                    existing = {**target, "rows": list(target["rows"])}
                    event_targets[event.id] = existing
                    summary_targets.append(existing)
                else:
                    known_ids = {row["article"].id for row in existing["rows"]}
                    existing["rows"].extend(
                        row for row in target["rows"] if row["article"].id not in known_ids
                    )
            for target in summary_targets:
                items = []
                target_results = []
                max_heat = max(
                    (float(row["article"].heat_contribution or 0) for row in target["rows"]),
                    default=0.0,
                )
                for row in target["rows"]:
                    article = row["article"]
                    result_row = created_by_article.get(article.id)
                    if result_row is None:
                        continue
                    item = SentimentAggregateItem(
                        article_id=article.id,
                        label=result_row.label,
                        score=result_row.score,
                        platform=article.platform,
                        publish_time=article.publish_time,
                        observed_time=article.first_crawled_at,
                        is_representative=row["is_representative"],
                        nlp_weight=float(article.nlp_weight or 0),
                        spam_weight=float(article.spam_weight if article.spam_weight is not None else 1),
                        duplicate_weight=float(
                            article.duplicate_weight
                            if article.duplicate_weight is not None
                            else 1
                        ),
                        heat_contribution=article.heat_contribution,
                    )
                    result_row.weight_details = article_sentiment_weight(
                        item, event_max_heat=max_heat
                    )[1]
                    items.append(item)
                    target_results.append(result_row)
                    article.sentiment_label = result_row.label
                    article.sentiment_score = result_row.score
                    article.sentiment_reason = result_row.reason
                    article.sentiment_method = result_row.method
                    article.sentiment_confidence = result_row.confidence
                    article.sentiment_dimension = result_row.dimension
                    article.sentiment_target = result_row.target
                    article.sentiment_content_identity = result_row.content_identity
                    article.current_sentiment_result_id = result_row.id
                    article.sentiment_analyzed_at = now
                representative_reasons = [
                    result_row.reason
                    for result_row in target_results
                    if result_row.reason and result_row.method != "inherited"
                ][:3]
                summary = summarize_sentiment(
                    items,
                    config,
                    representative_reasons=representative_reasons,
                )
                daily = build_daily_sentiment(items, config)
                platforms = build_platform_sentiment(items, config)
                reliable = sum(item.publish_time is not None for item in items)
                ratio = reliable / len(items) if items else 0
                time_confidence = "high" if ratio >= 0.8 else ("medium" if ratio >= 0.5 else "low")
                warnings = sorted(
                    set(
                        warning
                        for result_row in target_results
                        for warning in (result_row.warnings or [])
                    )
                    | {warning for row in daily for warning in row.get("warnings", [])}
                    | {warning for row in platforms for warning in row.get("warnings", [])}
                )
                snapshot = EventSentimentSnapshot(
                    sentiment_run_id=run.id,
                    event_id=target["event"].id if target["event"] else None,
                    aggregation_cluster_id=target["cluster"].id,
                    calculated_at=now,
                    article_count=summary["article_count"],
                    representative_count=summary["representative_count"],
                    raw_counts=summary["raw_counts"],
                    weighted_ratios=summary["weighted_ratios"],
                    dominant_label=summary["dominant_label"],
                    average_score=summary["average_score"],
                    daily_trend=daily,
                    platform_distribution=platforms,
                    time_confidence=time_confidence,
                    calculation_details={
                        "effective_weight": summary["effective_weight"],
                        "config_hash": run.config_hash,
                        "summary": summary["summary"],
                        "representative_reasons": representative_reasons,
                    },
                    algorithm_version=config.algorithm_version,
                    warnings=warnings,
                )
                db.session.add(snapshot)
                db.session.flush()
                if run.scope == "global" and target["event"] is not None:
                    event = target["event"]
                    event.sentiment_positive = summary["weighted_ratios"]["positive"]
                    event.sentiment_negative = summary["weighted_ratios"]["negative"]
                    event.sentiment_neutral = summary["weighted_ratios"]["neutral"]
                    event.sentiment_score = summary["average_score"]
                    event.current_sentiment_snapshot_id = snapshot.id
                    event.sentiment_updated_at = now
            counters["input_count"] = analyzable
            counters["result_count"] = successful
            counters["snapshot_count"] = len(summary_targets)
            run.statistics = dict(counters)
            run.warnings = sorted(run_warnings)
            run.status = "success"
            run.completed_at = now
            assert_task_lease(task_id)
            db.session.commit()
            return {"sentiment_run_id": run.id, "status": "success", **run.statistics}
    except StaleTaskLeaseError:
        db.session.rollback()
        raise
    except Exception as exc:
        db.session.rollback()
        failed = db.session.get(SentimentRun, run.id)
        failed.status = "failed"
        failed.error_code = str(exc) if str(exc).isupper() else type(exc).__name__.upper()
        failed.error_message = str(exc)
        failed.completed_at = now
        db.session.commit()
        raise


def get_sentiment_run(
    run_id: int, *, user_id: int | None = None, admin: bool = True
) -> dict | None:
    run = db.session.get(SentimentRun, int(run_id))
    if run is None:
        return None
    if not admin and run.scope != "search_shared" and run.user_id != user_id:
        return None
    return {
        "sentiment_run_id": run.id,
        "aggregation_run_id": run.aggregation_run_id,
        "scope": run.scope,
        "mode": run.mode,
        "status": run.status,
        "statistics": run.statistics or {},
        "warnings": run.warnings or [],
        "versions": run.versions or {},
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def list_sentiment_runs(*, user_id: int | None = None, admin: bool = False) -> list[dict]:
    query = SentimentRun.query
    if not admin:
        query = query.filter((SentimentRun.scope == "search_shared") | (SentimentRun.user_id == user_id))
    return [
        get_sentiment_run(item.id)
        for item in query.order_by(SentimentRun.id.desc()).limit(100).all()
    ]


def list_sentiment_results(run_id: int, *, page: int = 1, size: int = 50) -> dict:
    page = max(1, int(page))
    size = max(1, min(200, int(size)))
    query = ArticleSentimentResult.query.filter_by(sentiment_run_id=int(run_id))
    total = query.count()
    rows = query.order_by(ArticleSentimentResult.id).offset((page - 1) * size).limit(size).all()
    return {
        "results": [
            {
                "article_id": item.article_id,
                "event_id": item.event_id,
                "aggregation_cluster_id": item.aggregation_cluster_id,
                "label": item.label,
                "score": item.score,
                "confidence": item.confidence,
                "dimension": item.dimension,
                "target": item.target,
                "reason": item.reason,
                "method": item.method,
                "warnings": item.warnings or [],
            }
            for item in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


def get_event_sentiment(event_id: int) -> dict | None:
    event = db.session.get(Event, int(event_id))
    if event is None:
        return None
    snapshot = (
        db.session.get(EventSentimentSnapshot, event.current_sentiment_snapshot_id)
        if event.current_sentiment_snapshot_id
        else EventSentimentSnapshot.query.filter_by(event_id=event.id)
        .order_by(EventSentimentSnapshot.calculated_at.desc(), EventSentimentSnapshot.id.desc())
        .first()
    )
    if snapshot is None:
        return {
            "event_id": event.id,
            "positive": float(event.sentiment_positive or 0),
            "negative": float(event.sentiment_negative or 0),
            "neutral": float(event.sentiment_neutral or 0),
            "raw_counts": {},
            "weighted_ratios": {
                "positive": float(event.sentiment_positive or 0),
                "negative": float(event.sentiment_negative or 0),
                "neutral": float(event.sentiment_neutral or 0),
            },
            "daily_trend": [],
            "daily": [],
            "platform_distribution": [],
            "warnings": ["SENTIMENT_SNAPSHOT_UNAVAILABLE"],
        }
    return _serialize_snapshot(snapshot)


def get_cluster_sentiment(cluster_id: int) -> dict | None:
    snapshot = (
        EventSentimentSnapshot.query.filter_by(aggregation_cluster_id=int(cluster_id))
        .order_by(EventSentimentSnapshot.calculated_at.desc(), EventSentimentSnapshot.id.desc())
        .first()
    )
    return _serialize_snapshot(snapshot) if snapshot else None


__all__ = [
    "create_sentiment_run",
    "get_cluster_sentiment",
    "get_event_sentiment",
    "get_sentiment_run",
    "list_sentiment_results",
    "list_sentiment_runs",
    "run_sentiment_analysis",
]
