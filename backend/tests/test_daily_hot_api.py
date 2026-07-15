import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.core.security import create_token
from app.extensions import db
from app.models import DailyHotItem, DailyHotRun, Event, User


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
    DEMO_ADMIN_USERNAME = "admin"
    DEMO_ADMIN_PASSWORD = "admin123"
    DAILY_HOT_SOURCES = ["weibo_hot", "baidu_hot", "zhihu_hot"]
    DAILY_HOT_SOURCE_LIMIT = 30
    DAILY_HOT_RESULT_LIMIT = 10
    DAILY_HOT_RRF_K = 60
    DAILY_HOT_TTL_SECONDS = 900


class DailyHotApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        self.admin_headers = self._login_admin()
        user = User(
            username="reader",
            password_hash="unused",
            nickname="reader",
            role="user",
            status=1,
        )
        db.session.add(user)
        db.session.commit()
        token, _ = create_token(
            {"id": user.id, "username": user.username, "role": "user"}
        )
        self.user_headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _login_admin(self):
        response = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        token = response.get_json()["data"]["token"]
        return {"Authorization": f"Bearer {token}"}

    def _run(self, *, count=12, status="partial", completed_at=None):
        completed_at = completed_at or datetime.now(timezone.utc).replace(tzinfo=None)
        run = DailyHotRun(
            run_date=completed_at.date(),
            status=status,
            attempt=1,
            available_sources=["baidu_hot", "weibo_hot"],
            failed_sources=["zhihu_hot"] if status == "partial" else [],
            errors={
                "zhihu_hot": {
                    "code": "CRAWL_AUTH_FAILED",
                    "message": "source collection failed",
                    "retryable": False,
                }
            }
            if status == "partial"
            else {},
            item_count=count,
            config_hash="api-test",
            completed_at=completed_at,
        )
        db.session.add(run)
        db.session.flush()
        for rank in range(1, count + 1):
            db.session.add(
                DailyHotItem(
                    run_id=run.id,
                    normalized_key=f"event{rank}",
                    title=f"热点事件{rank}",
                    fused_score=1 / (60 + rank),
                    rank=rank,
                    source_ranks={"weibo_hot": rank},
                    source_payloads={"weibo_hot": {"source_url": "https://example.com"}},
                    first_seen_at=completed_at,
                    last_seen_at=completed_at,
                    enrichment_status="pending",
                )
            )
        db.session.commit()
        return run

    def test_today_requires_login_and_empty_state_is_explicit(self):
        unauthorized = self.client.get("/api/hotspots/today")
        empty = self.client.get("/api/hotspots/today", headers=self.user_headers)

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(empty.status_code, 200)
        data = empty.get_json()["data"]
        self.assertEqual(data["items"], [])
        self.assertTrue(data["stale"])
        self.assertIsNone(data["generated_at"])

    def test_today_defaults_to_top_ten_and_returns_partial_diagnostics(self):
        self._run(count=12)

        response = self.client.get("/api/hotspots/today", headers=self.user_headers)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(len(data["items"]), 10)
        self.assertEqual(data["items"][0]["rank"], 1)
        self.assertEqual(data["available_sources"], ["baidu_hot", "weibo_hot"])
        self.assertEqual(data["failed_sources"], ["zhihu_hot"])
        self.assertEqual(data["status"], "partial")
        self.assertFalse(data["stale"])

    def test_today_validates_limit_and_marks_old_cache_stale(self):
        self._run(
            completed_at=datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(hours=1)
        )

        for value in ("x", "0", "101"):
            response = self.client.get(
                f"/api/hotspots/today?limit={value}",
                headers=self.user_headers,
            )
            self.assertEqual(response.status_code, 400)
        stale = self.client.get(
            "/api/hotspots/today?limit=5",
            headers=self.user_headers,
        )
        self.assertTrue(stale.get_json()["data"]["stale"])
        self.assertEqual(len(stale.get_json()["data"]["items"]), 5)

    def test_refresh_is_admin_only_and_uses_configured_sources(self):
        forbidden = self.client.post(
            "/api/hotspots/today/refresh",
            headers=self.user_headers,
        )
        run = self._run(count=1, status="success")

        with patch(
            "app.api.hotspots.collect_daily_hot",
            return_value=run,
        ) as collect:
            response = self.client.post(
                "/api/hotspots/today/refresh",
                headers=self.admin_headers,
            )

        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(response.status_code, 200)
        kwargs = collect.call_args.kwargs
        self.assertEqual(
            kwargs["sources"],
            ["weibo_hot", "baidu_hot", "zhihu_hot"],
        )
        self.assertEqual(kwargs["source_limit"], 30)
        self.assertEqual(kwargs["result_limit"], 10)
        self.assertEqual(kwargs["rrf_k"], 60)
        self.assertTrue(kwargs["force"])
        self.assertEqual(
            db.session.query(DailyHotItem)
            .filter(DailyHotItem.analysis_task_id.isnot(None))
            .count(),
            0,
        )

    def test_user_can_manually_enrich_one_hot_item_and_reuse_active_task(self):
        run = self._run(count=2, status="success")
        item = DailyHotItem.query.filter_by(run_id=run.id, rank=1).one()

        with patch("app.api.hotspots.submit_background_job") as submit:
            first = self.client.post(
                f"/api/hotspots/today/items/{item.id}/enrich",
                headers=self.user_headers,
            )
            second = self.client.post(
                f"/api/hotspots/today/items/{item.id}/enrich",
                headers=self.user_headers,
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_data = first.get_json()["data"]
        second_data = second.get_json()["data"]
        self.assertEqual(first_data["task_id"], second_data["task_id"])
        self.assertFalse(first_data["reused"])
        self.assertTrue(second_data["reused"])
        self.assertEqual(submit.call_count, 1)
        other = DailyHotItem.query.filter_by(run_id=run.id, rank=2).one()
        self.assertIsNone(other.analysis_task_id)

    def test_manual_enrichment_rejects_merged_item(self):
        run = self._run(count=2, status="success")
        canonical = DailyHotItem.query.filter_by(run_id=run.id, rank=1).one()
        merged = DailyHotItem.query.filter_by(run_id=run.id, rank=2).one()
        merged.merged_into_item_id = canonical.id
        db.session.commit()

        response = self.client.post(
            f"/api/hotspots/today/items/{merged.id}/enrich",
            headers=self.user_headers,
        )

        self.assertEqual(response.status_code, 400)

    def test_today_and_formal_hotspot_endpoints_keep_distinct_contracts(self):
        event = Event(
            title="Analyzed formal event",
            is_hot=True,
            hot_rank=1,
            heat_index=91.0,
        )
        db.session.add(event)
        db.session.commit()
        run = self._run(count=1, status="success")
        item = DailyHotItem.query.filter_by(run_id=run.id).one()
        item.title = "Raw fused hot-list item"
        item.event_id = event.id
        item.enrichment_status = "completed"
        db.session.commit()

        formal_response = self.client.get(
            "/api/hotspots",
            headers=self.user_headers,
        )
        today_response = self.client.get(
            "/api/hotspots/today",
            headers=self.user_headers,
        )

        self.assertEqual(formal_response.status_code, 200)
        formal_data = formal_response.get_json()["data"]
        self.assertEqual(formal_data["total"], 1)
        self.assertNotIn("items", formal_data)
        self.assertEqual(formal_data["events"][0]["id"], event.id)
        self.assertEqual(
            formal_data["events"][0]["title"],
            "Analyzed formal event",
        )
        self.assertNotIn("source_ranks", formal_data["events"][0])

        self.assertEqual(today_response.status_code, 200)
        today_data = today_response.get_json()["data"]
        self.assertNotIn("events", today_data)
        self.assertEqual(today_data["items"][0]["title"], "Raw fused hot-list item")
        self.assertEqual(today_data["items"][0]["event_id"], event.id)
        self.assertEqual(today_data["items"][0]["source_ranks"], {"weibo_hot": 1})
        self.assertNotIn("heat_index", today_data["items"][0])


if __name__ == "__main__":
    unittest.main()
