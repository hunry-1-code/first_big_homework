import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.crawler.base import CrawlerRegistry, RawDocument
from app.crawler.comments import RawComment
from app.crawler.errors import CrawlerError
from app.crawler.news_comments import NewsCommentResult
from app.crawler.sample import SampleCrawler
from app.extensions import db
from app.models import (
    AggregationRun,
    AnalysisRun,
    Article,
    Comment,
    Event,
    EventHeatSnapshot,
    DailyHotRun,
    HotSeedExpansion,
    HotspotRun,
    SentimentRun,
    Task,
    User,
)
from app.services.task_service import create_task, get_task, reset_task_store, update_task
from app.services import task_service
from app.tasks.jobs import (
    _enrich_article_comments,
    crawl_job,
    daily_hot_job,
    hotspot_job,
    import_job,
)
from app.services.article_pipeline_service import persist_raw_document
from app.services.public_opinion_service import get_public_opinion_snapshot
from app.tasks import runner
from app.tasks.runner import submit_background_job
from app.tasks.scheduler import enqueue_daily_hot_refresh


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FRONTEND_ORIGINS = ["http://localhost:5173"]
    CRAWL_DEFAULT_TARGET_COUNT = 100
    CRAWL_MAX_TARGET_COUNT = 200
    CRAWL_PLATFORM_PREFERRED_LIMIT = 50


