from __future__ import annotations

from threading import RLock

from flask import Blueprint, current_app, g, request

from app.core.response import fail, ok
from app.core.security import admin_required, login_required
from app.extensions import db
from app.services.hotspot_service import (
    create_hotspot_run,
    get_current_hotspots,
    get_hotspot_run,
    list_hotspot_runs,
)
from app.services.daily_hot_service import (
    collect_daily_hot,
    get_today_hotspots,
    serialize_daily_hot_run,
)
from app.services.task_service import create_task
from app.tasks.jobs import hotspot_job
from app.tasks.runner import submit_background_job


hotspots_bp = Blueprint("hotspots", __name__)
_RUN_TASK_LOCK = RLock()


@hotspots_bp.post("/runs")
@admin_required
def create_run():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return fail("请求体必须是 JSON 对象", 400)
    analysis_run_id = payload.get("analysis_run_id")
    if isinstance(analysis_run_id, bool) or not isinstance(analysis_run_id, int):
        return fail("analysis_run_id 必须是正整数", 400)
    with _RUN_TASK_LOCK:
        try:
            run, reused = create_hotspot_run(
                analysis_run_id, user_id=g.current_user["id"]
            )
        except (KeyError, ValueError) as exc:
            return fail(str(exc), 400)
        if reused and run.status == "success":
            return ok(
                {"hotspot_run_id": run.id, "task_id": None, "reused": True},
                message="已复用相同内容快照和配置的热点分析结果。",
            )
        if reused and run.source_task_id is not None:
            return ok(
                {
                    "hotspot_run_id": run.id,
                    "task_id": run.source_task_id,
                    "reused": True,
                },
                message="已存在相同的热点分析任务。",
            )
        task = create_task(
            "hotspot",
            created_by=g.current_user["id"],
            payload={"hotspot_run_id": run.id},
        )
        run.source_task_id = task["id"]
        db.session.commit()
        submit_background_job(
            current_app._get_current_object(), hotspot_job, task["id"]
        )
    return ok(
        {"hotspot_run_id": run.id, "task_id": task["id"], "reused": False},
        message="热点分析任务已启动。",
    )


@hotspots_bp.get("/runs")
@login_required
def runs():
    admin = g.current_user.get("role") == "admin"
    return ok(
        {
            "runs": list_hotspot_runs(
                user_id=g.current_user["id"], admin=admin
            )
        }
    )


@hotspots_bp.get("/runs/<int:hotspot_run_id>")
@login_required
def run_detail(hotspot_run_id: int):
    admin = g.current_user.get("role") == "admin"
    run = get_hotspot_run(
        hotspot_run_id, user_id=g.current_user["id"], admin=admin
    )
    if run is None:
        return fail("热点分析记录不存在或无权查看", 404)
    return ok(run)


@hotspots_bp.get("")
@login_required
def current_hotspots():
    value = request.args.get("limit", 20)
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return fail("limit 必须是整数", 400)
    return ok(get_current_hotspots(limit))


@hotspots_bp.get("/today")
@login_required
def today_hotspots():
    raw_limit = request.args.get(
        "limit",
        current_app.config.get("DAILY_HOT_RESULT_LIMIT", 10),
    )
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return fail("limit 必须是 1 到 100 的整数", 400)
    if not 1 <= limit <= 100:
        return fail("limit 必须是 1 到 100 的整数", 400)
    return ok(
        get_today_hotspots(
            limit=limit,
            ttl_seconds=current_app.config.get("DAILY_HOT_TTL_SECONDS", 900),
        )
    )


@hotspots_bp.post("/today/refresh")
@admin_required
def refresh_today_hotspots():
    run = collect_daily_hot(
        sources=list(
            current_app.config.get(
                "DAILY_HOT_SOURCES",
                ["weibo_hot", "baidu_hot", "zhihu_hot"],
            )
        ),
        source_limit=current_app.config.get("DAILY_HOT_SOURCE_LIMIT", 30),
        result_limit=current_app.config.get("DAILY_HOT_RESULT_LIMIT", 10),
        rrf_k=current_app.config.get("DAILY_HOT_RRF_K", 60),
        ttl_seconds=current_app.config.get("DAILY_HOT_TTL_SECONDS", 900),
        force=True,
    )
    return ok(
        serialize_daily_hot_run(
            run,
            limit=current_app.config.get("DAILY_HOT_RESULT_LIMIT", 10),
            ttl_seconds=current_app.config.get("DAILY_HOT_TTL_SECONDS", 900),
        ),
        message="今日热点已刷新。",
    )
