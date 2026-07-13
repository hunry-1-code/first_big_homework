from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from threading import RLock

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.analysis.aggregation_config import AggregationConfig
from app.analysis.event_clusterer import AggregationDocument, cluster_documents
from app.analysis.event_similarity import (
    cosine_similarity,
    entity_similarity,
    score_event_match,
    set_similarity,
)
from app.analysis.feature_config import FeatureConfig
from app.analysis.feature_matrix import build_feature_matrices
from app.analysis.result import AnalysisDocument, DatasetChangedError
from app.extensions import db
from app.models import (
    AggregationAssignment,
    AggregationCluster,
    AggregationRun,
    AnalysisRun,
    AnalysisRunArticle,
    Article,
    ArticleEmbedding,
    DocumentFeatures,
    Event,
    EventArticleMembership,
    EventMergeRecord,
    EventRepresentation,
    HotspotRun,
    Report,
    TopicArticleAssignment,
    TopicResult,
)
from app.preprocessing.segmenter import segment_document
from app.services.lifecycle_service import (
    daily_counts_from_articles,
    update_event_lifecycle,
)
from app.services.task_service import StaleTaskLeaseError, assert_task_lease


_CREATION_LOCK = RLock()
_GLOBAL_WRITE_LOCK = RLock()


def _postprocess_published_event(event_id: int, publish_run_id: int, user_id: int, now: datetime) -> dict:
    """Build formal-event derivatives after publication; safe to call repeatedly."""
    status = {"sentiment": "skipped", "heat": "skipped", "report": "skipped", "warnings": []}
    try:
        from app.services.sentiment_analysis_service import create_sentiment_run, run_sentiment_analysis

        sentiment_run, _ = create_sentiment_run(publish_run_id, user_id=user_id)
        if sentiment_run.status != "success":
            run_sentiment_analysis(sentiment_run.id, now=now)
        status["sentiment"] = "success"
    except Exception as exc:
        db.session.rollback()
        status["sentiment"] = "failed"
        status["warnings"].append(f"SENTIMENT_POSTPROCESS_FAILED:{type(exc).__name__}")

    publish_run = db.session.get(AggregationRun, int(publish_run_id))
    hotspot = (
        HotspotRun.query.filter_by(analysis_run_id=publish_run.analysis_run_id, topic_status="success")
        .order_by(HotspotRun.id.desc()).first()
        if publish_run else None
    )
    if hotspot is not None:
        try:
            from app.services.hotspot_service import finalize_hotspot_heat

            finalize_hotspot_heat(hotspot.id, calculated_at=now)
            hotspot.warnings = [w for w in (hotspot.warnings or []) if w != "EVENT_AGGREGATION_PENDING"]
            db.session.commit()
            status["heat"] = "success" if hotspot.heat_status == "success" else "pending"
        except Exception as exc:
            db.session.rollback()
            status["heat"] = "failed"
            status["warnings"].append(f"HEAT_POSTPROCESS_FAILED:{type(exc).__name__}")
    else:
        # 搜索/手动发布没有 HotspotRun 时，仍持久化版本化热度快照。
        try:
            from app.services.hotspot_service import persist_event_heat_snapshot

            persist_event_heat_snapshot(
                event_id,
                calculated_at=now,
                aggregation_run_id=publish_run_id,
            )
            db.session.commit()
            status["heat"] = "success"
        except Exception as exc:
            db.session.rollback()
            status["heat"] = "failed"
            status["warnings"].append(
                f"HEAT_SNAPSHOT_POSTPROCESS_FAILED:{type(exc).__name__}"
            )

    try:
        event = db.session.get(Event, int(event_id))
        article_count = Article.query.filter_by(event_id=event.id).count()
        platforms = Article.query.with_entities(Article.platform).filter_by(event_id=event.id).distinct().count()
        from app.services.event_service import _event_keywords

        event_keyword_payload = _event_keywords(event)
        ai_report = _ai_generate_report(
            event.title or '未命名事件',
            Article.query.filter_by(event_id=event.id).limit(10).all(),
            platforms,
            event_keywords=event_keyword_payload,
        )
        if ai_report:
            event.time_code = ai_report.get("time_code") or event.time_code
            event.location = ai_report.get("location") or event.location
            event.key_figures = ai_report.get("key_figures") or event.key_figures
            event.cause = ai_report.get("cause") or event.cause
            overview = ai_report.get("overview", "")
        else:
            overview = event.summary
        if not overview:
            overview = '事件「' + (event.title or '未命名事件') + '」已聚合 ' + str(article_count) + ' 篇报道，覆盖 ' + str(platforms) + ' 个平台。'
        report = Report.query.filter_by(event_id=event.id).order_by(Report.id.desc()).first()
        if report is None:
            report = Report(event_id=event.id)
            db.session.add(report)
        event.summary = overview
        report.overview_text = overview
        report.sentiment_data = {
            "positive": float(event.sentiment_positive or 0),
            "negative": float(event.sentiment_negative or 0),
            "neutral": float(event.sentiment_neutral or 0),
        }
        report.platform_data = {"platform_count": platforms}
        db.session.commit()
        status["report"] = "success"
    except Exception as exc:
        db.session.rollback()
        status["report"] = "failed"
        status["warnings"].append(f"REPORT_POSTPROCESS_FAILED:{type(exc).__name__}")
    return status


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _content_identity(article: Article) -> str:
    if article.latest_snapshot_id:
        return f"snapshot:{article.latest_snapshot_id}:v{article.content_version or 1}"
    return f"article:{article.id}:v{article.content_version or 1}"


