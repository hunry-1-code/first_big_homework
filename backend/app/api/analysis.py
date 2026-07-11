from __future__ import annotations

from flask import Blueprint, current_app, g, request

from app.analysis.result import ContentAnalysisError
from app.core.response import fail, ok
from app.core.security import login_required
from app.services.content_analysis_service import (
    create_analysis_run,
    get_analysis_run,
    list_analysis_runs,
)
from app.services.task_service import create_task
from app.tasks.jobs import analyze_job
from app.tasks.runner import submit_background_job


analysis_bp = Blueprint("analysis", __name__)


def _article_ids(payload: dict) -> list[int] | None:
    values = payload.get("article_ids")
    if not isinstance(values, list) or not values or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in values
    ):
        return None
    return list(dict.fromkeys(values))


def _platforms(payload: dict) -> list[str] | None:
    values = payload.get("platforms", [])
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        return None
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


@analysis_bp.post("/runs")
@login_required
def create_run():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return fail("请求体必须是 JSON 对象", 400)
    article_ids = _article_ids(payload)
    if article_ids is None:
        return fail("article_ids 必须是非空正整数数组", 400)
    mode = str(payload.get("mode") or "search").strip().casefold()
    if mode not in {"search", "hot", "manual"}:
        return fail("mode 必须是 search、hot 或 manual", 400)
    platforms = _platforms(payload)
    if platforms is None:
        return fail("platforms 必须是字符串数组", 400)
    if mode == "search" and not platforms:
        return fail("搜索分析必须选择至少一个平台", 400)
    keyword = payload.get("keyword")
    if keyword is not None and not isinstance(keyword, str):
        return fail("keyword 必须是字符串", 400)
    try:
        run, reused = create_analysis_run(
            article_ids,
            user_id=g.current_user["id"],
            mode=mode,
            keyword=(keyword or "").strip() or None,
            platforms=platforms,
        )
    except (ContentAnalysisError, KeyError, ValueError) as exc:
        return fail(str(exc), 400)
    if reused:
        return ok(
            {"analysis_run_id": run.id, "task_id": None, "reused": True},
            message="已复用相同数据和配置的分析结果。",
        )
    task = create_task(
        "analysis",
        created_by=g.current_user["id"],
        payload={"analysis_run_id": run.id},
    )
    submit_background_job(
        current_app._get_current_object(), analyze_job, task["id"]
    )
    return ok(
        {"analysis_run_id": run.id, "task_id": task["id"], "reused": False},
        message="内容分析任务已启动。",
    )


@analysis_bp.get("/runs")
@login_required
def runs():
    admin = g.current_user.get("role") == "admin"
    return ok(
        {
            "runs": list_analysis_runs(
                user_id=g.current_user["id"], admin=admin
            )
        }
    )


@analysis_bp.get("/runs/<int:analysis_run_id>")
@login_required
def run_detail(analysis_run_id: int):
    admin = g.current_user.get("role") == "admin"
    run = get_analysis_run(
        analysis_run_id, user_id=g.current_user["id"], admin=admin
    )
    if run is None:
        return fail("分析记录不存在或无权查看", 404)
    return ok(run)

