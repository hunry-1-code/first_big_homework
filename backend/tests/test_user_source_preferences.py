import sys
from datetime import timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.core.security import create_token
from app.extensions import db
from app.models import User


class Config:
    TESTING = True
    SECRET_KEY = "x"
    JWT_SECRET_KEY = "x"
    JWT_EXPIRES_DELTA = timedelta(hours=1)
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_DB = False
    TASK_RECOVER_ON_STARTUP = False
    FRONTEND_ORIGINS = []


def setup_function():
    global app, ctx, client, headers, user
    app = create_app(Config)
    ctx = app.app_context()
    ctx.push()
    db.create_all()
    user = User(username="reader", password_hash="unused", role="user", status=1)
    db.session.add(user)
    db.session.commit()
    token, _ = create_token({"id": user.id, "username": user.username, "role": "user"})
    headers = {"Authorization": f"Bearer {token}"}
    client = app.test_client()


def teardown_function():
    db.session.remove()
    db.drop_all()
    ctx.pop()


def test_platform_catalog_contains_official_and_search_urls():
    response = client.get("/api/user/sources", headers=headers)
    assert response.status_code == 200
    rows = response.get_json()["data"]["presets"]
    bilibili = next(row for row in rows if row["code"] == "bilibili")
    assert bilibili["official_url"] == "https://www.bilibili.com"
    assert "{keyword}" in bilibili["search_url"]
    assert bilibili["crawler_supported"] is True
    assert bilibili["comment_supported"] is True


def test_user_can_follow_and_unfollow_catalog_source():
    followed = client.post("/api/user/sources/bilibili/follow", headers=headers)
    assert followed.status_code == 200
    assert "bilibili" in followed.get_json()["data"]["followed_sources"]

    unfollowed = client.delete("/api/user/sources/bilibili/follow", headers=headers)
    assert unfollowed.status_code == 200
    assert "bilibili" not in unfollowed.get_json()["data"]["followed_sources"]


def test_search_history_can_be_listed_deleted_and_reused():
    from app.services.user_search_history_service import record_search

    row = record_search(user.id, "张雪峰", ["bilibili", "weibo"], 50)
    response = client.get("/api/user/search-history", headers=headers)
    assert response.status_code == 200
    item = response.get_json()["data"]["items"][0]
    assert item["keyword"] == "张雪峰"
    assert item["platforms"] == ["bilibili", "weibo"]

    repeat = client.post(f"/api/user/search-history/{row.id}/repeat", headers=headers)
    assert repeat.get_json()["data"]["search_payload"] == {
        "keyword": "张雪峰",
        "platforms": ["bilibili", "weibo"],
        "target_count": 50,
    }

    deleted = client.delete(f"/api/user/search-history/{row.id}", headers=headers)
    assert deleted.status_code == 200
    assert client.get("/api/user/search-history", headers=headers).get_json()["data"]["total"] == 0
