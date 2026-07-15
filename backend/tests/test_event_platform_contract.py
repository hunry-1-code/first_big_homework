from datetime import timedelta
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.models import Article, Event
from app.services.event_service import get_event_detail


class Config:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    JWT_EXPIRES_DELTA = timedelta(hours=1)
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_DB = False
    TASK_RECOVER_ON_STARTUP = False
    FRONTEND_ORIGINS = []
    LLM_API_KEY = ""


def test_event_detail_keeps_real_news_platform_counts_and_unknown_label():
    app = create_app(Config)
    with app.app_context():
        db.create_all()
        event = Event(title="平台真实性测试")
        db.session.add(event)
        db.session.flush()
        rows = [
            ("news_people", "人民网报道"),
            ("news_people", "人民网跟进"),
            ("news_thepaper", "澎湃报道"),
            ("unknown_source", "未知来源"),
        ]
        for index, (platform, title) in enumerate(rows, start=1):
            db.session.add(
                Article(
                    event_id=event.id,
                    platform=platform,
                    source_type="news",
                    url=f"https://example.com/{index}",
                    url_hash=f"hash-{index}",
                    title=title,
                    clean_content="用于平台统计的正文内容。" * 5,
                    clean_status="success",
                )
            )
        db.session.commit()

        detail = get_event_detail(event.id)

        assert detail is not None
        assert detail["platform"]["platforms"] == [
            {"platform": "人民网", "count": 2, "percentage": 0.5},
            {"platform": "澎湃新闻", "count": 1, "percentage": 0.25},
        ]
        unknown = next(item for item in detail["articles"]["articles"] if item["title"] == "未知来源")
        assert unknown["platform"] == "未知平台"
