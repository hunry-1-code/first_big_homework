from datetime import datetime, timedelta
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.models import Article, Comment, Event
from app.services.lifecycle_service import build_daily_lifecycle_series
from app.services.lifecycle_explanation_service import explain_lifecycle


class Config:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_DB = False
    TASK_RECOVER_ON_STARTUP = False
    FRONTEND_ORIGINS = []


def test_daily_lifecycle_series_uses_one_aligned_date_axis():
    app = create_app(Config)
    with app.app_context():
        db.create_all()
        event = Event(title="生命周期")
        db.session.add(event)
        db.session.flush()
        day1 = datetime(2026, 7, 10, 8)
        day3 = day1 + timedelta(days=2)
        first = Article(
            event_id=event.id,
            platform="news_people",
            source_type="news",
            url="https://example.com/1",
            url_hash="life-1",
            title="第一天",
            clean_content="正文" * 30,
            clean_status="success",
            publish_time=day1,
        )
        second = Article(
            event_id=event.id,
            platform="bilibili",
            source_type="social",
            url="https://example.com/2",
            url_hash="life-2",
            title="第三天",
            clean_content="正文" * 30,
            clean_status="success",
            publish_time=day3,
        )
        db.session.add_all([first, second])
        db.session.flush()
        db.session.add(
            Comment(
                article_id=second.id,
                platform="bilibili",
                source_comment_id="life-comment",
                content="争议评论",
                content_hash="life-comment-hash",
                sentiment_label="negative",
            )
        )
        db.session.commit()

        series = build_daily_lifecycle_series([first, second])

        assert series["dates"] == ["2026-07-10", "2026-07-11", "2026-07-12"]
        assert series["articles"] == [1, 0, 1]
        assert series["comments"] == [0, 0, 1]
        assert series["platforms"] == [1, 0, 1]
        assert series["sentiment_polarity"] == [0.0, 0.0, 1.0]


def test_lifecycle_llm_explanation_is_validated_and_rule_stage_is_preserved():
    class Client:
        model_name = "test-model"

        def chat(self, messages, **kwargs):
            return {
                "model": "test-model",
                "content": '{"trend_explanation":"报道与评论同步上升","next_stage_reason":"可能接近高潮期","risks":["样本仅三天"]}',
            }

    result = explain_lifecycle(
        event_title="测试事件",
        stage="成长期",
        confidence=0.7,
        momentum=0.4,
        next_stage_hint="高潮期",
        series={
            "dates": ["d1", "d2", "d3"],
            "articles": [1, 3, 6],
            "comments": [2, 8, 20],
            "sentiment_polarity": [0.1, 0.2, 0.5],
            "platforms": [1, 2, 3],
        },
        client=Client(),
    )

    assert result["status"] == "success"
    assert result["rule_stage"] == "成长期"
    assert result["trend_explanation"] == "报道与评论同步上升"
    assert result["next_stage_reason"] == "可能接近高潮期"
