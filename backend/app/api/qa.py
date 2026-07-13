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
    return ok(answer_question(g.current_user["id"], question, event_id, platform))


@qa_bp.post("/ask/stream")
@login_required
def ask_stream():
    payload = request.get_json(silent=True) or {}
    question = payload.get("question", "").strip()
    if not question:
        return fail("question 不能为空", 400)
    event_id = payload.get("event_id")
    platform = payload.get("platform")
    return ok(answer_question(g.current_user["id"], question, event_id, platform), message="stream reserved")


@qa_bp.get("/history")
@login_required
def history():
    return ok(list_history(g.current_user["id"]))

