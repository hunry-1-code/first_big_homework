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
from app.models import DailyHotItem, DailyHotRun
from migrations.migrate_daily_hot import migrate


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_DB = False
    FRONTEND_ORIGINS = ["http://localhost"]
    TASK_RECOVER_ON_STARTUP = False


class DailyHotMigrationTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_models_create_tables_and_constraints(self):
        inspector = inspect(db.engine)
        self.assertTrue(
            {"daily_hot_run", "daily_hot_item"}.issubset(
                set(inspector.get_table_names())
            )
        )
        run_uniques = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("daily_hot_run")
        }
        item_uniques = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("daily_hot_item")
        }
        self.assertIn(("run_date", "config_hash"), run_uniques)
        self.assertIn(("run_id", "normalized_key"), item_uniques)
        self.assertIn(("run_id", "rank"), item_uniques)

    def test_models_expose_json_and_nullable_enrichment_fields(self):
        for name in ("available_sources", "failed_sources", "errors"):
            self.assertTrue(hasattr(DailyHotRun, name))
        for name in ("source_ranks", "source_payloads"):
            self.assertTrue(hasattr(DailyHotItem, name))
        self.assertTrue(DailyHotItem.__table__.c.event_id.nullable)
        self.assertTrue(DailyHotItem.__table__.c.analysis_task_id.nullable)

    def test_sql_contains_both_tables_and_foreign_keys(self):
        sql = (BACKEND_ROOT / "migrations" / "20260713_daily_hot.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS daily_hot_run", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS daily_hot_item", sql)
        self.assertIn("FOREIGN KEY (event_id) REFERENCES event(id)", sql)
        self.assertIn("FOREIGN KEY (analysis_task_id) REFERENCES task(id)", sql)

    def test_sqlite_runner_creates_tables_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "daily-hot.db"
            url = f"sqlite:///{path.as_posix()}"

            migrate(url)
            migrate(url)

            from sqlalchemy import create_engine

            engine = create_engine(url)
            tables = set(inspect(engine).get_table_names())
            engine.dispose()
            self.assertTrue({"daily_hot_run", "daily_hot_item"}.issubset(tables))


if __name__ == "__main__":
    unittest.main()
