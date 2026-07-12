from __future__ import annotations

from threading import RLock

from flask import Blueprint, current_app, g, request

from app.core.response import fail, ok
from app.core.security import admin_required, login_required
from app.extensions import db
from app.services.sentiment_analysis_service import (
    create_sentiment_run,
    get_sentiment_run,
    list_sentiment_results,
    list_sentiment_runs,
)
from app.services.task_service import create_task
from app.tasks.jobs import sentiment_job
from app.tasks.runner import submit_background_job


sentiment_bp = Blueprint("sentiment", __name__)
_RUN_LOCK = RLock()


@sentiment_bp.post("/runs")
@admin_required
def create_run():
    payload = request.get_json(silent=True) or {}
    aggregation_run_id = payload.get("aggregation_run_id")
    if isinstance(aggregation_run_id, bool) or not isinstance(aggregation_run_id, int):
        return fail("aggregation_run_id 必须是正整数", 400)
    with _RUN_LOCK:
        try:
            run, reused = create_sentiment_run(
                aggregation_run_id, user_id=g.current_user["id"]
            )
        except KeyError:
            return fail("事件聚合运行不存在", 404)
        except ValueError as exc:
            return fail(str(exc), 400)
        if reused and run.status == "success":
            return ok(
                {"sentiment_run_id": run.id, "task_id": None, "reused": True},
                message="已复用相同数据和版本的情感分析结果。",
            )
        if reused and run.source_task_id:
            return ok(
                {
                    "sentiment_run_id": run.id,
                    "task_id": run.source_task_id,
                    "reused": True,
                }
            )
        task = create_task(
            "sentiment",
            created_by=g.current_user["id"],
            payload={"sentiment_run_id": run.id},
        )
        run.source_task_id = task["id"]
        db.session.commit()
        submit_background_job(
            current_app._get_current_object(), sentiment_job, task["id"]
        )
    return ok(
        {"sentiment_run_id": run.id, "task_id": task["id"], "reused": False},
        message="情感分析任务已启动。",
    )


@sentiment_bp.get("/runs")
@login_required
def runs():
    return ok(
        {
            "runs": list_sentiment_runs(
                user_id=g.current_user["id"],
                admin=g.current_user.get("role") == "admin",
            )
        }
    )


@sentiment_bp.get("/runs/<int:run_id>")
@login_required
def run_detail(run_id: int):
    data = get_sentiment_run(
        run_id,
        user_id=g.current_user["id"],
        admin=g.current_user.get("role") == "admin",
    )
    return ok(data) if data is not None else fail("情感分析运行不存在", 404)


@sentiment_bp.get("/runs/<int:run_id>/results")
@admin_required
def results(run_id: int):
    if get_sentiment_run(run_id) is None:
        return fail("情感分析运行不存在", 404)
    try:
        page = int(request.args.get("page", 1))
        size = int(request.args.get("size", 50))
    except (TypeError, ValueError):
        return fail("page 和 size 必须是整数", 400)
    return ok(list_sentiment_results(run_id, page=page, size=size))


__all__ = ["sentiment_bp"]
