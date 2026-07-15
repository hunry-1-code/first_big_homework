DEFAULT_CONFIG = {
    "followed_sources": ["sample", "news"],
    "keywords": ["舆情", "食品安全", "网络暴力"],
}


def get_profile(current_user: dict) -> dict:
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "nickname": "管理员" if current_user["role"] == "admin" else current_user["username"],
        "role": current_user["role"],
    }


def update_profile(current_user: dict, payload: dict) -> dict:
    from app.extensions import db
    from app.models import User
    profile = get_profile(current_user)
    if "nickname" in payload:
        profile["nickname"] = str(payload["nickname"]).strip()[:50]
    if "password" in payload:
        pwd = str(payload["password"]).strip()
        if 6 <= len(pwd) <= 128:
            from app.api.auth import _hash_password
            user = db.session.get(User, int(current_user["id"]))
            if user:
                hashed, _ = _hash_password(pwd)
                user.password_hash = hashed
                db.session.commit()
    return profile


def get_config(user_id: int) -> dict:
    from app.models.user_config import UserConfig
    row = UserConfig.query.filter_by(user_id=user_id).first()
    if row:
        return {
            "user_id": user_id,
            "followed_sources": row.followed_sources or DEFAULT_CONFIG["followed_sources"],
            "keywords": row.keywords or DEFAULT_CONFIG["keywords"],
        }
    return {"user_id": user_id, **DEFAULT_CONFIG}


def update_config(user_id: int, payload: dict) -> dict:
    from app.extensions import db
    from app.models.user_config import UserConfig
    row = UserConfig.query.filter_by(user_id=user_id).first()
    if row is None:
        row = UserConfig(user_id=user_id)
        db.session.add(row)
    row.followed_sources = payload.get("followed_sources", DEFAULT_CONFIG["followed_sources"])
    row.keywords = payload.get("keywords", DEFAULT_CONFIG["keywords"])
    db.session.commit()
    return {
        "user_id": user_id,
        "followed_sources": row.followed_sources,
        "keywords": row.keywords,
    }


def list_sources() -> list[dict]:
    from app.services.platform_catalog_service import list_platform_catalog
    return list_platform_catalog()


def set_source_followed(user_id: int, code: str, followed: bool) -> dict:
    from app.services.platform_catalog_service import platform_codes
    if code not in platform_codes():
        raise KeyError("平台不存在")
    current = get_config(user_id)
    values = list(current.get("followed_sources") or [])
    if followed and code not in values:
        values.append(code)
    if not followed:
        values = [item for item in values if item != code]
    return update_config(user_id, {"followed_sources": values, "keywords": current.get("keywords") or []})

