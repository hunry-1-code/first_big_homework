import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.crawler.base import CrawlerRegistry, RawDocument
from app.crawler.errors import CrawlerError
from app.extensions import db
from app.models import DailyHotItem, DailyHotRun
from app.services.daily_hot_service import collect_daily_hot, serialize_daily_hot_run


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_DB = False
    FRONTEND_ORIGINS = ["http://localhost"]
    TASK_RECOVER_ON_STARTUP = False


class FakeCrawler:
    def __init__(self, platform, documents=None, error=None):
        self.platform = platform
        self.documents = list(documents or [])
        self.error = error
        self.calls = []

    def crawl(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.documents[: request.limit]


def document(platform, rank, title, *, raw=None):
    return RawDocument(
        platform=platform,
        source_url=f"https://example.com/{platform}/{rank}",
        title=title,
        raw_content=title,
        source_type="hotlist",
        raw_json={"rank": rank, **(raw or {})},
    )


class DailyHotServiceTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.now = datetime(2026, 7, 13, 9, 0, 0)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _registry(self):
        registry = CrawlerRegistry()
        crawlers = {
            "weibo_hot": FakeCrawler(
                "weibo_hot",
                [document("weibo_hot", 1, "#某地暴雨#")],
            ),
            "baidu_hot": FakeCrawler(
                "baidu_hot",
                [
                    document(
                        "baidu_hot",
                        3,
                        "某地暴雨",
                        raw={"Authorization": "Bearer payload-secret"},
                    )
                ],
            ),
            "zhihu_hot": FakeCrawler(
                "zhihu_hot",
                error=CrawlerError(
                    "zhihu_hot",
                    "CRAWL_AUTH_FAILED",
                    "Authorization: Bearer exception-secret",
                ),
            ),
        }
        for crawler in crawlers.values():
            registry.register(crawler)
        return registry, crawlers

    def test_partial_source_failure_still_persists_fused_run_without_secrets(self):
        registry, crawlers = self._registry()

        run = collect_daily_hot(
            registry=registry,
            sources=["weibo_hot", "baidu_hot", "zhihu_hot"],
            source_limit=30,
            result_limit=10,
            rrf_k=60,
            ttl_seconds=900,
            now=self.now,
        )

        self.assertEqual(run.status, "partial")
        self.assertEqual(run.available_sources, ["baidu_hot", "weibo_hot"])
        self.assertEqual(run.failed_sources, ["zhihu_hot"])
        self.assertEqual(run.item_count, 1)
        item = DailyHotItem.query.one()
        self.assertEqual(item.title, "某地暴雨")
        self.assertEqual(item.source_ranks, {"baidu_hot": 3, "weibo_hot": 1})
        serialized = str({"errors": run.errors, "payloads": item.source_payloads})
        self.assertNotIn("exception-secret", serialized)
        self.assertNotIn("payload-secret", serialized)
        self.assertNotIn("Authorization", serialized)
        self.assertEqual(crawlers["weibo_hot"].calls[0].mode, "hot")
        self.assertEqual(crawlers["weibo_hot"].calls[0].limit, 30)

    def test_fresh_run_is_reused_and_stale_run_creates_new_attempt(self):
        registry, crawlers = self._registry()
        sources = ["weibo_hot", "baidu_hot", "zhihu_hot"]

        first = collect_daily_hot(
            registry=registry,
            sources=sources,
            now=self.now,
            ttl_seconds=900,
        )
        fresh = collect_daily_hot(
            registry=registry,
            sources=sources,
            now=self.now + timedelta(minutes=10),
            ttl_seconds=900,
        )
        stale = collect_daily_hot(
            registry=registry,
            sources=sources,
            now=self.now + timedelta(minutes=16),
            ttl_seconds=900,
        )

        self.assertEqual(fresh.id, first.id)
        self.assertNotEqual(stale.id, first.id)
        self.assertEqual((first.attempt, stale.attempt), (1, 2))
        self.assertEqual(DailyHotRun.query.count(), 2)
        self.assertEqual(len(crawlers["weibo_hot"].calls), 2)

    def test_all_source_failures_create_failed_run_without_items(self):
        registry = CrawlerRegistry()
        for source in ("weibo_hot", "baidu_hot", "zhihu_hot"):
            registry.register(
                FakeCrawler(
                    source,
                    error=CrawlerError(source, "CRAWL_DOWN", "temporary outage"),
                )
            )

        run = collect_daily_hot(
            registry=registry,
            sources=["weibo_hot", "baidu_hot", "zhihu_hot"],
            now=self.now,
        )

        self.assertEqual(run.status, "failed")
        self.assertEqual(run.item_count, 0)
        self.assertEqual(DailyHotItem.query.count(), 0)

    def test_unenriched_items_are_classified_for_category_filtering(self):
        registry, _crawlers = self._registry()
        registry.get("weibo_hot").documents = [
            RawDocument(
                platform="weibo_hot",
                source_url="https://example.com/education",
                source_article_id="education",
                title="高考志愿填报与大学专业选择",
                raw_content="高考志愿填报与大学专业选择",
                raw_json={"rank": 1},
            )
        ]
        run = collect_daily_hot(
            registry=registry,
            sources=["weibo_hot"],
            now=self.now,
            force=True,
        )

        payload = serialize_daily_hot_run(run, limit=10, ttl_seconds=900, now=self.now)

        self.assertEqual(payload["items"][0]["category"], "教育")
        self.assertEqual(payload["items"][0]["topic_name"], "高考志愿填报与大学专业选择")
        self.assertIn("高考", payload["items"][0]["topic_keywords"])
        self.assertEqual(payload["category_counts"], {"教育": 1})


if __name__ == "__main__":
    unittest.main()
