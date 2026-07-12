import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import inspect


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.models import Article, Event
from app.models.sentiment import (
    ArticleSentimentResult,
    EventSentimentSnapshot,
    SentimentRun,
)


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FRONTEND_ORIGINS = ["http://localhost:5173"]
    AUTO_CREATE_DB = False


class SentimentMigrationTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_tables_constraints_and_current_summary_fields_exist(self):
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())

        self.assertTrue(
            {"sentiment_run", "article_sentiment_result", "event_sentiment_snapshot"}
            <= tables
        )
        result_uniques = inspector.get_unique_constraints("article_sentiment_result")
        self.assertIn(
            "uq_article_sentiment_run_article",
            {item["name"] for item in result_uniques},
        )
        self.assertTrue(hasattr(Article, "sentiment_confidence"))
        self.assertTrue(hasattr(Article, "current_sentiment_result_id"))
        self.assertTrue(hasattr(Event, "current_sentiment_snapshot_id"))
        self.assertTrue(hasattr(Event, "sentiment_score"))

    def test_models_expose_versions_evidence_and_snapshot_dimensions(self):
        for name in (
            "config_hash",
            "versions",
            "statistics",
            "warnings",
            "attempt",
        ):
            self.assertTrue(hasattr(SentimentRun, name))
        for name in (
            "content_identity",
            "confidence",
            "dimension",
            "target",
            "prompt_version",
            "inherited_from_result_id",
            "weight_details",
        ):
            self.assertTrue(hasattr(ArticleSentimentResult, name))
        for name in (
            "raw_counts",
            "weighted_ratios",
            "daily_trend",
            "platform_distribution",
            "calculation_details",
        ):
            self.assertTrue(hasattr(EventSentimentSnapshot, name))

    def test_sql_file_contains_all_tables_and_summary_columns(self):
        sql = (BACKEND_ROOT / "migrations" / "20260711_sentiment_analysis.sql").read_text(
            encoding="utf-8"
        )
        for value in (
            "sentiment_run",
            "article_sentiment_result",
            "event_sentiment_snapshot",
            "sentiment_confidence",
            "current_sentiment_snapshot_id",
        ):
            self.assertIn(value, sql)

    def test_runner_rejects_non_mysql_url(self):
        from migrations.migrate_sentiment_analysis import migrate

        with tempfile.TemporaryDirectory() as directory:
            sql_path = Path(directory) / "migration.sql"
            sql_path.write_text("SELECT 1;", encoding="utf-8")
            with self.assertRaises(ValueError):
                migrate("sqlite:///example.db", sql_path=sql_path)


if __name__ == "__main__":
    unittest.main()
