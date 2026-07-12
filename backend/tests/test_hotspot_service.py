import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.analysis.hotspot_config import HotspotConfig
from app.analysis.result import DatasetChangedError
from app.extensions import db
from app.models import (
    AggregationRun,
    AnalysisRunArticle,
    Article,
    ArticleSnapshot,
    DocumentFeatures,
    Event,
    EventHeatSnapshot,
    HotspotRun,
    HotSeedExpansion,
    TopicArticleAssignment,
    TopicResult,
    Task,
)
from app.services.content_analysis_service import create_analysis_run, run_content_analysis
from app.services.hotspot_service import (
    _heat_article,
    create_hotspot_run,
    discover_hotspot_topics,
    finalize_hotspot_heat,
    get_current_hotspots,
    get_hotspot_run,
    run_hotspot_analysis,
)
from app.services.task_service import reset_task_store


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FRONTEND_ORIGINS = ["http://localhost:5173"]
    BGE_ENABLED = False
    LLM_API_KEY = ""
    LLM_BASE_URL = "https://api.deepseek.com"
    LLM_MODEL_NAME = "deepseek-chat"
    LLM_REQUEST_TIMEOUT = 5
    JWT_EXPIRES_DELTA = timedelta(hours=24)
    DEMO_ADMIN_USERNAME = "admin"
    DEMO_ADMIN_PASSWORD = "admin123"
    TASKS_RUN_SYNC = True
    TASK_RUNNING_TIMEOUT_SECONDS = 3600


