from __future__ import annotations

from datetime import datetime, timezone

from flask import current_app

from app.analysis.hot_seed import HotSeedSnapshot, merge_hot_seeds
from app.crawler.base import CrawlIssue, CrawlerRegistry, RawDocument
from app.crawler.factory import build_crawler_registry
from app.extensions import db
from app.models import HotSeedExpansion
from app.services.article_pipeline_service import persist_raw_document
from app.services.comment_service import persist_comment
from app.crawler.tikhub_comments import TikHubCommentAdapter
from app.services.crawl_service import CrawlService
from app.services.task_service import get_task, update_task, record_stage, build_summary


def _first_present(item: dict, *keys: str):
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return None


def _raw_document(item: dict) -> RawDocument:
    raw_content = item.get("raw_content") or item.get("content") or ""
    return RawDocument(
        platform=item["platform"],
        source_url=item.get("source_url") or item.get("url"),
        source_article_id=item.get("source_article_id"),
        title=item.get("title") or "",
        raw_content=raw_content,
        source_type=item.get("source_type") or "sample",
        content_type=item.get("content_type") or ("html" if "<" in raw_content else "text"),
        author=item.get("author"),
        author_id=item.get("author_id"),
        author_followers=item.get("author_followers"),
        author_verified=item.get("author_verified"),
        author_type=item.get("author_type"),
        publish_time=item.get("publish_time"),
        likes_count=_first_present(item, "likes_count", "like_count"),
        comments_count=_first_present(item, "comments_count", "comment_count"),
        reposts_count=_first_present(item, "reposts_count", "repost_count"),
        views_count=_first_present(item, "views_count", "view_count"),
        raw_json=item.get("raw_json") or dict(item),
    )


def _enrich_article_comments(article, document, registry) -> tuple[int, str | None]:
    platform = document.platform
    if platform not in {"zhihu", "weibo", "douyin", "xiaohongshu", "bilibili"}:
        return 0, None
    try:
        limit = current_app.config.get("COMMENT_MAX_PER_ARTICLE", 50)
        if platform == "bilibili":
            crawler = registry.get("bilibili")
            rows = crawler.fetch_comments(document.source_article_id, limit=limit)
        else:
            keys = current_app.config.get("TIKHUB_PLATFORM_API_KEYS", {})
            key = keys.get(platform) or current_app.config.get("TIKHUB_API_KEY", "")
            adapter = TikHubCommentAdapter(platform, key, current_app.config.get("TIKHUB_BASE_URL", "https://api.tikhub.io"), current_app.config.get("CRAWL_REQUEST_TIMEOUT", 30))
            rows = adapter.fetch(document.source_article_id, limit=limit, reply_limit=current_app.config.get("COMMENT_MAX_REPLIES", 20))
        count = 0
        for raw in rows:
            try:
                persist_comment(article, raw)
                count += 1
            except ValueError:
                continue
        return count, None
    except Exception as exc:
        db.session.rollback()
        return 0, str(exc)


