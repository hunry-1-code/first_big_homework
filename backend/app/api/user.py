from flask import Blueprint, g, request

from app.core.response import fail, ok
from app.core.security import login_required
from app.services.user_service import get_config, get_profile, list_sources, set_source_followed, update_config, update_profile


user_bp = Blueprint("user", __name__)


@user_bp.get("/profile")
@login_required
def profile():
    return ok(get_profile(g.current_user))


@user_bp.put("/profile")
@login_required
def save_profile():
    return ok(update_profile(g.current_user, request.get_json(silent=True) or {}))


@user_bp.get("/config")
@login_required
def config():
    return ok(get_config(g.current_user["id"]))


@user_bp.put("/config")
@login_required
def save_config():
    return ok(update_config(g.current_user["id"], request.get_json(silent=True) or {}))


@user_bp.get("/sources")
@login_required
def sources():
    return ok({"presets": list_sources()})


@user_bp.route("/sources/<code>/follow", methods=["POST", "DELETE"])
@login_required
def follow_source(code: str):
    try:
        return ok(set_source_followed(g.current_user["id"], code, request.method == "POST"))
    except KeyError as exc:
        return fail(str(exc), 404)


@user_bp.get("/search-history")
@login_required
def search_history():
    from app.services.user_search_history_service import list_search_history
    try:
        return ok(list_search_history(g.current_user["id"], page=int(request.args.get("page", 1)), size=int(request.args.get("size", 20))))
    except ValueError:
        return fail("page 和 size 必须是整数", 400)


@user_bp.delete("/search-history/<int:history_id>")
@login_required
def remove_search_history(history_id: int):
    from app.services.user_search_history_service import delete_search_history
    try:
        delete_search_history(g.current_user["id"], history_id)
        return ok(message="搜索记录已删除")
    except KeyError as exc:
        return fail(str(exc), 404)


@user_bp.post("/search-history/<int:history_id>/repeat")
@login_required
def repeat_search(history_id: int):
    from app.services.user_search_history_service import repeat_search_payload
    try:
        return ok({"search_payload": repeat_search_payload(g.current_user["id"], history_id)})
    except KeyError as exc:
        return fail(str(exc), 404)

