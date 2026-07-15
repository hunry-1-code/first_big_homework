import sys
from datetime import datetime, timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.models import Event


class Config:
    TESTING = True
    SECRET_KEY = "x"
    JWT_SECRET_KEY = "x"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_DB = False
    TASK_RECOVER_ON_STARTUP = False
    FRONTEND_ORIGINS = []
    JWT_EXPIRES_DELTA = timedelta(hours=1)


def setup_function():
    global app, ctx
    app = create_app(Config)
    ctx = app.app_context()
    ctx.push()
    db.create_all()


def teardown_function():
    db.session.remove()
    db.drop_all()
    ctx.pop()


def test_prediction_payload_exposes_rule_and_llm_evidence():
    from app.services.lifecycle_prediction_service import build_prediction_payload

    event = Event(
        title="张雪峰事件",
        lifecycle_stage="成长期",
        lifecycle_status="sufficient",
        lifecycle_confidence=0.65,
        lifecycle_updated_at=datetime(2026, 7, 15, 8),
        lifecycle_evidence={
            "total_articles": 63,
            "total_comments": 472,
            "recent_articles_24h": 13,
            "recent_comments_24h": 94,
            "comment_growing": True,
            "sentiment_polarizing": True,
            "momentum": 1.0,
            "next_stage_hint": "高潮期",
            "llm_status": "success",
            "llm_model": "deepseek-v4-flash",
            "trend_explanation": "讨论量快速增长",
            "next_stage_reason": "动量较高",
            "trend_risks": ["样本限制"],
        },
    )
    db.session.add(event)
    db.session.commit()

    result = build_prediction_payload(event)

    assert result["current_stage"] == "成长期"
    assert result["next_stage"] == "高潮期"
    assert result["trend_direction"] == "上升"
    assert result["analysis_status"] == "success"
    assert result["model"] == "deepseek-v4-flash"
    assert result["evidence"]["recent_comments"] == 94


def test_prediction_endpoint_requires_login_and_returns_contract():
    from app.models import User

    user = User(username="tester", password_hash="unused", role="user")
    db.session.add(user)
    event = Event(title="事件", lifecycle_stage="潜伏期", lifecycle_status="sufficient", lifecycle_confidence=0.5)
    db.session.add(event)
    db.session.commit()
    client = app.test_client()

    unauthenticated = client.get(f"/api/events/{event.id}/prediction")
    assert unauthenticated.status_code in {401, 422}
