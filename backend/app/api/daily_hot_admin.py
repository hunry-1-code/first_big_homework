"""每日热点调度管理 API — 管理员控制开关、间隔、手动触发"""
from __future__ import annotations

from flask import Blueprint, current_app, g, request

from app.core.response import fail, ok
from app.core.security import admin_required

daily_hot_admin_bp = Blueprint("daily_hot_admin", __name__)

# 调度状态（存储在 app.extensions 中）
_STATE_KEY = "daily_hot_scheduler_state"


def _state():
    if _STATE_KEY not in current_app.extensions:
        current_app.extensions[_STATE_KEY] = {
            "enabled": current_app.config.get("DAILY_HOT_SCHEDULER_ENABLED", False),
            "interval_minutes": current_app.config.get("DAILY_HOT_REFRESH_INTERVAL_SECONDS", 900) // 60,
        }
    return current_app.extensions[_STATE_KEY]


@daily_hot_admin_bp.get("/status")
@admin_required
def status():
    s = _state()
    last_run = current_app.extensions.get("daily_hot_last_run")
    scheduler = current_app.extensions.get("task_recovery_scheduler")
    job = scheduler.get_job("daily-hot-refresh") if scheduler and hasattr(scheduler, "get_job") else None
    next_run = getattr(job, "next_run_time", None)
    return ok({
        "enabled": job is not None,
        "interval_minutes": s["interval_minutes"],
        "last_run": last_run.isoformat() if last_run else None,
        "next_run": next_run.isoformat() if hasattr(next_run, "isoformat") else next_run,
    })


@daily_hot_admin_bp.post("/toggle")
@admin_required
def toggle():
    body = request.get_json(silent=True) or {}
    enabled = bool(body.get("enabled", False))
    s = _state()
    s["enabled"] = enabled
    scheduler = current_app.extensions.get("task_recovery_scheduler")
    if enabled and scheduler is None:
        scheduler = _scheduler()
    if scheduler is not None:
        from app.tasks.scheduler import set_daily_hot_schedule
        set_daily_hot_schedule(
            current_app._get_current_object(),
            scheduler,
            enabled=enabled,
            interval_seconds=s["interval_minutes"] * 60,
        )

    return ok({"enabled": s["enabled"]}, message="每日热点已启用" if enabled else "每日热点已停用")


@daily_hot_admin_bp.post("/interval")
@admin_required
def set_interval():
    body = request.get_json(silent=True) or {}
    minutes = int(body.get("minutes", 60))
    if minutes < 15 or minutes > 1440:
        return fail("间隔必须在 15-1440 分钟之间", 400)
    s = _state()
    s["interval_minutes"] = minutes
    if s["enabled"]:
        from app.tasks.scheduler import set_daily_hot_schedule
        set_daily_hot_schedule(
            current_app._get_current_object(),
            _scheduler(),
            enabled=True,
            interval_seconds=minutes * 60,
        )
    return ok({"interval_minutes": minutes}, message=f"间隔已设为 {minutes} 分钟")


@daily_hot_admin_bp.post("/run")
@admin_required
def trigger_now():
    """手动触发一次每日热点采集（不等待定时器）。"""
    try:
        from app.services.task_service import create_task
        from app.tasks.jobs import daily_hot_job
        from app.tasks.runner import submit_background_job

        task = create_task("daily_hot", g.current_user["id"], {"force": True})
        submit_background_job(current_app._get_current_object(), daily_hot_job, task["id"])
        return ok({"task_id": task["id"]}, message="每日热点采集已手动触发")
    except Exception as e:
        return fail(str(e), 500)


def _scheduler():
    scheduler = current_app.extensions.get("task_recovery_scheduler")
    if scheduler is not None:
        return scheduler
    from app.tasks.runner import start_recovery_scheduler

    return start_recovery_scheduler(current_app._get_current_object())
