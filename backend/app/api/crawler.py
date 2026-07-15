from flask import Blueprint, current_app, g, request

from app.core.response import fail, ok
from app.core.security import admin_required, login_required
from app.services.task_service import create_or_reuse_recent_task, latest_status
from app.services.content_analysis_service import query_fingerprint
from app.services.event_aggregation_service import find_search_cache
from app.tasks.jobs import crawl_job
from app.tasks.runner import submit_background_job


crawler_bp = Blueprint("crawler", __name__)


def _platforms(payload: dict):
    platforms = payload.get("platforms", [])
    if not isinstance(platforms, list) or not all(isinstance(item, str) for item in platforms):
        return None
    return list(dict.fromkeys(item.strip() for item in platforms if item.strip()))


@crawler_bp.post("/trigger")
@admin_required
def trigger():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return fail("请求体必须是 JSON 对象", 400)
    platforms = _platforms(payload)
    if platforms is None:
        return fail("platforms 必须是字符串数组", 400)
    if isinstance(payload.get("target_count", 100), bool):
        return fail("target_count 必须是整数", 400)
    try:
        target_count = int(payload.get("target_count", 50))
    except (TypeError, ValueError):
        return fail("target_count 必须是整数", 400)
    if target_count < 1 or target_count > 200:
        return fail("target_count 必须在 1 到 200 之间", 400)
    task_payload = {
        "platforms": platforms,
        "mode": "hot",
        "target_count": target_count,
    }
    task, reused = create_or_reuse_recent_task(
        "crawl",
        g.current_user["id"],
        task_payload,
        current_app.config.get("CRAWL_DUPLICATE_WINDOW_SECONDS", 60),
    )
    if reused:
        return ok(
            {"task_id": task["id"], "reused": True},
            message="已存在相同的近期采集任务。",
        )
    submit_background_job(current_app._get_current_object(), crawl_job, task["id"])
    return ok({"task_id": task["id"], "reused": False}, message="爬取任务已启动")


@crawler_bp.post("/search")
@login_required
def keyword_search():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return fail("请求体必须是 JSON 对象", 400)
    keyword_value = payload.get("keyword")
    if not isinstance(keyword_value, str):
        return fail("keyword 必须是非空字符串", 400)
    keyword = keyword_value.strip()
    if not keyword:
        return fail("keyword 不能为空", 400)
    platforms = _platforms(payload)
    if platforms is None:
        return fail("platforms 必须是字符串数组", 400)
    if isinstance(payload.get("target_count", 100), bool):
        return fail("target_count 必须是整数", 400)
    force_refresh = bool(payload.get("force", False))
    try:
        target_count = int(payload.get("target_count", 50))
    except (TypeError, ValueError):
        return fail("target_count 必须是整数", 400)
    if target_count < 1 or target_count > 200:
        return fail("target_count 必须在 1 到 200 之间", 400)
    task_payload = {
        "keyword": keyword,
        "platforms": platforms,
        "target_count": target_count,
        "mode": "search",
    }
    from app.services.user_search_history_service import record_search
    record_search(g.current_user["id"], keyword, platforms, target_count)
    fingerprint = query_fingerprint("search", keyword, platforms)
    cache = {"cached": False, "stale": False, "run": None}

    # force 刷新：跳过所有缓存，直接开始新采集
    if not force_refresh:
        cache = find_search_cache(fingerprint)
        # 缓存未过期（默认 2h 内）：直接返回已有结果，不重复采集
        if cache["cached"]:
            return ok(
                {
                    "task_id": None,
                    "reused": True,
                    "cached": True,
                    "stale": False,
                    "aggregation_run_id": cache["run"]["aggregation_run_id"],
                    "cache_expires_at": cache["run"]["cache_expires_at"],
                },
                message="近期已有相同关键词的分析结果（{} 内有效），无需重复采集。如需最新数据请勾选强制刷新。".format(
                    f'{current_app.config.get("EVENT_SEARCH_CACHE_HOURS", 2)}小时'
                ),
            )
        # 缓存已过期 → 静默启动后台刷新，但优先返回旧结果给用户
        if cache["stale"] and cache["run"] is not None:
            task, reused = create_or_reuse_recent_task(
                "crawl",
                g.current_user["id"],
                task_payload,
                current_app.config.get("CRAWL_DUPLICATE_WINDOW_SECONDS", 60),
            )
            if not reused:
                submit_background_job(current_app._get_current_object(), crawl_job, task["id"])
            return ok(
                {
                    "task_id": task["id"] if not reused else None,
                    "reused": True,
                    "cached": False,
                    "stale": True,
                    "aggregation_run_id": cache["run"]["aggregation_run_id"],
                    "cache_expires_at": cache["run"]["cache_expires_at"],
                },
                message="已有过期缓存结果，后台已启动增量采集，新数据将补充到已有事件中。",
            )

    task, reused = create_or_reuse_recent_task(
        "crawl",
        g.current_user["id"],
        task_payload,
        current_app.config.get("CRAWL_DUPLICATE_WINDOW_SECONDS", 60),
    )
    if reused:
        return ok(
            {
                "task_id": task["id"],
                "reused": True,
                "cached": False,
                "stale": bool(cache["stale"]),
                "aggregation_run_id": (
                    cache["run"]["aggregation_run_id"] if cache["run"] else None
                ),
            },
            message="已存在相同的近期关键词采集任务。",
        )
    submit_background_job(current_app._get_current_object(), crawl_job, task["id"])
    return ok(
        {
            "task_id": task["id"],
            "reused": False,
            "cached": False,
            "stale": bool(cache["stale"]),
            "aggregation_run_id": (
                cache["run"]["aggregation_run_id"] if cache["run"] else None
            ),
        },
        message=(
            "已返回过期搜索结果，并启动后台增量刷新。"
            if cache["stale"]
            else "关键词采集任务已启动"
        ),
    )


@crawler_bp.get("/platforms")
@login_required
def available_platforms():
    """返回实际可用的搜索类爬虫平台列表（只返回有Key或公开可用的）。"""
    from app.crawler.factory import build_crawler_registry
    registry = build_crawler_registry(current_app.config)
    # 排除：热榜类、演示类、不可用的
    unavailable = {"sample", "rss"}  # 排除演示和RSS
    # 已知配额耗尽/不可用的平台（动态变化，临时排除）
    rate_limited = current_app.config.get("CRAWL_RATE_LIMITED_PLATFORMS", [])
    searchable = [
        name for name in registry.platforms()
        if name not in unavailable and name not in rate_limited
        and not name.endswith("_hot")
        and not name.startswith("rss_")
    ]
    # RSS 订阅源作为独立信源（不需要关键词搜索，提供最新资讯）
    rss_platforms = [
        name for name in registry.platforms()
        if name.startswith("rss_")
    ]
    return ok({
        "platforms": sorted(searchable),
        "rss": sorted(rss_platforms),
    })


@crawler_bp.get("/status")
@login_required
def status():
    created_by = None if g.current_user.get("role") == "admin" else g.current_user["id"]
    return ok(latest_status(created_by=created_by))
