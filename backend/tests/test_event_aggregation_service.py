import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.analysis.aggregation_config import AggregationConfig
from app.extensions import db
from app.core.security import create_token
from app.models import (
    AggregationAssignment,
    AggregationCluster,
    AggregationRun,
    AnalysisRun,
    AnalysisRunArticle,
    Article,
    ArticleEmbedding,
    DocumentFeatures,
    Event,
    EventArticleMembership,
    EventMergeRecord,
    EventRepresentation,
    EventSentimentSnapshot,
    Report,
)
from app.services.event_aggregation_service import (
    create_aggregation_run,
    find_search_cache,
    publish_cluster,
    review_merge_candidate,
    run_event_aggregation,
)


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_DB = False
    FRONTEND_ORIGINS = ["http://localhost"]
    TASK_RECOVER_ON_STARTUP = False
    TASKS_RUN_SYNC = True
    JWT_EXPIRES_DELTA = timedelta(hours=1)
    DEMO_ADMIN_USERNAME = "admin"
    DEMO_ADMIN_PASSWORD = "admin123"
    BGE_ENABLED = True
    BGE_MODEL = "test-bge"
    BGE_MODEL_VERSION = "v1"
    BGE_PREPROCESS_VERSION = "v1"
    EVENT_AGGREGATION_ATTACH_THRESHOLD = 0.72
    EVENT_AGGREGATION_CREATE_THRESHOLD = 0.58
    EVENT_AGGREGATION_MOVE_MARGIN = 0.15
    EVENT_AGGREGATION_BGE_WEIGHT = 0.45
    EVENT_AGGREGATION_TFIDF_WEIGHT = 0.25
    EVENT_AGGREGATION_ENTITY_WEIGHT = 0.20
    EVENT_AGGREGATION_TIME_WEIGHT = 0.10
    EVENT_AGGREGATION_CANDIDATE_LIMIT = 20
    EVENT_AGGREGATION_MIN_EVIDENCE = 1
    EVENT_AGGREGATION_ALGORITHM_VERSION = "event-aggregation-v1"
    EVENT_SEARCH_CACHE_HOURS = 24
    EVENT_RELATED_LIMIT = 5


class EventAggregationServiceTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.now = datetime(2026, 7, 11, 12)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _article(self, index, title, tokens, vector, *, mode="hot", location="重庆"):
        article = Article(
            platform="news" if index % 2 else "weibo",
            source_type="news",
            source_article_id=f"source-{index}",
            url=f"https://example.com/{index}",
            url_hash=f"hash-{index}",
            title=title,
            clean_content=" ".join(tokens),
            clean_status="success",
            publish_time=self.now + timedelta(minutes=index),
            content_version=1,
            quality_score=0.9,
            nlp_weight=1.0,
        )
        db.session.add(article)
        db.session.flush()
        db.session.add(
            DocumentFeatures(
                article_id=article.id,
                tokens=tokens,
                tfidf_tokens=tokens,
                topics=["暴雨"],
                mentions=[location],
            )
        )
        db.session.add(
            ArticleEmbedding(
                article_id=article.id,
                content_version=1,
                content_identity=f"article:{article.id}:v1",
                model_name="test-bge",
                model_version="v1",
                preprocess_version="v1",
                dimension=len(vector),
                vector=vector,
            )
        )
        return article

    def _analysis_run(self, articles, *, mode="hot", status="success", fingerprint="query"):
        run = AnalysisRun(
            mode=mode,
            keyword="重庆暴雨" if mode == "search" else None,
            platforms=["news", "weibo"],
            query_fingerprint=fingerprint,
            dataset_hash=f"dataset-{fingerprint}-{len(articles)}",
            config_hash="feature-config",
            article_count=len(articles),
            representative_count=len(articles),
            tfidf_config={},
            versions={"algorithm": "content-v1"},
            status=status,
            completed_at=self.now,
        )
        db.session.add(run)
        db.session.flush()
        for article in articles:
            db.session.add(
                AnalysisRunArticle(
                    analysis_run_id=run.id,
                    article_id=article.id,
                    content_version=1,
                    content_identity=f"article:{article.id}:v1",
                    is_representative=True,
                    nlp_weight=1.0,
                    feature_status="success",
                    keywords=[{"term": "暴雨", "score": 1.0}],
                )
            )
        db.session.commit()
        return run

    def test_create_run_requires_success_and_reuses_same_fingerprint(self):
        article = self._article(1, "重庆暴雨救援", ["重庆", "暴雨", "救援"], [1.0, 0.0])
        failed_analysis = self._analysis_run([article], status="failed", fingerprint="failed")
        with self.assertRaises(ValueError):
            create_aggregation_run(failed_analysis.id)

        analysis = self._analysis_run([article], fingerprint="success")
        first, reused_first = create_aggregation_run(analysis.id)
        second, reused_second = create_aggregation_run(analysis.id)

        self.assertFalse(reused_first)
        self.assertTrue(reused_second)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.scope, "global")

    def test_search_scope_persists_clusters_without_formal_events(self):
        articles = [
            self._article(1, "重庆暴雨启动救援", ["重庆", "暴雨", "救援"], [1.0, 0.0]),
            self._article(2, "重庆暴雨救援进展", ["重庆", "暴雨", "进展"], [0.99, 0.01]),
        ]
        analysis = self._analysis_run(articles, mode="search", fingerprint="search-shared")
        run, _ = create_aggregation_run(analysis.id)

        result = run_event_aggregation(run.id, now=self.now)

        self.assertEqual(result["scope"], "search_shared")
        self.assertEqual(Event.query.count(), 0)
        self.assertEqual(AggregationCluster.query.count(), 1)
        self.assertEqual(AggregationAssignment.query.count(), 2)
        self.assertEqual({article.event_id for article in articles}, {None})
        self.assertIsNotNone(db.session.get(AggregationRun, run.id).cache_expires_at)

    def test_global_scope_creates_stable_event_membership_and_representation(self):
        articles = [
            self._article(1, "重庆暴雨启动救援", ["重庆", "暴雨", "救援"], [1.0, 0.0]),
            self._article(2, "重庆暴雨救援进展", ["重庆", "暴雨", "进展"], [0.99, 0.01]),
        ]
        analysis = self._analysis_run(articles, fingerprint="global")
        run, _ = create_aggregation_run(analysis.id)

        result = run_event_aggregation(run.id, now=self.now)

        self.assertEqual(result["created_event_count"], 1)
        event = Event.query.one()
        self.assertEqual({article.event_id for article in articles}, {event.id})
        self.assertEqual(EventArticleMembership.query.filter_by(is_active=True).count(), 2)
        representation = EventRepresentation.query.filter_by(event_id=event.id).one()
        self.assertEqual(representation.member_count, 2)
        self.assertIn("mention", representation.entities)
        self.assertIn("重庆", representation.entities["mention"])
        self.assertAlmostEqual(sum(value * value for value in representation.vector), 1.0, places=6)

        repeated = run_event_aggregation(run.id, now=self.now)
        self.assertEqual(repeated["aggregation_run_id"], run.id)
        self.assertEqual(Event.query.count(), 1)
        self.assertEqual(EventArticleMembership.query.count(), 2)

    def test_duplicate_article_inherits_event_without_changing_representation_center(self):
        representative = self._article(
            1, "重庆暴雨启动救援", ["重庆", "暴雨", "救援"], [1.0, 0.0]
        )
        duplicate = self._article(
            2, "转载：重庆暴雨启动救援", ["重庆", "暴雨", "救援"], [0.0, 1.0]
        )
        duplicate.is_duplicate = True
        duplicate.duplicate_of_id = representative.id
        analysis = self._analysis_run([representative, duplicate], fingerprint="duplicate")
        duplicate_row = AnalysisRunArticle.query.filter_by(
            analysis_run_id=analysis.id, article_id=duplicate.id
        ).one()
        duplicate_row.is_representative = False
        duplicate_row.feature_status = "skipped_duplicate"
        db.session.commit()
        run, _ = create_aggregation_run(analysis.id)

        run_event_aggregation(run.id, now=self.now)

        self.assertIsNotNone(representative.event_id)
        self.assertEqual(duplicate.event_id, representative.event_id)
        self.assertEqual(EventArticleMembership.query.filter_by(is_active=True).count(), 2)
        representation = EventRepresentation.query.one()
        self.assertEqual(representation.member_count, 1)
        inherited = AggregationAssignment.query.filter_by(article_id=duplicate.id).one()
        self.assertFalse(inherited.is_representative)
        self.assertIn("DUPLICATE_INHERITANCE", inherited.decision_reason)

    def test_existing_membership_does_not_move_for_small_score_improvement(self):
        article = self._article(1, "重庆暴雨", ["重庆", "暴雨"], [1.0, 0.0])
        first_analysis = self._analysis_run([article], fingerprint="move-first")
        first_run, _ = create_aggregation_run(first_analysis.id)
        run_event_aggregation(first_run.id, now=self.now)
        current_event = Event.query.one()
        current_representation = EventRepresentation.query.one()
        current_representation.vector = [0.98, 0.02]
        candidate = Event(title="重庆强降雨")
        db.session.add(candidate)
        db.session.flush()
        db.session.add(
            EventRepresentation(
                event_id=candidate.id,
                model_name="test-bge",
                model_version="v1",
                preprocess_version="v1",
                dimension=2,
                vector=[1.0, 0.0],
                keywords=["重庆", "暴雨"],
                entities={"mention": ["重庆"]},
                member_count=1,
                source_aggregation_run_id=first_run.id,
            )
        )
        db.session.commit()
        second_analysis = self._analysis_run([article], fingerprint="move-second")
        second_run, _ = create_aggregation_run(second_analysis.id)

        run_event_aggregation(second_run.id, now=self.now + timedelta(hours=1))

        self.assertEqual(article.event_id, current_event.id)
        assignment = AggregationAssignment.query.filter_by(
            aggregation_run_id=second_run.id, article_id=article.id
        ).one()
        self.assertEqual(assignment.membership_action, "unchanged")
        self.assertIn("MOVE_MARGIN_NOT_MET", assignment.decision_reason)

    def test_confirming_merge_candidate_moves_active_memberships(self):
        articles = [
            self._article(1, "事件A", ["事件", "A"], [1.0, 0.0]),
            self._article(2, "事件B", ["事件", "B"], [0.0, 1.0]),
        ]
        analysis = self._analysis_run(articles, fingerprint="merge")
        run, _ = create_aggregation_run(analysis.id)
        source = Event(title="来源事件")
        target = Event(title="目标事件")
        db.session.add_all([source, target])
        db.session.flush()
        for event, article in zip((source, target), articles):
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
                    valid_from=self.now,
                )
            )
        record = EventMergeRecord(
            source_event_id=source.id,
            target_event_id=target.id,
            aggregation_run_id=run.id,
            similarity_evidence={"bge": 0.95},
            status="pending",
        )
        db.session.add(record)
        db.session.commit()

        result = review_merge_candidate(
            record.id, approve=True, reviewer_id=1, now=self.now + timedelta(hours=1)
        )

        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(articles[0].event_id, target.id)
        self.assertEqual(
            EventArticleMembership.query.filter_by(event_id=target.id, is_active=True).count(),
            2,
        )
        self.assertEqual(
            EventArticleMembership.query.filter_by(event_id=source.id, is_active=True).count(),
            0,
        )

    def test_admin_can_reject_merge_candidate_via_api(self):
        article = self._article(1, "合并候选", ["合并", "候选"], [1.0, 0.0])
        analysis = self._analysis_run([article], fingerprint="merge-api")
        run, _ = create_aggregation_run(analysis.id)
        source = Event(title="来源")
        target = Event(title="目标")
        db.session.add_all([source, target])
        db.session.flush()
        record = EventMergeRecord(
            source_event_id=source.id,
            target_event_id=target.id,
            aggregation_run_id=run.id,
            status="pending",
        )
        db.session.add(record)
        db.session.commit()
        client = self.app.test_client()
        login = client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin123"}
        )
        headers = {"Authorization": f"Bearer {login.get_json()['data']['token']}"}

        response = client.post(
            f"/api/aggregation/merge-candidates/{record.id}/reject", headers=headers
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["status"], "rejected")

    def test_search_cache_boundary_is_exactly_twenty_four_hours(self):
        article = self._article(1, "重庆暴雨", ["重庆", "暴雨"], [1.0, 0.0])
        analysis = self._analysis_run([article], mode="search", fingerprint="cache")
        run, _ = create_aggregation_run(analysis.id)
        run_event_aggregation(run.id, now=self.now)

        fresh = find_search_cache("cache", now=self.now + timedelta(hours=23, minutes=59, seconds=59))
        stale = find_search_cache("cache", now=self.now + timedelta(hours=24))

        self.assertTrue(fresh["cached"])
        self.assertFalse(fresh["stale"])
        self.assertTrue(stale["stale"])
        self.assertTrue(stale["refresh_required"])
        invalidated = find_search_cache(
            "cache",
            now=self.now + timedelta(hours=1),
            config=AggregationConfig(attach_threshold=0.75),
        )
        self.assertIsNone(invalidated["run"])

    def test_admin_can_read_aggregation_run_and_clusters_via_api(self):
        article = self._article(1, "重庆暴雨", ["重庆", "暴雨"], [1.0, 0.0])
        analysis = self._analysis_run([article], fingerprint="api")
        run, _ = create_aggregation_run(analysis.id)
        run_event_aggregation(run.id, now=self.now)
        client = self.app.test_client()
        login = client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin123"}
        )
        headers = {"Authorization": f"Bearer {login.get_json()['data']['token']}"}

        detail = client.get(f"/api/aggregation/runs/{run.id}", headers=headers)
        clusters = client.get(
            f"/api/aggregation/runs/{run.id}/clusters", headers=headers
        )

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["data"]["aggregation_run_id"], run.id)
        self.assertEqual(clusters.status_code, 200)
        self.assertEqual(clusters.get_json()["data"]["total"], 1)

    def test_private_manual_run_is_not_visible_to_another_user(self):
        article = self._article(1, "手动分析", ["手动", "分析"], [1.0, 0.0])
        analysis = self._analysis_run([article], mode="manual", fingerprint="private")
        run, _ = create_aggregation_run(analysis.id, user_id=1)
        token, _ = create_token({"id": 2, "username": "other", "role": "user"})
        headers = {"Authorization": f"Bearer {token}"}

        response = self.app.test_client().get(
            f"/api/aggregation/runs/{run.id}", headers=headers
        )

        self.assertEqual(response.status_code, 404)

    def test_admin_can_start_aggregation_task_via_api(self):
        article = self._article(1, "重庆暴雨", ["重庆", "暴雨"], [1.0, 0.0])
        analysis = self._analysis_run([article], fingerprint="api-start")
        client = self.app.test_client()
        login = client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin123"}
        )
        headers = {"Authorization": f"Bearer {login.get_json()['data']['token']}"}

        response = client.post(
            "/api/aggregation/runs",
            json={"analysis_run_id": analysis.id},
            headers=headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertIsInstance(data["aggregation_run_id"], int)
        self.assertIsInstance(data["task_id"], int)
        self.assertEqual(db.session.get(AggregationRun, data["aggregation_run_id"]).status, "success")

    def test_search_cluster_publication_is_idempotent(self):
        articles = [
            self._article(1, "重庆暴雨启动救援", ["重庆", "暴雨", "救援"], [1.0, 0.0]),
            self._article(2, "重庆暴雨救援进展", ["重庆", "暴雨", "进展"], [0.99, 0.01]),
        ]
        analysis = self._analysis_run(articles, mode="search", fingerprint="publish")
        search_run, _ = create_aggregation_run(analysis.id)
        run_event_aggregation(search_run.id, now=self.now)
        cluster = AggregationCluster.query.one()

        first = publish_cluster(cluster.id, user_id=1, now=self.now)
        second = publish_cluster(cluster.id, user_id=1, now=self.now)

        self.assertEqual(first["event_id"], second["event_id"])
        self.assertEqual(Event.query.count(), 1)
        self.assertEqual(EventArticleMembership.query.filter_by(is_active=True).count(), 2)
        self.assertEqual(db.session.get(AggregationCluster, cluster.id).resolved_event_id, first["event_id"])
        self.assertEqual(EventSentimentSnapshot.query.filter_by(event_id=first["event_id"]).count(), 1)
        self.assertTrue(Report.query.filter_by(event_id=first["event_id"]).one().overview_text)
        self.assertEqual(first["postprocess"]["sentiment"], "success")

    def test_admin_can_publish_search_cluster_via_api(self):
        article = self._article(1, "重庆暴雨", ["重庆", "暴雨"], [1.0, 0.0])
        analysis = self._analysis_run([article], mode="search", fingerprint="publish-api")
        search_run, _ = create_aggregation_run(analysis.id)
        run_event_aggregation(search_run.id, now=self.now)
        cluster = AggregationCluster.query.one()
        client = self.app.test_client()
        login = client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin123"}
        )
        headers = {"Authorization": f"Bearer {login.get_json()['data']['token']}"}

        response = client.post(
            f"/api/aggregation/clusters/{cluster.id}/publish", headers=headers
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.get_json()["data"]["event_id"], int)


if __name__ == "__main__":
    unittest.main()
