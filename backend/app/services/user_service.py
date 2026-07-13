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
    return {"user_id": user_id, **DEFAULT_CONFIG}


def update_config(user_id: int, payload: dict) -> dict:
    followed_sources = payload.get("followed_sources", DEFAULT_CONFIG["followed_sources"])
    keywords = payload.get("keywords", DEFAULT_CONFIG["keywords"])
    return {"user_id": user_id, "followed_sources": followed_sources, "keywords": keywords}


def list_sources() -> list[dict]:
    return [
        {"platform": "样例数据", "code": "sample", "type": "sample"},
        {"platform": "新闻网页", "code": "news", "type": "news"},
        {"platform": "热搜/热榜", "code": "hotlist", "type": "hotlist"},
        {"platform": "社交平台", "code": "social", "type": "social"},
    ]

