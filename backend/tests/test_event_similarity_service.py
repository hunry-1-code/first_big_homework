import sys
import unittest
from datetime import datetime
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.models import (
    AggregationRun,
    AnalysisRun,
    Event,
    EventArticleMembership,
    EventMergeRecord,
    EventRepresentation,
)
from app.services.event_similarity_service import find_similar_events, search_historical_events
from app.services.event_service import search_events


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    JWT_SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_DB = False
    FRONTEND_ORIGINS = ["http://localhost"]
    TASK_RECOVER_ON_STARTUP = False
    BGE_MODEL = "test-bge"
    BGE_MODEL_VERSION = "v1"
    BGE_PREPROCESS_VERSION = "v1"
    EVENT_RELATED_LIMIT = 5


class EventSimilarityServiceTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        analysis = AnalysisRun(
            mode="hot",
            query_fingerprint="similarity",
            dataset_hash="dataset",
            config_hash="feature",
            status="success",
        )
        db.session.add(analysis)
        db.session.flush()
        self.run = AggregationRun(
            analysis_run_id=analysis.id,
            scope="global",
            mode="hot",
            attempt=1,
            dataset_hash="dataset",
            config_hash="aggregation",
            status="success",
        )
        db.session.add(self.run)
        db.session.flush()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _event(self, title, vector, *, category="自然灾害", keywords=None, entities=None, year=2026):
        event = Event(
            title=title,
            topic_category=category,
            topic_name=title,
            first_publish_time=datetime(year, 7, 1),
        )
        db.session.add(event)
        db.session.flush()
        db.session.add(
            EventRepresentation(
                event_id=event.id,
                model_name="test-bge",
                model_version="v1",
                preprocess_version="v1",
                dimension=len(vector),
                vector=vector,
                keywords=keywords or ["暴雨", "救援"],
                entities=entities or {"location": ["重庆"]},
                member_count=2,
                source_aggregation_run_id=self.run.id,
            )
        )
        return event

    def test_related_events_are_ranked_without_writing_memberships(self):
        current = self._event("2026年重庆暴雨救援", [1.0, 0.0], year=2026)
        close = self._event("2025年重庆暴雨救援", [0.98, 0.02], year=2025)
        distant = self._event(
            "某电影上映",
            [0.0, 1.0],
            category="娱乐事件",
            keywords=["电影", "票房"],
            entities={"organization": ["影院"]},
            year=2025,
        )
        db.session.commit()
        before = EventArticleMembership.query.count()

        result = find_similar_events(current.id)

        after = EventArticleMembership.query.count()
        self.assertEqual(before, after)
        self.assertEqual(result[0]["event_id"], close.id)
        self.assertGreater(result[0]["similarity"], result[-1]["similarity"])
        self.assertNotIn(current.id, {item["event_id"] for item in result})
        self.assertIn(distant.id, {item["event_id"] for item in result})

    def test_confirmed_merge_alias_is_excluded(self):
        current = self._event("重庆暴雨", [1.0, 0.0])
        alias = self._event("重庆强降雨", [0.99, 0.01])
        db.session.add(
            EventMergeRecord(
                source_event_id=alias.id,
                target_event_id=current.id,
                aggregation_run_id=self.run.id,
                status="confirmed",
            )
        )
        db.session.commit()

        result = find_similar_events(current.id)

        self.assertNotIn(alias.id, {item["event_id"] for item in result})

    def test_historical_search_uses_title_topic_and_keywords(self):
        rain = self._event("重庆暴雨救援", [1.0, 0.0], keywords=["重庆", "暴雨", "救援"])
        self._event(
            "电影票房增长",
            [0.0, 1.0],
            category="娱乐事件",
            keywords=["电影", "票房"],
            entities={},
        )
        db.session.commit()

        result = search_historical_events("暴雨救援")

        self.assertEqual(result[0]["event_id"], rain.id)
        self.assertIn("关键词匹配", result[0]["match_reasons"])

        public_result = search_events("暴雨救援")
        self.assertEqual(public_result[0]["id"], rain.id)
        self.assertIn("关键词匹配", public_result[0]["match_reasons"])


if __name__ == "__main__":
    unittest.main()
