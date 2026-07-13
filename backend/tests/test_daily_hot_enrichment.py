import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.models import DailyHotItem, DailyHotRun, Event, Task
from app.services.daily_hot_service import create_daily_hot_enrichment_tasks
from app.services.task_service import get_task
from app.tasks.jobs import daily_hot_enrichment_job


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_DB = False
    FRONTEND_ORIGINS = ["http://localhost"]
    TASK_RECOVER_ON_STARTUP = False
    JWT_EXPIRES_DELTA = timedelta(hours=1)


class DailyHotEnrichmentTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        now = datetime(2026, 7, 13, 10, 0, 0)
        self.run = DailyHotRun(
            run_date=now.date(),
            status="success",
            attempt=1,
            available_sources=["weibo_hot", "baidu_hot"],
            failed_sources=[],
            errors={},
            item_count=3,
            config_hash="enrichment-test",
            completed_at=now,
        )
        db.session.add(self.run)
        db.session.flush()
        for rank in range(1, 4):
            db.session.add(
                DailyHotItem(
                    run_id=self.run.id,
                    normalized_key=f"event{rank}",
                    title=f"热点事件{rank}",
                    fused_score=1 / (60 + rank),
                    rank=rank,
                    source_ranks={"weibo_hot": rank},
                    source_payloads={},
                    first_seen_at=now,
                    last_seen_at=now,
                    enrichment_status="pending",
                )
            )
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_enrichment_tasks_are_idempotent_while_active(self):
        first = create_daily_hot_enrichment_tasks(self.run.id, created_by=1)
        second = create_daily_hot_enrichment_tasks(self.run.id, created_by=1)

        self.assertEqual([task["id"] for task in first], [task["id"] for task in second])
        self.assertEqual(Task.query.filter_by(task_type="daily_hot_enrichment").count(), 3)
        self.assertTrue(
            all(item.analysis_task_id for item in DailyHotItem.query.all())
        )

    def test_one_item_failure_does_not_block_other_items_or_fail_run(self):
        tasks = create_daily_hot_enrichment_tasks(self.run.id, created_by=1)
        event = Event(title="已发布热点事件")
        db.session.add(event)
        db.session.commit()

        for task in tasks:
            item_id = task["payload"]["daily_hot_item_id"]

            def processor(item, current_id=item_id):
                if current_id == tasks[0]["payload"]["daily_hot_item_id"]:
                    return event.id
                if current_id == tasks[1]["payload"]["daily_hot_item_id"]:
                    raise RuntimeError("Authorization: Bearer enrichment-secret")
                return None

            daily_hot_enrichment_job(task["id"], processor=processor)

        items = DailyHotItem.query.order_by(DailyHotItem.rank).all()
        self.assertEqual(
            [item.enrichment_status for item in items],
            ["completed", "failed", "no_event"],
        )
        self.assertEqual(items[0].event_id, event.id)
        self.assertIsNone(items[2].event_id)
        self.assertNotIn("enrichment-secret", items[1].error_message or "")
        self.assertEqual(items[1].error_message, "item enrichment failed")
        db.session.refresh(self.run)
        self.assertEqual(self.run.status, "success")
        self.assertEqual(
            [get_task(task["id"])["status"] for task in tasks],
            ["success", "failed", "success"],
        )


if __name__ == "__main__":
    unittest.main()
