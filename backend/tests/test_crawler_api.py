import sys
import unittest
from datetime import timedelta
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.models import AggregationRun, Article, Task
from app.services.task_service import reset_task_store


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    JWT_EXPIRES_DELTA = timedelta(hours=24)
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FRONTEND_ORIGINS = ["http://localhost:5173"]
    DEMO_ADMIN_USERNAME = "admin"
    DEMO_ADMIN_PASSWORD = "admin123"
    TASKS_RUN_SYNC = True
    CRAWL_DEFAULT_TARGET_COUNT = 100
    CRAWL_MAX_TARGET_COUNT = 200
    CRAWL_PLATFORM_PREFERRED_LIMIT = 50
    CRAWL_REQUEST_TIMEOUT = 3
    CRAWL_DUPLICATE_WINDOW_SECONDS = 60
    QIANFAN_API_KEY = ""
    ZHIHU_ACCESS_SECRET = ""
    TIKHUB_API_KEY = ""
    TIKHUB_ENABLED_PLATFORMS = []
    RSS_FEED_URL = ""


class CrawlerApiTest(unittest.TestCase):
    def setUp(self):
        reset_task_store()
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        response = self.client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin123"}
        )
        token = response.get_json()["data"]["token"]
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        reset_task_store()

    def test_keyword_search_runs_sample_pipeline_and_exposes_task(self):
        response = self.client.post(
            "/api/crawler/search",
            json={"keyword": "公共事件", "platforms": ["sample"], "target_count": 1},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        task_id = response.get_json()["data"]["task_id"]
        task_response = self.client.get(f"/api/tasks/{task_id}", headers=self.headers)
        self.assertEqual(task_response.get_json()["data"]["status"], "success")
        self.assertIsInstance(
            task_response.get_json()["data"]["result"]["aggregation_run_id"], int
        )
        self.assertEqual(Article.query.count(), 1)
        self.assertEqual(AggregationRun.query.count(), 1)

    def test_keyword_search_rejects_target_above_first_version_limit(self):
        response = self.client.post(
            "/api/crawler/search",
            json={"keyword": "公共事件", "target_count": 201},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 400)

    def test_equivalent_keyword_search_reuses_recent_task(self):
        payload = {
            "keyword": "公共事件",
            "platforms": ["sample"],
            "target_count": 1,
        }

        first = self.client.post(
            "/api/crawler/search", json=payload, headers=self.headers
        )
        second = self.client.post(
            "/api/crawler/search", json=payload, headers=self.headers
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertIsInstance(first.get_json()["data"]["task_id"], int)
        self.assertIsNone(second.get_json()["data"]["task_id"])
        self.assertTrue(second.get_json()["data"]["cached"])
        self.assertIsInstance(second.get_json()["data"]["aggregation_run_id"], int)
        self.assertEqual(Task.query.filter_by(task_type="crawl").count(), 1)

    def test_keyword_search_rejects_non_object_and_null_keyword(self):
        list_response = self.client.post(
            "/api/crawler/search", json=[], headers=self.headers
        )
        null_response = self.client.post(
            "/api/crawler/search", json={"keyword": None}, headers=self.headers
        )

        self.assertEqual(list_response.status_code, 400)
        self.assertEqual(null_response.status_code, 400)

    def test_json_import_enters_same_preprocessing_pipeline(self):
        response = self.client.post(
            "/api/import/json",
            json=[
                {
                    "platform": "sample",
                    "url": "sample://api-import/1",
                    "title": "接口导入样例",
                    "raw_content": "这是通过接口导入的测试正文。" * 20,
                    "publish_time": "2026-07-10T08:00:00+08:00",
                    "likes_count": "1.2万",
                }
            ],
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Article.query.count(), 1)
        self.assertEqual(Article.query.first().clean_status, "success")
        self.assertEqual(Article.query.first().likes_count, 12000)

    def test_json_import_rejects_null_required_values(self):
        response = self.client.post(
            "/api/import/json",
            json=[
                {
                    "platform": "sample",
                    "url": None,
                    "title": "",
                    "raw_content": None,
                    "publish_time": None,
                }
            ],
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 400)

    def test_crawler_status_only_returns_sanitized_crawl_task(self):
        self.client.post(
            "/api/crawler/search",
            json={"keyword": "状态测试", "platforms": ["sample"], "target_count": 1},
            headers=self.headers,
        )
        self.client.post(
            "/api/import/json",
            json=[
                {
                    "platform": "sample",
                    "url": "sample://status-import/1",
                    "title": "状态导入",
                    "raw_content": "状态接口测试正文。" * 20,
                    "publish_time": "2026-07-10T08:00:00+08:00",
                }
            ],
            headers=self.headers,
        )

        response = self.client.get("/api/crawler/status", headers=self.headers)
        latest = response.get_json()["data"]["latest_task"]

        self.assertEqual(latest["task_type"], "crawl")
        self.assertNotIn("documents", latest.get("payload", {}))


if __name__ == "__main__":
    unittest.main()
