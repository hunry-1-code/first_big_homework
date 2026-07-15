from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from flask import current_app
from sqlalchemy import func

from app.analysis.daily_hot import (
    HotRankItem,
    fuse_hot_rankings,
    normalize_hot_title,
)
from app.crawler.base import CrawlRequest, CrawlerRegistry
from app.crawler.errors import CrawlerError
from app.crawler.factory import build_crawler_registry
from app.extensions import db
from app.models import DailyHotItem, DailyHotRun, Task
from app.services.task_service import create_or_reuse_recent_task


_SENSITIVE_KEY = re.compile(
    r"authorization|api[-_]?key|access[-_]?token|secret|cookie",
    flags=re.IGNORECASE,
)
_BEARER_VALUE = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", flags=re.IGNORECASE)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sanitize_payload(value):
    if isinstance(value, dict):
        return {
            str(key): _sanitize_payload(item)
            for key, item in value.items()
            if not _SENSITIVE_KEY.search(str(key))
        }
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, str):
        return _BEARER_VALUE.sub("Bearer [REDACTED]", value)[:2000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:500]


def _config_hash(
    sources: list[str],
    *,
    source_limit: int,
    result_limit: int,
    rrf_k: int,
    candidate_limit: int = 50,
    consensus_bonus: float = 0.10,
) -> str:
    payload = json.dumps(
        {
            "sources": sorted(set(sources)),
            "source_limit": int(source_limit),
            "result_limit": int(result_limit),
            "rrf_k": int(rrf_k),
            "candidate_limit": int(candidate_limit),
            "consensus_bonus": float(consensus_bonus),
            "algorithm": "weighted-rrf-v2",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_error(code: str, *, retryable: bool = False) -> dict:
    return {
        "code": str(code or "CRAWL_FAILED")[:64],
        "message": "source collection failed",
        "retryable": bool(retryable),
    }


def _rank(document, fallback: int) -> int:
    raw = document.raw_json or {}
    # 按优先级尝试各平台原生排名字段，排除非正数
    for field in ("rank", "realpos", "index", "pos"):
        value = raw.get(field)
        if value is not None:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                return parsed
    return fallback


def collect_daily_hot(
    *,
    registry: CrawlerRegistry | None = None,
    sources: list[str] | None = None,
    source_limit: int = 30,
    result_limit: int = 20,
    rrf_k: int = 10,
    ttl_seconds: int = 900,
    candidate_limit: int = 50,
    consensus_bonus: float = 0.10,
    now: datetime | None = None,
    force: bool = False,
    progress_callback=None,
) -> DailyHotRun:
    now = now or _utcnow()
    selected_sources = sorted(
        {
            str(source).strip().casefold()
            for source in (sources or ["weibo_hot", "baidu_hot", "zhihu_hot"])
            if str(source).strip()
        }
    )
    source_limit = max(1, min(int(source_limit), 100))
    result_limit = max(1, min(int(result_limit), 100))
    rrf_k = max(1, int(rrf_k))
    ttl_seconds = max(0, int(ttl_seconds))
    candidate_limit = max(10, min(int(candidate_limit), 100))
    config_hash = _config_hash(
        selected_sources,
        source_limit=source_limit,
        result_limit=result_limit,
        rrf_k=rrf_k,
        candidate_limit=candidate_limit,
        consensus_bonus=consensus_bonus,
    )
    latest = (
        DailyHotRun.query.filter_by(
            run_date=now.date(),
            config_hash=config_hash,
        )
        .order_by(DailyHotRun.attempt.desc(), DailyHotRun.id.desc())
        .first()
    )
    if (
        not force
        and latest is not None
        and latest.status in {"success", "partial"}
        and latest.completed_at is not None
        and (now - latest.completed_at).total_seconds() <= ttl_seconds
    ):
        return latest

    registry = registry or build_crawler_registry(current_app.config)
    ranked_items = []
    available_sources = []
    failed_sources = []
    errors = {}
    for index, source in enumerate(selected_sources, start=1):
        if progress_callback is not None:
            progress_callback("source", index, len(selected_sources), source)
        try:
            crawler = registry.get(source)
            documents = crawler.crawl(
                CrawlRequest(
                    platform=source,
                    keyword=None,
                    limit=source_limit,
                    mode="hot",
                )
            )
            source_items = []
            for position, document in enumerate(documents[:source_limit], start=1):
                title = normalize_hot_title(document.title)
                if not title:
                    continue
                source_items.append(
                    HotRankItem(
                        source=source,
                        rank=_rank(document, position),
                        title=title,
                        source_url=document.source_url,
                        raw={
                            "source_url": document.source_url,
                            "source_article_id": document.source_article_id,
                            "raw_json": _sanitize_payload(document.raw_json or {}),
                        },
                    )
                )
            if not source_items:
                raise CrawlerError(
                    source,
                    "CRAWL_EMPTY_RESPONSE",
                    "platform returned no usable hot items",
                    False,
                )
            ranked_items.extend(source_items)
            available_sources.append(source)
        except KeyError:
            failed_sources.append(source)
            errors[source] = _source_error("CRAWLER_NOT_CONFIGURED")
        except CrawlerError as exc:
            failed_sources.append(source)
            errors[source] = _source_error(exc.code, retryable=exc.retryable)
        except Exception as exc:
            failed_sources.append(source)
            errors[source] = _source_error(type(exc).__name__.upper())

    if progress_callback is not None:
        progress_callback("fusion", len(ranked_items), len(selected_sources), None)
    # 先全量融合（不截断），LLM去重后再截Top N
    fused_all = fuse_hot_rankings(
        ranked_items,
        rrf_k=rrf_k,
        limit=None,
        consensus_bonus=consensus_bonus,
    )
    previous_attempt = (
        db.session.query(func.max(DailyHotRun.attempt))
        .filter(
            DailyHotRun.run_date == now.date(),
            DailyHotRun.config_hash == config_hash,
        )
        .scalar()
        or 0
    )
    status = (
        "failed"
        if not available_sources
        else ("partial" if failed_sources else "success")
    )
    if progress_callback is not None:
        progress_callback("persistence", len(fused_all), result_limit, None)
    run = DailyHotRun(
        run_date=now.date(),
        status=status,
        attempt=int(previous_attempt) + 1,
        available_sources=sorted(available_sources),
        failed_sources=sorted(failed_sources),
        errors=errors,
        item_count=len(fused_all),
        config_hash=config_hash,
        completed_at=now,
    )
    db.session.add(run)
    db.session.flush()
    item_map: dict[str, DailyHotItem] = {}
    for rank, item in enumerate(fused_all, start=1):
        from app.services.event_topic_service import classify_topic_text
        classification = classify_topic_text(item.normalized_title)
        db_item = DailyHotItem(
            run_id=run.id,
            normalized_key=item.normalized_key,
            title=item.normalized_title,
            fused_score=item.fused_score,
            rank=rank,
            source_ranks=item.source_ranks,
            source_payloads=_sanitize_payload(item.source_payloads),
            first_seen_at=now,
            last_seen_at=now,
            enrichment_status="pending",
            topic_keywords=classification["evidence"],
        )
        db.session.add(db_item)
        item_map[item.normalized_title] = db_item
    db.session.flush()

    # LLM 语义去重：取前 candidate_limit 条，用 ID 匹配
    dedup_candidates = fused_all[:candidate_limit]
    if len(dedup_candidates) > 1:
        deduplicate_hot_topics(list(item_map.values()), dedup_candidates)

    # 重新排序：merged 项不参与排名，主条目重新编号
    # 先清空所有 rank 避免 UNIQUE 冲突
    DailyHotItem.query.filter_by(run_id=run.id).update({DailyHotItem.rank: None})
    db.session.flush()
    canonical_items = (
        DailyHotItem.query.filter_by(run_id=run.id, merged_into_item_id=None)
        .order_by(DailyHotItem.fused_score.desc(), DailyHotItem.id)
        .all()
    )
    for new_rank, item in enumerate(canonical_items, start=1):
        item.rank = new_rank
    run.item_count = len(canonical_items)
    db.session.commit()
    return run


def serialize_daily_hot_run(
    run: DailyHotRun | None,
    *,
    limit: int,
    ttl_seconds: int,
    now: datetime | None = None,
) -> dict:
    now = now or _utcnow()
    if run is None:
        return {
            "run_id": None,
            "date": now.date().isoformat(),
            "generated_at": None,
            "status": "empty",
            "stale": True,
            "available_sources": [],
            "failed_sources": [],
            "errors": {},
            "items": [],
            "total": 0,
        }
    items = (
        DailyHotItem.query.filter_by(run_id=run.id, merged_into_item_id=None)
        .order_by(DailyHotItem.rank, DailyHotItem.id)
        .limit(max(1, min(int(limit), 100)))
        .all()
    )
    from app.models import Event
    event_ids = [item.event_id for item in items if item.event_id]
    event_map = {event.id: event for event in Event.query.filter(Event.id.in_(event_ids)).all()} if event_ids else {}
    from app.services.event_topic_service import classify_topic_text
    item_topics = {}
    category_counts = {}
    for item in items:
        event = event_map.get(item.event_id)
        fallback = classify_topic_text(item.title)
        topic = {
            "category": event.topic_category if event and event.topic_category else fallback["category"],
            "topic_name": event.topic_name if event and event.topic_name else fallback["topic_name"],
            "topic_keywords": item.topic_keywords or fallback["evidence"],
        }
        item_topics[item.id] = topic
        category = topic["category"]
        category_counts[category] = category_counts.get(category, 0) + 1
    stale = (
        run.completed_at is None
        or (now - run.completed_at).total_seconds() > max(0, int(ttl_seconds))
    )
    return {
        "run_id": run.id,
        "date": run.run_date.isoformat(),
        "generated_at": run.completed_at.isoformat() if run.completed_at else None,
        "status": run.status,
        "stale": stale,
        "available_sources": run.available_sources or [],
        "failed_sources": run.failed_sources or [],
        "errors": run.errors or {},
        "category_counts": category_counts,
        "items": [
            {
                "id": item.id,
                "rank": item.rank,
                "title": item.title,
                "fused_score": float(item.fused_score),
                "source_ranks": item.source_ranks or {},
                "source_urls": {
                    source: payload.get("source_url")
                    for source, payload in (item.source_payloads or {}).items()
                    if isinstance(payload, dict) and payload.get("source_url")
                },
                "enrichment_status": item.enrichment_status,
                "event_id": item.event_id,
                "analysis_task_id": item.analysis_task_id,
                "category": item_topics[item.id]["category"],
                "topic_name": item_topics[item.id]["topic_name"],
                "topic_keywords": item_topics[item.id]["topic_keywords"],
            }
            for item in items
        ],
        "total": int(run.item_count or 0),
    }


def get_today_hotspots(
    *,
    limit: int = 10,
    ttl_seconds: int = 900,
    now: datetime | None = None,
) -> dict:
    run = DailyHotRun.query.order_by(
        DailyHotRun.run_date.desc(),
        DailyHotRun.attempt.desc(),
        DailyHotRun.id.desc(),
    ).first()
    return serialize_daily_hot_run(
        run,
        limit=limit,
        ttl_seconds=ttl_seconds,
        now=now,
    )


def create_daily_hot_enrichment_tasks(
    run_id: int,
    *,
    created_by: int,
) -> list[dict]:
    run = db.session.get(DailyHotRun, int(run_id))
    if run is None:
        raise KeyError(f"daily hot run not found: {run_id}")
    tasks = []
    items = DailyHotItem.query.filter_by(run_id=run.id).order_by(DailyHotItem.rank).all()
    for item in items:
        if item.enrichment_status in {"completed", "no_event"} or item.merged_into_item_id:
            continue
        tasks.append(create_daily_hot_item_enrichment_task(item.id, created_by=created_by))
    db.session.commit()
    return tasks


def create_daily_hot_item_enrichment_task(item_id: int, *, created_by: int) -> dict:
    item = db.session.get(DailyHotItem, int(item_id))
    if item is None:
        raise KeyError(f"daily hot item not found: {item_id}")
    if item.merged_into_item_id is not None:
        raise ValueError("merged hot item cannot be enriched independently")
    active = db.session.get(Task, item.analysis_task_id) if item.analysis_task_id else None
    if active is not None and active.status in {"pending", "running", "success"}:
        return {
            "id": active.id,
            "type": active.task_type,
            "task_type": active.task_type,
            "status": active.status,
            "payload": active.payload or {},
            "created_by": active.created_by,
            "reused": True,
        }
    task, reused = create_or_reuse_recent_task(
        "daily_hot_enrichment",
        created_by=created_by,
        payload={
            "daily_hot_item_id": item.id,
            "normalized_keyword": item.normalized_key,
            "keyword": item.title,
        },
        within_seconds=24 * 3600,
    )
    task = dict(task)
    task["reused"] = reused
    item.analysis_task_id = task["id"]
    if item.enrichment_status in {"failed", "no_event"}:
        item.enrichment_status = "pending"
        item.error_code = None
        item.error_message = None
    db.session.commit()
    return task


def deduplicate_hot_topics(
    all_items: list[DailyHotItem],
    candidates: list[FusedHotItem],
) -> None:
    """LLM 语义去重（ID 匹配），直接修改 DailyHotItem.merged_into_item_id。

    给 LLM 传入带稳定 ID 的候选标题列表，要求返回分组。
    匹配用 ID 而非标题字符串，避免标点偏差导致合并失败。
    """
    if len(candidates) <= 1:
        return

    # 构建 ID→item 映射（用 rank 作为稳定 ID）
    id_map: dict[str, DailyHotItem] = {}
    id_list: list[dict] = []
    for c in candidates:
        item = next((i for i in all_items if i.normalized_key == c.normalized_key), None)
        if item is None:
            continue
        sid = str(item.rank)
        id_map[sid] = item
        id_list.append({"id": sid, "title": c.normalized_title})

    if len(id_list) < 2:
        return

    try:
        from flask import current_app
        from app.llm.client import LLMClient
        client = LLMClient(
            api_key=current_app.config.get("LLM_API_KEY", ""),
            base_url=current_app.config.get("LLM_BASE_URL", ""),
            model_name=current_app.config.get("LLM_MODEL_NAME", ""),
            timeout=20,
        )
        joined = "\n".join(f'{d["id"]}. {d["title"]}' for d in id_list)
        resp = client.chat([
            {"role": "system", "content": (
                "你是热榜去重助手。输入是带ID的标题列表。将描述同一事件的标题分组。"
                "返回 JSON 数组（每组 >=2 个标题才输出）：\n"
                '[{"canonical_id":"主ID","member_ids":["ID1","ID2"],'
                '"keywords":["词1","词2"]}]\n'
                "ID 必须来自输入的 ID，不能自己编造。不输出单条标题的组。"
            )},
            {"role": "user", "content": f"热榜标题：\n{joined}\n\n分组去重（只输出 JSON）："}
        ], temperature=0.2, max_tokens=300)
        text = resp["content"].strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced:
            text = fenced.group(1)
        text = text.replace('\n', ' ').replace('\r', '')
        try:
            groups = json.loads(text)
        except json.JSONDecodeError:
            idx = text.rfind(']')
            if idx > 0:
                groups = json.loads(text[:idx + 1])
            else:
                raise

        if not isinstance(groups, list):
            return

        seen_ids: set[str] = set()
        for g in groups:
            if not isinstance(g, dict):
                continue
            member_ids = g.get("member_ids", [])
            if not isinstance(member_ids, list) or len(member_ids) < 2:
                continue
            canonical_id = str(g.get("canical_id") or member_ids[0])
            canonical_item = id_map.get(canonical_id)
            if canonical_item is None:
                continue
            canonical_item.topic_keywords = g.get("keywords", [])
            for mid in member_ids:
                mid_str = str(mid)
                if mid_str == canonical_id:
                    continue
                if mid_str in seen_ids:
                    continue
                merged_item = id_map.get(mid_str)
                if merged_item and merged_item.id != canonical_item.id:
                    merged_item.merged_into_item_id = canonical_item.id
                    seen_ids.add(mid_str)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("LLM topic dedup failed: %s", e)


__all__ = [
    "collect_daily_hot",
    "create_daily_hot_enrichment_tasks",
    "create_daily_hot_item_enrichment_task",
    "deduplicate_hot_topics",
    "get_today_hotspots",
    "serialize_daily_hot_run",
]
