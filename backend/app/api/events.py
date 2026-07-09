from flask import Blueprint, request

from app.core.response import ok
from app.core.security import login_required
from app.services.event_service import get_event_detail, list_events, search_events


events_bp = Blueprint("events", __name__)


@events_bp.get("")
@login_required
def events():
    return ok(list_events(request.args))


@events_bp.get("/search")
@login_required
def events_search():
    return ok({"events": search_events(request.args.get("q", ""))})


@events_bp.get("/<int:event_id>")
@login_required
def event_detail(event_id: int):
    return ok(get_event_detail(event_id))


@events_bp.get("/<int:event_id>/trend")
@login_required
def event_trend(event_id: int):
    return ok(get_event_detail(event_id)["trend"])


@events_bp.get("/<int:event_id>/sentiment")
@login_required
def event_sentiment(event_id: int):
    return ok(get_event_detail(event_id)["sentiment"])


@events_bp.get("/<int:event_id>/platform")
@login_required
def event_platform(event_id: int):
    return ok(get_event_detail(event_id)["platform"])


@events_bp.get("/<int:event_id>/keywords")
@login_required
def event_keywords(event_id: int):
    return ok(get_event_detail(event_id)["keywords"])


@events_bp.get("/<int:event_id>/articles")
@login_required
def event_articles(event_id: int):
    return ok(get_event_detail(event_id)["articles"])

