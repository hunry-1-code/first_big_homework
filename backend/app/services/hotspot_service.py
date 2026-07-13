from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from threading import RLock

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.analysis.feature_config import FeatureConfig
from app.analysis.feature_matrix import build_feature_matrices
from app.analysis.heat_calculator import (
    EventHeatResult,
    HeatArticle,
    EventHeatInput,
    calculate_event_heats,
    calculate_single_event_heat,
)
from app.analysis.hotspot_config import HotspotConfig
from app.analysis.result import AnalysisDocument, ContentAnalysisError, DatasetChangedError
from app.analysis.topic_classifier import classify_topic
from app.analysis.topic_model import discover_topics
from app.extensions import db
from app.llm.client import LLMClient
from app.models import (
    AnalysisRun,
    AnalysisRunArticle,
    Article,
    ArticleSnapshot,
    DailyHotItem,
    DocumentFeatures,
    Event,
    EventHeatSnapshot,
    HotSeedExpansion,
    HotspotRun,
    TopicArticleAssignment,
    TopicResult,
)
from app.preprocessing.segmenter import segment_document
from app.services.lifecycle_service import (
    daily_counts_from_articles,
    update_event_lifecycle,
)
from app.services.task_service import StaleTaskLeaseError, assert_task_lease


_HOTSPOT_CREATION_LOCK = RLock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _content_identity(article: Article) -> str:
    if article.latest_snapshot_id:
        return f"snapshot:{article.latest_snapshot_id}:v{article.content_version or 1}"
    return f"article:{article.id}:v{article.content_version or 1}"


def _config_from_app() -> HotspotConfig:
    return HotspotConfig(
        window_days=current_app.config.get("HOTSPOT_WINDOW_DAYS", 7),
        max_topics=current_app.config.get("LDA_MAX_TOPICS", 12),
        top_words=current_app.config.get("LDA_TOP_WORDS", 20),
        random_state=current_app.config.get("LDA_RANDOM_STATE", 42),
        lda_max_iter=current_app.config.get("LDA_MAX_ITER", 100),
        topic_diversity_min=current_app.config.get("LDA_TOPIC_DIVERSITY_MIN", 0.70),
        small_topic_ratio_max=current_app.config.get("LDA_SMALL_TOPIC_RATIO_MAX", 0.20),
        low_confidence_threshold=current_app.config.get(
            "LDA_LOW_CONFIDENCE_THRESHOLD", 0.45
        ),
        minimum_reports=current_app.config.get("HOTSPOT_MIN_REPORTS", 3),
        minimum_platforms=current_app.config.get("HOTSPOT_MIN_PLATFORMS", 2),
        recent_activity_hours=current_app.config.get(
            "HOTSPOT_RECENT_ACTIVITY_HOURS", 24
        ),
        half_life_hours=current_app.config.get("HEAT_HALF_LIFE_HOURS", 24),
        core_weight=current_app.config.get("HEAT_CORE_WEIGHT", 0.70),
        spread_weight=current_app.config.get("HEAT_SPREAD_WEIGHT", 0.30),
        ranking_limit=current_app.config.get("HOTSPOT_TOP_LIMIT", 20),
        formula_version=current_app.config.get("HEAT_FORMULA_VERSION", "v1"),
    )


def _feature_config(run: AnalysisRun) -> FeatureConfig:
    values = {
        key: tuple(value) if key == "ngram_range" else value
        for key, value in (run.tfidf_config or {}).items()
    }
    return FeatureConfig(**values) if values else FeatureConfig()


def _default_client():
    return LLMClient(
        current_app.config.get("LLM_API_KEY", ""),
        current_app.config.get("LLM_BASE_URL", "https://api.deepseek.com"),
        current_app.config.get("LLM_MODEL_NAME", "deepseek-chat"),
        timeout=current_app.config.get("LLM_REQUEST_TIMEOUT", 30),
    )


