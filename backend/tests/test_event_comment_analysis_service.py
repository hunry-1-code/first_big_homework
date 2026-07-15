import sys
from datetime import timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.models import Event
from app.models import Article, Comment


class C:
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
    app = create_app(C)
    ctx = app.app_context()
    ctx.push()
    db.create_all()


def teardown_function():
    db.session.remove()
    db.drop_all()
    ctx.pop()


def test_event_comment_analysis_upgrades_then_caches_derivatives(monkeypatch):
    from app.services.event_comment_analysis_service import analyze_event_comments

    event = Event(title="张雪峰事件")
    db.session.add(event)
    db.session.commit()
    calls = []
    monkeypatch.setattr(
        "app.services.event_comment_analysis_service.upgrade_comment_sentiments",
        lambda event_id: calls.append(("sentiment", event_id))
        or {"selected": 2, "llm": 2, "snownlp_fallback": 0, "failed": 0},
    )
    monkeypatch.setattr(
        "app.services.event_comment_analysis_service.extract_opinion_themes",
        lambda event_id: calls.append(("themes", event_id))
        or [{"theme": "职业选择", "example": "需要理性判断", "sentiment": "neutral"}],
    )
    monkeypatch.setattr(
        "app.services.event_comment_analysis_service.analyze_narrative_gap",
        lambda event_id: calls.append(("gap", event_id))
        or {"media_focus": "就业", "public_focus": "选择", "gap": "侧重点不同", "intensity": "low"},
    )

    result = analyze_event_comments(event.id)

    assert [name for name, _ in calls] == ["sentiment", "themes", "gap"]
    assert result["sentiment"]["llm"] == 2
    saved = db.session.get(Event, event.id)
    assert saved.metadata_evidence["opinion_themes"][0]["theme"] == "职业选择"
    assert saved.metadata_evidence["narrative_gap_analysis"]["intensity"] == "low"


def test_event_comment_analysis_keeps_sentiment_when_optional_derivative_fails(monkeypatch):
    from app.services.event_comment_analysis_service import analyze_event_comments

    event = Event(title="事件")
    db.session.add(event)
    db.session.commit()
    monkeypatch.setattr(
        "app.services.event_comment_analysis_service.upgrade_comment_sentiments",
        lambda event_id: {"selected": 1, "llm": 0, "snownlp_fallback": 1, "failed": 0},
    )
    monkeypatch.setattr(
        "app.services.event_comment_analysis_service.extract_opinion_themes",
        lambda event_id: (_ for _ in ()).throw(TimeoutError()),
    )
    monkeypatch.setattr(
        "app.services.event_comment_analysis_service.analyze_narrative_gap",
        lambda event_id: None,
    )

    result = analyze_event_comments(event.id)

    assert result["sentiment"]["snownlp_fallback"] == 1
    assert result["warnings"] == ["OPINION_THEMES_FAILED:TimeoutError"]


def test_backfill_selects_only_events_with_comments(monkeypatch):
    from scripts.backfill_event_comment_analysis import select_event_ids, run_backfill

    included = Event(title="有评论")
    excluded = Event(title="无评论")
    db.session.add_all([included, excluded])
    db.session.flush()
    article = Article(
        event_id=included.id,
        platform="bilibili",
        source_type="social",
        url="https://bilibili.com/video/BV1",
        url_hash="backfill-bv1",
        title="视频",
        clean_content="正文",
        clean_status="success",
    )
    db.session.add(article)
    db.session.flush()
    db.session.add(
        Comment(
            article_id=article.id,
            platform="bilibili",
            source_comment_id="backfill-c1",
            content="评论",
            content_hash="hash",
            analysis_status="success",
        )
    )
    db.session.commit()

    assert select_event_ids() == [included.id]
    called = []
    monkeypatch.setattr(
        "scripts.backfill_event_comment_analysis.analyze_event_comments",
        lambda event_id: called.append(event_id) or {"sentiment": {"llm": 1}},
    )
    assert run_backfill([included.id], dry_run=True)["processed"] == 0
    assert called == []
    assert run_backfill([included.id], dry_run=False)["processed"] == 1
    assert called == [included.id]
