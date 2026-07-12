import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.crawler.base import RawDocument
from app.extensions import db
from app.models import Article, ArticleSnapshot, DocumentFeatures, ProcessingLog, Task
from app.services import article_pipeline_service
from app.services.article_pipeline_service import persist_raw_document
from app.services import task_service
from app.services.task_service import create_task
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.schema import CreateTable


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FRONTEND_ORIGINS = ["http://localhost:5173"]


class PersistenceTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _document(self, likes=10):
        return RawDocument(
            platform="sample",
            source_url="sample://event/1",
            source_article_id="1",
            title="样例公共事件",
            raw_content="这是用于持久化测试的公共事件正文。" * 20,
            source_type="sample",
            content_type="text",
            author="样例媒体",
            publish_time="2026-07-10T08:00:00+08:00",
            likes_count=likes,
            raw_json={"source": "test"},
        )

    def test_first_observation_persists_article_snapshot_features_and_logs(self):
        article, output = persist_raw_document(self._document(), task_id=None)

        self.assertEqual(output.clean_status, "success")
        self.assertEqual(Article.query.count(), 1)
        self.assertEqual(ArticleSnapshot.query.count(), 1)
        self.assertEqual(DocumentFeatures.query.count(), 1)
        self.assertGreaterEqual(ProcessingLog.query.count(), 7)
        self.assertEqual(article.raw_content, self._document().raw_content)
        self.assertTrue(article.clean_content)
        self.assertEqual(article.latest_snapshot_id, ArticleSnapshot.query.first().id)

    def test_second_observation_updates_article_and_creates_metric_only_snapshot(self):
        first, _ = persist_raw_document(self._document(likes=10), task_id=None)
        first_snapshot = ArticleSnapshot.query.first()
        first_snapshot.crawled_at = (
            datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        )
        db.session.commit()
        second, _ = persist_raw_document(self._document(likes=25), task_id=None)

        self.assertEqual(first.id, second.id)
        self.assertEqual(Article.query.count(), 1)
        self.assertEqual(ArticleSnapshot.query.count(), 2)
        snapshots = ArticleSnapshot.query.order_by(ArticleSnapshot.id).all()
        self.assertIsNotNone(snapshots[0].raw_content)
        self.assertIsNone(snapshots[1].raw_content)
        self.assertEqual(second.likes_count, 25)

    def test_identical_observation_does_not_create_snapshot_or_repeat_features(self):
        persist_raw_document(self._document(likes=10), task_id=None)
        persist_raw_document(self._document(likes=10), task_id=None)

        self.assertEqual(ArticleSnapshot.query.count(), 1)
        self.assertEqual(DocumentFeatures.query.count(), 1)

    def test_duplicate_chain_always_points_to_group_representative(self):
        text = "这是同一篇被多个平台转载的公共事件报道。" * 20
        first = self._document()
        first.raw_content = text
        representative, _ = persist_raw_document(first, task_id=None)

        second = self._document()
        second.platform = "baidu"
        second.source_url = "https://example.com/duplicate-2"
        second.source_article_id = "2"
        second.raw_content = text
        duplicate, _ = persist_raw_document(second, task_id=None)

        third = self._document()
        third.platform = "zhihu"
        third.source_url = "https://example.com/duplicate-3"
        third.source_article_id = "3"
        third.raw_content = text
        third_duplicate, _ = persist_raw_document(third, task_id=None)

        self.assertEqual(duplicate.duplicate_of_id, representative.id)
        self.assertEqual(third_duplicate.duplicate_of_id, representative.id)

    def test_mysql_schema_uses_longtext_for_raw_and_clean_content(self):
        article_sql = str(CreateTable(Article.__table__).compile(dialect=mysql.dialect()))
        snapshot_sql = str(
            CreateTable(ArticleSnapshot.__table__).compile(dialect=mysql.dialect())
        )

        self.assertGreaterEqual(article_sql.count("LONGTEXT"), 2)
        self.assertIn("LONGTEXT", snapshot_sql)

    def test_existing_article_lookup_uses_database_row_lock(self):
        self.assertTrue(hasattr(article_pipeline_service, "_existing_article_query"))
        query = article_pipeline_service._existing_article_query(
            {
                "url_hash": "a" * 64,
                "platform": "sample",
                "source_article_id": "1",
            }
        )

        sql = str(query.statement.compile(dialect=mysql.dialect()))

        self.assertIn("FOR UPDATE", sql)

    def test_duplicate_representative_chain_resolves_under_row_lock(self):
        self.assertTrue(hasattr(article_pipeline_service, "_lock_current_representative"))
        first = Article(
            platform="sample",
            source_type="sample",
            source_article_id="first",
            url="sample://representative/first",
            url_hash="a" * 64,
            title="旧代表",
        )
        current = Article(
            platform="sample",
            source_type="sample",
            source_article_id="current",
            url="sample://representative/current",
            url_hash="b" * 64,
            title="当前代表",
        )
        db.session.add_all([first, current])
        db.session.flush()
        first.is_duplicate = True
        first.duplicate_of_id = current.id
        db.session.commit()

        representative = article_pipeline_service._lock_current_representative(first.id)

        self.assertEqual(representative.id, current.id)

    def test_stale_task_lease_cannot_commit_article_transaction(self):
        task = create_task("crawl", created_by=1, payload={})
        first_lease = task_service.claim_task(task["id"])
        row = db.session.get(Task, task["id"])
        row.heartbeat_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        db.session.commit()
        task_service.recoverable_task_ids(["crawl"], stale_after_seconds=3600)
        second_lease = task_service.claim_task(task["id"])
        self.assertNotEqual(first_lease, second_lease)
        context_token = task_service.activate_task_lease(first_lease)

        try:
            with self.assertRaises(task_service.StaleTaskLeaseError):
                persist_raw_document(self._document(), task_id=task["id"])
        finally:
            task_service.reset_task_lease(context_token)

        self.assertEqual(Article.query.count(), 0)

    @patch("app.services.article_pipeline_service.time.sleep")
    @patch("app.services.article_pipeline_service._persist_raw_document")
    def test_deadlock_is_retried_at_most_three_times(self, persist_mock, sleep_mock):
        deadlock = OperationalError("statement", {}, Exception(1213, "deadlock"))
        sentinel = (object(), object())
        persist_mock.side_effect = [deadlock, deadlock, sentinel]

        result = persist_raw_document(self._document(), task_id=None)

        self.assertEqual(result, sentinel)
        self.assertEqual(persist_mock.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep_mock.call_args_list], [1, 2])

    @patch("app.services.article_pipeline_service._persist_raw_document")
    def test_unique_conflict_is_retried_after_rollback(self, persist_mock):
        conflict = IntegrityError("statement", {}, Exception(1062, "duplicate"))
        sentinel = (object(), object())
        persist_mock.side_effect = [conflict, sentinel]

        result = persist_raw_document(self._document(), task_id=None)

        self.assertEqual(result, sentinel)
        self.assertEqual(persist_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