def create_hotspot_run(
    analysis_run_id: int,
    *,
    user_id: int | None = None,
    source_task_id: int | None = None,
    config: HotspotConfig | None = None,
) -> tuple[HotspotRun, bool]:
    config = config or _config_from_app()
    analysis_run = db.session.get(AnalysisRun, int(analysis_run_id))
    if analysis_run is None:
        raise KeyError(f"analysis run not found: {analysis_run_id}")
    if analysis_run.status != "success":
        raise ValueError("只有成功的内容分析运行才能创建热点分析")
    mode = analysis_run.mode or "manual"
    scope = "global" if mode == "hot" else ("manual" if mode == "manual" else "user")
    with _HOTSPOT_CREATION_LOCK:
        latest = (
            HotspotRun.query.filter_by(
                analysis_run_id=analysis_run.id,
                config_hash=config.config_hash(),
                scope=scope,
                mode=mode,
            )
            .order_by(HotspotRun.attempt.desc())
            .first()
        )
        if latest is not None and latest.status != "failed":
            return latest, True
        attempt = int(latest.attempt or 1) + 1 if latest is not None else 1
        window_end = analysis_run.completed_at or _utcnow()
        run = HotspotRun(
            analysis_run_id=analysis_run.id,
            source_task_id=source_task_id,
            user_id=user_id if user_id is not None else analysis_run.user_id,
            mode=mode,
            scope=scope,
            attempt=attempt,
            window_start=window_end - timedelta(days=config.window_days),
            window_end=window_end,
            dataset_hash=analysis_run.dataset_hash,
            config_hash=config.config_hash(),
            lda_config=config.as_dict(),
            metrics={},
            versions={
                "algorithm": config.algorithm_version,
                "heat_formula": config.formula_version,
                "llm_model": current_app.config.get("LLM_MODEL_NAME", "deepseek-chat"),
            },
            status="pending",
            topic_status="pending",
            heat_status="pending",
            warnings=[],
        )
        db.session.add(run)
        try:
            db.session.commit()
            return run, False
        except IntegrityError:
            db.session.rollback()
            winner = HotspotRun.query.filter_by(
                analysis_run_id=analysis_run.id,
                config_hash=config.config_hash(),
                scope=scope,
                mode=mode,
                attempt=attempt,
            ).first()
            if winner is None:
                raise
            return winner, True


def _load_documents(run: HotspotRun):
    analysis_run = db.session.get(AnalysisRun, run.analysis_run_id)
    rows = AnalysisRunArticle.query.filter_by(
        analysis_run_id=analysis_run.id
    ).order_by(AnalysisRunArticle.id).all()
    representative_rows = [row for row in rows if row.is_representative]
    articles = {
        article.id: article
        for article in Article.query.filter(
            Article.id.in_([row.article_id for row in rows])
        ).all()
    }
    for row in rows:
        article = articles.get(row.article_id)
        if article is None or _content_identity(article) != row.content_identity:
            raise DatasetChangedError(f"文章 {row.article_id} 的内容版本已变化")
    if run.window_start is not None or run.window_end is not None:
        rows = [
            row
            for row in rows
            if (
                (articles[row.article_id].publish_time or articles[row.article_id].first_crawled_at)
                and (
                    run.window_start is None
                    or (articles[row.article_id].publish_time or articles[row.article_id].first_crawled_at)
                    >= run.window_start
                )
                and (
                    run.window_end is None
                    or (articles[row.article_id].publish_time or articles[row.article_id].first_crawled_at)
                    <= run.window_end
                )
            )
        ]
        representative_rows = [row for row in rows if row.is_representative]
    features = {
        item.article_id: item
        for item in DocumentFeatures.query.filter(
            DocumentFeatures.article_id.in_(
                [row.article_id for row in representative_rows]
            )
        ).all()
    }
    documents = []
    for row in representative_rows:
        article = articles[row.article_id]
        feature = features[row.article_id]
        title = segment_document(article.title or "")
        documents.append(
            AnalysisDocument(
                article_id=article.id,
                snapshot_id=row.article_snapshot_id,
                content_version=row.content_version,
                title=article.title or "",
                title_tokens=title.data.get("tfidf_tokens") or [],
                body_tokens=feature.tfidf_tokens or [],
                platform=article.platform,
                entities={str(item): "entity" for item in (feature.mentions or [])},
                topics=feature.topics or [],
                nlp_weight=float(row.nlp_weight or 0),
                warnings=list(title.warnings),
            )
        )
    return analysis_run, rows, representative_rows, articles, documents


