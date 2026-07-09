from flask import Blueprint, g, request

from app.core.response import fail, ok
from app.core.security import admin_required, login_required
from app.services.task_service import create_task, latest_status


crawler_bp = Blueprint("crawler", __name__)


@crawler_bp.post("/trigger")
@admin_required
def trigger():
    payload = request.get_json(silent=True) or {}
    task = create_task("crawl", g.current_user["id"], {"platforms": payload.get("platforms", [])})
    return ok({"task_id": task["id"]}, message="爬取任务已启动")


@crawler_bp.post("/search")
@login_required
def keyword_search():
    payload = request.get_json(silent=True) or {}
    keyword = payload.get("keyword", "").strip()
    if not keyword:
        return fail("keyword 不能为空", 400)
    task = create_task("crawl", g.current_user["id"], {"keyword": keyword, "mode": "keyword"})
    return ok({"task_id": task["id"]}, message="关键词采集任务已启动")


@crawler_bp.get("/status")
@login_required
def status():
    return ok(latest_status())