class FakeTopicClient:
    def chat(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        if "电影" in prompt:
            category, name = "娱乐事件", "电影票房讨论"
        else:
            category, name = "自然灾害", "重庆暴雨救援"
        return {
            "content": json.dumps(
                {"category": category, "topic_name": name, "confidence": 0.9},
                ensure_ascii=False,
            ),
            "model": "fake",
            "raw": {},
        }


class HotspotServiceTest(unittest.TestCase):
    def setUp(self):
        reset_task_store()
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.now = datetime.now(timezone.utc).replace(tzinfo=None)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        reset_task_store()

    def _article(self, index, title, tokens, platform, event_id=None):
        publish_time = self.now - timedelta(hours=index)
        article = Article(
            event_id=event_id,
            platform=platform,
            source_type="news",
            source_article_id=str(index),
            url=f"https://example.com/{index}",
            url_hash=f"{index:064x}",
            title=title,
            raw_content=" ".join(tokens),
            clean_content=" ".join(tokens),
            clean_status="success",
            content_version=1,
            nlp_weight=1.0,
            publish_time=publish_time,
            first_crawled_at=publish_time,
            comments_count=index * 3,
            likes_count=index * 10,
            reposts_count=index,
        )
        db.session.add(article)
        db.session.flush()
        snapshot = ArticleSnapshot(
            article_id=article.id,
            crawled_at=publish_time + timedelta(minutes=10),
            fetch_status="success",
            content_hash=f"{index + 100:064x}",
            comments_count=article.comments_count,
            likes_count=article.likes_count,
            reposts_count=article.reposts_count,
        )
        db.session.add(snapshot)
        db.session.flush()
        article.latest_snapshot_id = snapshot.id
        db.session.add(
            DocumentFeatures(
                article_id=article.id,
                tokens=tokens,
                tfidf_tokens=tokens,
                sentiment_tokens=tokens,
                topics=[],
                mentions=["重庆"] if "重庆" in tokens else [],
                segment_version="v1",
            )
        )
        db.session.commit()
        return article

    def _analysis_run(self, with_events=False):
        event_a = Event(title="重庆暴雨") if with_events else None
        event_b = Event(title="暑期电影") if with_events else None
        if with_events:
            db.session.add_all([event_a, event_b])
            db.session.commit()
        rows = [
            self._article(1, "重庆暴雨预警", ["重庆", "暴雨", "预警", "救援"], "news", event_a.id if event_a else None),
            self._article(2, "暴雨道路积水", ["暴雨", "积水", "道路", "救援"], "weibo", event_a.id if event_a else None),
            self._article(3, "重庆应急救援", ["重庆", "应急", "救援", "暴雨"], "zhihu", event_a.id if event_a else None),
            self._article(4, "新电影上映", ["电影", "上映", "演员", "票房"], "news", event_b.id if event_b else None),
            self._article(5, "电影票房增长", ["电影", "票房", "影院", "观众"], "weibo", event_b.id if event_b else None),
            self._article(6, "演员参加首映", ["演员", "首映", "电影", "观众"], "bilibili", event_b.id if event_b else None),
        ]
        run, _ = create_analysis_run(
            [article.id for article in rows], mode="hot", platforms=[]
        )
        run_content_analysis(run.id)
        return run, rows, (event_a, event_b)

    def test_create_run_is_reused_for_same_analysis_and_config(self):
        analysis_run, _articles, _events = self._analysis_run()

        first, reused_first = create_hotspot_run(
            analysis_run.id, config=HotspotConfig()
        )
        second, reused_second = create_hotspot_run(
            analysis_run.id, config=HotspotConfig()
        )

        self.assertFalse(reused_first)
        self.assertTrue(reused_second)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.scope, "global")

    def test_failed_run_retry_creates_new_attempt(self):
        analysis_run, _articles, _events = self._analysis_run()
        first, _ = create_hotspot_run(analysis_run.id, config=HotspotConfig())
        first.status = "failed"
        first.error_code = "TEST_FAILURE"
        db.session.commit()

        second, reused = create_hotspot_run(
            analysis_run.id, config=HotspotConfig()
        )

        self.assertFalse(reused)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(first.attempt, 1)
        self.assertEqual(second.attempt, 2)

    def test_topic_discovery_succeeds_without_fabricating_events(self):
        analysis_run, articles, _events = self._analysis_run()
        hotspot_run, _ = create_hotspot_run(analysis_run.id, config=HotspotConfig())

        result = run_hotspot_analysis(
            hotspot_run.id,
            config=HotspotConfig(),
            client=FakeTopicClient(),
            calculated_at=self.now,
        )

        db.session.refresh(hotspot_run)
        self.assertEqual(result["topic_status"], "success")
        self.assertEqual(result["heat_status"], "pending")
        self.assertIn("EVENT_AGGREGATION_PENDING", result["warnings"])
        self.assertGreaterEqual(TopicResult.query.count(), 2)
        self.assertEqual(TopicArticleAssignment.query.count(), len(articles))
        self.assertEqual(EventHeatSnapshot.query.count(), 0)
        self.assertEqual({article.event_id for article in articles}, {None})

    def test_aggregation_closes_topic_to_heat_loop_without_preassigned_events(self):
        from app.services.event_aggregation_service import (
            create_aggregation_run,
            run_event_aggregation,
        )

        analysis_run, articles, _events = self._analysis_run()
        hotspot_run, _ = create_hotspot_run(analysis_run.id, config=HotspotConfig())

        topic_result = discover_hotspot_topics(
            hotspot_run.id,
            config=HotspotConfig(),
            client=FakeTopicClient(),
        )
        aggregation_run, _ = create_aggregation_run(
            analysis_run.id, hotspot_run_id=hotspot_run.id
        )
        aggregation_result = run_event_aggregation(aggregation_run.id, now=self.now)
        heat_result = finalize_hotspot_heat(
            hotspot_run.id,
            aggregation_run_id=aggregation_run.id,
            config=HotspotConfig(),
            calculated_at=self.now,
        )

        self.assertEqual(topic_result["topic_status"], "success")
        self.assertEqual(aggregation_result["status"], "success")
        self.assertEqual(heat_result["heat_status"], "success")
        self.assertTrue(all(article.event_id is not None for article in articles))
        self.assertGreaterEqual(Event.query.count(), 2)
        self.assertGreaterEqual(EventHeatSnapshot.query.count(), 2)
        self.assertEqual(AggregationRun.query.count(), 1)

    def test_existing_event_mapping_creates_heat_snapshots_and_updates_events(self):
        analysis_run, articles, events = self._analysis_run(with_events=True)
        seed = self._article(
            99,
            "#重庆暴雨#",
            ["重庆", "暴雨"],
            "weibo_hot",
        )
        seed.source_type = "hotlist"
        seed.raw_json = {"rank": 1}
        db.session.add(
            HotSeedExpansion(
                seed_article_id=seed.id,
                search_query="重庆暴雨",
                crawl_task_id=None,
                platform=articles[0].platform,
                article_id=articles[0].id,
                source_rank=1,
                discovered_at=self.now,
            )
        )
        db.session.commit()
        hotspot_run, _ = create_hotspot_run(analysis_run.id, config=HotspotConfig())

        result = run_hotspot_analysis(
            hotspot_run.id,
            config=HotspotConfig(),
            client=FakeTopicClient(),
            calculated_at=self.now,
        )

        self.assertEqual(result["heat_status"], "success")
        self.assertEqual(EventHeatSnapshot.query.count(), 2)
        snapshots = EventHeatSnapshot.query.order_by(EventHeatSnapshot.event_id).all()
        self.assertTrue(all(item.final_heat >= 0 for item in snapshots))
        event_a_snapshot = next(item for item in snapshots if item.event_id == events[0].id)
        self.assertEqual(event_a_snapshot.raw_statistics["best_hotlist_rank"], 1)
        for event in events:
            db.session.refresh(event)
            self.assertIsNotNone(event.current_heat_snapshot_id)
            self.assertEqual(event.independent_report_count, 3)
            self.assertEqual(event.platform_count, 3)
        self.assertEqual(len(get_current_hotspots()["events"]), 2)

    def test_heat_article_preserves_explicit_zero_quality_weights(self):
        article = self._article(88, "低质量样本", ["低质量", "样本"], "news")
        article.duplicate_weight = 0
        article.spam_weight = 0

        heat_article = _heat_article(article, None, is_representative=True)

        self.assertEqual(heat_article.duplicate_weight, 0)
        self.assertEqual(heat_article.spam_weight, 0)

    def test_heat_uses_analysis_run_representative_flag(self):
        analysis_run, articles, events = self._analysis_run(with_events=True)
        row = AnalysisRunArticle.query.filter_by(
            analysis_run_id=analysis_run.id, article_id=articles[0].id
        ).one()
        row.is_representative = False
        db.session.commit()
        hotspot_run, _ = create_hotspot_run(analysis_run.id, config=HotspotConfig())

        run_hotspot_analysis(
            hotspot_run.id,
            config=HotspotConfig(),
            client=FakeTopicClient(),
            calculated_at=self.now,
        )

        snapshot = EventHeatSnapshot.query.filter_by(event_id=events[0].id).one()
        self.assertEqual(snapshot.raw_statistics["independent_report_count_7d"], 2)

    def test_hotspot_window_excludes_old_documents_from_topics_and_heat(self):
        analysis_run, articles, events = self._analysis_run(with_events=True)
        old_time = self.now - timedelta(days=8)
        articles[0].publish_time = old_time
        articles[0].first_crawled_at = old_time
        db.session.commit()
        hotspot_run, _ = create_hotspot_run(analysis_run.id, config=HotspotConfig())

        run_hotspot_analysis(
            hotspot_run.id,
            config=HotspotConfig(),
            client=FakeTopicClient(),
            calculated_at=self.now,
        )

        db.session.refresh(hotspot_run)
        snapshot = EventHeatSnapshot.query.filter_by(event_id=events[0].id).one()
        self.assertEqual(hotspot_run.metrics["document_count"], 5)
        self.assertEqual(snapshot.raw_statistics["independent_report_count_7d"], 2)

    def test_default_snapshot_time_is_run_window_end(self):
        analysis_run, _articles, _events = self._analysis_run(with_events=True)
        hotspot_run, _ = create_hotspot_run(analysis_run.id, config=HotspotConfig())

        run_hotspot_analysis(
            hotspot_run.id, config=HotspotConfig(), client=FakeTopicClient()
        )

        self.assertEqual(
            {item.calculated_at for item in EventHeatSnapshot.query.all()},
            {hotspot_run.window_end},
        )

    def test_changed_content_identity_fails_without_partial_topics(self):
        analysis_run, articles, _events = self._analysis_run()
        hotspot_run, _ = create_hotspot_run(analysis_run.id, config=HotspotConfig())
        articles[0].content_version = 2
        db.session.commit()

        with self.assertRaises(DatasetChangedError):
            run_hotspot_analysis(
                hotspot_run.id,
                config=HotspotConfig(),
                client=FakeTopicClient(),
                calculated_at=self.now,
            )

        self.assertEqual(TopicResult.query.count(), 0)
        detail = get_hotspot_run(hotspot_run.id, admin=True)
        self.assertEqual(detail["status"], "failed")
        self.assertEqual(detail["error_code"], "DATASET_CHANGED")

    def test_older_run_cannot_overwrite_newer_event_summary(self):
        analysis_run, _articles, events = self._analysis_run(with_events=True)
        older_config = HotspotConfig()
        newer_config = HotspotConfig(core_weight=0.8, spread_weight=0.2)
        older_run, _ = create_hotspot_run(analysis_run.id, config=older_config)
        newer_run, _ = create_hotspot_run(analysis_run.id, config=newer_config)
        newer_time = self.now + timedelta(hours=1)
        older_time = self.now

        run_hotspot_analysis(
            newer_run.id,
            config=newer_config,
            client=FakeTopicClient(),
            calculated_at=newer_time,
        )
        newer_snapshot_ids = {}
        for event in events:
            db.session.refresh(event)
            newer_snapshot_ids[event.id] = event.current_heat_snapshot_id

        run_hotspot_analysis(
            older_run.id,
            config=older_config,
            client=FakeTopicClient(),
            calculated_at=older_time,
        )

        for event in events:
            db.session.refresh(event)
            self.assertEqual(event.current_heat_snapshot_id, newer_snapshot_ids[event.id])

    def test_absent_previous_hot_event_is_cleared_with_left_hot_snapshot(self):
        first_analysis, articles, events = self._analysis_run(with_events=True)
        first_run, _ = create_hotspot_run(first_analysis.id, config=HotspotConfig())
        run_hotspot_analysis(
            first_run.id,
            config=HotspotConfig(),
            client=FakeTopicClient(),
            calculated_at=self.now,
        )
        event_a, event_b = events
        db.session.refresh(event_b)
        self.assertTrue(event_b.is_hot)

        second_analysis, _ = create_analysis_run(
            [article.id for article in articles[:3]], mode="hot", platforms=[]
        )
        run_content_analysis(second_analysis.id)
        second_run, _ = create_hotspot_run(
            second_analysis.id,
            config=HotspotConfig(core_weight=0.8, spread_weight=0.2),
        )
        run_hotspot_analysis(
            second_run.id,
            config=HotspotConfig(core_weight=0.8, spread_weight=0.2),
            client=FakeTopicClient(),
            calculated_at=self.now + timedelta(hours=1),
        )

        db.session.refresh(event_a)
        db.session.refresh(event_b)
        self.assertTrue(event_a.is_hot)
        self.assertFalse(event_b.is_hot)
        self.assertIsNone(event_b.hot_rank)
        left_snapshot = EventHeatSnapshot.query.filter_by(
            hotspot_run_id=second_run.id, event_id=event_b.id
        ).one()
        self.assertEqual(left_snapshot.status_change, "left_hot")
        self.assertFalse(left_snapshot.eligible_as_hot)

    def test_admin_api_runs_background_hotspot_and_exposes_ranking(self):
        analysis_run, _articles, _events = self._analysis_run(with_events=True)
        client = self.app.test_client()
        login = client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin123"}
        )
        token = login.get_json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post(
            "/api/hotspots/runs",
            json={"analysis_run_id": analysis_run.id},
            headers=headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()["data"]
        self.assertIn("hotspot_run_id", payload)
        self.assertIn("task_id", payload)
        self.assertEqual(db.session.get(Task, payload["task_id"]).status, "success")
        detail = client.get(
            f"/api/hotspots/runs/{payload['hotspot_run_id']}", headers=headers
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["data"]["topic_status"], "success")
        self.assertTrue(detail.get_json()["data"]["topics"])
        ranked = client.get("/api/hotspots", headers=headers)
        self.assertEqual(ranked.status_code, 200)
        self.assertEqual(ranked.get_json()["data"]["total"], 2)
        ranked_item = ranked.get_json()["data"]["events"][0]
        self.assertIn("calculated_at", ranked_item)
        self.assertEqual(ranked_item["formula_version"], "v1")
        self.assertIn("warnings", ranked_item)
        board = client.get("/api/events", headers=headers)
        self.assertEqual(board.status_code, 200)
        self.assertEqual(board.get_json()["data"]["total"], 2)
        self.assertEqual(
            {item["id"] for item in board.get_json()["data"]["events"]},
            {event.id for event in _events},
        )
        board_item = board.get_json()["data"]["events"][0]
        self.assertIn("calculated_at", board_item)
        self.assertEqual(board_item["formula_version"], "v1")
        self.assertIn("warnings", board_item)

        invalid_page = client.get("/api/events?page=x", headers=headers)
        self.assertEqual(invalid_page.status_code, 400)

    def test_repeated_pending_api_request_reuses_same_task(self):
        analysis_run, _articles, _events = self._analysis_run()
        client = self.app.test_client()
        login = client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin123"}
        )
        token = login.get_json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.api.hotspots.submit_background_job", return_value=None):
            first = client.post(
                "/api/hotspots/runs",
                json={"analysis_run_id": analysis_run.id},
                headers=headers,
            )
            second = client.post(
                "/api/hotspots/runs",
                json={"analysis_run_id": analysis_run.id},
                headers=headers,
            )

        first_data = first.get_json()["data"]
        second_data = second.get_json()["data"]
        self.assertEqual(first_data["task_id"], second_data["task_id"])
        self.assertTrue(second_data["reused"])
        self.assertEqual(Task.query.filter_by(task_type="hotspot").count(), 1)


if __name__ == "__main__":
    unittest.main()
