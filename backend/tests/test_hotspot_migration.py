import sys
import unittest
from pathlib import Path

from sqlalchemy import inspect


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.models import Event, EventHeatSnapshot, HotSeedExpansion, HotspotRun, TopicArticleAssignment, TopicResult
from migrations.migrate_hotspot_discovery import SQL_PATH, _statements, run_migration


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FRONTEND_ORIGINS = ["http://localhost:5173"]


class HotspotSchemaTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_hotspot_tables_and_event_summary_columns_exist(self):
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())

        self.assertTrue(
            {
                "hotspot_run",
                "topic_result",
                "topic_article_assignment",
                "event_heat_snapshot",
                "hot_seed_expansion",
            }.issubset(tables)
        )
        event_columns = {item["name"] for item in inspector.get_columns("event")}
        self.assertTrue(
            {
                "current_heat_snapshot_id",
                "core_heat",
                "spread_heat",
                "is_hot",
                "hot_rank",
                "topic_category",
                "topic_name",
                "first_publish_time",
                "last_activity_time",
                "independent_report_count",
                "platform_count",
                "time_confidence",
            }.issubset(event_columns)
        )
        event_foreign_keys = {
            tuple(item["constrained_columns"])
            for item in inspector.get_foreign_keys("event")
        }
        self.assertIn(("current_heat_snapshot_id",), event_foreign_keys)

    def test_hotspot_unique_constraints_exist(self):
        inspector = inspect(db.engine)
        topic_uniques = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("topic_result")
        }
        snapshot_uniques = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("event_heat_snapshot")
        }
        assignment_uniques = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("topic_article_assignment")
        }

        self.assertIn(("hotspot_run_id", "topic_index"), topic_uniques)
        self.assertIn(("hotspot_run_id", "event_id"), snapshot_uniques)
        self.assertIn(
            ("hotspot_run_id", "topic_result_id", "article_id"),
            assignment_uniques,
        )

    def test_models_expose_json_and_status_fields(self):
        self.assertTrue(hasattr(HotspotRun, "lda_config"))
        self.assertTrue(hasattr(HotspotRun, "attempt"))
        self.assertTrue(hasattr(HotspotRun, "metrics"))
        self.assertTrue(hasattr(TopicResult, "keywords"))
        self.assertTrue(hasattr(TopicArticleAssignment, "probabilities"))
        self.assertTrue(hasattr(EventHeatSnapshot, "raw_statistics"))
        self.assertTrue(hasattr(EventHeatSnapshot, "calculation_details"))
        self.assertTrue(hasattr(HotSeedExpansion, "seed_article_id"))
        self.assertTrue(hasattr(HotSeedExpansion, "article_id"))
        self.assertTrue(hasattr(Event, "current_heat_snapshot_id"))


class HotspotMigrationTest(unittest.TestCase):
    def test_sql_contains_hotspot_tables_and_event_columns(self):
        sql = SQL_PATH.read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS hotspot_run", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS topic_result", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS event_heat_snapshot", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS hot_seed_expansion", sql)
        self.assertIn("current_heat_snapshot_id", sql)
        self.assertIn("fk_event_current_heat_snapshot", sql)
        self.assertGreater(len(_statements(sql)), 4)

    def test_runner_rejects_non_mysql_url(self):
        with self.assertRaises(RuntimeError):
            run_migration("sqlite:///example.db")


if __name__ == "__main__":
    unittest.main()
