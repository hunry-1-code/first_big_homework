import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.analysis.feature_config import FeatureConfig
from app.analysis.result import DatasetChangedError, NoValidDocumentError
from app.extensions import db
from app.models import (
    AnalysisRun,
    AnalysisRunArticle,
    Article,
    ArticleEmbedding,
    ArticleSnapshot,
    DocumentFeatures,
    Task,
)
from app.services.task_service import create_task, get_task, reset_task_store
from app.services import task_service
from app.tasks.jobs import analyze_job
from app.services.content_analysis_service import (
    create_analysis_run,
    get_analysis_run,
    list_analysis_runs,
    run_content_analysis,
)


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FRONTEND_ORIGINS = ["http://localhost:5173"]
    BGE_ENABLED = False
    BGE_MODEL = "fake-model"
    BGE_MODEL_VERSION = "test"
    BGE_PREPROCESS_VERSION = "v1"
    BGE_MAX_TEXT_LENGTH = 1000


class FakeEncoder:
    model_name = "fake-model"
    model_version = "test"
    preprocess_version = "v1"

    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def encode(self, texts):
        self.calls += 1
        if self.fail:
            raise RuntimeError("model unavailable")
        return [[0.6, 0.8] for _ in texts]


class ContentAnalysisServiceTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _article(
        self,
        index,
        title,
        tokens,
        platform="news",
        clean_status="success",
        duplicate_of_id=None,
        is_advertisement=False,
        nlp_weight=1.0,
    ):
        article = Article(
            platform=platform,
            source_type="news",
            source_article_id=str(index),
            url=f"https://example.com/{index}",
            url_hash=f"{index:064x}",
            title=title,
            raw_content=" ".join(tokens * 15),
            clean_content=" ".join(tokens * 15),
            clean_status=clean_status,
            content_version=1,
            duplicate_of_id=duplicate_of_id,
            is_duplicate=duplicate_of_id is not None,
            is_advertisement=is_advertisement,
            nlp_weight=nlp_weight,
        )
        db.session.add(article)
        db.session.flush()
        snapshot = ArticleSnapshot(
            article_id=article.id,
            fetch_status="success",
            content_hash=f"{index + 100:064x}",
            raw_content=article.raw_content,
        )
        db.session.add(snapshot)
        db.session.flush()
        article.latest_snapshot_id = snapshot.id
        features = DocumentFeatures(
            article_id=article.id,
            tokens=tokens,
            tfidf_tokens=tokens,
            sentiment_tokens=tokens,
            topics=["重庆暴雨"],
            mentions=["重庆"],
            segment_version="v1",
        )
        db.session.add(features)
        db.session.commit()
        return article

    def _valid_articles(self):
        return [
            self._article(1, "重庆暴雨官方通报", ["重庆", "暴雨", "官方", "通报", "救援"], "weibo"),
            self._article(2, "重庆启动应急响应", ["重庆", "应急", "响应", "积水", "救援"], "news"),
            self._article(3, "暴雨影响交通", ["暴雨", "交通", "道路", "积水"], "bilibili"),
            self._article(4, "城市内涝引发关注", ["城市", "内涝", "居民", "排水"], "zhihu"),
            self._article(5, "气象台发布预警", ["重庆", "气象", "预警", "强降雨"], "news"),
        ]

    def test_create_run_snapshots_requested_articles_and_marks_skips(self):
        valid = self._valid_articles()
        duplicate = self._article(6, "转载", ["重庆", "暴雨"], duplicate_of_id=valid[0].id)
        advertisement = self._article(7, "广告", ["限时", "优惠"], is_advertisement=True)
        failed = self._article(8, "失败", ["失败"], clean_status="failed")

        run, reused = create_analysis_run(
            [item.id for item in [*valid, duplicate, advertisement, failed]],
            mode="search",
            keyword="重庆暴雨",
            platforms=["weibo", "news", "bilibili", "zhihu"],
            config=FeatureConfig(),
        )

        self.assertFalse(reused)
        self.assertEqual(run.article_count, 8)
        self.assertEqual(run.representative_count, 3)
        rows = AnalysisRunArticle.query.filter_by(analysis_run_id=run.id).all()
        statuses = {row.article_id: row.feature_status for row in rows}
        self.assertEqual(statuses[duplicate.id], "skipped_duplicate")
        self.assertEqual(statuses[advertisement.id], "skipped_advertisement")
        self.assertEqual(statuses[failed.id], "skipped_invalid")
        self.assertTrue(all(row.content_identity for row in rows))

    def test_run_analysis_persists_run_specific_keywords_without_vectors(self):
        articles = self._valid_articles()
        run, _ = create_analysis_run(
            [article.id for article in articles],
            mode="search",
            keyword="重庆暴雨",
            platforms=["news", "weibo", "bilibili", "zhihu"],
            config=FeatureConfig(),
        )

        result = run_content_analysis(run.id, config=FeatureConfig())

        db.session.refresh(run)
        self.assertEqual(run.status, "success")
        self.assertEqual(result["analysis_run_id"], run.id)
        self.assertEqual(result["representative_count"], 3)
        rows = AnalysisRunArticle.query.filter_by(
            analysis_run_id=run.id, is_representative=True
        ).all()
        self.assertTrue(all(row.feature_status == "success" for row in rows))
        self.assertTrue(all(row.keywords for row in rows))
        for row in rows:
            json.dumps(row.keywords, ensure_ascii=False)
            self.assertTrue(all(isinstance(item, dict) for item in row.keywords))
            self.assertTrue(
                all("term" in item and "score" in item for item in row.keywords)
            )
        self.assertTrue(
            all(
                DocumentFeatures.query.filter_by(article_id=article.id).one().tfidf_vector
                is None
                for article in articles
            )
        )

    def test_successful_identical_run_is_reused(self):
        articles = self._valid_articles()
        first, _ = create_analysis_run(
            [article.id for article in articles],
            mode="search",
            keyword="重庆暴雨",
            platforms=["weibo", "news"],
            config=FeatureConfig(),
        )
        run_content_analysis(first.id, config=FeatureConfig())

        second, reused = create_analysis_run(
            [article.id for article in articles],
            mode="search",
            keyword="重庆暴雨",
            platforms=["news", "weibo"],
            config=FeatureConfig(),
        )

        self.assertTrue(reused)
        self.assertEqual(first.id, second.id)
        self.assertEqual(AnalysisRun.query.count(), 1)

    def test_one_document_uses_fallback_and_zero_documents_fail(self):
        article = self._article(1, "重庆暴雨", ["重庆", "暴雨", "救援"])
        run, _ = create_analysis_run(
            [article.id], mode="search", keyword="重庆暴雨", platforms=["news"]
        )

        result = run_content_analysis(run.id)

        self.assertIn("SINGLE_DOCUMENT_FALLBACK", result["warnings"])
        with self.assertRaises(NoValidDocumentError):
            create_analysis_run([], mode="search", keyword="空", platforms=["news"])

    def test_explicit_recrawled_article_ids_are_not_filtered_by_first_task_id(self):
        article = self._article(
            1,
            "人工智能产业发展",
            ["人工智能产业发展模型应用"] * 10,
            platform="news_people",
        )
        article.crawl_task_id = 1
        db.session.commit()

        run, reused = create_analysis_run(
            [article.id],
            mode="search",
            keyword="人工智能",
            platforms=["mainstream_news"],
            source_task_id=2,
        )

        self.assertFalse(reused)
        self.assertEqual(run.representative_count, 1)
        self.assertEqual(
            AnalysisRunArticle.query.filter_by(analysis_run_id=run.id).count(), 1
        )

    def test_artificial_intelligence_alias_matches_ai_but_not_smartphone(self):
        ai_article = self._article(
            1,
            "AI 基础设施投资持续升温",
            ["AI基础设施投资与大模型产业发展"] * 10,
            platform="news_infoq",
        )
        phone_article = self._article(
            2,
            "全球智能手机出货量创新低",
            ["智能手机市场出货量与消费电子行业"] * 10,
            platform="news_sspai",
        )

        run, _ = create_analysis_run(
            [ai_article.id, phone_article.id],
            mode="search",
            keyword="人工智能",
            platforms=["mainstream_news"],
        )

        rows = AnalysisRunArticle.query.filter_by(analysis_run_id=run.id).all()
        self.assertEqual([row.article_id for row in rows], [ai_article.id])
        self.assertEqual(run.representative_count, 1)

    def test_content_version_change_fails_snapshot_verification(self):
        article = self._article(1, "重庆暴雨", ["重庆", "暴雨", "救援"])
        run, _ = create_analysis_run(
            [article.id], mode="search", keyword="重庆暴雨", platforms=["news"]
        )
        article.content_version = 2
        db.session.commit()

        with self.assertRaises(DatasetChangedError):
            run_content_analysis(run.id)

        db.session.refresh(run)
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.error_code, "DATASET_CHANGED")

    def test_embedding_is_cached_and_failure_only_adds_warning(self):
        articles = self._valid_articles()
        run, _ = create_analysis_run(
            [article.id for article in articles],
            mode="search",
            keyword="重庆暴雨",
            platforms=["news", "weibo"],
        )
        encoder = FakeEncoder()

        result = run_content_analysis(run.id, encoder=encoder)

        self.assertEqual(encoder.calls, 1)
        self.assertEqual(ArticleEmbedding.query.count(), 3)
        self.assertNotIn("BGE_UNAVAILABLE", result["warnings"])
        vectors = [row.vector for row in ArticleEmbedding.query.all()]
        self.assertTrue(all(abs(sum(value * value for value in vector) - 1.0) < 1e-6 for vector in vectors))

        second_articles = [
            self._article(index + 20, f"新文章{index}", ["重庆", "暴雨", str(index)])
            for index in range(2)
        ]
        second, _ = create_analysis_run(
            [article.id for article in second_articles],
            mode="search",
            keyword="新文章",
            platforms=["news"],
        )
        failed_result = run_content_analysis(second.id, encoder=FakeEncoder(fail=True))
        self.assertIn("BGE_UNAVAILABLE", failed_result["warnings"])
        self.assertEqual(db.session.get(AnalysisRun, second.id).status, "success")

    def test_serializers_list_and_get_owned_runs(self):
        articles = self._valid_articles()
        run, _ = create_analysis_run(
            [article.id for article in articles],
            user_id=12,
            mode="search",
            keyword="重庆暴雨",
            platforms=["news"],
        )
        run_content_analysis(run.id)

        detail = get_analysis_run(run.id, user_id=12)
        denied = get_analysis_run(run.id, user_id=13)
        listed = list_analysis_runs(user_id=12)

        self.assertEqual(detail["id"], run.id)
        self.assertTrue(detail["articles"])
        self.assertIsNone(denied)
        self.assertEqual([item["id"] for item in listed], [run.id])
        self.assertNotIn("clean_content", detail["articles"][0])

    def test_stale_analysis_task_lease_cannot_commit_run(self):
        article = self._article(1, "重庆暴雨", ["重庆", "暴雨", "救援"])
        run, _ = create_analysis_run(
            [article.id], mode="search", keyword="重庆暴雨", platforms=["news"]
        )
        task = create_task(
            "analysis", created_by=1, payload={"analysis_run_id": run.id}
        )
        first_lease = task_service.claim_task(task["id"])
        task_row = db.session.get(Task, task["id"])
        task_row.status = "pending"
        task_row.lease_token = None
        db.session.commit()
        second_lease = task_service.claim_task(task["id"])
        self.assertNotEqual(first_lease, second_lease)
        context_token = task_service.activate_task_lease(first_lease)

        try:
            with self.assertRaises(task_service.StaleTaskLeaseError):
                run_content_analysis(run.id, task_id=task["id"])
        finally:
            task_service.reset_task_lease(context_token)

        db.session.refresh(run)
        self.assertEqual(run.status, "pending")


