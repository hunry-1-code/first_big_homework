import hashlib
import os

from flask import Blueprint, current_app, g, request

from app.core.response import fail, ok
from app.core.security import create_token, login_required
from app.extensions import db
from app.models.user import User


auth_bp = Blueprint("auth", __name__)


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """使用 PBKDF2-SHA256 对密码进行哈希。"""
    salt = salt or os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return salt + ":" + dk.hex(), salt


def _verify_password(password: str, stored: str) -> bool:
    """验证密码是否与存储的哈希匹配。"""
    try:
        salt, _ = stored.split(":", 1)
        hashed, _ = _hash_password(password, salt)
        return hashed == stored
    except (ValueError, AttributeError):
        return False


def _ensure_demo_admin(username: str, password: str) -> User | None:
    """如果 demo admin 凭据匹配，确保数据库中存在对应用户。"""
    demo_user = current_app.config.get("DEMO_ADMIN_USERNAME", "admin")
    demo_pass = current_app.config.get("DEMO_ADMIN_PASSWORD", "admin123")
    if username != demo_user or password != demo_pass:
        return None
    user = User.query.filter_by(username=demo_user).first()
    if user is None:
        hashed, _ = _hash_password(demo_pass)
        user = User(
            username=demo_user,
            password_hash=hashed,
            nickname="管理员",
            role="admin",
        )
        db.session.add(user)
        db.session.commit()
    return user


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = payload.get("username", "").strip()
    password = payload.get("password", "")

    # 尝试 demo admin 快速通道
    user_model = _ensure_demo_admin(username, password)

    # 常规数据库认证
    if user_model is None:
        user_model = User.query.filter_by(username=username).first()
        if user_model is None or not _verify_password(password, user_model.password_hash or ""):
            return fail("用户名或密码错误", 401)

    user = {
        "id": user_model.id,
        "username": user_model.username,
        "nickname": user_model.nickname or user_model.username,
        "role": user_model.role or "user",
    }
    token, expires_in = create_token(user)
    return ok({"token": token, "expires_in": expires_in, "user": user})


@auth_bp.get("/me")
@login_required
def me():
    user = dict(g.current_user)
    user.setdefault("nickname", "管理员" if user.get("role") == "admin" else user["username"])
    return ok(user)
