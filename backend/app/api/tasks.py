from flask import Blueprint, g

from app.core.response import fail, ok
from app.core.security import admin_required, login_required
from app.services.task_service import get_task, list_tasks, sanitize_task


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
