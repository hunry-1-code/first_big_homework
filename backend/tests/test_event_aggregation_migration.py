import sys
import unittest
from pathlib import Path

from sqlalchemy import inspect


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.models import (
    AggregationAssignment,
    AggregationCluster,
    AggregationRun,
    EventArticleMembership,
    EventMergeRecord,
    EventRepresentation,
)
from migrations.migrate_event_aggregation import _statements, run_migration


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_DB = False
    FRONTEND_ORIGINS = ["http://localhost"]
    TASK_RECOVER_ON_STARTUP = False


class EventAggregationMigrationTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_tables_and_unique_constraints_exist(self):
        inspector = inspect(db.engine)
        expected = {
            "aggregation_run",
            "aggregation_cluster",
            "aggregation_assignment",
            "event_article_membership",
            "event_representation",
            "event_merge_record",
        }
        self.assertTrue(expected.issubset(set(inspector.get_table_names())))

        assignment_uniques = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("aggregation_assignment")
        }
        cluster_uniques = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("aggregation_cluster")
        }
        membership_uniques = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("event_article_membership")
        }
        self.assertIn(("aggregation_run_id", "article_id"), assignment_uniques)
        self.assertIn(("aggregation_run_id", "cluster_index"), cluster_uniques)
        self.assertIn(("active_article_id",), membership_uniques)

    def test_models_expose_version_and_evidence_fields(self):
        self.assertTrue(hasattr(AggregationRun, "config_hash"))
        self.assertTrue(hasattr(AggregationCluster, "resolved_event_id"))
        self.assertTrue(hasattr(AggregationAssignment, "score_details"))
        self.assertTrue(hasattr(EventArticleMembership, "active_article_id"))
        self.assertTrue(hasattr(EventRepresentation, "model_version"))
        self.assertTrue(hasattr(EventMergeRecord, "similarity_evidence"))

    def test_sql_file_contains_all_tables(self):
        sql = (BACKEND_ROOT / "migrations" / "20260711_event_aggregation.sql").read_text(
            encoding="utf-8"
        )
        for name in (
            "aggregation_run",
            "aggregation_cluster",
            "aggregation_assignment",
            "event_article_membership",
            "event_representation",
            "event_merge_record",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {name}", sql)
        self.assertGreaterEqual(len(_statements(sql)), 6)

    def test_runner_rejects_non_mysql_url(self):
        with self.assertRaises(RuntimeError):
            run_migration("sqlite:///:memory:")


if __name__ == "__main__":
    unittest.main()