class JobTest(unittest.TestCase):
    def setUp(self):
        reset_task_store()
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        reset_task_store()

    def test_crawl_job_updates_task_and_persists_documents(self):
        registry = CrawlerRegistry()
        registry.register(SampleCrawler())
        task = create_task(
            "crawl",
            created_by=1,
            payload={
                "keyword": "公共事件",
                "platforms": ["sample"],
                "target_count": 1,
                "mode": "search",
            },
        )

        summary = crawl_job(task["id"], registry=registry)

        self.assertEqual(get_task(task["id"])["status"], "success")
        self.assertEqual(summary["processed"], 1)
        self.assertEqual(Article.query.count(), 1)
        self.assertEqual(Task.query.count(), 1)

    def test_news_comment_enrichment_persists_comments_and_returns_status(self):
        document = RawDocument(
            platform="news_sspai",
            source_url="https://sspai.com/post/112320",
            source_article_id="112320",
            title="少数派文章",
            raw_content="人工智能新闻正文" * 20,
        )
        article, _ = persist_raw_document(document, 1)

        class AggregateCrawler:
            platform = "mainstream_news"

            def crawl(self, request):
                return []

            def fetch_comments(self, fetched_document, limit=10):
                self.limit = limit
                return NewsCommentResult(
                    status="success",
                    comments=[
                        RawComment(
                            platform="news_sspai",
                            source_comment_id="428733",
                            content="公开评论内容",
                            author="Setsuna",
                        )
                    ],
                )

        crawler = AggregateCrawler()
        registry = CrawlerRegistry()
        registry.register(crawler)

        count, status, error = _enrich_article_comments(article, document, registry)

        self.assertEqual((count, status, error), (1, "success", None))
        self.assertEqual(crawler.limit, 10)
        self.assertEqual(Comment.query.count(), 1)
        self.assertEqual(Comment.query.first().article_id, article.id)
        event = Event(title="主流新闻评论分析")
        db.session.add(event)
        db.session.flush()
        article.event_id = event.id
        db.session.commit()

        opinion = get_public_opinion_snapshot(event.id)

        self.assertEqual(opinion["comment_count"], 1)
        self.assertEqual(opinion["analysis_mode"], "narrative_gap")

    def test_news_comment_failure_does_not_remove_persisted_article(self):
        document = RawDocument(
            platform="news_thepaper",
            source_url="https://m.thepaper.cn/newsDetail_forward_33585997",
            source_article_id="33585997",
            title="澎湃文章",
            raw_content="人工智能新闻正文" * 20,
        )
        article, _ = persist_raw_document(document, 1)

        class AggregateCrawler:
            platform = "mainstream_news"

            def crawl(self, request):
                return []

            def fetch_comments(self, fetched_document, limit=10):
                return NewsCommentResult(status="failed", error="timeout")

        registry = CrawlerRegistry()
        registry.register(AggregateCrawler())

        count, status, error = _enrich_article_comments(article, document, registry)

        self.assertEqual((count, status, error), (0, "failed", "timeout"))
        self.assertIsNotNone(db.session.get(Article, article.id))

    def test_mainstream_crawl_summary_reports_concrete_comment_statuses(self):
        class AggregateCrawler:
            platform = "mainstream_news"

            def crawl(self, request):
                return [
                    RawDocument(
                        platform="news_people",
                        source_url="https://people.com.cn/1",
                        source_article_id="people-1",
                        title="人民网人工智能报道",
                        raw_content="人工智能产业发展新闻正文" * 30,
                    )
                ]

            def fetch_comments(self, document, limit=10):
                return NewsCommentResult(status="unsupported")

        registry = CrawlerRegistry()
        registry.register(AggregateCrawler())
        task = create_task(
            "crawl",
            created_by=1,
            payload={
                "keyword": "人工智能",
                "platforms": ["mainstream_news"],
                "target_count": 1,
                "mode": "search",
            },
        )

        with patch(
            "app.tasks.jobs.run_search_analysis_pipeline",
            return_value={"aggregation_run_id": 1, "event_count": 0},
        ):
            summary = crawl_job(task["id"], registry=registry)

        self.assertEqual(summary["platform_counts"], {"news_people": 1})
        self.assertEqual(
            summary["comment_statuses"]["news_people"],
            {
                "success": 0,
                "empty": 0,
                "unsupported": 1,
                "failed": 0,
                "saved": 0,
            },
        )
        self.assertEqual(summary["collected"], 1)

    def test_import_job_processes_validated_documents(self):
        task = create_task(
            "import",
            created_by=1,
            payload={
                "documents": [
                    {
                        "platform": "sample",
                        "url": "sample://import/1",
                        "title": "导入样例",
                        "raw_content": "这是导入样例正文。" * 20,
                        "publish_time": "2026-07-10T08:00:00+08:00",
                        "source_type": "sample",
                    }
                ]
            },
        )

        summary = import_job(task["id"])

        self.assertEqual(summary["processed"], 1)
        self.assertEqual(get_task(task["id"])["status"], "success")
        self.assertEqual(Article.query.first().title, "导入样例")

    def test_hot_crawl_expands_seed_and_runs_content_and_topic_analysis(self):
        class HotCrawler:
            platform = "sample_hot"

            def crawl(self, request):
                return [
                    RawDocument(
                        platform=self.platform,
                        source_url="https://example.com/hot/1",
                        source_article_id="hot-1",
                        title="#重庆暴雨#",
                        raw_content="重庆暴雨",
                        source_type="hotlist",
                        raw_json={"rank": 1},
                    )
                ]

        class SearchCrawler:
            platform = "sample_search"

            def crawl(self, request):
                self.keyword = request.keyword
                return [
                    RawDocument(
                        platform=self.platform,
                        source_url=f"https://example.com/search/{index}",
                        source_article_id=f"search-{index}",
                        title=f"重庆暴雨救援进展{index}",
                        raw_content=("重庆 暴雨 救援 应急 积水 道路 " * 20),
                        source_type="news",
                        publish_time=datetime.now(timezone.utc).isoformat(),
                        comments_count=index,
                        likes_count=index * 10,
                    )
                    for index in range(1, 6)
                ]

        hot = HotCrawler()
        search = SearchCrawler()
        registry = CrawlerRegistry()
        registry.register(hot)
        registry.register(search)
        task = create_task(
            "crawl",
            created_by=1,
            payload={
                "platforms": ["sample_hot"],
                "target_count": 1,
                "mode": "hot",
            },
        )

        summary = crawl_job(task["id"], registry=registry)

        self.assertEqual(search.keyword, "重庆暴雨")
        self.assertEqual(summary["expanded"], 5)
        self.assertIsInstance(summary["analysis_run_id"], int)
        self.assertIsInstance(summary["hotspot_run_id"], int)
        self.assertIsInstance(summary["aggregation_run_id"], int)
        self.assertIsInstance(summary["sentiment_run_id"], int)
        self.assertEqual(AnalysisRun.query.count(), 1)
        self.assertEqual(AggregationRun.query.count(), 1)
        self.assertEqual(SentimentRun.query.count(), 1)
        self.assertEqual(HotSeedExpansion.query.count(), 5)
        self.assertEqual(
            {item.search_query for item in HotSeedExpansion.query.all()}, {"重庆暴雨"}
        )
        hotspot_run = db.session.get(HotspotRun, summary["hotspot_run_id"])
        self.assertEqual(hotspot_run.topic_status, "success")
        self.assertEqual(hotspot_run.heat_status, "success")
        self.assertGreater(EventHeatSnapshot.query.count(), 0)

    def test_runner_marks_task_failed_when_job_raises(self):
        task = create_task("crawl", created_by=1, payload={})
        self.app.config["TASKS_RUN_SYNC"] = True

        def failing_job(task_id):
            raise RuntimeError("boom")

        submit_background_job(self.app, failing_job, task["id"])

        self.assertEqual(get_task(task["id"])["status"], "failed")

    def test_daily_hot_job_is_claimed_once_and_survives_one_source_failure(self):
        class HotCrawler:
            def __init__(self, platform, *, fail=False):
                self.platform = platform
                self.fail = fail
                self.calls = 0

            def crawl(self, request):
                self.calls += 1
                if self.fail:
                    raise CrawlerError(
                        self.platform,
                        "CRAWL_DOWN",
                        "temporary outage",
                    )
                return [
                    RawDocument(
                        platform=self.platform,
                        source_url=f"https://example.com/{self.platform}",
                        title="#测试热点#",
                        raw_content="测试热点",
                        source_type="hotlist",
                        raw_json={"rank": 1},
                    )
                ]

        registry = CrawlerRegistry()
        crawlers = [
            HotCrawler("weibo_hot"),
            HotCrawler("baidu_hot"),
            HotCrawler("zhihu_hot", fail=True),
        ]
        for crawler in crawlers:
            registry.register(crawler)
        task = create_task(
            "daily_hot",
            created_by=1,
            payload={
                "sources": ["weibo_hot", "baidu_hot", "zhihu_hot"],
                "source_limit": 30,
                "result_limit": 10,
                "rrf_k": 60,
                "ttl_seconds": 900,
            },
        )
        self.app.config["TASKS_RUN_SYNC"] = True

        function = lambda task_id: daily_hot_job(task_id, registry=registry)
        submit_background_job(self.app, function, task["id"])
        submit_background_job(self.app, function, task["id"])

        current = get_task(task["id"])
        self.assertEqual(current["status"], "success")
        self.assertEqual(current["result"]["status"], "partial")
        self.assertEqual(current["result"]["item_count"], 1)
        self.assertEqual(current["result"]["enrichment_task_count"], 0)
        self.assertEqual(DailyHotRun.query.count(), 1)
        self.assertEqual(Task.query.filter_by(task_type="daily_hot_enrichment").count(), 0)
        self.assertEqual([crawler.calls for crawler in crawlers], [1, 1, 1])

    def test_sync_sqlite_execution_does_not_start_heartbeat_thread(self):
        task = create_task("crawl", created_by=1, payload={})
        self.app.config["TASKS_RUN_SYNC"] = True

        with patch("app.tasks.runner.Thread") as thread:
            runner._execute(self.app, lambda task_id: {"task_id": task_id}, task["id"])

        thread.assert_not_called()

    def test_explicitly_disabled_heartbeat_does_not_start_thread_for_async_sqlite(self):
        task = create_task("crawl", created_by=1, payload={})
        self.app.config["TASKS_RUN_SYNC"] = False
        self.app.config["TASK_HEARTBEAT_ENABLED"] = False

        with patch("app.tasks.runner.Thread") as thread:
            runner._execute(self.app, lambda task_id: {"task_id": task_id}, task["id"])

        thread.assert_not_called()

    def test_runner_recovers_pending_database_task_on_startup(self):
        task = create_task("crawl", created_by=1, payload={})
        self.app.config["TASKS_RUN_SYNC"] = True
        executed = []

        def recovered_job(task_id):
            executed.append(task_id)
            return {"task_id": task_id}

        self.assertTrue(hasattr(runner, "recover_background_jobs"))
        runner.recover_background_jobs(self.app, {"crawl": recovered_job})

        self.assertEqual(executed, [task["id"]])
        self.assertEqual(get_task(task["id"])["status"], "running")

    def test_default_recovery_registry_includes_hotspot_job(self):
        task = create_task(
            "hotspot", created_by=1, payload={"hotspot_run_id": 999}
        )
        self.app.config["TASKS_RUN_SYNC"] = True

        with patch("app.tasks.jobs.hotspot_job", wraps=hotspot_job) as job:
            runner.recover_background_jobs(
                self.app,
                {
                    "hotspot": lambda task_id: job(task_id),
                },
            )

        self.assertTrue(job.called)

    def test_default_recovery_registry_includes_daily_hot_job(self):
        task = create_task("daily_hot", created_by=1, payload={})
        self.app.config["TASKS_RUN_SYNC"] = True

        def complete(task_id):
            update_task(
                task_id,
                status="success",
                progress=100,
                message="done",
                result={"run_id": 1},
            )
            return {"run_id": 1}

        with patch("app.tasks.jobs.daily_hot_job", side_effect=complete) as job:
            runner.recover_background_jobs(self.app)

        self.assertTrue(job.called)
        self.assertEqual(get_task(task["id"])["status"], "success")

    def test_runner_requeues_stale_running_task_on_startup(self):
        task = create_task("crawl", created_by=1, payload={})
        row = db.session.get(Task, task["id"])
        row.status = "running"
        row.started_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        db.session.commit()
        self.app.config["TASKS_RUN_SYNC"] = True
        self.app.config["TASK_RUNNING_TIMEOUT_SECONDS"] = 3600
        executed = []

        self.assertTrue(hasattr(runner, "recover_background_jobs"))
        runner.recover_background_jobs(
            self.app,
            {"crawl": lambda task_id: executed.append(task_id)},
        )

        self.assertEqual(executed, [task["id"]])

    def test_runner_does_not_requeue_task_with_fresh_heartbeat(self):
        self.assertTrue(hasattr(Task, "heartbeat_at"))
        task = create_task("crawl", created_by=1, payload={})
        row = db.session.get(Task, task["id"])
        row.status = "running"
        row.started_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        row.heartbeat_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
        self.app.config["TASKS_RUN_SYNC"] = True
        self.app.config["TASK_RUNNING_TIMEOUT_SECONDS"] = 3600
        executed = []

        runner.recover_background_jobs(
            self.app,
            {"crawl": lambda task_id: executed.append(task_id)},
        )

        self.assertEqual(executed, [])
        self.assertEqual(get_task(task["id"])["status"], "running")

    def test_touch_task_refreshes_running_task_heartbeat(self):
        self.assertTrue(hasattr(Task, "heartbeat_at"))
        self.assertTrue(hasattr(task_service, "touch_task"))
        task = create_task("crawl", created_by=1, payload={})
        lease_token = task_service.claim_task(task["id"])
        self.assertTrue(lease_token)
        row = db.session.get(Task, task["id"])
        row.heartbeat_at = datetime(2020, 1, 1)
        db.session.commit()

        self.assertTrue(task_service.touch_task(task["id"], lease_token))

        db.session.refresh(row)
        self.assertGreater(row.heartbeat_at, datetime(2020, 1, 1))

    def test_stale_lease_cannot_overwrite_recovered_task(self):
        self.assertTrue(hasattr(Task, "lease_token"))
        self.assertTrue(hasattr(Task, "attempt"))
        self.assertTrue(hasattr(task_service, "StaleTaskLeaseError"))
        task = create_task("crawl", created_by=1, payload={})
        first_lease = task_service.claim_task(task["id"])
        row = db.session.get(Task, task["id"])
        row.heartbeat_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        db.session.commit()

        task_service.recoverable_task_ids(["crawl"], stale_after_seconds=3600)
        second_lease = task_service.claim_task(task["id"])

        self.assertNotEqual(first_lease, second_lease)
        with self.assertRaises(task_service.StaleTaskLeaseError):
            update_task(
                task["id"],
                lease_token=first_lease,
                status="failed",
                message="旧实例不应覆盖新状态",
            )
        current = db.session.get(Task, task["id"])
        self.assertEqual(current.status, "running")
        self.assertEqual(current.lease_token, second_lease)

    def test_heartbeat_loop_retries_after_transient_database_error(self):
        self.assertTrue(hasattr(runner, "_heartbeat_loop"))

        class StopAfterTwoWaits:
            def __init__(self):
                self.calls = 0

            def wait(self, interval):
                self.calls += 1
                return self.calls > 2

        stop = StopAfterTwoWaits()
        with patch(
            "app.services.task_service.touch_task",
            side_effect=[RuntimeError("temporary database error"), False],
        ) as touch:
            runner._heartbeat_loop(self.app, 1, "lease-token", stop, 1)

        self.assertEqual(touch.call_count, 2)

    def test_recovery_leaves_task_pending_when_local_queue_is_full(self):
        task = create_task("crawl", created_by=1, payload={})

        class FullQueue:
            def acquire(self, blocking=False):
                return False

        with patch.object(runner, "_PENDING_SLOTS", FullQueue()):
            runner.recover_background_jobs(
                self.app,
                {"crawl": lambda task_id: None},
            )

        self.assertEqual(get_task(task["id"])["status"], "pending")

    def test_recovery_scheduler_registers_periodic_scan(self):
        class FakeScheduler:
            def __init__(self):
                self.jobs = []
                self.started = False

            def add_job(self, function, trigger, **kwargs):
                self.jobs.append((function, trigger, kwargs))

            def start(self):
                self.started = True

        scheduler = FakeScheduler()
        self.app.config["TASK_RECOVERY_SCAN_SECONDS"] = 30
        self.app.config["DAILY_HOT_SCHEDULER_ENABLED"] = True

        self.assertTrue(hasattr(runner, "start_recovery_scheduler"))
        runner.start_recovery_scheduler(self.app, scheduler=scheduler)

        jobs = {item[2]["id"]: item for item in scheduler.jobs}
        self.assertEqual(jobs["task-recovery-scan"][1], "interval")
        self.assertEqual(jobs["task-recovery-scan"][2]["seconds"], 30)
        self.assertIn("daily-hot-refresh", jobs)
        self.assertTrue(scheduler.started)

    def test_recovery_scheduler_start_is_idempotent_per_app(self):
        class FakeScheduler:
            def __init__(self):
                self.jobs = []
                self.started = False

            def add_job(self, function, trigger, **kwargs):
                self.jobs.append((function, trigger, kwargs))

            def start(self):
                self.started = True

        first = FakeScheduler()
        second = FakeScheduler()

        returned_first = runner.start_recovery_scheduler(self.app, scheduler=first)
        returned_second = runner.start_recovery_scheduler(self.app, scheduler=second)

        self.assertIs(returned_first, first)
        self.assertIs(returned_second, first)
        self.assertTrue(first.started)
        self.assertFalse(second.started)

    def test_daily_hot_scheduler_uses_active_admin_and_reuses_task(self):
        admin = User(
            username="scheduler-admin",
            password_hash="unused",
            role="admin",
            status=1,
        )
        db.session.add(admin)
        db.session.commit()
        self.app.config.update(
            DAILY_HOT_SYSTEM_USERNAME="scheduler-admin",
            DAILY_HOT_REFRESH_INTERVAL_SECONDS=900,
            DAILY_HOT_SOURCES=["weibo_hot", "baidu_hot"],
            DAILY_HOT_SOURCE_LIMIT=20,
            DAILY_HOT_RESULT_LIMIT=10,
            DAILY_HOT_RRF_K=60,
            DAILY_HOT_TTL_SECONDS=900,
        )

        with patch("app.tasks.scheduler.submit_background_job") as submit:
            first = enqueue_daily_hot_refresh(self.app)
            self.app.config["DAILY_HOT_SOURCES"] = ["baidu_hot", "weibo_hot"]
            second = enqueue_daily_hot_refresh(self.app)

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(Task.query.filter_by(task_type="daily_hot").count(), 1)
        self.assertEqual(db.session.get(Task, first["id"]).created_by, admin.id)
        self.assertEqual(submit.call_count, 1)

    def test_daily_hot_scheduler_rejects_missing_system_actor(self):
        self.app.config["DAILY_HOT_SYSTEM_USERNAME"] = "missing-admin"

        with self.assertRaisesRegex(RuntimeError, "daily hot system actor"):
            enqueue_daily_hot_refresh(self.app)

    def test_concurrent_equivalent_task_creation_creates_one_database_row(self):
        self.assertTrue(hasattr(task_service, "create_or_reuse_recent_task"))
        barrier = threading.Barrier(2)
        results = []

        def create_once():
            with self.app.app_context():
                barrier.wait()
                results.append(
                    task_service.create_or_reuse_recent_task(
                        "crawl",
                        created_by=1,
                        payload={
                            "keyword": "公共事件",
                            "platforms": ["sample"],
                            "target_count": 1,
                            "mode": "search",
                        },
                        within_seconds=60,
                    )
                )

        threads = [threading.Thread(target=create_once) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0]["id"], results[1][0]["id"])
        self.assertEqual(Task.query.filter_by(task_type="crawl").count(), 1)


if __name__ == "__main__":
    unittest.main()