def _config_from_app() -> AggregationConfig:
    return AggregationConfig(
        attach_threshold=current_app.config.get("EVENT_AGGREGATION_ATTACH_THRESHOLD", 0.72),
        create_threshold=current_app.config.get("EVENT_AGGREGATION_CREATE_THRESHOLD", 0.58),
        move_margin=current_app.config.get("EVENT_AGGREGATION_MOVE_MARGIN", 0.15),
        bge_weight=current_app.config.get("EVENT_AGGREGATION_BGE_WEIGHT", 0.45),
        tfidf_weight=current_app.config.get("EVENT_AGGREGATION_TFIDF_WEIGHT", 0.25),
        entity_weight=current_app.config.get("EVENT_AGGREGATION_ENTITY_WEIGHT", 0.20),
        time_weight=current_app.config.get("EVENT_AGGREGATION_TIME_WEIGHT", 0.10),
        candidate_limit=current_app.config.get("EVENT_AGGREGATION_CANDIDATE_LIMIT", 20),
        minimum_evidence_count=current_app.config.get("EVENT_AGGREGATION_MIN_EVIDENCE", 1),
        search_cache_hours=current_app.config.get("EVENT_SEARCH_CACHE_HOURS", 24),
        related_event_limit=current_app.config.get("EVENT_RELATED_LIMIT", 5),
        algorithm_version=current_app.config.get(
            "EVENT_AGGREGATION_ALGORITHM_VERSION", "event-aggregation-v1"
        ),
    )


def _feature_config(run: AnalysisRun) -> FeatureConfig:
    values = {
        key: tuple(value) if key == "ngram_range" else value
        for key, value in (run.tfidf_config or {}).items()
    }
    return FeatureConfig(**values) if values else FeatureConfig()