class ApiTestConfig(TestConfig):
    JWT_EXPIRES_DELTA = timedelta(hours=24)
    DEMO_ADMIN_USERNAME = "admin"
    DEMO_ADMIN_PASSWORD = "admin123"
    TASKS_RUN_SYNC = True
    TASK_RUNNING_TIMEOUT_SECONDS = 3600


class ContentAnalysisApiTest(unittest.TestCase):
    def setUp(self):
        reset_task_store()
        self.app = create_app(ApiTestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        login = self.client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin123"}
        )
        token = login.get_json()["data"]["token"]
        self.headers = {"Authorization": f"Bearer {token}"}
        self.article = self._article()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        reset_task_store()

    def _article(self):
        article = Article(
            platform="news",
            source_type="news",
            source_article_id="api-1",
            url="https://example.com/api-1",
            url_hash="f" * 64,
            title="重庆暴雨官方通报",
            raw_content="重庆 暴雨 官方 通报 救援 " * 15,
            clean_content="重庆 暴雨 官方 通报 救援 " * 15,
            clean_status="success",
            content_version=1,
            nlp_weight=1.0,
        )
        db.session.add(article)
        db.session.flush()
        snapshot = ArticleSnapshot(
            article_id=article.id,
            fetch_status="success",
            content_hash="e" * 64,
            raw_content=article.raw_content,
        )
        db.session.add(snapshot)
        db.session.flush()
        article.latest_snapshot_id = snapshot.id
        db.session.add(
            DocumentFeatures(
                article_id=article.id,
                tokens=["重庆", "暴雨", "官方", "通报", "救援"],
                tfidf_tokens=["重庆", "暴雨", "官方", "通报", "救援"],
                sentiment_tokens=["重庆", "暴雨", "官方", "通报", "救援"],
                topics=["重庆暴雨"],
                mentions=["重庆"],
                segment_version="v1",
            )
        )
        db.session.commit()
        return article

    def test_post_run_executes_background_analysis_and_exposes_detail(self):
        response = self.client.post(
            "/api/analysis/runs",
            json={
                "article_ids": [self.article.id],
                "mode": "search",
                "keyword": "重庆暴雨",
                "platforms": ["news"],
            },
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertIn("analysis_run_id", data)
        self.assertIn("task_id", data)
        task = db.session.get(Task, data["task_id"])
        self.assertEqual(task.status, "success")
        detail = self.client.get(
            f"/api/analysis/runs/{data['analysis_run_id']}", headers=self.headers
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["data"]["status"], "success")

    def test_search_run_requires_platform_and_list_returns_owned_runs(self):
        invalid = self.client.post(
            "/api/analysis/runs",
            json={
                "article_ids": [self.article.id],
                "mode": "search",
                "keyword": "重庆暴雨",
                "platforms": [],
            },
            headers=self.headers,
        )
        self.assertEqual(invalid.status_code, 400)

        self.client.post(
            "/api/analysis/runs",
            json={
                "article_ids": [self.article.id],
                "mode": "search",
                "keyword": "重庆暴雨",
                "platforms": ["news"],
            },
            headers=self.headers,
        )
        listed = self.client.get("/api/analysis/runs", headers=self.headers)

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.get_json()["data"]["runs"]), 1)

    def test_analyze_job_updates_existing_task(self):
        run, _ = create_analysis_run(
            [self.article.id],
            mode="search",
            keyword="重庆暴雨",
            platforms=["news"],
        )
        task = create_task(
            "analysis", created_by=1, payload={"analysis_run_id": run.id}
        )

        result = analyze_job(task["id"])

        self.assertEqual(result["analysis_run_id"], run.id)
        self.assertEqual(get_task(task["id"])["status"], "success")


if __name__ == "__main__":
    unittest.main()
