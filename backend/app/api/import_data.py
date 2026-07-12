from flask import Blueprint, current_app, g, request

from app.core.response import fail, ok
from app.core.security import admin_required
from app.services.import_service import validate_json_documents
from app.services.task_service import create_task
from app.tasks.jobs import import_job
from app.tasks.runner import submit_background_job


import_bp = Blueprint("import", __name__)


@import_bp.post("/json")
@admin_required
def import_json():
    documents = request.get_json(silent=True)
    if not isinstance(documents, list):
        return fail("请求体必须是 JSON 数组", 400)
    normalized, errors = validate_json_documents(documents)
    if errors:
        return fail("样例数据校验失败", 400, {"errors": errors})
    task = create_task(
        "import",
        g.current_user["id"],
        {"count": len(normalized), "documents": normalized},
    )
    submit_background_job(current_app._get_current_object(), import_job, task["id"])
    return ok({"task_id": task["id"], "count": len(normalized)}, message="导入任务已创建")
