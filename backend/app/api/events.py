from flask import Blueprint, request

from app.core.response import fail, ok
from app.core.security import login_required
from app.services.event_service import get_event_detail, get_propagation_data, list_events, search_events
from app.services.event_similarity_service import find_similar_events
from app.services.sentiment_analysis_service import get_event_sentiment


events_bp = Blueprint("events", __name__)


@events_bp.get("")
@login_required
def events():
    try:
        return ok(list_events(request.args))
    except (TypeError, ValueError):
        return fail("page 和 size 必须是整数", 400)


@events_bp.get("/search")
@login_required
def events_search():
    return ok({"events": search_events(request.args.get("q", ""))})


@events_bp.route("/<int:event_id>", methods=["GET", "DELETE"])
@login_required
def event_detail(event_id: int):
    if request.method == "DELETE":
        from app.core.security import admin_required as _admin_required
        try:
            _admin_required(lambda: None)()
        except Exception:
            return fail("需要管理员权限", 403)
        from app.services.event_service import delete_event
        try:
            delete_event(event_id)
            return ok(message="删除成功")
        except KeyError:
            return fail("事件不存在", 404)
    detail = get_event_detail(event_id)
    if detail is None:
        return fail("事件不存在", 404)
    return ok(detail)


@events_bp.get("/<int:event_id>/trend")
@login_required
def event_trend(event_id: int):
    detail = get_event_detail(event_id)
    if detail is None:
        return fail("事件不存在", 404)
    return ok(detail["trend"])


@events_bp.get("/<int:event_id>/sentiment")
@login_required
def event_sentiment(event_id: int):
    sentiment = get_event_sentiment(event_id)
    if sentiment is None:
        return fail("事件不存在", 404)
    return ok(sentiment)


@events_bp.get("/<int:event_id>/platform")
@login_required
def event_platform(event_id: int):
    detail = get_event_detail(event_id)
    if detail is None:
        return fail("事件不存在", 404)
    return ok(detail["platform"])


@events_bp.get("/<int:event_id>/keywords")
@login_required
def event_keywords(event_id: int):
    detail = get_event_detail(event_id)
    if detail is None:
        return fail("事件不存在", 404)
    return ok(detail["keywords"])


@events_bp.get("/<int:event_id>/articles")
@login_required
def event_articles(event_id: int):
    detail = get_event_detail(event_id)
    if detail is None:
        return fail("事件不存在", 404)
    return ok(detail["articles"])


@events_bp.get("/<int:event_id>/propagation")
@login_required
def event_propagation(event_id: int):
    data = get_propagation_data(event_id)
    if data is None:
        return fail("事件不存在", 404)
    return ok(data)


@events_bp.get("/<int:event_id>/similar")
@login_required
def event_similar(event_id: int):
    try:
        limit = int(request.args.get("limit", 5))
    except (TypeError, ValueError):
        return fail("limit 必须是整数", 400)
    if not 1 <= limit <= 20:
        return fail("limit 必须在 1 到 20 之间", 400)
    try:
        events = find_similar_events(event_id, limit=limit)
    except KeyError:
        return fail("事件不存在", 404)
    return ok({"events": events, "total": len(events)})
