from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, OperationalError

from app.crawler.base import RawDocument
from app.extensions import db
from app.models import Article, ArticleSnapshot, DocumentFeatures, ProcessingLog
from app.preprocessing.normalizer import normalize_document
from app.preprocessing.pipeline import PipelineOutput, preprocess_document
from app.services.task_service import assert_task_lease


_PERSIST_LOCK = RLock()


def _database_datetime(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _candidate_rows(exclude_id: int | None = None, limit: int = 200) -> list[dict[str, Any]]:
    query = Article.query.filter(
        Article.clean_status == "success",
        Article.duplicate_of_id.is_(None),
    )
    if exclude_id is not None:
        query = query.filter(Article.id != exclude_id)
    articles = query.order_by(Article.id.desc()).limit(limit).all()
    return [
        {
            "id": article.id,
            "title": article.title,
            "clean_content": article.clean_content or "",
            "duplicate_group_id": article.duplicate_group_id,
            "quality_score": article.quality_score,
            "extraction_degraded": article.extraction_degraded,
            "publish_time": article.publish_time,
        }
        for article in articles
    ]


def _existing_article_query(data: dict[str, Any]):
    return Article.query.filter(
        or_(
            Article.url_hash == data["url_hash"],
            db.and_(
                Article.platform == data["platform"],
                Article.source_article_id == data.get("source_article_id"),
                Article.source_article_id.isnot(None),
            ),
        )
    ).with_for_update()


def _lock_current_representative(article_id: int) -> Article | None:
    visited = set()
    current_id = article_id
    while current_id is not None:
        if current_id in visited:
            raise RuntimeError("duplicate representative cycle detected")
        visited.add(current_id)
        article = Article.query.filter(Article.id == current_id).with_for_update().first()
        if article is None or article.duplicate_of_id is None:
            return article
        current_id = article.duplicate_of_id
    return None


def _existing_output(
    article: Article,
    normalized_data: dict[str, Any],
    raw_content: str,
) -> PipelineOutput:
    features = DocumentFeatures.query.filter_by(article_id=article.id).first()
    return PipelineOutput(
        raw_content=raw_content,
        normalized_data=normalized_data,
        clean_content=article.clean_content or "",
        clean_status=article.clean_status or "success",
        clean_error=article.clean_error,
        extraction_method=article.extraction_method,
        extraction_degraded=bool(article.extraction_degraded),
        processing_warnings=article.processing_warnings or [],
        normalize_version=article.normalize_version or "v1",
        preprocess_version=article.preprocess_version or "v1",
        quality={
            "quality_score": article.quality_score,
            "quality_level": article.quality_level,
            "quality_flags": article.quality_flags or [],
            "nlp_weight": article.nlp_weight,
            "is_advertisement": article.is_advertisement,
            "advertisement_score": article.advertisement_score,
            "advertisement_reasons": article.advertisement_reasons or [],
            "spam_weight": article.spam_weight,
        },
        duplicate={
            "is_duplicate": article.is_duplicate,
            "duplicate_of_id": article.duplicate_of_id,
            "duplicate_group_id": article.duplicate_group_id,
            "duplicate_method": article.duplicate_method,
            "duplicate_score": article.duplicate_score,
            "content_hash": article.content_hash,
            "simhash": article.simhash,
            "dedup_version": article.dedup_version,
        },
        features={
            "tokens": features.tokens if features else [],
            "tfidf_tokens": features.tfidf_tokens if features else [],
            "sentiment_tokens": features.sentiment_tokens if features else [],
            "topics": features.topics if features else [],
            "mentions": features.mentions if features else [],
            "segment_version": features.segment_version if features else None,
        },
        logs=[],
    )


def _apply_output(article: Article, output: PipelineOutput, preserve_identity: bool = False) -> None:
    data = output.normalized_data
    quality = output.quality
    duplicate = output.duplicate
    original_platform = article.platform
    if not preserve_identity:
        article.platform = data.get("platform") or article.platform
    article.source_type = data.get("source_type") or "news"
    if not preserve_identity:
        article.source_article_id = data.get("source_article_id")
        article.url = data.get("url") or article.url
        article.url_hash = data.get("url_hash") or article.url_hash
    article.title = data.get("title") or article.title
    article.raw_content = output.raw_content
    article.clean_content = output.clean_content
    if not preserve_identity or data.get("platform") == original_platform:
        article.raw_json = data.get("raw_json") or {}
    article.content_type = data.get("content_type")
    article.language = data.get("language") or "unknown"
    article.clean_status = output.clean_status
    article.clean_error = output.clean_error
    article.extraction_method = output.extraction_method
    article.extraction_degraded = output.extraction_degraded
    article.processing_warnings = output.processing_warnings
    article.normalize_version = output.normalize_version
    article.preprocess_version = output.preprocess_version
    article.quality_score = quality.get("quality_score")
    article.quality_level = quality.get("quality_level")
    article.quality_flags = quality.get("quality_flags") or []
    article.nlp_weight = quality.get("nlp_weight", 0 if output.clean_status == "failed" else 1)
    article.is_advertisement = quality.get("is_advertisement", False)
    article.advertisement_score = quality.get("advertisement_score")
    article.advertisement_reasons = quality.get("advertisement_reasons") or []
    article.spam_weight = quality.get("spam_weight", 1.0)
    article.is_duplicate = duplicate.get("is_duplicate", False)
    article.duplicate_of_id = duplicate.get("duplicate_of_id")
    article.duplicate_group_id = duplicate.get("duplicate_group_id")
    article.duplicate_method = duplicate.get("duplicate_method")
    article.duplicate_score = duplicate.get("duplicate_score")
    article.content_hash = duplicate.get("content_hash")
    article.simhash = duplicate.get("simhash")
    article.dedup_version = duplicate.get("dedup_version")
    article.author = data.get("author")
    article.author_id = data.get("author_id")
    article.author_followers = data.get("author_followers")
    article.author_verified = data.get("author_verified")
    article.author_type = data.get("author_type")
    article.publish_time = _database_datetime(data.get("publish_time"))
    article.comments_count = data.get("comments_count")
    article.reposts_count = data.get("reposts_count")
    article.likes_count = data.get("likes_count")
    article.views_count = data.get("views_count")
    article.last_crawled_at = datetime.now(timezone.utc).replace(tzinfo=None)


def _representative_rank(article: Article) -> tuple[float, int, int, float]:
    quality = float(article.quality_score or 0)
    extraction = 0 if article.extraction_degraded else 1
    completeness = sum(bool(value) for value in (article.title, article.author, article.publish_time))
    publish_rank = -article.publish_time.timestamp() if article.publish_time else float("-inf")
    return quality, extraction, completeness, publish_rank


def persist_raw_document(
    document: RawDocument,
    task_id: int | None,
) -> tuple[Article, PipelineOutput]:
    with _PERSIST_LOCK:
        for attempt in range(3):
            try:
                return _persist_raw_document(document, task_id)
            except IntegrityError:
                db.session.rollback()
                if attempt >= 1:
                    raise
            except OperationalError as exc:
                db.session.rollback()
                original_args = getattr(exc.orig, "args", ())
                code = original_args[0] if original_args else None
                message = str(exc).lower()
                retryable = code in {1205, 1213} or "deadlock" in message or "database is locked" in message
                if not retryable or attempt == 2:
                    raise
                time.sleep(2**attempt)
            except Exception:
                db.session.rollback()
                raise
    raise RuntimeError("unreachable persistence retry state")


def _persist_raw_document(
    document: RawDocument,
    task_id: int | None,
) -> tuple[Article, PipelineOutput]:
    assert_task_lease(task_id)
    raw_hash = hashlib.sha256((document.raw_content or "").encode("utf-8")).hexdigest()
    normalized = normalize_document(document)
    data = normalized.data
    if not data.get("url_hash") or not data.get("url"):
        raise ValueError((normalized.errors or ["document cannot be persisted"])[0])

    existing = _existing_article_query(data).first()
    article = existing or Article(
        platform=data["platform"],
        source_type=data.get("source_type") or "news",
        url=data["url"],
        url_hash=data["url_hash"],
        title=data.get("title") or "",
    )
    previous_snapshot = None
    if existing and existing.latest_snapshot_id:
        previous_snapshot = db.session.get(ArticleSnapshot, existing.latest_snapshot_id)
    content_changed = previous_snapshot is None or previous_snapshot.content_hash != raw_hash
    needs_preprocess = (
        existing is None
        or content_changed
        or existing.clean_status != "success"
        or existing.preprocess_version != "v1"
    )
    if needs_preprocess:
        candidates = _candidate_rows(existing.id if existing else None)
        output = preprocess_document(document, duplicate_candidates=candidates)
    else:
        output = _existing_output(existing, data, document.raw_content)

    metrics_changed = previous_snapshot is None or any(
        getattr(previous_snapshot, field) != getattr(document, field)
        for field in ("comments_count", "reposts_count", "likes_count", "views_count")
    )
    status_changed = previous_snapshot is None or any(
        (
            previous_snapshot.http_status != document.http_status,
            previous_snapshot.fetch_status != document.fetch_status,
            previous_snapshot.fetch_error != document.fetch_error,
        )
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    interaction_snapshot_allowed = (
        previous_snapshot is None
        or previous_snapshot.crawled_at is None
        or now - previous_snapshot.crawled_at >= timedelta(hours=1)
    )
    snapshot_needed = (
        previous_snapshot is None
        or content_changed
        or status_changed
        or (metrics_changed and interaction_snapshot_allowed)
    )
    if existing and content_changed:
        article.content_version = (article.content_version or 1) + 1

    _apply_output(article, output, preserve_identity=existing is not None)
    if not existing:
        article.content_version = 1
        article.first_crawled_at = datetime.now(timezone.utc).replace(tzinfo=None)
        article.crawl_task_id = task_id
        db.session.add(article)
    db.session.flush()

    snapshot = previous_snapshot
    if snapshot_needed:
        snapshot = ArticleSnapshot(
            article_id=article.id,
            http_status=document.http_status,
            fetch_status=document.fetch_status,
            content_hash=raw_hash,
            raw_content=document.raw_content if content_changed else None,
            raw_json=document.raw_json,
            comments_count=document.comments_count,
            reposts_count=document.reposts_count,
            likes_count=document.likes_count,
            views_count=document.views_count,
            fetch_error=document.fetch_error,
            crawled_at=now,
        )
        db.session.add(snapshot)
        db.session.flush()
        article.latest_snapshot_id = snapshot.id

    if article.is_duplicate and article.duplicate_of_id:
        representative = _lock_current_representative(article.duplicate_of_id)
        if representative:
            article.duplicate_of_id = representative.id
            output.duplicate["duplicate_of_id"] = representative.id
            group_id = representative.duplicate_group_id or f"group-{representative.id}"
            if _representative_rank(article) > _representative_rank(representative):
                members = Article.query.filter(
                    or_(Article.id == representative.id, Article.duplicate_of_id == representative.id)
                ).with_for_update().all()
                for member in members:
                    if member.id == article.id:
                        continue
                    member.is_duplicate = True
                    member.duplicate_of_id = article.id
                    member.duplicate_group_id = group_id
                article.is_duplicate = False
                article.duplicate_of_id = None
                article.duplicate_method = None
                article.duplicate_score = None
                article.duplicate_group_id = group_id
                output.duplicate.update(
                    {
                        "is_duplicate": False,
                        "duplicate_of_id": None,
                        "duplicate_group_id": group_id,
                        "duplicate_method": None,
                        "duplicate_score": None,
                    }
                )
            else:
                representative.duplicate_group_id = group_id
                article.duplicate_group_id = group_id

    features = DocumentFeatures.query.filter_by(article_id=article.id).first()
    if features is None and needs_preprocess:
        features = DocumentFeatures(article_id=article.id)
        db.session.add(features)
    if features is not None and needs_preprocess:
        features.tokens = output.features.get("tokens") or []
        features.tfidf_tokens = output.features.get("tfidf_tokens") or []
        features.sentiment_tokens = output.features.get("sentiment_tokens") or []
        features.topics = output.features.get("topics") or []
        features.mentions = output.features.get("mentions") or []
        features.segment_version = output.features.get("segment_version")

    for item in output.logs:
        db.session.add(
            ProcessingLog(
                task_id=task_id,
                article_id=article.id,
                snapshot_id=snapshot.id if snapshot else None,
                stage=item.stage,
                status=item.status,
                error_code=item.error_code,
                message=item.message,
                retryable=item.retryable,
                duration_ms=item.duration_ms,
            )
        )
    db.session.add(
        ProcessingLog(
            task_id=task_id,
            article_id=article.id,
            snapshot_id=snapshot.id if snapshot else None,
            stage="persist",
            status="success",
            duration_ms=0,
        )
    )
    db.session.commit()
    return article, output
