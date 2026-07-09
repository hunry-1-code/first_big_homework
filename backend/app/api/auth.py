from flask import Blueprint, current_app, g, request

from app.core.response import fail, ok
from app.core.security import create_token, login_required


auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = payload.get("username", "")
    password = payload.get("password", "")
    if username != current_app.config["DEMO_ADMIN_USERNAME"] or password != current_app.config["DEMO_ADMIN_PASSWORD"]:
        return fail("用户名或密码错误", 401)

    user = {"id": 1, "username": username, "nickname": "管理员", "role": "admin"}
    token, expires_in = create_token(user)
    return ok({"token": token, "expires_in": expires_in, "user": user})


@auth_bp.get("/me")
@login_required
def me():
    user = dict(g.current_user)
    user.setdefault("nickname", "管理员" if user.get("role") == "admin" else user["username"])
    return ok(user)

