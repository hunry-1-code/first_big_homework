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
) -> str:
    payload = json.dumps(
        {
            "sources": sorted(set(sources)),
            "source_limit": int(source_limit),
            "result_limit": int(result_limit),
            "rrf_k": int(rrf_k),
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
    value = raw.get("rank") or raw.get("realpos") or fallback
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def collect_daily_hot(
    *,
    registry: CrawlerRegistry | None = None,
    sources: list[str] | None = None,
    source_limit: int = 30,
    result_limit: int = 10,
    rrf_k: int = 60,
    ttl_seconds: int = 900,
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
    config_hash = _config_hash(
        selected_sources,
        source_limit=source_limit,
        result_limit=result_limit,
        rrf_k=rrf_k,
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
    fused = fuse_hot_rankings(
        ranked_items,
        rrf_k=rrf_k,
        limit=result_limit,
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
        progress_callback("persistence", len(fused), result_limit, None)
    run = DailyHotRun(
        run_date=now.date(),
        status=status,
        attempt=int(previous_attempt) + 1,
        available_sources=sorted(available_sources),
        failed_sources=sorted(failed_sources),
        errors=errors,
        item_count=len(fused),
        config_hash=config_hash,
        completed_at=now,
    )
    db.session.add(run)
    db.session.flush()
    for rank, item in enumerate(fused, start=1):
        db.session.add(
            DailyHotItem(
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
            )
        )
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
        DailyHotItem.query.filter_by(run_id=run.id)
        .order_by(DailyHotItem.rank, DailyHotItem.id)
        .limit(max(1, min(int(limit), 100)))
        .all()
    )
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
        if item.enrichment_status in {"completed", "no_event"}:
            continue
        active = (
            db.session.get(Task, item.analysis_task_id)
            if item.analysis_task_id
            else None
        )
        if active is not None and active.status in {"pending", "running"}:
            task = {
                "id": active.id,
                "type": active.task_type,
                "task_type": active.task_type,
                "status": active.status,
                "payload": active.payload or {},
                "created_by": active.created_by,
                "reused": True,
            }
            tasks.append(task)
            continue
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
        if item.enrichment_status == "failed":
            item.enrichment_status = "pending"
            item.error_code = None
            item.error_message = None
        tasks.append(task)
    db.session.commit()
    return tasks


def deduplicate_hot_topics(items: list[DailyHotItem]) -> list[DailyHotItem]:
    """LLM 主题聚合：语义去重，合并描述同一事件的标题。返回主条目列表。"""
    if len(items) <= 1:
        return items

    titles = [item.title for item in items]
    try:
        from flask import current_app
        from app.llm.client import LLMClient
        client = LLMClient(
            api_key=current_app.config.get("LLM_API_KEY", ""),
            base_url=current_app.config.get("LLM_BASE_URL", ""),
            model_name=current_app.config.get("LLM_MODEL_NAME", ""),
            timeout=20,
        )
        joined = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
        resp = client.chat([
            {"role": "system", "content": (
                "你是热榜去重助手。以下热榜标题可能描述同一事件。"
                "将它们分组，每组用 canonical_name 命名，提取 3-5 个关键词。"
                "返回 JSON: [{\"canonical_name\":\"规范名称\",\"keywords\":[\"词1\",\"词2\"],\"merged_indices\":[1,3,5]}]"
                "未合并的标题单独成组。只输出 JSON 数组。"
            )},
            {"role": "user", "content": f"热榜标题：\n{joined}\n\n请分组去重："}
        ], temperature=0.2, max_tokens=500)
        text = resp["content"].strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced: text = fenced.group(1)
        groups = json.loads(text)

        if not isinstance(groups, list) or not groups:
            return items

        # 应用分组：保留每组的第一个作为主条目，其余标记为 merged
        merged_set = set()
        canonical_map = {}
        for g in groups:
            if not isinstance(g, dict): continue
            indices = g.get("merged_indices", [])
            if not indices: continue
            canonical_idx = indices[0] - 1  # 1-indexed -> 0-indexed
            if 0 <= canonical_idx < len(items):
                canonical_item = items[canonical_idx]
                canonical_item.topic_keywords = g.get("keywords", [])
                canonical_map[canonical_idx] = canonical_item
                for idx in indices[1:]:
                    merged_idx = idx - 1
                    if 0 <= merged_idx < len(items):
                        items[merged_idx].merged_into_item_id = canonical_item.id
                        merged_set.add(merged_idx)

        return [item for i, item in enumerate(items) if i not in merged_set]
    except Exception:
        return items  # LLM 失败时回退：全部保留


__all__ = [
    "collect_daily_hot",
    "create_daily_hot_enrichment_tasks",
    "deduplicate_hot_topics",
    "get_today_hotspots",
    "serialize_daily_hot_run",
]