def create_aggregation_run(
    analysis_run_id: int,
    *,
    hotspot_run_id: int | None = None,
    scope: str | None = None,
    mode: str | None = None,
    user_id: int | None = None,
    source_task_id: int | None = None,
    config: AggregationConfig | None = None,
) -> tuple[AggregationRun, bool]:
    config = config or _config_from_app()
    analysis = db.session.get(AnalysisRun, int(analysis_run_id))
    if analysis is None:
        raise KeyError(f"analysis run not found: {analysis_run_id}")
    if analysis.status != "success":
        raise ValueError("只有成功的内容分析运行才能创建事件聚合")
    hotspot = None
    if hotspot_run_id is not None:
        hotspot = db.session.get(HotspotRun, int(hotspot_run_id))
        if hotspot is None or hotspot.analysis_run_id != analysis.id:
            raise ValueError("热点运行不存在或不属于当前内容分析运行")
        if hotspot.topic_status != "success":
            raise ValueError("热点主题发现尚未成功")
    effective_mode = mode or analysis.mode or "manual"
    effective_scope = scope or (
        "global"
        if effective_mode in {"hot", "publish"}
        else ("search_shared" if effective_mode == "search" else "manual")
    )
    with _CREATION_LOCK:
        latest = (
            AggregationRun.query.filter_by(
                analysis_run_id=analysis.id,
                hotspot_run_id=hotspot.id if hotspot else None,
                scope=effective_scope,
                mode=effective_mode,
                config_hash=config.config_hash(),
            )
            .order_by(AggregationRun.attempt.desc())
            .first()
        )
        if latest is not None and latest.status != "failed":
            return latest, True
        attempt = int(latest.attempt or 1) + 1 if latest else 1
        run = AggregationRun(
            analysis_run_id=analysis.id,
            hotspot_run_id=hotspot.id if hotspot else None,
            source_task_id=source_task_id,
            user_id=user_id if user_id is not None else analysis.user_id,
            scope=effective_scope,
            mode=effective_mode,
            attempt=attempt,
            query_fingerprint=analysis.query_fingerprint,
            dataset_hash=analysis.dataset_hash,
            config_hash=config.config_hash(),
            config=config.as_dict(),
            versions={
                "algorithm": config.algorithm_version,
                "bge_model": current_app.config.get("BGE_MODEL", "BAAI/bge-small-zh-v1.5"),
                "bge_model_version": current_app.config.get("BGE_MODEL_VERSION", "default"),
                "bge_preprocess_version": current_app.config.get("BGE_PREPROCESS_VERSION", "v1"),
            },
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
            winner = AggregationRun.query.filter_by(
                analysis_run_id=analysis.id,
                hotspot_run_id=hotspot.id if hotspot else None,
                scope=effective_scope,
                mode=effective_mode,
                config_hash=config.config_hash(),
                attempt=attempt,
            ).first()
            if winner is None:
                raise
            return winner, True


def _load_frozen_documents(run: AggregationRun):
    analysis = db.session.get(AnalysisRun, run.analysis_run_id)
    rows = (
        AnalysisRunArticle.query.filter_by(analysis_run_id=analysis.id)
        .order_by(AnalysisRunArticle.id)
        .all()
    )
    articles = {
        item.id: item
        for item in Article.query.filter(Article.id.in_([row.article_id for row in rows])).all()
    }
    for row in rows:
        article = articles.get(row.article_id)
        if article is None or _content_identity(article) != row.content_identity:
            raise DatasetChangedError(f"文章 {row.article_id} 的内容版本已变化")
    representatives = [row for row in rows if row.is_representative]
    features = {
        item.article_id: item
        for item in DocumentFeatures.query.filter(
            DocumentFeatures.article_id.in_([row.article_id for row in representatives])
        ).all()
    }
    analysis_documents = []
    for row in representatives:
        article = articles[row.article_id]
        feature = features.get(row.article_id)
        if feature is None:
            continue
        title_tokens = segment_document(article.title or "").data.get("tfidf_tokens") or []
        analysis_documents.append(
            AnalysisDocument(
                article_id=article.id,
                snapshot_id=row.article_snapshot_id,
                content_version=row.content_version,
                title=article.title or "",
                title_tokens=title_tokens,
                body_tokens=feature.tfidf_tokens or [],
                platform=article.platform,
                entities={},
                topics=feature.topics or [],
                nlp_weight=float(row.nlp_weight or 0),
                warnings=[],
            )
        )
    matrix = build_feature_matrices(analysis_documents, _feature_config(analysis))
    tfidf_vectors = {}
    if matrix.tfidf_matrix is not None:
        for index, article_id in enumerate(matrix.document_ids):
            tfidf_vectors[article_id] = matrix.tfidf_matrix.getrow(index).toarray()[0].tolist()
    versions = run.versions or {}
    embeddings = {
        item.article_id: item.vector
        for item in ArticleEmbedding.query.filter(
            ArticleEmbedding.article_id.in_([row.article_id for row in representatives]),
            ArticleEmbedding.model_name == versions.get("bge_model"),
            ArticleEmbedding.model_version == versions.get("bge_model_version"),
            ArticleEmbedding.preprocess_version == versions.get("bge_preprocess_version"),
        ).all()
    }
    topics = {}
    if run.hotspot_run_id:
        topic_rows = {
            item.id: item
            for item in TopicResult.query.filter_by(hotspot_run_id=run.hotspot_run_id).all()
        }
        for assignment in TopicArticleAssignment.query.filter_by(
            hotspot_run_id=run.hotspot_run_id, is_primary=True
        ).all():
            topics[assignment.article_id] = topic_rows.get(assignment.topic_result_id)
    documents = []
    row_by_article = {row.article_id: row for row in rows}
    for item in analysis_documents:
        article = articles[item.article_id]
        feature = features[item.article_id]
        topic = topics.get(item.article_id)
        keywords = {
            str(value.get("term")).strip()
            for value in (row_by_article[item.article_id].keywords or [])
            if isinstance(value, dict) and value.get("term")
        }
        entities = {
            "mention": frozenset(str(value) for value in (feature.mentions or [])),
            "topic": frozenset(str(value) for value in (feature.topics or [])),
        }
        documents.append(
            AggregationDocument(
                article_id=article.id,
                title=article.title or "",
                effective_time=article.publish_time or article.first_crawled_at,
                platform=article.platform,
                tfidf_vector=tfidf_vectors.get(article.id),
                bge_vector=embeddings.get(article.id),
                keywords=frozenset(keywords),
                entities={key: values for key, values in entities.items() if values},
                topic_category=topic.category if topic else None,
                topic_name=topic.topic_name if topic else None,
            )
        )
    return analysis, rows, representatives, articles, documents


def _mean_normalized(vectors):
    rows = [[float(value) for value in vector] for vector in vectors if vector]
    if not rows or any(len(row) != len(rows[0]) for row in rows):
        return None
    output = [sum(row[index] for row in rows) / len(rows) for index in range(len(rows[0]))]
    norm = math.sqrt(sum(value * value for value in output))
    return [value / norm for value in output] if norm else None


def _score_formal_representation(cluster, representation, config):
    entity_score = entity_similarity(cluster.entities, representation.entities or {})
    keyword_score = set_similarity(cluster.keywords, representation.keywords or [])
    return score_event_match(
            config=config,
            bge_similarity=cosine_similarity(cluster.bge_center, representation.vector),
            entity_similarity=entity_score if entity_score is not None else keyword_score,
            time_compatibility=1.0,
            article_entities=cluster.entities,
            candidate_entities=representation.entities or {},
        )


def _formal_candidate(cluster, config, versions):
    representations = EventRepresentation.query.filter_by(
        model_name=versions.get("bge_model"),
        model_version=versions.get("bge_model_version"),
        preprocess_version=versions.get("bge_preprocess_version"),
    ).all()
    best = None
    for representation in representations:
        event = db.session.get(Event, representation.event_id)
        if event is None:
            continue
        result = _score_formal_representation(cluster, representation, config)
        if best is None or result.final_score > best[2].final_score:
            best = (event, representation, result)
    if best and not best[2].hard_conflict and best[2].final_score >= config.attach_threshold:
        return best
    return None


def _cluster_title(cluster) -> str:
    raw = max(cluster.documents, key=lambda item: (len(item.title), -item.article_id)).title or "未命名事件"
    # 尝试 AI 生成标题（单篇也走 AI，因为微博 text_raw 是全文）
    titles = list(dict.fromkeys(d.title for d in cluster.documents if d.title and len(d.title) > 5))
    if titles:
        ai_title = _ai_generate_title(titles[:10])
        if ai_title:
            return ai_title
    # 回退：去 hashtag + 截断到 60 字
    import re as _re
    cleaned = _re.sub(r'#\S+?#', '', raw)  # 去微博 hashtag
    cleaned = _re.sub(r'【.+?】', '', cleaned)  # 去微博话题标记
    cleaned = cleaned.strip()
    if len(cleaned) > 60:
        for sep in ("。", "！", "？", "；", "，", " ", "\n"):
            idx = cleaned.rfind(sep, 0, 60)
            if idx > 20:
                return cleaned[:idx + 1]
        return cleaned[:57] + "..."
    return cleaned or raw[:60]


def _llm_client():
    """统一的 LLM 客户端工厂，复用已有的配置模式。"""
    from flask import current_app
    from app.llm.client import LLMClient
    return LLMClient(
        api_key=current_app.config.get("LLM_API_KEY", ""),
        base_url=current_app.config.get("LLM_BASE_URL", ""),
        model_name=current_app.config.get("LLM_MODEL_NAME", ""),
        timeout=15,
    )


def _ai_generate_title(titles: list[str]) -> str | None:
    """用 LLM 从多篇文章标题生成简洁事件标题（≤20字）。"""
    try:
        client = _llm_client()
        joined = "\n".join(f"- {t}" for t in titles[:10])
        resp = client.chat([
            {"role": "system", "content": "你是舆情分析助手。根据多篇报道标题，生成一个简洁的事件标题（≤20字），不要加引号和标点符号，直接输出标题文本。"},
            {"role": "user", "content": f"请从以下报道标题生成事件标题：\n{joined}"}
        ], temperature=0.3, max_tokens=30)
        result = resp["content"].strip().strip('"''""''「」[]（）()')
        if 4 <= len(result) <= 40:
            return result
    except Exception:
        pass
    return None


def _ai_generate_report(
    title: str,
    articles: list,
    platform_count: int,
    *,
    event_keywords: dict | None = None,
) -> dict | None:
    """一次 LLM 调用生成结构化研判报告（摘要+时间+地点+起因+人物+舆论焦点）。

    领域无关提示词，适用自然灾害/政治/经济/娱乐等所有事件类型。
    """
    try:
        client = _llm_client()
        samples = "\n".join(f"- [{a.platform}] {a.title}" for a in articles[:8] if a.title)
        kw_context = ""
        if event_keywords and event_keywords.get("keywords"):
            kw_list = event_keywords["keywords"][:10]
            kw_context = "关键词: " + ", ".join(k["word"] for k in kw_list)
        resp = client.chat([
            {"role": "system", "content": (
                "你是舆情分析师。根据事件信息和相关报道，生成一份结构化研判报告。"
                "只返回 JSON 对象，字段如下：\n"
                '{\n  "overview": "100-200字事件概述（事件性质、核心内容、传播规模）",\n'
                '  "time_code": "发生时间（如可推断，否则用报道最早时间）",\n'
                '  "location": "涉及地点（多个用逗号分隔，无则留空）",\n'
                '  "key_figures": "关键人物/机构（多个用逗号分隔，无则留空）",\n'
                '  "cause": "事件起因/背景（50字以内）",\n'
                '  "focus": "舆论焦点（网民/媒体主要关注什么）",\n'
                '  "trend": "发展趋势判断（上升/平稳/下降）"\n'
                '}\n'
                "不要加解释文字，只输出 JSON。"
            )},
            {"role": "user", "content": (
                f"事件标题：{title}\n"
                f"覆盖平台：{platform_count}个\n"
                f"{kw_context}\n"
                f"相关报道：\n{samples}\n\n"
                "请生成结构化研判报告（JSON）："
            )}
        ], temperature=0.3, max_tokens=400)
        result = resp["content"].strip()
        import json as _json
        fenced = _json.loads.__doc__ and __import__('re').fullmatch(
            r"```(?:json)?\s*(.*?)\s*```", result, __import__('re').DOTALL | __import__('re').IGNORECASE
        )
        if fenced: result = fenced.group(1)
        data = _json.loads(result)
        if isinstance(data, dict) and data.get("overview"):
            return {
                "overview": str(data.get("overview", ""))[:300],
                "time_code": str(data.get("time_code", ""))[:50],
                "location": str(data.get("location", ""))[:100],
                "key_figures": str(data.get("key_figures", ""))[:200],
                "cause": str(data.get("cause", ""))[:200],
                "focus": str(data.get("focus", ""))[:200],
                "trend": str(data.get("trend", ""))[:20],
            }
    except Exception:
        pass
    return None


def _ensure_membership(article, event, run, confidence, method, now):
    current = EventArticleMembership.query.filter_by(active_article_id=article.id).first()
    if current and current.event_id == event.id:
        article.event_id = event.id
        return "unchanged"
    if current:
        current.is_active = False
        current.active_article_id = None
        current.valid_to = now
        action = "moved"
    else:
        action = "attach"
    db.session.add(
        EventArticleMembership(
            event_id=event.id,
            article_id=article.id,
            active_article_id=article.id,
            source_aggregation_run_id=run.id,
            confidence=confidence,
            decision_method=method,
            is_active=True,
            valid_from=now,
        )
    )
    article.event_id = event.id
    return action


def _update_event(event, run, now):
    memberships = EventArticleMembership.query.filter_by(event_id=event.id, is_active=True).all()
    articles = [db.session.get(Article, item.article_id) for item in memberships]
    articles = [item for item in articles if item is not None]
    times = [item.publish_time or item.first_crawled_at for item in articles if item.publish_time or item.first_crawled_at]
    event.first_publish_time = min(times, default=None)
    event.last_activity_time = max(times, default=None)
    event.independent_report_count = len([item for item in articles if not item.is_duplicate])
    event.platform_count = len({item.platform for item in articles if item.platform})
    update_event_lifecycle(
        event,
        daily_counts_from_articles(articles),
        now=now,
    )
    from app.services.event_service import update_event_metadata

    update_event_metadata(
        event,
        articles,
        now=now,
        client_factory=_llm_client,
    )
    versions = run.versions or {}
    representative_articles = [item for item in articles if not item.is_duplicate]
    embedding_rows = ArticleEmbedding.query.filter(
        ArticleEmbedding.article_id.in_([item.id for item in representative_articles]),
        ArticleEmbedding.model_name == versions.get("bge_model"),
        ArticleEmbedding.model_version == versions.get("bge_model_version"),
        ArticleEmbedding.preprocess_version == versions.get("bge_preprocess_version"),
    ).all()
    vector = _mean_normalized([item.vector for item in embedding_rows])
    if vector is None:
        return
    keywords = sorted(
        {
            value.get("term")
            for item in AnalysisRunArticle.query.filter(
                AnalysisRunArticle.analysis_run_id == run.analysis_run_id,
                AnalysisRunArticle.article_id.in_([article.id for article in articles]),
            ).all()
            for value in (item.keywords or [])
            if isinstance(value, dict) and value.get("term")
        }
    )
    representation = EventRepresentation.query.filter_by(
        event_id=event.id,
        model_name=versions.get("bge_model"),
        model_version=versions.get("bge_model_version"),
        preprocess_version=versions.get("bge_preprocess_version"),
    ).first()
    if representation is None:
        representation = EventRepresentation(
            event_id=event.id,
            model_name=versions.get("bge_model"),
            model_version=versions.get("bge_model_version"),
            preprocess_version=versions.get("bge_preprocess_version"),
            dimension=len(vector),
            vector=vector,
            source_aggregation_run_id=run.id,
        )
        db.session.add(representation)
    representation.dimension = len(vector)
    representation.vector = vector
    representation.keywords = keywords
    feature_rows = DocumentFeatures.query.filter(
        DocumentFeatures.article_id.in_([item.id for item in representative_articles])
    ).all()
    representation.entities = {
        "mention": sorted(
            {str(value) for feature in feature_rows for value in (feature.mentions or [])}
        ),
        "topic": sorted(
            {str(value) for feature in feature_rows for value in (feature.topics or [])}
        ),
    }
    representation.entities = {
        key: values for key, values in representation.entities.items() if values
    }
    representation.member_count = len(embedding_rows)
    representation.source_aggregation_run_id = run.id
    representation.updated_at = now


def _serialize_run(run: AggregationRun) -> dict:
    statistics = dict(run.statistics or {})
    return {
        "aggregation_run_id": run.id,
        "analysis_run_id": run.analysis_run_id,
        "hotspot_run_id": run.hotspot_run_id,
        "scope": run.scope,
        "mode": run.mode,
        "status": run.status,
        "cache_expires_at": run.cache_expires_at.isoformat() if run.cache_expires_at else None,
        "warnings": run.warnings or [],
        **statistics,
    }


def run_event_aggregation(
    aggregation_run_id: int,
    *,
    task_id: int | None = None,
    config: AggregationConfig | None = None,
    now: datetime | None = None,
) -> dict:
    config = config or _config_from_app()
    now = now or _utcnow()
    run = db.session.get(AggregationRun, int(aggregation_run_id))
    if run is None:
        raise KeyError(f"aggregation run not found: {aggregation_run_id}")
    if run.status == "success":
        return _serialize_run(run)
    run.status = "running"
    run.started_at = now
    db.session.commit()
    try:
        analysis, rows, representatives, articles, documents = _load_frozen_documents(run)
        result = cluster_documents(documents, config)
        assert_task_lease(task_id)
        lock = _GLOBAL_WRITE_LOCK if run.scope == "global" else RLock()
        with lock:
            AggregationAssignment.query.filter_by(aggregation_run_id=run.id).delete()
            AggregationCluster.query.filter_by(aggregation_run_id=run.id).delete()
            db.session.flush()
            assignment_by_article = {item.article_id: item for item in result.assignments}
            created_event_count = 0
            actions = Counter()
            cluster_rows = {}
            for cluster in result.clusters:
                decision_extras = []
                existing_event_ids = {
                    articles[item.article_id].event_id
                    for item in cluster.documents
                    if articles[item.article_id].event_id is not None
                }
                formal_match = None
                legacy_event = None
                current_event = (
                    db.session.get(Event, next(iter(existing_event_ids)))
                    if run.scope == "global" and len(existing_event_ids) == 1
                    else None
                )
                if run.scope == "global":
                    formal_match = _formal_candidate(cluster, config, run.versions or {})
                    if current_event is not None:
                        versions = run.versions or {}
                        current_representation = EventRepresentation.query.filter_by(
                            event_id=current_event.id,
                            model_name=versions.get("bge_model"),
                            model_version=versions.get("bge_model_version"),
                            preprocess_version=versions.get("bge_preprocess_version"),
                        ).first()
                        if current_representation is None:
                            legacy_event = current_event
                            formal_match = None
                        elif formal_match and formal_match[0].id != current_event.id:
                            current_score = _score_formal_representation(
                                cluster, current_representation, config
                            )
                            if (
                                formal_match[2].final_score - current_score.final_score
                                < config.move_margin
                            ):
                                legacy_event = current_event
                                formal_match = None
                                decision_extras.append("MOVE_MARGIN_NOT_MET")
                if run.scope == "global":
                    if legacy_event is not None:
                        event = legacy_event
                        formal_score = None
                    elif formal_match:
                        event, _representation, formal_score = formal_match
                    else:
                        event = Event(
                            title=_cluster_title(cluster),
                            topic_category=cluster.topic_category,
                            topic_name=cluster.topic_name,
                            source="search" if run.mode != "hot" else "daily_hot",
                            ttl_days=7 if run.mode == "hot" else None,
                            first_publish_time=min(
                                (item.effective_time for item in cluster.documents if item.effective_time),
                                default=None,
                            ),
                            last_activity_time=max(
                                (item.effective_time for item in cluster.documents if item.effective_time),
                                default=None,
                            ),
                        )
                        db.session.add(event)
                        db.session.flush()
                        formal_score = None
                        created_event_count += 1
                else:
                    event = None
                    formal_score = None
                cluster_row = AggregationCluster(
                    aggregation_run_id=run.id,
                    cluster_index=cluster.cluster_index,
                    resolved_event_id=event.id if event else None,
                    title=_cluster_title(cluster),
                    topic_category=cluster.topic_category,
                    topic_name=cluster.topic_name,
                    keywords=sorted(cluster.keywords),
                    entities={key: sorted(values) for key, values in cluster.entities.items()},
                    first_publish_time=min(
                        (item.effective_time for item in cluster.documents if item.effective_time),
                        default=None,
                    ),
                    last_activity_time=max(
                        (item.effective_time for item in cluster.documents if item.effective_time),
                        default=None,
                    ),
                    representative_article_id=cluster.documents[0].article_id,
                    member_count=len(cluster.documents),
                    platform_count=len({item.platform for item in cluster.documents}),
                    confidence=max(
                        (assignment_by_article[item.article_id].similarity for item in cluster.documents),
                        default=0.0,
                    ),
                )
                db.session.add(cluster_row)
                db.session.flush()
                cluster_rows[cluster.cluster_index] = cluster_row
                for document in cluster.documents:
                    base = assignment_by_article[document.article_id]
                    if event:
                        membership_action = _ensure_membership(
                            articles[document.article_id],
                            event,
                            run,
                            formal_score.final_score if formal_score else max(base.similarity, 1.0 if base.action == "create" else base.similarity),
                            "formal_match" if formal_score else "new_cluster",
                            now,
                        )
                        if created_event_count and base.action == "create" and len(cluster.documents) == 1:
                            membership_action = "create"
                    else:
                        membership_action = base.action
                    actions[membership_action] += 1
                    db.session.add(
                        AggregationAssignment(
                            aggregation_run_id=run.id,
                            aggregation_cluster_id=cluster_row.id,
                            article_id=document.article_id,
                            content_identity=_content_identity(articles[document.article_id]),
                            resolved_event_id=event.id if event else None,
                            membership_action=membership_action,
                            candidate_event_id=event.id if formal_match else None,
                            similarity=formal_score.final_score if formal_score else base.similarity,
                            score_details={
                                "components": formal_score.component_scores if formal_score else base.component_scores,
                                "warnings": formal_score.warnings if formal_score else base.warnings,
                            },
                            decision_reason=(
                                (formal_score.reasons if formal_score else base.reasons)
                                + decision_extras
                            ),
                            is_representative=True,
                        )
                    )
                if event:
                    _update_event(event, run, now)
            for assignment in result.assignments:
                if assignment.action != "deferred":
                    continue
                actions["deferred"] += 1
                db.session.add(
                    AggregationAssignment(
                        aggregation_run_id=run.id,
                        article_id=assignment.article_id,
                        content_identity=_content_identity(articles[assignment.article_id]),
                        membership_action="deferred",
                        similarity=0.0,
                        score_details={},
                        decision_reason=assignment.reasons,
                        is_representative=True,
                    )
                )
            row_by_article = {row.article_id: row for row in rows}
            for row in rows:
                if row.is_representative:
                    continue
                article = articles[row.article_id]
                representative_id = article.duplicate_of_id
                if representative_id is None:
                    continue
                representative_assignment = assignment_by_article.get(representative_id)
                if representative_assignment is None or representative_assignment.cluster_index is None:
                    continue
                cluster_row = cluster_rows[representative_assignment.cluster_index]
                event = (
                    db.session.get(Event, cluster_row.resolved_event_id)
                    if cluster_row.resolved_event_id is not None
                    else None
                )
                if event is not None:
                    _ensure_membership(
                        article,
                        event,
                        run,
                        float(representative_assignment.similarity or 1.0),
                        "duplicate_inheritance",
                        now,
                    )
                    _update_event(event, run, now)
                actions["attach"] += 1
                db.session.add(
                    AggregationAssignment(
                        aggregation_run_id=run.id,
                        aggregation_cluster_id=cluster_row.id,
                        article_id=article.id,
                        content_identity=_content_identity(article),
                        resolved_event_id=event.id if event else None,
                        membership_action="attach",
                        candidate_event_id=event.id if event else None,
                        similarity=representative_assignment.similarity,
                        score_details={"inherited_from_article_id": representative_id},
                        decision_reason=["DUPLICATE_INHERITANCE"],
                        is_representative=False,
                    )
                )
            run.statistics = {
                "input_count": len(rows),
                "representative_count": len(representatives),
                "cluster_count": len(result.clusters),
                "created_event_count": created_event_count,
                "attached_article_count": actions["attach"],
                "unchanged_count": actions["unchanged"],
                "moved_count": actions["moved"],
                "deferred_count": actions["deferred"],
            }
            run.warnings = sorted(
                {warning for assignment in result.assignments for warning in assignment.warnings}
            )
            run.status = "success"
            run.completed_at = now
            if run.scope == "search_shared":
                run.cache_expires_at = now + timedelta(hours=config.search_cache_hours)
            assert_task_lease(task_id)
            db.session.commit()
            return _serialize_run(run)
    except StaleTaskLeaseError:
        db.session.rollback()
        raise
    except Exception as exc:
        db.session.rollback()
        failed = db.session.get(AggregationRun, run.id)
        failed.status = "failed"
        failed.error_code = type(exc).__name__.upper()
        failed.error_message = str(exc)
        failed.completed_at = now
        db.session.commit()
        raise


def find_search_cache(
    query_fingerprint: str,
    *,
    now: datetime | None = None,
    config: AggregationConfig | None = None,
) -> dict:
    now = now or _utcnow()
    config = config or _config_from_app()
    candidates = (
        AggregationRun.query.filter_by(
            query_fingerprint=str(query_fingerprint),
            scope="search_shared",
            status="success",
            config_hash=config.config_hash(),
        )
        .order_by(AggregationRun.completed_at.desc(), AggregationRun.id.desc())
        .all()
    )
    expected_versions = {
        "bge_model": current_app.config.get("BGE_MODEL", "BAAI/bge-small-zh-v1.5"),
        "bge_model_version": current_app.config.get("BGE_MODEL_VERSION", "default"),
        "bge_preprocess_version": current_app.config.get("BGE_PREPROCESS_VERSION", "v1"),
    }
    run = next(
        (
            item
            for item in candidates
            if all((item.versions or {}).get(key) == value for key, value in expected_versions.items())
        ),
        None,
    )
    if run is None:
        return {"run": None, "cached": False, "stale": False, "refresh_required": True}
    stale = run.cache_expires_at is None or now >= run.cache_expires_at
    return {
        "run": _serialize_run(run),
        "cached": not stale,
        "stale": stale,
        "refresh_required": stale,
    }


def get_aggregation_run(
    run_id: int, *, user_id: int | None = None, admin: bool = True
) -> dict | None:
    run = db.session.get(AggregationRun, int(run_id))
    if run is None:
        return None
    if not admin and run.scope != "search_shared" and run.user_id != user_id:
        return None
    return _serialize_run(run)


def list_aggregation_runs(*, user_id: int | None = None, admin: bool = False) -> list[dict]:
    query = AggregationRun.query
    if not admin:
        query = query.filter(
            (AggregationRun.scope == "search_shared")
            | (AggregationRun.user_id == user_id)
        )
    return [
        _serialize_run(item)
        for item in query.order_by(AggregationRun.id.desc()).limit(100).all()
    ]


def list_aggregation_clusters(run_id: int, *, page: int = 1, size: int = 20) -> dict:
    page = max(1, int(page))
    size = max(1, min(100, int(size)))
    query = AggregationCluster.query.filter_by(aggregation_run_id=int(run_id))
    total = query.count()
    rows = query.order_by(AggregationCluster.cluster_index).offset((page - 1) * size).limit(size).all()
    return {
        "clusters": [
            {
                "id": item.id,
                "cluster_index": item.cluster_index,
                "resolved_event_id": item.resolved_event_id,
                "title": item.title,
                "topic_category": item.topic_category,
                "topic_name": item.topic_name,
                "keywords": item.keywords or [],
                "entities": item.entities or {},
                "first_publish_time": item.first_publish_time.isoformat()
                if item.first_publish_time
                else None,
                "last_activity_time": item.last_activity_time.isoformat()
                if item.last_activity_time
                else None,
                "member_count": item.member_count,
                "platform_count": item.platform_count,
                "confidence": item.confidence,
            }
            for item in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


def list_aggregation_assignments(run_id: int, *, page: int = 1, size: int = 50) -> dict:
    page = max(1, int(page))
    size = max(1, min(200, int(size)))
    query = AggregationAssignment.query.filter_by(aggregation_run_id=int(run_id))
    total = query.count()
    rows = query.order_by(AggregationAssignment.id).offset((page - 1) * size).limit(size).all()
    return {
        "assignments": [
            {
                "article_id": item.article_id,
                "cluster_id": item.aggregation_cluster_id,
                "event_id": item.resolved_event_id,
                "membership_action": item.membership_action,
                "similarity": item.similarity,
                "score_details": item.score_details or {},
                "decision_reason": item.decision_reason or [],
            }
            for item in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


def publish_cluster(
    cluster_id: int,
    *,
    user_id: int,
    now: datetime | None = None,
    config: AggregationConfig | None = None,
) -> dict:
    now = now or _utcnow()
    config = config or _config_from_app()
    source = db.session.get(AggregationCluster, int(cluster_id))
    if source is None:
        raise KeyError(f"aggregation cluster not found: {cluster_id}")
    source_run = db.session.get(AggregationRun, source.aggregation_run_id)
    if source_run is None or source_run.status != "success":
        raise ValueError("只有成功聚合运行中的事件簇可以发布")
    if source_run.scope not in {"search_shared", "manual"}:
        raise ValueError("只有搜索或手动事件簇需要发布")
    if source.resolved_event_id is not None:
        published = AggregationCluster.query.filter_by(resolved_event_id=source.resolved_event_id).filter(AggregationCluster.id != source.id).order_by(AggregationCluster.id.desc()).first()
        return {
            "source_cluster_id": source.id,
            "event_id": source.resolved_event_id,
            "reused": True,
            "postprocess": _postprocess_published_event(source.resolved_event_id, published.aggregation_run_id, user_id, now) if published else {"warnings": ["PUBLISH_RUN_UNAVAILABLE"]},
        }
    publish_run, reused = create_aggregation_run(
        source_run.analysis_run_id,
        scope="global",
        mode="publish",
        user_id=user_id,
        config=config,
    )
    if reused and publish_run.status == "success":
        published = AggregationCluster.query.filter_by(
            aggregation_run_id=publish_run.id,
            cluster_index=source.cluster_index,
        ).first()
        if published and published.resolved_event_id:
            source.resolved_event_id = published.resolved_event_id
            db.session.commit()
            return {
                "source_cluster_id": source.id,
                "aggregation_run_id": publish_run.id,
                "event_id": published.resolved_event_id,
                "reused": True,
            }
    assignments = AggregationAssignment.query.filter_by(
        aggregation_cluster_id=source.id
    ).all()
    articles = [db.session.get(Article, item.article_id) for item in assignments]
    articles = [item for item in articles if item is not None]
    if not articles:
        raise ValueError("事件簇没有可发布文章")
    event = Event(
        title=source.title,
        topic_category=source.topic_category,
        topic_name=source.topic_name,
        source="daily_hot" if publish_run.mode == "hot" else "search",
        ttl_days=7 if publish_run.mode == "hot" else None,
        first_publish_time=source.first_publish_time,
        last_activity_time=source.last_activity_time,
    )
    db.session.add(event)
    db.session.flush()
    published_cluster = AggregationCluster(
        aggregation_run_id=publish_run.id,
        cluster_index=source.cluster_index,
        resolved_event_id=event.id,
        title=source.title,
        topic_category=source.topic_category,
        topic_name=source.topic_name,
        keywords=source.keywords or [],
        entities=source.entities or {},
        first_publish_time=source.first_publish_time,
        last_activity_time=source.last_activity_time,
        representative_article_id=source.representative_article_id,
        member_count=source.member_count,
        platform_count=source.platform_count,
        confidence=source.confidence,
    )
    db.session.add(published_cluster)
    db.session.flush()
    for original, article in zip(assignments, articles):
        action = _ensure_membership(
            article,
            event,
            publish_run,
            float(original.similarity or source.confidence or 0),
            "published_search_cluster",
            now,
        )
        db.session.add(
            AggregationAssignment(
                aggregation_run_id=publish_run.id,
                aggregation_cluster_id=published_cluster.id,
                article_id=article.id,
                content_identity=_content_identity(article),
                resolved_event_id=event.id,
                membership_action="create" if action == "attach" else action,
                similarity=original.similarity,
                score_details=original.score_details or {},
                decision_reason=["PUBLISHED_SEARCH_CLUSTER"],
                is_representative=original.is_representative,
            )
        )
    _update_event(event, publish_run, now)
    source.resolved_event_id = event.id
    publish_run.statistics = {
        "input_count": len(articles),
        "representative_count": sum(bool(item.is_representative) for item in assignments),
        "cluster_count": 1,
        "created_event_count": 1,
        "attached_article_count": len(articles),
        "unchanged_count": 0,
        "moved_count": 0,
        "deferred_count": 0,
        "source_cluster_id": source.id,
    }
    publish_run.status = "success"
    publish_run.started_at = publish_run.started_at or now
    publish_run.completed_at = now
    db.session.commit()
    result = {
        "source_cluster_id": source.id,
        "aggregation_run_id": publish_run.id,
        "event_id": event.id,
        "reused": False,
    }
    result["postprocess"] = _postprocess_published_event(event.id, publish_run.id, user_id, now)
    return result


def list_merge_candidates(*, status: str = "pending") -> list[dict]:
    rows = EventMergeRecord.query.filter_by(status=status).order_by(EventMergeRecord.id.desc()).all()
    return [
        {
            "id": item.id,
            "source_event_id": item.source_event_id,
            "target_event_id": item.target_event_id,
            "aggregation_run_id": item.aggregation_run_id,
            "similarity_evidence": item.similarity_evidence or {},
            "reason": item.reason,
            "status": item.status,
            "reviewed_by": item.reviewed_by,
            "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        }
        for item in rows
    ]


def review_merge_candidate(
    record_id: int,
    *,
    approve: bool,
    reviewer_id: int,
    now: datetime | None = None,
) -> dict:
    now = now or _utcnow()
    record = db.session.get(EventMergeRecord, int(record_id))
    if record is None:
        raise KeyError(f"merge candidate not found: {record_id}")
    if record.status != "pending":
        return {
            "id": record.id,
            "source_event_id": record.source_event_id,
            "target_event_id": record.target_event_id,
            "status": record.status,
        }
    if not approve:
        record.status = "rejected"
        record.reviewed_by = reviewer_id
        record.reviewed_at = now
        db.session.commit()
        return {
            "id": record.id,
            "source_event_id": record.source_event_id,
            "target_event_id": record.target_event_id,
            "status": record.status,
        }
    source = db.session.get(Event, record.source_event_id)
    target = db.session.get(Event, record.target_event_id)
    if source is None or target is None or source.id == target.id:
        raise ValueError("合并候选中的来源或目标事件无效")
    source_memberships = EventArticleMembership.query.filter_by(
        event_id=source.id, is_active=True
    ).all()
    moved_articles = []
    for membership in source_memberships:
        membership.is_active = False
        membership.active_article_id = None
        membership.valid_to = now
        moved_articles.append((membership, db.session.get(Article, membership.article_id)))
    db.session.flush()
    for previous, article in moved_articles:
        if article is None:
            continue
        existing = EventArticleMembership.query.filter_by(
            event_id=target.id, article_id=article.id, is_active=True
        ).first()
        if existing is None:
            db.session.add(
                EventArticleMembership(
                    event_id=target.id,
                    article_id=article.id,
                    active_article_id=article.id,
                    source_aggregation_run_id=(
                        record.aggregation_run_id or previous.source_aggregation_run_id
                    ),
                    confidence=previous.confidence,
                    decision_method="confirmed_event_merge",
                    is_active=True,
                    valid_from=now,
                )
            )
        article.event_id = target.id
    record.status = "confirmed"
    record.reviewed_by = reviewer_id
    record.reviewed_at = now
    if record.aggregation_run_id:
        run = db.session.get(AggregationRun, record.aggregation_run_id)
        if run is not None:
            _update_event(target, run, now)
    db.session.commit()
    return {
        "id": record.id,
        "source_event_id": source.id,
        "target_event_id": target.id,
        "status": record.status,
        "moved_article_count": len(moved_articles),
    }


__all__ = [
    "create_aggregation_run",
    "find_search_cache",
    "get_aggregation_run",
    "list_aggregation_assignments",
    "list_aggregation_clusters",
    "list_aggregation_runs",
    "list_merge_candidates",
    "publish_cluster",
    "review_merge_candidate",
    "run_event_aggregation",
]
