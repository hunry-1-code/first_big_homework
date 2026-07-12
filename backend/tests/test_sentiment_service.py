import hashlib
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.analysis.sentiment_analyzer import SentimentAnalysisError
from app.analysis.sentiment_config import SentimentConfig
from app.core.security import create_token
from app.extensions import db
from app.models import (
    AggregationAssignment,
    AggregationCluster,
    AggregationRun,
    Article,
    ArticleSentimentResult,
    Event,
    EventArticleMembership,
    EventSentimentSnapshot,
    SentimentRun,
)
from app.services.sentiment_analysis_service import (
    create_sentiment_run,
    get_cluster_sentiment,
    get_event_sentiment,
    run_sentiment_analysis,
)
from app.services.event_service import get_event_detail


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FRONTEND_ORIGINS = ["http://localhost:5173"]
    AUTO_CREATE_DB = False
    LLM_MODEL_NAME = "deepseek-chat"
    LLM_API_KEY = "test-key"
    LLM_BASE_URL = "https://example.invalid"
    LLM_REQUEST_TIMEOUT = 5
    JWT_EXPIRES_DELTA = timedelta(hours=1)
    TASKS_RUN_SYNC = True
    TASK_RECOVER_ON_STARTUP = False


def llm_result(label="negative", score=-0.7, dimension="stance"):
    return {
        "label": label,
        "score": score,
        "confidence": 0.9,
        "dimension": dimension,
        "target": "事件处置",
        "reason": "测试判断依据",
        "method": "llm",
        "model_name": "deepseek-chat",
        "warnings": [],
        "raw_response": {"label": label},
    }


class SentimentServiceTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _article(self, index, *, duplicate_of_id=None, platform="weibo"):
        return Article(
            platform=platform,
            source_type="news",
            source_article_id=f"sentiment-{index}",
            url=f"https://example.com/sentiment/{index}",
            url_hash=hashlib.sha256(str(index).encode()).hexdigest(),
            title=f"事件报道 {index}",
            clean_content="事件处置引发讨论，相关部门发布最新通报。" * 20,
            clean_status="success",
            nlp_weight=1.0,
            spam_weight=1.0,
            duplicate_weight=0.2 if duplicate_of_id else 1.0,
            is_duplicate=duplicate_of_id is not None,
            duplicate_of_id=duplicate_of_id,
            content_version=1,
            publish_time=datetime(2026, 7, 10 + index, 8),
        )

    def _aggregation(self, articles, *, scope="search_shared", status="success"):
        run = AggregationRun(
            analysis_run_id=1,
            scope=scope,
            mode="search" if scope == "search_shared" else "hot",
            attempt=1,
            dataset_hash="aggregation-dataset",
            config_hash="aggregation-config",
            config={},
            versions={},
            statistics={},
            status=status,
            warnings=[],
        )
        db.session.add(run)
        db.session.flush()
        event = None
        if scope == "global":
            event = Event(title="测试事件", topic_category="社会事件")
            db.session.add(event)
            db.session.flush()
        cluster = AggregationCluster(
            aggregation_run_id=run.id,
            cluster_index=0,
            resolved_event_id=event.id if event else None,
            title="测试事件",
            topic_category="社会事件",
            topic_name="测试事件进展",
            keywords=[],
            entities={},
            member_count=len(articles),
            platform_count=len({item.platform for item in articles}),
            confidence=0.9,
        )
        db.session.add(cluster)
        db.session.flush()
        for article in articles:
            db.session.add(article)
        db.session.flush()
        for article in articles:
            db.session.add(
                AggregationAssignment(
                    aggregation_run_id=run.id,
                    aggregation_cluster_id=cluster.id,
                    article_id=article.id,
                    content_identity=f"article:{article.id}:v1",
                    resolved_event_id=event.id if event else None,
                    membership_action="attach",
                    similarity=0.9,
                    score_details={},
                    decision_reason=[],
                    is_representative=not article.is_duplicate,
                )
            )
            if event:
                article.event_id = event.id
                db.session.add(
                    EventArticleMembership(
                        event_id=event.id,
                        article_id=article.id,
                        active_article_id=article.id,
                        source_aggregation_run_id=run.id,
                        confidence=0.9,
                        decision_method="test",
                        is_active=True,
                        valid_from=datetime(2026, 7, 11),
                    )
                )
        db.session.commit()
        return run, cluster, event

    def test_create_run_requires_success_and_reuses_same_config(self):
        article = self._article(1)
        aggregation, _cluster, _event = self._aggregation([article])

        first, reused_first = create_sentiment_run(aggregation.id)
        second, reused_second = create_sentiment_run(aggregation.id)

        self.assertFalse(reused_first)
        self.assertTrue(reused_second)
        self.assertEqual(first.id, second.id)
        aggregation.status = "failed"
        db.session.commit()
        with self.assertRaises(ValueError):
            create_sentiment_run(aggregation.id)

    def test_search_run_creates_cluster_snapshot_without_formal_event(self):
        articles = [self._article(1), self._article(2, platform="news")]
        aggregation, cluster, _event = self._aggregation(articles)
        run, _ = create_sentiment_run(aggregation.id)

        result = run_sentiment_analysis(
            run.id,
            llm_analyzer=lambda *args, **kwargs: llm_result(),
            fallback_analyzer=lambda *args, **kwargs: llm_result("neutral", 0.0, "factual"),
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(Event.query.count(), 0)
        snapshot = EventSentimentSnapshot.query.one()
        self.assertEqual(snapshot.aggregation_cluster_id, cluster.id)
        self.assertIsNone(snapshot.event_id)
        self.assertEqual(snapshot.raw_counts["negative"], 2)
        self.assertIsNotNone(get_cluster_sentiment(cluster.id))

    def test_global_run_updates_current_summary_and_duplicate_inherits(self):
        representative = self._article(1)
        db.session.add(representative)
        db.session.flush()
        duplicate = self._article(2, duplicate_of_id=representative.id)
        aggregation, _cluster, event = self._aggregation([representative, duplicate], scope="global")
        run, _ = create_sentiment_run(aggregation.id)
        calls = []

        def analyzer(*args, **kwargs):
            calls.append(args[0])
            return llm_result()

        run_sentiment_analysis(run.id, llm_analyzer=analyzer)

        self.assertEqual(len(calls), 1)
        results = ArticleSentimentResult.query.order_by(ArticleSentimentResult.article_id).all()
        self.assertEqual([item.method for item in results], ["llm", "inherited"])
        self.assertEqual(results[1].inherited_from_result_id, results[0].id)
        self.assertEqual(event.sentiment_negative, 1.0)
        self.assertIsNotNone(event.current_sentiment_snapshot_id)
        self.assertIsNotNone(representative.current_sentiment_result_id)
        self.assertEqual(get_event_sentiment(event.id)["raw_counts"]["negative"], 2)
        self.assertEqual(get_event_detail(event.id)["sentiment"]["raw_counts"]["negative"], 2)

    def test_llm_failure_uses_fallback(self):
        article = self._article(1)
        aggregation, _cluster, _event = self._aggregation([article])
        run, _ = create_sentiment_run(aggregation.id)

        def failing(*args, **kwargs):
            raise SentimentAnalysisError("invalid llm output")

        run_sentiment_analysis(
            run.id,
            llm_analyzer=failing,
            fallback_analyzer=lambda *args, **kwargs: {
                **llm_result("neutral", 0.0, "factual"),
                "method": "snownlp",
                "model_name": "snownlp",
                "warnings": ["SNOWNLP_FALLBACK"],
            },
        )

        row = ArticleSentimentResult.query.one()
        self.assertEqual(row.method, "snownlp")
        self.assertIn("SNOWNLP_FALLBACK", row.warnings)
        self.assertEqual(SentimentRun.query.one().statistics["snownlp_count"], 1)

    def test_transient_llm_failure_retries_before_fallback(self):
        article = self._article(1)
        aggregation, _cluster, _event = self._aggregation([article])
        run, _ = create_sentiment_run(aggregation.id)
        calls = []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("temporary")
            return llm_result("positive", 0.6)

        run_sentiment_analysis(
            run.id,
            llm_analyzer=flaky,
            fallback_analyzer=lambda *args, **kwargs: self.fail(
                "fallback should not be called"
            ),
        )

        self.assertEqual(len(calls), 3)
        self.assertEqual(ArticleSentimentResult.query.one().method, "llm")

    def test_content_change_fails_without_updating_current_summary(self):
        article = self._article(1)
        aggregation, _cluster, _event = self._aggregation([article])
        run, _ = create_sentiment_run(aggregation.id)
        article.content_version = 2
        db.session.commit()

        with self.assertRaises(ValueError):
            run_sentiment_analysis(
                run.id, llm_analyzer=lambda *args, **kwargs: llm_result()
            )

        self.assertIsNone(article.current_sentiment_result_id)
        self.assertEqual(SentimentRun.query.one().status, "failed")

    def test_one_article_failure_does_not_abort_when_success_ratio_is_met(self):
        articles = [self._article(index) for index in range(1, 6)]
        aggregation, _cluster, _event = self._aggregation(articles)
        run, _ = create_sentiment_run(aggregation.id)

        def analyzer(text, **kwargs):
            if "事件报道 5" in text:
                raise SentimentAnalysisError("llm failed")
            return llm_result()

        def fallback(text, **kwargs):
            if "事件报道 5" in text:
                raise SentimentAnalysisError("fallback failed")
            return llm_result("neutral", 0.0, "factual")

        result = run_sentiment_analysis(
            run.id, llm_analyzer=analyzer, fallback_analyzer=fallback
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["failed_count"], 1)
        self.assertEqual(ArticleSentimentResult.query.count(), 4)

    def test_compatible_article_results_are_reused_across_runs(self):
        article = self._article(1)
        aggregation, _cluster, _event = self._aggregation([article])
        first, _ = create_sentiment_run(aggregation.id)
        run_sentiment_analysis(
            first.id, llm_analyzer=lambda *args, **kwargs: llm_result()
        )
        second_config = SentimentConfig(llm_retry_count=1)
        second, reused = create_sentiment_run(aggregation.id, config=second_config)
        calls = []

        result = run_sentiment_analysis(
            second.id,
            config=second_config,
            llm_analyzer=lambda *args, **kwargs: calls.append(1) or llm_result(),
        )

        self.assertFalse(reused)
        self.assertEqual(calls, [])
        self.assertEqual(result["reused_count"], 1)

    def test_event_and_cluster_sentiment_endpoints_return_snapshots(self):
        search_article = self._article(1)
        search_aggregation, cluster, _event = self._aggregation([search_article])
        search_run, _ = create_sentiment_run(search_aggregation.id)
        run_sentiment_analysis(
            search_run.id, llm_analyzer=lambda *args, **kwargs: llm_result()
        )
        global_article = self._article(2)
        global_aggregation, _global_cluster, event = self._aggregation(
            [global_article], scope="global"
        )
        global_run, _ = create_sentiment_run(global_aggregation.id)
        run_sentiment_analysis(
            global_run.id, llm_analyzer=lambda *args, **kwargs: llm_result()
        )
        token, _ = create_token({"id": 1, "username": "user", "role": "user"})
        client = self.app.test_client()
        headers = {"Authorization": f"Bearer {token}"}

        event_response = client.get(f"/api/events/{event.id}/sentiment", headers=headers)
        cluster_response = client.get(
            f"/api/aggregation/clusters/{cluster.id}/sentiment", headers=headers
        )

        self.assertEqual(event_response.status_code, 200)
        self.assertEqual(cluster_response.status_code, 200)
        self.assertEqual(event_response.get_json()["data"]["raw_counts"]["negative"], 1)
        self.assertEqual(cluster_response.get_json()["data"]["raw_counts"]["negative"], 1)

    def test_sentiment_job_calls_service_and_updates_task(self):
        from app.services.task_service import create_task, get_task
        from app.tasks import jobs

        task = create_task("sentiment", created_by=1, payload={"sentiment_run_id": 9})
        self.assertTrue(hasattr(jobs, "sentiment_job"))
        with patch(
            "app.services.sentiment_analysis_service.run_sentiment_analysis",
            return_value={"sentiment_run_id": 9, "status": "success"},
        ):
            result = jobs.sentiment_job(task["id"])

        self.assertEqual(result["sentiment_run_id"], 9)
        self.assertEqual(get_task(task["id"])["status"], "success")


if __name__ == "__main__":
    unittest.main()
