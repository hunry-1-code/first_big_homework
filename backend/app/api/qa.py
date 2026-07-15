from flask import Blueprint, g, request

from app.core.response import fail, ok
from app.core.security import login_required
from app.services.qa_service import answer_question, list_history


qa_bp = Blueprint("qa", __name__)


@qa_bp.post("/ask")
@login_required
def ask():
    payload = request.get_json(silent=True) or {}
    question = payload.get("question", "").strip()
    if not question:
        return fail("question 不能为空", 400)
    event_id = payload.get("event_id")
    platform = payload.get("platform")
    use_history = payload.get("use_history", True)
    deep_thinking = payload.get("deep_thinking", False)
    return ok(answer_question(g.current_user["id"], question, event_id, platform, use_history=use_history, deep_thinking=deep_thinking))


@qa_bp.post("/ask/stream")
@login_required
def ask_stream():
    payload = request.get_json(silent=True) or {}
    question = payload.get("question", "").strip()
    if not question:
        return fail("question 不能为空", 400)
    event_id = payload.get("event_id")
    platform = payload.get("platform")
    use_history = payload.get("use_history", True)
    deep_thinking = payload.get("deep_thinking", False)
    return ok(answer_question(g.current_user["id"], question, event_id, platform, use_history=use_history, deep_thinking=deep_thinking), message="stream reserved")


@qa_bp.get("/history")
@login_required
def history():
    return ok(list_history(g.current_user["id"]))


@qa_bp.delete("/history")
@login_required
def clear_history():
    """清空当前用户全部或指定事件的问答历史。"""
    from app.extensions import db
    from app.models.qa_history import QaHistory
    event_id = request.args.get("event_id", type=int)
    query = QaHistory.query.filter_by(user_id=g.current_user["id"])
    if event_id:
        query = query.filter_by(event_id=event_id)
    deleted = query.delete()
    db.session.commit()
    return ok({"deleted": deleted}, message=f"已清空 {deleted} 条历史记录")

