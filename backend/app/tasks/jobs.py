from __future__ import annotations

from datetime import datetime, timezone

from flask import current_app

from app.analysis.hot_seed import HotSeedSnapshot, merge_hot_seeds
from app.crawler.base import CrawlIssue, CrawlerRegistry, RawDocument
from app.crawler.factory import build_crawler_registry
from app.extensions import db
from app.models import HotSeedExpansion
from app.services.article_pipeline_service import persist_raw_document
from app.services.crawl_service import CrawlService
from app.services.task_service import get_task, update_task


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
    update_task(task_id, progress=30, message=f"采集完成，获得 {len(batch.documents)} 条原始数据。")

    processed = 0
    failed = 0
    persisted_hot_documents = []
    persisted_article_ids = []
    for index, document in enumerate(batch.documents, start=1):
        try:
            article, _output = persist_raw_document(document, task_id)
            processed += 1
            persisted_article_ids.append(article.id)
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
        progress = 30 + int(index / max(1, len(batch.documents)) * 65)
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

        update_task(task_id, progress=96, message="正在执行搜索语料内容分析。")
        analysis_run, analysis_reused = create_analysis_run(
            list(dict.fromkeys(persisted_article_ids)),
            user_id=task.get("created_by"),
            mode="search",
            keyword=payload.get("keyword"),
            platforms=platforms or [],
            source_task_id=task_id,
        )
        if not analysis_reused or analysis_run.status != "success":
            run_content_analysis(analysis_run.id, task_id=task_id)
        update_task(task_id, progress=98, message="正在生成共享搜索事件。")
        aggregation_run, aggregation_reused = create_aggregation_run(
            analysis_run.id,
            user_id=task.get("created_by"),
            source_task_id=task_id,
        )
        if not aggregation_reused or aggregation_run.status != "success":
            run_event_aggregation(aggregation_run.id, task_id=task_id)
        sentiment_run, sentiment_reused = create_sentiment_run(
            aggregation_run.id,
            source_task_id=task_id,
            user_id=task.get("created_by"),
        )
        if not sentiment_reused or sentiment_run.status != "success":
            run_sentiment_analysis(sentiment_run.id, task_id=task_id)
        summary.update(
            analysis_run_id=analysis_run.id,
            aggregation_run_id=aggregation_run.id,
            sentiment_run_id=sentiment_run.id,
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
    return summary


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
