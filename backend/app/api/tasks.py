from flask import Blueprint, current_app, g

from app.core.response import fail, ok
from app.core.security import admin_required, login_required
from app.services.task_service import create_or_reuse_recent_task, get_task, list_tasks, sanitize_task


tasks_bp = Blueprint("tasks", __name__)


@tasks_bp.get("/<int:task_id>")
@login_required
def task_detail(task_id: int):
    task = get_task(task_id)
    if not task:
        return fail("任务不存在", 404)
    if task["created_by"] != g.current_user["id"] and g.current_user["role"] != "admin":
        return fail("无权查看该任务", 403)
    return ok(sanitize_task(task))


@tasks_bp.post("/<int:task_id>/retry-analysis")
@login_required
def retry_analysis(task_id: int):
    """在已采集的数据上重新运行分析管线，不重新爬取。"""
    from app.extensions import db
    from app.models.article import Article
    from app.models.task import Task
    from app.tasks.runner import submit_background_job

    task = db.session.get(Task, task_id)
    if task is None:
        return fail("任务不存在", 404)
    if task.created_by != g.current_user["id"] and g.current_user.get("role") != "admin":
        return fail("无权操作该任务", 403)

    # 找到该任务已采集的所有文章
    articles = Article.query.filter_by(crawl_task_id=task_id).all()
    article_ids = [a.id for a in articles]
    if not article_ids:
        return fail("该任务没有已采集的文章数据，无法重新分析", 400)

    payload = task.payload or {}
    keyword = payload.get("keyword")
    platforms = payload.get("platforms")

    # 创建新的分析子任务
    retry_payload = {
        "keyword": keyword,
        "platforms": platforms,
        "article_ids": article_ids,
        "mode": "retry_analysis",
        "original_task_id": task_id,
    }
    user_id = g.current_user["id"]

    # 直接复用原任务，不创建新任务
    from app.extensions import db
    from app.models.task import Task
    from app.services.task_service import update_task, record_stage

    # 重置原任务状态
    update_task(task_id, status="running", progress=0, message="正在复用已采集数据，重新分析...")
    # 清除旧阶段记录
    t = db.session.get(Task, task_id)
    if t:
        t.stages = []
        db.session.commit()

    def retry_job(tid: int):
        from app.tasks.jobs import run_search_analysis_pipeline
        return run_search_analysis_pipeline(
            tid, article_ids, keyword=keyword, platforms=platforms, user_id=user_id, original_task_id=task_id
        )

    from app.tasks.runner import submit_background_job
    submit_background_job(current_app._get_current_object(), retry_job, task_id)
    return ok({"task_id": task_id}, message=f"重新分析已启动，将复用已采集的 {len(article_ids)} 篇文章。")


@tasks_bp.delete("/<int:task_id>")
@admin_required
def delete_task(task_id: int):
    from app.extensions import db
    from app.models.task import Task
    t = db.session.get(Task, task_id)
    if t is None:
        return fail("任务不存在", 404)
    db.session.delete(t)
    db.session.commit()
    return ok(message="已删除")


@tasks_bp.get("/my")
@login_required
def my_tasks():
    return ok({"tasks": [sanitize_task(task) for task in list_tasks(created_by=g.current_user["id"])]})


@tasks_bp.get("")
@admin_required
def all_tasks():
    return ok({"tasks": [sanitize_task(task) for task in list_tasks()]})
