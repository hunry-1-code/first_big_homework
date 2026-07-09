from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps

import jwt
from flask import current_app, g, request

from app.core.response import fail


def create_token(user: dict) -> tuple[str, int]:
    expires_delta = current_app.config["JWT_EXPIRES_DELTA"]
    expires_at = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user.get("role", "user"),
        "exp": expires_at,
    }
    token = jwt.encode(payload, current_app.config["JWT_SECRET_KEY"], algorithm="HS256")
    return token, int(expires_delta.total_seconds())


def decode_token(token: str) -> dict:
    return jwt.decode(token, current_app.config["JWT_SECRET_KEY"], algorithms=["HS256"])


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return fail("缺少或无效的 Authorization Token", 401)
        token = auth_header.removeprefix("Bearer ").strip()
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            return fail("登录已过期，请重新登录", 401)
        except jwt.PyJWTError:
            return fail("Token 校验失败", 401)

        g.current_user = {
            "id": int(payload["sub"]),
            "username": payload["username"],
            "role": payload.get("role", "user"),
        }
        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    @login_required
    @wraps(view)
    def wrapper(*args, **kwargs):
        if getattr(g, "current_user", {}).get("role") != "admin":
            return fail("需要管理员权限", 403)
        return view(*args, **kwargs)

    return wrapper

