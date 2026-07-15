from apscheduler.schedulers.background import BackgroundScheduler

from app.extensions import db
from app.services.task_service import create_or_reuse_recent_task
from app.tasks.jobs import daily_hot_job
from app.tasks.runner import submit_background_job


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    return scheduler


def _daily_hot_payload(app) -> dict:
    return {
        "sources": list(
            app.config.get(
                "DAILY_HOT_SOURCES",
                ["weibo_hot", "baidu_hot", "zhihu_hot"],
            )
        ),
        "source_limit": app.config.get("DAILY_HOT_SOURCE_LIMIT", 30),
        "result_limit": app.config.get("DAILY_HOT_RESULT_LIMIT", 10),
        "rrf_k": app.config.get("DAILY_HOT_RRF_K", 60),
        "ttl_seconds": app.config.get("DAILY_HOT_TTL_SECONDS", 900),
    }


def enqueue_daily_hot_refresh(app) -> dict:
    with app.app_context():
        from app.models import User

        username = str(
            app.config.get("DAILY_HOT_SYSTEM_USERNAME", "admin")
        ).strip()
        actor = User.query.filter_by(username=username, status=1).first()
        if actor is None or actor.role not in {"admin", "system"}:
            raise RuntimeError("daily hot system actor is missing or inactive")
        task, reused = create_or_reuse_recent_task(
            "daily_hot",
            created_by=actor.id,
            payload=_daily_hot_payload(app),
            within_seconds=app.config.get(
                "DAILY_HOT_REFRESH_INTERVAL_SECONDS",
                900,
            ),
        )
        if not reused:
            submit_background_job(app, daily_hot_job, task["id"])
        db.session.remove()
        return task


def register_daily_hot_refresh(app, scheduler, *, interval_seconds: int | None = None) -> None:
    scheduler.add_job(
        lambda: enqueue_daily_hot_refresh(app),
        "interval",
        seconds=max(
            60,
            int(
                interval_seconds
                if interval_seconds is not None
                else app.config.get("DAILY_HOT_REFRESH_INTERVAL_SECONDS", 900)
            ),
        ),
        id="daily-hot-refresh",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )


def set_daily_hot_schedule(
    app,
    scheduler,
    *,
    enabled: bool,
    interval_seconds: int | None = None,
) -> None:
    job = scheduler.get_job("daily-hot-refresh") if hasattr(scheduler, "get_job") else None
    if not enabled:
        if job is not None:
            scheduler.remove_job("daily-hot-refresh")
        return
    register_daily_hot_refresh(
        app,
        scheduler,
        interval_seconds=interval_seconds,
    )

