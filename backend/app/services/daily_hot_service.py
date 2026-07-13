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
from app.models import DailyHotItem, DailyHotRun


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
    for source in selected_sources:
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


__all__ = [
    "collect_daily_hot",
    "get_today_hotspots",
    "serialize_daily_hot_run",
]