def _topic_signature(keywords: list[dict]) -> str:
    payload = json.dumps(
        [item.get("term") for item in keywords],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _persist_topics(run, discovery, documents, representative_rows, client):
    TopicArticleAssignment.query.filter_by(hotspot_run_id=run.id).delete()
    TopicResult.query.filter_by(hotspot_run_id=run.id).delete()
    db.session.flush()
    assignments_by_topic = defaultdict(list)
    for assignment in discovery.assignments:
        assignments_by_topic[assignment.topic_index].append(assignment)
    titles = {document.article_id: document.title for document in documents}
    topic_rows = {}
    warnings = list(discovery.warnings)
    for topic in discovery.topics:
        representative_titles = [
            titles[item.article_id]
            for item in sorted(
                assignments_by_topic[topic.topic_index],
                key=lambda item: -item.probability,
            )[:5]
        ]
        naming = classify_topic(
            [item["term"] for item in topic.keywords],
            representative_titles,
            client=client,
        )
        warnings.extend(naming.get("warnings") or [])
        topic_row = TopicResult(
            hotspot_run_id=run.id,
            topic_index=topic.topic_index,
            keywords=topic.keywords,
            category=naming["category"],
            topic_name=naming["topic_name"],
            naming_method=naming["method"],
            naming_confidence=naming["confidence"],
            document_count=topic.document_count,
            probability_mass=topic.probability_mass,
            topic_signature=_topic_signature(topic.keywords),
            warnings=naming.get("warnings") or [],
        )
        db.session.add(topic_row)
        db.session.flush()
        topic_rows[topic.topic_index] = topic_row
    rows_by_article = {row.article_id: row for row in representative_rows}
    for assignment in discovery.assignments:
        row = rows_by_article[assignment.article_id]
        db.session.add(
            TopicArticleAssignment(
                hotspot_run_id=run.id,
                topic_result_id=topic_rows[assignment.topic_index].id,
                article_id=assignment.article_id,
                content_identity=row.content_identity,
                probability=assignment.probability,
                probabilities=assignment.probabilities,
                is_primary=True,
                warnings=assignment.warnings,
            )
        )
    return topic_rows, list(dict.fromkeys(warnings))


def _heat_article(
    article: Article,
    snapshot: ArticleSnapshot | None,
    *,
    is_representative: bool,
) -> HeatArticle:
    return HeatArticle(
        article_id=article.id,
        platform=article.platform,
        publish_time=article.publish_time,
        observed_at=article.first_crawled_at,
        is_representative=is_representative,
        comments_count=(snapshot.comments_count if snapshot else None)
        if (snapshot and snapshot.comments_count is not None)
        else article.comments_count,
        reposts_count=(snapshot.reposts_count if snapshot else None)
        if (snapshot and snapshot.reposts_count is not None)
        else article.reposts_count,
        likes_count=(snapshot.likes_count if snapshot else None)
        if (snapshot and snapshot.likes_count is not None)
        else article.likes_count,
        views_count=(snapshot.views_count if snapshot else None)
        if (snapshot and snapshot.views_count is not None)
        else article.views_count,
        duplicate_weight=float(
            1.0 if article.duplicate_weight is None else article.duplicate_weight
        ),
        spam_weight=float(1.0 if article.spam_weight is None else article.spam_weight),
    )


def persist_event_heat_snapshot(
    event_id: int,
    *,
    calculated_at: datetime,
    aggregation_run_id: int,
    config: HotspotConfig | None = None,
) -> EventHeatSnapshot:
    """Create or reuse a real heat snapshot for an aggregation-published event."""
    config = config or _config_from_app()
    event = db.session.get(Event, int(event_id))
    if event is None:
        raise KeyError(f"event not found: {event_id}")

    existing = next(
        (
            snapshot
            for snapshot in EventHeatSnapshot.query.filter_by(
                event_id=event.id,
                hotspot_run_id=None,
            ).all()
            if (snapshot.calculation_details or {}).get("aggregation_run_id")
            == int(aggregation_run_id)
        ),
        None,
    )
    if existing is not None:
        event.current_heat_snapshot_id = existing.id
        event.heat_index = existing.final_heat
        event.core_heat = existing.core_heat
        event.spread_heat = existing.spread_heat
        event.is_hot = bool(existing.eligible_as_hot)
        event.hot_rank = existing.rank
        event.time_confidence = existing.time_confidence
        event.independent_report_count = int(
            (existing.raw_statistics or {}).get("independent_report_count_7d", 0)
        )
        event.platform_count = int(
            (existing.raw_statistics or {}).get("platform_count", 0)
        )
        return existing

    articles = Article.query.filter_by(event_id=event.id).all()
    if not articles:
        raise ValueError("event has no articles for heat calculation")
    snapshot_ids = [article.latest_snapshot_id for article in articles if article.latest_snapshot_id]
    article_snapshots = {
        item.id: item
        for item in ArticleSnapshot.query.filter(ArticleSnapshot.id.in_(snapshot_ids)).all()
    }
    hotlist_ranks = []
    for article in articles:
        if article.source_type != "hotlist":
            continue
        raw_rank = (article.raw_json or {}).get("rank") or (article.raw_json or {}).get(
            "realpos"
        )
        try:
            rank = int(raw_rank)
        except (TypeError, ValueError):
            continue
        if rank > 0:
            hotlist_ranks.append(rank)
    # 统一热度算法：优先用热榜排名信号，其次用文章数据
    representative_articles = [
        article for article in articles if not bool(article.is_duplicate)
    ]
    total = len(representative_articles) or 1
    article_platform_count = len({a.platform for a in articles if a.platform}) or 1
    hours_ago = max(0, (calculated_at - (event.first_publish_time or calculated_at)).total_seconds() / 3600)

    # 查找关联的热榜条目（daily hot 事件有，搜索事件没有）
    hot_item = DailyHotItem.query.filter_by(event_id=event.id).first()
    source_ranks = (hot_item.source_ranks or {}) if hot_item else {}

    if source_ranks:
        # ── 热榜事件：排名为主要信号 ──
        best_rank = min(source_ranks.values())
        hot_platforms = len(source_ranks)
        # 排名分：rank 1→55, rank 3→48, rank 10→35, rank 20→18, rank 30→2
        rank_score = max(2, round((31 - min(30, best_rank)) / 30 * 55, 1))
        # 跨平台加成：3平台×1.4, 2平台×1.2, 1平台×1.0
        platform_mult = round(1.0 + (hot_platforms - 1) * 0.2, 1)
        # 文章证据附加分（最多+13，反映实际采集质量）
        article_bonus = min(13, total * 0.4)
        time_decay = max(0.5, 1.0 - hours_ago / (24 * 14))
        final_heat = round(max(10, rank_score * platform_mult + article_bonus) * time_decay, 1)
        warnings = []
    else:
        # ── 搜索事件：文章数据为主要信号 ──
        total = len(representative_articles) or 1
        time_decay = max(0.15, 1.0 - hours_ago / (24 * 7))
        raw_heat = min(100, total * 2.5 * (1 + article_platform_count * 0.3) * time_decay)
        total_engagement = sum(
            (a.comments_count or 0) + (a.reposts_count or 0) + (a.likes_count or 0)
            for a in articles
        )
        engagement_bonus = min(20, total_engagement / max(1, total) * 0.1)
        final_heat = round(min(100, raw_heat + engagement_bonus), 1)
        warnings = []

    result = EventHeatResult(
        event_id=event.id,
        raw_statistics={
            "independent_report_count_7d": total,
            "platform_count": article_platform_count,
            "hot_platform_count": len(source_ranks),
            "best_hot_rank": min(source_ranks.values()) if source_ranks else None,
        },
        component_scores={
            "rank_score": rank_score if source_ranks else None,
            "platform_bonus": platform_bonus if source_ranks else None,
            "article_factor": article_factor if source_ranks else None,
            "time_decay": round(time_decay, 4),
            "final_heat": final_heat,
        },
        core_heat=round(final_heat * 0.7, 1),
        spread_heat=round(final_heat * 0.3, 1),
        final_heat=final_heat,
        eligible_as_hot=final_heat >= 40,
        rank=None,
        latest_activity_time=event.last_activity_time,
        time_confidence="high" if source_ranks else ("medium" if total >= 3 else "low"),
        warnings=warnings,
    )
    snapshot = EventHeatSnapshot(
        hotspot_run_id=None,
        event_id=event.id,
        calculated_at=calculated_at,
        raw_statistics=result.raw_statistics,
        component_scores=result.component_scores,
        core_heat=result.core_heat,
        spread_heat=result.spread_heat,
        final_heat=result.final_heat,
        eligible_as_hot=result.eligible_as_hot,
        rank=result.rank,
        status_change=_status_change(
            result.event_id,
            result.eligible_as_hot,
            result.final_heat,
        ),
        time_confidence=result.time_confidence,
        formula_version=config.formula_version,
        calculation_details={
            "source": "aggregation_publish",
            "aggregation_run_id": int(aggregation_run_id),
            "core_weight": config.core_weight,
            "spread_weight": config.spread_weight,
            "warnings": result.warnings,
        },
    )
    db.session.add(snapshot)
    db.session.flush()
    event.current_heat_snapshot_id = snapshot.id
    event.heat_index = result.final_heat
    event.core_heat = result.core_heat
    event.spread_heat = result.spread_heat
    event.is_hot = result.rank is not None
    event.hot_rank = result.rank
    event.last_activity_time = result.latest_activity_time
    event.independent_report_count = result.raw_statistics[
        "independent_report_count_7d"
    ]
    event.platform_count = result.raw_statistics["platform_count"]
    event.time_confidence = result.time_confidence
    return snapshot


def _status_change(event_id: int, eligible: bool, final_heat: float) -> str:
    previous = (
        EventHeatSnapshot.query.filter_by(event_id=event_id)
        .order_by(EventHeatSnapshot.calculated_at.desc(), EventHeatSnapshot.id.desc())
        .first()
    )
    if previous is None:
        return "new_hot" if eligible else "stable"
    if not eligible and previous.eligible_as_hot:
        return "left_hot"
    if eligible and not previous.eligible_as_hot:
        return "reheated"
    if final_heat > previous.final_heat + 5:
        return "rising"
    if final_heat < previous.final_heat - 5:
        return "cooling"
    return "stable"


def _persist_heat(run, rows, articles, topic_rows, calculated_at, config):
    event_articles = defaultdict(list)
    for row in rows:
        article = articles[row.article_id]
        if article.event_id is not None:
            event_articles[article.event_id].append((row, article))
    if not event_articles:
        return [], ["EVENT_AGGREGATION_PENDING"]
    snapshot_ids = [
        article.latest_snapshot_id
        for values in event_articles.values()
        for _row, article in values
        if article.latest_snapshot_id
    ]
    snapshots = {
        item.id: item
        for item in ArticleSnapshot.query.filter(ArticleSnapshot.id.in_(snapshot_ids)).all()
    }
    expansion_rows = HotSeedExpansion.query.filter(
        HotSeedExpansion.article_id.in_(
            [article.id for values in event_articles.values() for _row, article in values]
        )
    ).all()
    expansion_ranks = defaultdict(list)
    for item in expansion_rows:
        if item.source_rank is not None:
            expansion_ranks[item.article_id].append(item.source_rank)
    inputs = []
    for event_id, values in event_articles.items():
        hotlist_ranks = [
            rank
            for _row, article in values
            for rank in expansion_ranks.get(article.id, [])
        ]
        for _row, article in values:
            if article.source_type != "hotlist":
                continue
            raw = article.raw_json or {}
            rank = raw.get("rank") or raw.get("realpos")
            if isinstance(rank, int):
                hotlist_ranks.append(rank)
        inputs.append(
            EventHeatInput(
                event_id=event_id,
                articles=[
                    _heat_article(
                        article,
                        snapshots.get(article.latest_snapshot_id),
                        is_representative=row.is_representative,
                    )
                    for row, article in values
                ],
                hotlist_ranks=hotlist_ranks,
            )
        )
    results = calculate_event_heats(
        inputs, calculated_at=calculated_at, config=config
    )
    assignments = TopicArticleAssignment.query.filter_by(hotspot_run_id=run.id).all()
    assignment_topic = {item.article_id: item.topic_result_id for item in assignments}
    topic_by_id = {item.id: item for item in topic_rows.values()}
    warnings = []
    processed_event_ids = set()
    for result in results:
        processed_event_ids.add(result.event_id)
        existing = EventHeatSnapshot.query.filter_by(
            hotspot_run_id=run.id, event_id=result.event_id
        ).first()
        if existing is None:
            snapshot = EventHeatSnapshot(
                hotspot_run_id=run.id,
                event_id=result.event_id,
                calculated_at=calculated_at,
                raw_statistics=result.raw_statistics,
                component_scores=result.component_scores,
                core_heat=result.core_heat,
                spread_heat=result.spread_heat,
                final_heat=result.final_heat,
                eligible_as_hot=result.eligible_as_hot,
                rank=result.rank,
                status_change=_status_change(
                    result.event_id, result.eligible_as_hot, result.final_heat
                ),
                time_confidence=result.time_confidence,
                formula_version=config.formula_version,
                calculation_details={
                    "core_weight": config.core_weight,
                    "spread_weight": config.spread_weight,
                    "warnings": result.warnings,
                },
            )
            db.session.add(snapshot)
            db.session.flush()
        else:
            snapshot = existing
        event = db.session.get(Event, result.event_id)
        if event is None:
            continue
        current_snapshot = (
            db.session.get(EventHeatSnapshot, event.current_heat_snapshot_id)
            if event.current_heat_snapshot_id
            else None
        )
        if (
            current_snapshot is not None
            and current_snapshot.calculated_at > snapshot.calculated_at
        ):
            warnings.extend(result.warnings)
            continue
        member_topic_ids = [
            assignment_topic.get(article.id)
            for _row, article in event_articles[result.event_id]
            if assignment_topic.get(article.id) is not None
        ]
        dominant_topic_id = Counter(member_topic_ids).most_common(1)[0][0] if member_topic_ids else None
        dominant = topic_by_id.get(dominant_topic_id)
        event.current_heat_snapshot_id = snapshot.id
        event.heat_index = result.final_heat
        event.core_heat = result.core_heat
        event.spread_heat = result.spread_heat
        event.is_hot = result.rank is not None
        event.hot_rank = result.rank
        event.topic_category = dominant.category if dominant else event.topic_category
        event.topic_name = dominant.topic_name if dominant else event.topic_name
        reliable_times = [
            article.publish_time
            for _row, article in event_articles[result.event_id]
            if article.publish_time
        ]
        event.first_publish_time = min(reliable_times, default=event.first_publish_time)
        event.last_activity_time = result.latest_activity_time
        event.independent_report_count = result.raw_statistics[
            "independent_report_count_7d"
        ]
        event.platform_count = result.raw_statistics["platform_count"]
        event.time_confidence = result.time_confidence
        update_event_lifecycle(
            event,
            daily_counts_from_articles(
                [article for _row, article in event_articles[result.event_id]]
            ),
            now=calculated_at,
        )
        warnings.extend(result.warnings)
    if run.scope == "global" and processed_event_ids:
        stale_events = Event.query.filter(
            Event.is_hot.is_(True), Event.id.notin_(processed_event_ids)
        ).all()
        for event in stale_events:
            current_snapshot = (
                db.session.get(EventHeatSnapshot, event.current_heat_snapshot_id)
                if event.current_heat_snapshot_id
                else None
            )
            if (
                current_snapshot is not None
                and current_snapshot.calculated_at > calculated_at
            ):
                continue
            left_snapshot = EventHeatSnapshot.query.filter_by(
                hotspot_run_id=run.id, event_id=event.id
            ).first()
            if left_snapshot is None:
                left_snapshot = EventHeatSnapshot(
                    hotspot_run_id=run.id,
                    event_id=event.id,
                    calculated_at=calculated_at,
                    raw_statistics={"absent_from_run": True},
                    component_scores={},
                    core_heat=0.0,
                    spread_heat=None,
                    final_heat=0.0,
                    eligible_as_hot=False,
                    rank=None,
                    status_change="left_hot",
                    time_confidence=event.time_confidence or "low",
                    formula_version=config.formula_version,
                    calculation_details={
                        "reason": "event_absent_from_newer_global_run",
                        "core_weight": config.core_weight,
                        "spread_weight": config.spread_weight,
                    },
                )
                db.session.add(left_snapshot)
                db.session.flush()
            event.current_heat_snapshot_id = left_snapshot.id
            event.heat_index = 0.0
            event.core_heat = 0.0
            event.spread_heat = None
            event.is_hot = False
            event.hot_rank = None
    return results, list(dict.fromkeys(warnings))


def run_hotspot_analysis(
    hotspot_run_id: int,
    *,
    config: HotspotConfig | None = None,
    client=None,
    task_id: int | None = None,
    calculated_at: datetime | None = None,
) -> dict:
    discover_hotspot_topics(
        hotspot_run_id,
        config=config,
        client=client,
        task_id=task_id,
    )
    return finalize_hotspot_heat(
        hotspot_run_id,
        config=config,
        task_id=task_id,
        calculated_at=calculated_at,
    )


def discover_hotspot_topics(
    hotspot_run_id: int,
    *,
    config: HotspotConfig | None = None,
    client=None,
    task_id: int | None = None,
) -> dict:
    assert_task_lease(task_id)
    config = config or _config_from_app()
    run = db.session.get(HotspotRun, int(hotspot_run_id))
    if run is None:
        raise KeyError(f"hotspot run not found: {hotspot_run_id}")
    try:
        run.status = "running"
        run.started_at = run.started_at or _utcnow()
        run.error_code = None
        run.error_message = None
        db.session.commit()
        analysis_run, rows, representative_rows, articles, documents = _load_documents(run)
        matrices = build_feature_matrices(documents, _feature_config(analysis_run))
        discovery = discover_topics(
            documents,
            feature_names=matrices.feature_names,
            count_matrix=matrices.count_matrix,
            config=config,
        )
        topic_rows, warnings = _persist_topics(
            run, discovery, documents, representative_rows, client or _default_client()
        )
        run.selected_k = discovery.selected_k
        run.metrics = {
            "method": discovery.method,
            "document_count": len(documents),
            "candidates": [item.as_dict() for item in discovery.candidates],
        }
        run.topic_status = "success"
        run.heat_status = "pending"
        run.warnings = list(dict.fromkeys(warnings))
        assert_task_lease(task_id)
        db.session.commit()
        return {
            "hotspot_run_id": run.id,
            "status": run.status,
            "topic_status": run.topic_status,
            "heat_status": run.heat_status,
            "selected_k": run.selected_k,
            "topic_count": len(topic_rows),
            "event_count": 0,
            "warnings": run.warnings or [],
        }
    except StaleTaskLeaseError:
        db.session.rollback()
        raise
    except ContentAnalysisError as exc:
        db.session.rollback()
        run = db.session.get(HotspotRun, int(hotspot_run_id))
        run.status = "failed"
        run.error_code = exc.error_code
        run.error_message = str(exc)
        run.completed_at = _utcnow()
        db.session.commit()
        raise
    except Exception as exc:
        db.session.rollback()
        run = db.session.get(HotspotRun, int(hotspot_run_id))
        run.status = "failed"
        run.error_code = "HOTSPOT_ANALYSIS_ERROR"
        run.error_message = str(exc)
        run.completed_at = _utcnow()
        db.session.commit()
        raise


def finalize_hotspot_heat(
    hotspot_run_id: int,
    *,
    aggregation_run_id: int | None = None,
    config: HotspotConfig | None = None,
    task_id: int | None = None,
    calculated_at: datetime | None = None,
) -> dict:
    assert_task_lease(task_id)
    config = config or _config_from_app()
    run = db.session.get(HotspotRun, int(hotspot_run_id))
    if run is None:
        raise KeyError(f"hotspot run not found: {hotspot_run_id}")
    if run.topic_status != "success":
        raise ValueError("热点主题发现尚未成功")
    if aggregation_run_id is not None:
        from app.models import AggregationRun

        aggregation_run = db.session.get(AggregationRun, int(aggregation_run_id))
        if (
            aggregation_run is None
            or aggregation_run.hotspot_run_id != run.id
            or aggregation_run.status != "success"
        ):
            raise ValueError("事件聚合运行不存在、未成功或不属于当前热点运行")
    try:
        _analysis_run, rows, _representatives, articles, _documents = _load_documents(run)
        topic_rows = {
            item.topic_index: item
            for item in TopicResult.query.filter_by(hotspot_run_id=run.id).all()
        }
        warnings = list(run.warnings or [])
        heat_results, heat_warnings = _persist_heat(
            run,
            rows,
            articles,
            topic_rows,
            calculated_at or run.window_end or _utcnow(),
            config,
        )
        warnings.extend(heat_warnings)
        run.heat_status = "success" if heat_results else "pending"
        run.status = "success"
        run.warnings = list(dict.fromkeys(warnings))
        run.completed_at = _utcnow()
        assert_task_lease(task_id)
        db.session.commit()
        return {
            "hotspot_run_id": run.id,
            "aggregation_run_id": aggregation_run_id,
            "status": run.status,
            "topic_status": run.topic_status,
            "heat_status": run.heat_status,
            "selected_k": run.selected_k,
            "topic_count": len(topic_rows),
            "event_count": len(heat_results),
            "warnings": run.warnings or [],
        }
    except StaleTaskLeaseError:
        db.session.rollback()
        raise
    except Exception as exc:
        db.session.rollback()
        failed = db.session.get(HotspotRun, int(hotspot_run_id))
        failed.status = "failed"
        failed.error_code = "HOTSPOT_HEAT_ERROR"
        failed.error_message = str(exc)
        failed.completed_at = _utcnow()
        db.session.commit()
        raise
def _serialize_run(run: HotspotRun, include_topics: bool = False) -> dict:
    data = {
        "id": run.id,
        "analysis_run_id": run.analysis_run_id,
        "user_id": run.user_id,
        "mode": run.mode,
        "scope": run.scope,
        "attempt": run.attempt,
        "window_start": run.window_start.isoformat() if run.window_start else None,
        "window_end": run.window_end.isoformat() if run.window_end else None,
        "selected_k": run.selected_k,
        "metrics": run.metrics or {},
        "status": run.status,
        "topic_status": run.topic_status,
        "heat_status": run.heat_status,
        "warnings": run.warnings or [],
        "error_code": run.error_code,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
    if include_topics:
        data["topics"] = [
            {
                "id": item.id,
                "topic_index": item.topic_index,
                "keywords": item.keywords or [],
                "category": item.category,
                "topic_name": item.topic_name,
                "naming_method": item.naming_method,
                "naming_confidence": item.naming_confidence,
                "document_count": item.document_count,
            }
            for item in TopicResult.query.filter_by(hotspot_run_id=run.id)
            .order_by(TopicResult.topic_index)
            .all()
        ]
    return data


def get_hotspot_run(
    hotspot_run_id: int, *, user_id: int | None = None, admin: bool = False
) -> dict | None:
    run = db.session.get(HotspotRun, int(hotspot_run_id))
    if run is None:
        return None
    if not admin and user_id is not None and run.scope != "global" and run.user_id != user_id:
        return None
    return _serialize_run(run, include_topics=True)


def list_hotspot_runs(
    *, user_id: int | None = None, admin: bool = False
) -> list[dict]:
    query = HotspotRun.query
    if not admin and user_id is not None:
        query = query.filter(
            db.or_(HotspotRun.scope == "global", HotspotRun.user_id == user_id)
        )
    return [_serialize_run(item) for item in query.order_by(HotspotRun.id.desc()).all()]


def get_current_hotspots(limit: int = 20) -> dict:
    events = (
        Event.query.filter(Event.is_hot.is_(True), Event.hot_rank.isnot(None))
        .order_by(Event.hot_rank, Event.id)
        .limit(max(1, min(int(limit), 100)))
        .all()
    )
    snapshots = {
        item.id: item
        for item in EventHeatSnapshot.query.filter(
            EventHeatSnapshot.id.in_(
                [event.current_heat_snapshot_id for event in events if event.current_heat_snapshot_id]
            )
        ).all()
    }
    return {
        "events": [
            {
                "id": event.id,
                "title": event.title,
                "topic_category": event.topic_category,
                "topic_name": event.topic_name,
                "heat_index": event.heat_index,
                "core_heat": event.core_heat,
                "spread_heat": event.spread_heat,
                "hot_rank": event.hot_rank,
                "independent_report_count": event.independent_report_count,
                "platform_count": event.platform_count,
                "time_confidence": event.time_confidence,
                "calculated_at": snapshots[event.current_heat_snapshot_id].calculated_at.isoformat()
                if event.current_heat_snapshot_id in snapshots
                else None,
                "formula_version": snapshots[event.current_heat_snapshot_id].formula_version
                if event.current_heat_snapshot_id in snapshots
                else None,
                "warnings": (
                    snapshots[event.current_heat_snapshot_id].calculation_details or {}
                ).get("warnings", [])
                if event.current_heat_snapshot_id in snapshots
                else ["HEAT_SNAPSHOT_UNAVAILABLE"],
            }
            for event in events
        ],
        "total": len(events),
    }
