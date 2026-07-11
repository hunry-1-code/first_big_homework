from __future__ import annotations

from threading import RLock

from flask import Blueprint, current_app, g, request

from app.core.response import fail, ok
from app.core.security import admin_required, login_required
from app.extensions import db
from app.services.event_aggregation_service import (
    create_aggregation_run,
    get_aggregation_run,
    list_aggregation_assignments,
    list_aggregation_clusters,
    list_aggregation_runs,
    list_merge_candidates,
    publish_cluster,
    review_merge_candidate,
)
from app.services.task_service import create_task
from app.services.sentiment_analysis_service import get_cluster_sentiment
from app.tasks.jobs import aggregation_job
from app.tasks.runner import submit_background_job


aggregation_bp = Blueprint("aggregation", __name__)
_RUN_TASK_LOCK = RLock()


@aggregation_bp.post("/runs")
@admin_required
def create_run():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return fail("请求体必须是 JSON 对象", 400)
    analysis_run_id = payload.get("analysis_run_id")
    hotspot_run_id = payload.get("hotspot_run_id")
    if isinstance(analysis_run_id, bool) or not isinstance(analysis_run_id, int):
        return fail("analysis_run_id 必须是正整数", 400)
    if hotspot_run_id is not None and (
        isinstance(hotspot_run_id, bool) or not isinstance(hotspot_run_id, int)
    ):
        return fail("hotspot_run_id 必须是正整数", 400)
    with _RUN_TASK_LOCK:
        try:
            run, reused = create_aggregation_run(
                analysis_run_id,
                hotspot_run_id=hotspot_run_id,
                user_id=g.current_user["id"],
            )
        except (KeyError, ValueError) as exc:
            return fail(str(exc), 400)
        if reused and run.status == "success":
            return ok(
                {"aggregation_run_id": run.id, "task_id": None, "reused": True},
                message="已复用相同数据和配置的事件聚合结果。",
            )
        if reused and run.source_task_id is not None:
            return ok(
                {
                    "aggregation_run_id": run.id,
                    "task_id": run.source_task_id,
                    "reused": True,
                },
                message="已存在相同的事件聚合任务。",
            )
        task = create_task(
            "aggregation",
            created_by=g.current_user["id"],
            payload={"aggregation_run_id": run.id},
        )
        run.source_task_id = task["id"]
        db.session.commit()
        submit_background_job(
            current_app._get_current_object(), aggregation_job, task["id"]
        )
    return ok(
        {"aggregation_run_id": run.id, "task_id": task["id"], "reused": False},
        message="事件聚合任务已启动。",
    )


@aggregation_bp.get("/runs")
@login_required
def runs():
    return ok(
        {
            "runs": list_aggregation_runs(
                user_id=g.current_user["id"],
                admin=g.current_user.get("role") == "admin",
            )
        }
    )


@aggregation_bp.get("/runs/<int:run_id>")
@login_required
def run_detail(run_id: int):
    data = get_aggregation_run(
        run_id,
        user_id=g.current_user["id"],
        admin=g.current_user.get("role") == "admin",
    )
    if data is None:
        return fail("事件聚合运行不存在", 404)
    return ok(data)


def _page_args(default_size: int):
    try:
        return int(request.args.get("page", 1)), int(request.args.get("size", default_size))
    except (TypeError, ValueError):
        raise ValueError("page 和 size 必须是整数")


@aggregation_bp.get("/runs/<int:run_id>/clusters")
@login_required
def clusters(run_id: int):
    if get_aggregation_run(
        run_id,
        user_id=g.current_user["id"],
        admin=g.current_user.get("role") == "admin",
    ) is None:
        return fail("事件聚合运行不存在", 404)
    try:
        page, size = _page_args(20)
        return ok(list_aggregation_clusters(run_id, page=page, size=size))
    except ValueError as exc:
        return fail(str(exc), 400)


@aggregation_bp.get("/clusters/<int:cluster_id>/sentiment")
@login_required
def cluster_sentiment(cluster_id: int):
    from app.models import AggregationCluster

    cluster = db.session.get(AggregationCluster, int(cluster_id))
    if cluster is None or get_aggregation_run(
        cluster.aggregation_run_id,
        user_id=g.current_user["id"],
        admin=g.current_user.get("role") == "admin",
    ) is None:
        return fail("事件簇不存在", 404)
    sentiment = get_cluster_sentiment(cluster.id)
    return ok(sentiment) if sentiment is not None else fail("事件簇尚无情感结果", 404)


@aggregation_bp.get("/runs/<int:run_id>/assignments")
@admin_required
def assignments(run_id: int):
    if get_aggregation_run(run_id) is None:
        return fail("事件聚合运行不存在", 404)
    try:
        page, size = _page_args(50)
        return ok(list_aggregation_assignments(run_id, page=page, size=size))
    except ValueError as exc:
        return fail(str(exc), 400)


@aggregation_bp.post("/clusters/<int:cluster_id>/publish")
@admin_required
def publish(cluster_id: int):
    try:
        return ok(
            publish_cluster(cluster_id, user_id=g.current_user["id"]),
            message="搜索事件已发布到正式事件库。",
        )
    except KeyError:
        return fail("事件簇不存在", 404)
    except ValueError as exc:
        return fail(str(exc), 400)


@aggregation_bp.get("/merge-candidates")
@admin_required
def merge_candidates():
    status = str(request.args.get("status", "pending")).strip() or "pending"
    if status not in {"pending", "confirmed", "rejected"}:
        return fail("status 必须是 pending、confirmed 或 rejected", 400)
    return ok({"candidates": list_merge_candidates(status=status)})


def _review_merge(record_id: int, approve: bool):
    try:
        return ok(
            review_merge_candidate(
                record_id,
                approve=approve,
                reviewer_id=g.current_user["id"],
            )
        )
    except KeyError:
        return fail("事件合并候选不存在", 404)
    except ValueError as exc:
        return fail(str(exc), 400)


@aggregation_bp.post("/merge-candidates/<int:record_id>/confirm")
@admin_required
def confirm_merge(record_id: int):
    return _review_merge(record_id, True)


@aggregation_bp.post("/merge-candidates/<int:record_id>/reject")
@admin_required
def reject_merge(record_id: int):
    return _review_merge(record_id, False)


__all__ = ["aggregation_bp"]