def crawl_job(task_id: int, registry: CrawlerRegistry | None = None) -> dict:
    task = get_task(task_id)
    if task is None:
        raise KeyError(f"task not found: {task_id}")
    payload = task.get("payload") or {}
    update_task(task_id, status="running", progress=5, message="正在准备采集平台。")
    registry = registry or build_crawler_registry(current_app.config)
    platforms = payload.get("platforms") or None
    mode = payload.get("mode", "search")
    if mode == "hot" and not platforms:
        platforms = [name for name in registry.platforms() if name.endswith("_hot")]
    service = CrawlService(
        registry,
        default_target_count=current_app.config.get("CRAWL_DEFAULT_TARGET_COUNT", 100),
        maximum_target_count=current_app.config.get("CRAWL_MAX_TARGET_COUNT", 200),
        preferred_platform_limit=current_app.config.get("CRAWL_PLATFORM_PREFERRED_LIMIT", 50),
    )
    batch = service.collect(
        keyword=payload.get("keyword"),
        platforms=platforms,
        target_count=payload.get("target_count"),
        mode=mode,
    )
    update_task(task_id, progress=25, message=f"采集完成，获得 {len(batch.documents)} 条原始数据。")
    record_stage(task_id, "crawl", "done", f"{len(batch.documents)}篇")

    processed = 0
    failed = 0
    persisted_hot_documents = []
    persisted_article_ids = []
    comment_count = 0
    comment_errors = []
    for index, document in enumerate(batch.documents, start=1):
        try:
            article, _output = persist_raw_document(document, task_id)
            processed += 1
            persisted_article_ids.append(article.id)
            added, comment_error = _enrich_article_comments(article, document, registry)
            comment_count += added
            if comment_error:
                comment_errors.append({"platform": document.platform, "article_id": article.id, "message": comment_error})
            if mode == "hot" and document.source_type == "hotlist":
                persisted_hot_documents.append((article, document))
        except Exception as exc:
            failed += 1
            batch.errors.append(
                CrawlIssue(
                    document.platform,
                    "PERSIST_TRANSACTION_FAILED",
                    str(exc),
                    True,
                )
            )
        progress = 25 + int(index / max(1, len(batch.documents)) * 25)  # 预处理: 25-50%
        update_task(task_id, progress=progress, message=f"已处理 {index}/{len(batch.documents)} 条数据。")

    errors = [
        {
            "platform": issue.platform,
            "code": issue.code,
            "message": issue.message,
            "retryable": issue.retryable,
        }
        for issue in batch.errors
    ]
    summary = {
        "collected": len(batch.documents),
        "processed": processed,
        "failed": failed,
        "platform_counts": batch.platform_counts,
        "errors": errors,
        "comments_collected": comment_count,
        "comment_errors": comment_errors,
    }
    if mode == "hot" and persisted_hot_documents:
        update_task(task_id, progress=96, message="正在整理热榜种子并扩展多平台搜索。")
        seed_rows = []
        for article, document in persisted_hot_documents:
            raw = document.raw_json or {}
            rank = raw.get("rank") or raw.get("realpos") or raw.get("position")
            seed_rows.append(
                HotSeedSnapshot(
                    seed_id=article.id,
                    platform=document.platform,
                    title=document.title,
                    rank=int(rank) if isinstance(rank, (int, float)) else None,
                    snapshot_time=article.first_crawled_at or datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
        seeds = merge_hot_seeds(seed_rows)[
            : current_app.config.get("HOTSPOT_EXPANSION_SEED_LIMIT", 20)
        ]
        search_platforms = [
            name
            for name in registry.platforms()
            if name not in {"sample", "rss"} and not name.endswith("_hot")
        ]
        expanded_ids = []
        expansion_errors = []
        expansion_platform_counts = {}
        if search_platforms:
            for seed in seeds:
                expanded_batch = service.collect(
                    keyword=seed.query,
                    platforms=search_platforms,
                    target_count=current_app.config.get(
                        "HOTSPOT_EXPANSION_TARGET_PER_SEED", 20
                    ),
                    mode="search",
                )
                for issue in expanded_batch.errors:
                    expansion_errors.append(
                        {
                            "seed": seed.query,
                            "platform": issue.platform,
                            "code": issue.code,
                            "message": issue.message,
                            "retryable": issue.retryable,
                        }
                    )
                for platform, count in expanded_batch.platform_counts.items():
                    expansion_platform_counts[platform] = (
                        expansion_platform_counts.get(platform, 0) + count
                    )
                # 批量收集扩展映射，减少逐条查询
                pending_expansions = []
                for document in expanded_batch.documents:
                    try:
                        article, _output = persist_raw_document(document, task_id)
                        expanded_ids.append(article.id)
                        discovered_at = datetime.now(timezone.utc).replace(tzinfo=None)
                        for seed_article_id in seed.source_seed_ids:
                            pending_expansions.append(
                                {
                                    "seed_article_id": seed_article_id,
                                    "search_query": seed.query,
                                    "crawl_task_id": task_id,
                                    "platform": document.platform,
                                    "article_id": article.id,
                                    "source_rank": seed.best_rank,
                                    "discovered_at": discovered_at,
                                }
                            )
                    except Exception as exc:
                        expansion_errors.append(
                            {
                                "seed": seed.query,
                                "platform": document.platform,
                                "code": "EXPANSION_PERSIST_FAILED",
                                "message": str(exc),
                                "retryable": True,
                            }
                        )
                if pending_expansions:
                    existing_keys = set()
                    for exp in pending_expansions:
                        existing = HotSeedExpansion.query.filter_by(
                            seed_article_id=exp["seed_article_id"],
                            search_query=exp["search_query"],
                            article_id=exp["article_id"],
                        ).first()
                        if existing is not None:
                            existing_keys.add((exp["seed_article_id"], exp["search_query"], exp["article_id"]))
                    for exp in pending_expansions:
                        key = (exp["seed_article_id"], exp["search_query"], exp["article_id"])
                        if key not in existing_keys:
                            db.session.add(HotSeedExpansion(**exp))
                    db.session.commit()
        summary.update(
            seed_count=len(seeds),
            expansion_queries=[seed.query for seed in seeds],
            expanded=len(set(expanded_ids)),
            expansion_platform_counts=expansion_platform_counts,
            expansion_errors=expansion_errors,
            analysis_run_id=None,
            hotspot_run_id=None,
            aggregation_run_id=None,
            sentiment_run_id=None,
        )
        if expanded_ids:
            from app.services.content_analysis_service import (
                create_analysis_run,
                run_content_analysis,
            )
            from app.services.hotspot_service import (
                create_hotspot_run,
                discover_hotspot_topics,
                finalize_hotspot_heat,
            )
            from app.services.event_aggregation_service import (
                create_aggregation_run,
                run_event_aggregation,
            )
            from app.services.sentiment_analysis_service import (
                create_sentiment_run,
                run_sentiment_analysis,
            )

            update_task(task_id, progress=97, message="正在执行扩展语料内容分析。")
            analysis_run, analysis_reused = create_analysis_run(
                list(dict.fromkeys(expanded_ids)),
                mode="hot",
                platforms=search_platforms,
                source_task_id=task_id,
            )
            if not analysis_reused:
                run_content_analysis(analysis_run.id, task_id=task_id)
            update_task(task_id, progress=98, message="正在执行热点主题发现。")
            hotspot_run, hotspot_reused = create_hotspot_run(
                analysis_run.id, source_task_id=task_id
            )
            if not hotspot_reused or hotspot_run.topic_status != "success":
                discover_hotspot_topics(hotspot_run.id, task_id=task_id)
            update_task(task_id, progress=99, message="正在聚合稳定舆情事件。")
            aggregation_run, aggregation_reused = create_aggregation_run(
                analysis_run.id,
                hotspot_run_id=hotspot_run.id,
                source_task_id=task_id,
            )
            if not aggregation_reused or aggregation_run.status != "success":
                run_event_aggregation(aggregation_run.id, task_id=task_id)
            finalize_hotspot_heat(
                hotspot_run.id,
                aggregation_run_id=aggregation_run.id,
                task_id=task_id,
            )
            sentiment_run, sentiment_reused = create_sentiment_run(
                aggregation_run.id,
                source_task_id=task_id,
            )
            if not sentiment_reused or sentiment_run.status != "success":
                run_sentiment_analysis(sentiment_run.id, task_id=task_id)
            summary["analysis_run_id"] = analysis_run.id
            summary["hotspot_run_id"] = hotspot_run.id
            summary["aggregation_run_id"] = aggregation_run.id
            summary["sentiment_run_id"] = sentiment_run.id
    elif mode == "search" and persisted_article_ids:
        from app.services.content_analysis_service import (
            create_analysis_run,
            run_content_analysis,
        )
        from app.services.event_aggregation_service import (
            create_aggregation_run,
            run_event_aggregation,
        )
        from app.services.sentiment_analysis_service import (
            create_sentiment_run,
            run_sentiment_analysis,
        )

        update_task(task_id, progress=52, message="正在执行内容分析（TF-IDF + BGE）...")
        record_stage(task_id, "preprocess", "done", f"{processed}篇")
        effective_platforms = platforms or list(batch.platform_counts.keys())
        analysis_run, analysis_reused = create_analysis_run(
            list(dict.fromkeys(persisted_article_ids)),
            user_id=task.get("created_by"),
            mode="search",
            keyword=payload.get("keyword"),
            platforms=effective_platforms,
            source_task_id=task_id,
        )
        if not analysis_reused or analysis_run.status != "success":
            run_content_analysis(analysis_run.id, task_id=task_id)
        record_stage(task_id, "content_analysis", "done", f"{analysis_run.representative_count}篇代表")
        update_task(task_id, progress=66, message="正在执行事件聚合...")
        aggregation_run, aggregation_reused = create_aggregation_run(
            analysis_run.id,
            user_id=task.get("created_by"),
            source_task_id=task_id,
        )
        if not aggregation_reused or aggregation_run.status != "success":
            run_event_aggregation(aggregation_run.id, task_id=task_id)
        record_stage(task_id, "aggregation", "done", f"{aggregation_run.statistics.get('cluster_count','?')}个簇")
        update_task(task_id, progress=80, message="正在执行情感分析（LLM）...")
        sentiment_run, sentiment_reused = create_sentiment_run(
            aggregation_run.id,
            source_task_id=task_id,
            user_id=task.get("created_by"),
        )
        if not sentiment_reused or sentiment_run.status != "success":
            run_sentiment_analysis(sentiment_run.id, task_id=task_id)
        record_stage(task_id, "sentiment", "done", f"{sentiment_run.statistics.get('result_count','?')}篇")
        update_task(task_id, progress=93, message="正在发布事件...")
        # 自动发布事件簇 → 用户可直接在看板看到结果
        from app.services.event_aggregation_service import publish_cluster
        from app.models import AggregationCluster
        publish_count = 0
        auto_publish = current_app.config.get("AUTO_PUBLISH_EVENTS", False)
        if auto_publish:
            for cluster in AggregationCluster.query.filter_by(
                aggregation_run_id=aggregation_run.id
            ).order_by(AggregationCluster.member_count.desc()).all():
                try:
                    publish_cluster(cluster.id, user_id=task.get("created_by"))
                    publish_count += 1
                except Exception:
                    pass
        record_stage(task_id, "publish", "done", f"{publish_count}个事件")
        summary.update(
            analysis_run_id=analysis_run.id,
            aggregation_run_id=aggregation_run.id,
            sentiment_run_id=sentiment_run.id,
            event_count=publish_count,
            search_cache_expires_at=(
                aggregation_run.cache_expires_at.isoformat()
                if aggregation_run.cache_expires_at
                else None
            ),
        )
    if processed == 0 and errors:
        update_task(task_id, status="failed", progress=100, message="采集任务失败。", result=summary)
    else:
        update_task(task_id, status="success", progress=100, message="采集和预处理完成。", result=summary)
        record_stage(task_id, "done", "done", f"事件{summary.get('event_count',summary.get('cluster_count','?'))}个")
        from app.services.task_service import build_summary
        # 最终摘要
        s = build_summary(task_id)
        if s:
            from app.models import Task
            t = db.session.get(Task, task_id)
            if t:
                t.summary = s
                db.session.commit()
    return summary


def daily_hot_job(task_id: int, registry: CrawlerRegistry | None = None) -> dict:
    task = get_task(task_id)
    if task is None:
        raise KeyError(f"task not found: {task_id}")
    payload = task.get("payload") or {}
    from app.services.daily_hot_service import collect_daily_hot

    update_task(
        task_id,
        status="running",
        progress=5,
        message="正在准备今日热榜采集。",
    )

    def report(stage, current, total, source):
        if stage == "source":
            progress = 10 + int(current / max(1, total) * 50)
            message = f"正在采集热榜来源 {current}/{total}: {source}。"
        elif stage == "fusion":
            progress = 75
            message = f"正在融合 {current} 条跨平台热榜记录。"
        else:
            progress = 90
            message = f"正在持久化 Top{min(current, total)} 热点快照。"
        update_task(task_id, progress=progress, message=message)

    run = collect_daily_hot(
        registry=registry,
        sources=payload.get("sources")
        or current_app.config.get(
            "DAILY_HOT_SOURCES",
            ["weibo_hot", "baidu_hot", "zhihu_hot"],
        ),
        source_limit=payload.get(
            "source_limit",
            current_app.config.get("DAILY_HOT_SOURCE_LIMIT", 30),
        ),
        result_limit=payload.get(
            "result_limit",
            current_app.config.get("DAILY_HOT_RESULT_LIMIT", 10),
        ),
        rrf_k=payload.get(
            "rrf_k",
            current_app.config.get("DAILY_HOT_RRF_K", 60),
        ),
        ttl_seconds=payload.get(
            "ttl_seconds",
            current_app.config.get("DAILY_HOT_TTL_SECONDS", 900),
        ),
        force=bool(payload.get("force", False)),
        progress_callback=report,
    )
    # LLM 主题去重
    if run.status in {"success", "partial"}:
        from app.services.daily_hot_service import deduplicate_hot_topics
        from app.models import DailyHotItem
        items = DailyHotItem.query.filter_by(run_id=run.id, merged_into_item_id=None)\
            .order_by(DailyHotItem.rank).all()
        if items:
            update_task(task_id, progress=80, message=f"正在 LLM 主题去重 ({len(items)} 条)...")
            canonical = deduplicate_hot_topics(items)
            update_task(task_id, progress=85, message=f"去重完成: {len(items)} → {len(canonical)} 个主题")
    # 限制 enrichment 数量：最多 10 个，避免僵尸堆积
    enrichment_tasks = []
    if run.status in {"success", "partial"}:
        enrichment_tasks = enqueue_daily_hot_enrichments(
            run.id,
            created_by=task.get("created_by"),
            registry=registry,
        )[:10]
    summary = {
        "run_id": run.id,
        "status": run.status,
        "item_count": int(run.item_count or 0),
        "available_sources": run.available_sources or [],
        "failed_sources": run.failed_sources or [],
        "enrichment_task_count": len(enrichment_tasks),
    }
    task_status = "failed" if run.status == "failed" else "success"
    update_task(
        task_id,
        status=task_status,
        progress=100,
        message=(
            "今日热榜采集完成。"
            if task_status == "success"
            else "今日热榜所有来源均采集失败。"
        ),
        result=summary,
    )
    return summary


def _run_daily_hot_enrichment_chain(
    task_id: int,
    item,
    task: dict,
    *,
    registry: CrawlerRegistry | None = None,
) -> int | None:
    registry = registry or build_crawler_registry(current_app.config)
    search_platforms = (task.get("payload") or {}).get("platforms") or [
        name
        for name in registry.platforms()
        if name not in {"sample", "rss"} and not name.endswith("_hot")
    ]
    if not search_platforms:
        return None
    # 动态分配爬取量：跨平台越多、排名越高 → 爬越多
    source_ranks = item.source_ranks or {}
    platform_count = len(source_ranks)
    avg_rank = sum(source_ranks.values()) / platform_count if platform_count else 30
    rank_factor = 1.0 + max(0, (30 - avg_rank) / 30)    # rank=1→2x, rank=30→1x
    platform_factor = 1.0 + (platform_count - 1) * 0.5   # 1平台→1x, 3平台→2x
    dynamic_target = max(10, min(50, int(10 * rank_factor * platform_factor)))
    service = CrawlService(
        registry,
        default_target_count=dynamic_target,
        maximum_target_count=current_app.config.get("CRAWL_MAX_TARGET_COUNT", 200),
        preferred_platform_limit=current_app.config.get(
            "CRAWL_PLATFORM_PREFERRED_LIMIT", 50
        ),
    )
    batch = service.collect(
        keyword=item.title,
        platforms=search_platforms,
        target_count=dynamic_target,
        mode="search",
    )
    article_ids = []
    comment_count = 0
    comment_errors = []
    for document in batch.documents:
        article, _output = persist_raw_document(document, task_id)
        article_ids.append(article.id)
        added, comment_error = _enrich_article_comments(article, document, registry)
        comment_count += added
        if comment_error:
            comment_errors.append({"platform": document.platform, "article_id": article.id, "message": comment_error})
    if not article_ids:
        if batch.errors:
            raise RuntimeError("ENRICHMENT_CRAWL_FAILED")
        return None

    from app.models import AggregationCluster
    from app.services.content_analysis_service import (
        create_analysis_run,
        run_content_analysis,
    )
    from app.services.event_aggregation_service import (
        create_aggregation_run,
        publish_cluster,
        run_event_aggregation,
    )

    analysis_run, reused = create_analysis_run(
        list(dict.fromkeys(article_ids)),
        user_id=task.get("created_by"),
        mode="search",
        keyword=item.title,
        platforms=search_platforms,
        source_task_id=task_id,
    )
    if not reused or analysis_run.status != "success":
        run_content_analysis(analysis_run.id, task_id=task_id)
    aggregation_run, aggregation_reused = create_aggregation_run(
        analysis_run.id,
        user_id=task.get("created_by"),
        source_task_id=task_id,
    )
    if not aggregation_reused or aggregation_run.status != "success":
        run_event_aggregation(aggregation_run.id, task_id=task_id)
    cluster = (
        AggregationCluster.query.filter_by(aggregation_run_id=aggregation_run.id)
        .order_by(
            AggregationCluster.member_count.desc(),
            AggregationCluster.confidence.desc(),
            AggregationCluster.id,
        )
        .first()
    )
    if cluster is None:
        return None
    published = publish_cluster(
        cluster.id,
        user_id=task.get("created_by"),
    )
    event_id = int(published["event_id"]) if published.get("event_id") else None
    if event_id is not None:
        from app.services.event_topic_service import classify_event_topic
        classification = classify_event_topic(event_id)
        item.topic_keywords = classification.get("evidence") or []
        db.session.commit()
    return event_id


def daily_hot_enrichment_job(
    task_id: int,
    *,
    registry: CrawlerRegistry | None = None,
    processor=None,
) -> dict:
    task = get_task(task_id)
    if task is None:
        raise KeyError(f"task not found: {task_id}")
    item_id = (task.get("payload") or {}).get("daily_hot_item_id")
    if not isinstance(item_id, int):
        raise ValueError("daily hot enrichment task requires daily_hot_item_id")
    from app.models import DailyHotItem, Event

    item = db.session.get(DailyHotItem, item_id)
    if item is None:
        raise KeyError(f"daily hot item not found: {item_id}")
    update_task(
        task_id,
        status="running",
        progress=10,
        message="正在补全热点事件语料。",
    )
    item.enrichment_status = "running"
    item.error_code = None
    item.error_message = None
    db.session.commit()
    try:
        event_id = (
            processor(item)
            if processor is not None
            else _run_daily_hot_enrichment_chain(
                task_id,
                item,
                task,
                registry=registry,
            )
        )
        if event_id is not None and db.session.get(Event, int(event_id)) is None:
            raise ValueError("enrichment returned unknown event")
    except Exception as exc:
        item.enrichment_status = "failed"
        item.error_code = type(exc).__name__.upper()[:64]
        item.error_message = "item enrichment failed"
        db.session.commit()
        result = {
            "daily_hot_item_id": item.id,
            "status": "failed",
            "error_code": item.error_code,
        }
        update_task(
            task_id,
            status="failed",
            progress=100,
            message="热点条目补全失败。",
            result=result,
        )
        return result

    item.event_id = int(event_id) if event_id is not None else None
    item.enrichment_status = "completed" if event_id is not None else "no_event"
    db.session.commit()
    result = {
        "daily_hot_item_id": item.id,
        "status": item.enrichment_status,
        "event_id": item.event_id,
    }
    update_task(
        task_id,
        status="success",
        progress=100,
        message=(
            "热点条目已关联正式事件。"
            if event_id is not None
            else "热点条目暂未形成正式事件。"
        ),
        result=result,
    )
    return result


def enqueue_daily_hot_enrichments(
    run_id: int,
    *,
    created_by: int,
    registry: CrawlerRegistry | None = None,
) -> list[dict]:
    from app.services.daily_hot_service import create_daily_hot_enrichment_tasks
    from app.tasks.runner import submit_background_job

    tasks = create_daily_hot_enrichment_tasks(run_id, created_by=created_by)
    app = current_app._get_current_object()
    for task in tasks:
        if task.get("reused"):
            continue
        submit_background_job(
            app,
            lambda task_id, current_registry=registry: daily_hot_enrichment_job(
                task_id,
                registry=current_registry,
            ),
            task["id"],
        )
    return tasks


def import_job(task_id: int) -> dict:
    task = get_task(task_id)
    if task is None:
        raise KeyError(f"task not found: {task_id}")
    documents = (task.get("payload") or {}).get("documents") or []
    update_task(task_id, status="running", progress=5, message="正在导入样例数据。")
    processed = 0
    errors = []
    for index, item in enumerate(documents, start=1):
        try:
            persist_raw_document(_raw_document(item), task_id)
            processed += 1
        except Exception as exc:
            errors.append(
                {
                    "index": index - 1,
                    "code": "PERSIST_TRANSACTION_FAILED",
                    "message": str(exc),
                }
            )
        update_task(
            task_id,
            progress=5 + int(index / max(1, len(documents)) * 90),
            message=f"已导入 {index}/{len(documents)} 条数据。",
        )
    summary = {"processed": processed, "failed": len(errors), "errors": errors}
    status = "success" if processed or not documents else "failed"
    update_task(
        task_id,
        status=status,
        progress=100,
        message="样例数据导入和预处理完成。" if status == "success" else "样例数据导入失败。",
        result=summary,
    )
    return summary


def analyze_job(task_id: int) -> dict:
    task = get_task(task_id)
    if task is None:
        raise KeyError(f"task not found: {task_id}")
    analysis_run_id = (task.get("payload") or {}).get("analysis_run_id")
    if not isinstance(analysis_run_id, int):
        raise ValueError("analysis task requires integer analysis_run_id")
    from app.services.content_analysis_service import run_content_analysis

    update_task(task_id, status="running", progress=10, message="正在验证分析数据快照。")
    update_task(task_id, progress=35, message="正在构建 TF-IDF 特征矩阵。")
    result = run_content_analysis(analysis_run_id, task_id=task_id)
    update_task(task_id, progress=85, message="正在保存关键词和分析元数据。")
    update_task(
        task_id,
        status="success",
        progress=100,
        message="内容分析完成。",
        result=result,
    )
    return result


def hotspot_job(task_id: int) -> dict:
    task = get_task(task_id)
    if task is None:
        raise KeyError(f"task not found: {task_id}")
    hotspot_run_id = (task.get("payload") or {}).get("hotspot_run_id")
    if not isinstance(hotspot_run_id, int):
        raise ValueError("hotspot task requires integer hotspot_run_id")
    from app.models import HotspotRun
    from app.services.event_aggregation_service import (
        create_aggregation_run,
        run_event_aggregation,
    )
    from app.services.sentiment_analysis_service import (
        create_sentiment_run,
        run_sentiment_analysis,
    )
    from app.services.hotspot_service import (
        discover_hotspot_topics,
        finalize_hotspot_heat,
    )

    update_task(task_id, status="running", progress=10, message="正在验证热点分析数据快照。")
    update_task(task_id, progress=35, message="正在执行 LDA 主题发现。")
    hotspot_run = db.session.get(HotspotRun, hotspot_run_id)
    if hotspot_run is None:
        raise KeyError(f"hotspot run not found: {hotspot_run_id}")
    if hotspot_run.topic_status != "success":
        discover_hotspot_topics(hotspot_run_id, task_id=task_id)
    update_task(task_id, progress=60, message="正在聚合稳定舆情事件。")
    aggregation_run, reused = create_aggregation_run(
        hotspot_run.analysis_run_id,
        hotspot_run_id=hotspot_run.id,
        source_task_id=task_id,
    )
    if not reused or aggregation_run.status != "success":
        run_event_aggregation(aggregation_run.id, task_id=task_id)
    update_task(task_id, progress=80, message="正在保存事件热度快照。")
    result = finalize_hotspot_heat(
        hotspot_run_id,
        aggregation_run_id=aggregation_run.id,
        task_id=task_id,
    )
    sentiment_run, sentiment_reused = create_sentiment_run(
        aggregation_run.id,
        source_task_id=task_id,
    )
    if not sentiment_reused or sentiment_run.status != "success":
        run_sentiment_analysis(sentiment_run.id, task_id=task_id)
    result["sentiment_run_id"] = sentiment_run.id
    update_task(
        task_id,
        status="success",
        progress=100,
        message="热点事件发现完成。",
        result=result,
    )
    return result


def aggregation_job(task_id: int) -> dict:
    task = get_task(task_id)
    if task is None:
        raise KeyError(f"task not found: {task_id}")
    aggregation_run_id = (task.get("payload") or {}).get("aggregation_run_id")
    if not isinstance(aggregation_run_id, int):
        raise ValueError("aggregation task requires integer aggregation_run_id")
    from app.services.event_aggregation_service import run_event_aggregation

    update_task(task_id, status="running", progress=10, message="正在验证事件聚合数据快照。")
    update_task(task_id, progress=40, message="正在执行事件候选检索和聚类。")
    result = run_event_aggregation(aggregation_run_id, task_id=task_id)
    update_task(
        task_id,
        status="success",
        progress=100,
        message="事件聚合完成。",
        result=result,
    )
    return result


def sentiment_job(task_id: int) -> dict:
    task = get_task(task_id)
    if task is None:
        raise KeyError(f"task not found: {task_id}")
    sentiment_run_id = (task.get("payload") or {}).get("sentiment_run_id")
    if not isinstance(sentiment_run_id, int):
        raise ValueError("sentiment task requires integer sentiment_run_id")
    from app.services.sentiment_analysis_service import run_sentiment_analysis

    update_task(task_id, status="running", progress=10, message="正在验证情感分析数据快照。")
    update_task(task_id, progress=35, message="正在逐篇分析事件内容立场。")
    result = run_sentiment_analysis(sentiment_run_id, task_id=task_id)
    update_task(
        task_id,
        status="success",
        progress=100,
        message="情感倾向分析完成。",
        result=result,
    )
    return result


def report_job(task_id: int) -> dict:
    return {"task_id": task_id, "status": "reserved", "message": "报告任务由报告模块实现。"}
