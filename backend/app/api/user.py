from flask import Blueprint, g, request

from app.core.response import ok
from app.core.security import login_required
from app.services.user_service import get_config, get_profile, list_sources, update_config, update_profile


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

