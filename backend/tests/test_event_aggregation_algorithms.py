import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.analysis.aggregation_config import AggregationConfig
from app.analysis.event_clusterer import AggregationDocument, cluster_documents
from app.analysis.event_similarity import score_event_match
from app.analysis.hot_detector import assign_event_cluster
from app.core.config import Config


class AggregationConfigTest(unittest.TestCase):
    def test_defaults_and_hash_are_stable(self):
        first = AggregationConfig()
        second = AggregationConfig()

        self.assertEqual(first.attach_threshold, 0.55)
        self.assertEqual(first.create_threshold, 0.40)
        self.assertEqual(first.move_margin, 0.10)
        self.assertEqual(first.bge_weight, 0.55)
        self.assertEqual(first.tfidf_weight, 0.20)
        self.assertEqual(first.entity_weight, 0.15)
        self.assertEqual(first.time_weight, 0.10)
        self.assertEqual(first.config_hash(), second.config_hash())
        self.assertNotEqual(
            first.config_hash(), AggregationConfig(attach_threshold=0.75).config_hash()
        )

    def test_thresholds_must_be_ordered(self):
        with self.assertRaises(ValueError):
            AggregationConfig(create_threshold=0.8, attach_threshold=0.7)

    def test_application_defaults_match_algorithm_defaults(self):
        defaults = AggregationConfig()
        self.assertEqual(Config.EVENT_AGGREGATION_ATTACH_THRESHOLD, defaults.attach_threshold)
        self.assertEqual(Config.EVENT_AGGREGATION_CREATE_THRESHOLD, defaults.create_threshold)
        self.assertEqual(Config.EVENT_AGGREGATION_MOVE_MARGIN, defaults.move_margin)
        self.assertEqual(Config.EVENT_AGGREGATION_BGE_WEIGHT, defaults.bge_weight)
        self.assertEqual(Config.EVENT_AGGREGATION_TFIDF_WEIGHT, defaults.tfidf_weight)
        self.assertEqual(Config.EVENT_AGGREGATION_ENTITY_WEIGHT, defaults.entity_weight)
        self.assertEqual(Config.EVENT_AGGREGATION_TIME_WEIGHT, defaults.time_weight)
        self.assertEqual(Config.EVENT_SEARCH_CACHE_HOURS, 24)


class EventSimilarityTest(unittest.TestCase):
    def test_missing_bge_renormalizes_remaining_weights(self):
        result = score_event_match(
            config=AggregationConfig(),
            bge_similarity=None,
            tfidf_similarity=0.8,
            entity_similarity=0.6,
            time_compatibility=1.0,
        )

        self.assertAlmostEqual(sum(result.normalized_weights.values()), 1.0)
        self.assertNotIn("bge", result.normalized_weights)
        expected = (0.8 * 0.20 + 0.6 * 0.15 + 1.0 * 0.10) / 0.45
        self.assertAlmostEqual(result.final_score, expected, places=6)
        self.assertIn("BGE_UNAVAILABLE", result.warnings)

    def test_explicit_location_conflict_blocks_attachment(self):
        result = score_event_match(
            config=AggregationConfig(),
            bge_similarity=0.99,
            tfidf_similarity=0.95,
            entity_similarity=0.2,
            time_compatibility=1.0,
            article_entities={"location": ["重庆"]},
            candidate_entities={"location": ["广东"]},
        )

        self.assertTrue(result.hard_conflict)
        self.assertIn("LOCATION_CONFLICT", result.reasons)


class EventClustererTest(unittest.TestCase):
    def _document(
        self,
        article_id,
        title,
        hours,
        vector,
        *,
        location="重庆",
        keywords=None,
    ):
        return AggregationDocument(
            article_id=article_id,
            title=title,
            effective_time=datetime(2026, 7, 11, 12) + timedelta(hours=hours),
            platform="news",
            tfidf_vector=vector,
            bge_vector=vector,
            keywords=frozenset({"暴雨", "救援"} if keywords is None else keywords),
            entities={"location": frozenset({location})} if location else {},
            topic_category="自然灾害",
            topic_name="暴雨救援",
        )

    def test_same_event_articles_attach_deterministically(self):
        documents = [
            self._document(2, "重庆暴雨救援进展", 1, [0.99, 0.01]),
            self._document(1, "重庆暴雨启动救援", 0, [1.0, 0.0]),
        ]

        first = cluster_documents(documents, AggregationConfig())
        second = cluster_documents(list(reversed(documents)), AggregationConfig())

        self.assertEqual(len(first.clusters), 1)
        self.assertEqual(
            [(item.article_id, item.action) for item in first.assignments],
            [(1, "create"), (2, "attach")],
        )
        self.assertEqual(
            [(item.article_id, item.cluster_index) for item in first.assignments],
            [(item.article_id, item.cluster_index) for item in second.assignments],
        )

    def test_different_locations_remain_separate_despite_semantic_similarity(self):
        documents = [
            self._document(1, "重庆暴雨救援", 0, [1.0, 0.0], location="重庆"),
            self._document(2, "广东暴雨救援", 1, [1.0, 0.0], location="广东"),
        ]

        result = cluster_documents(documents, AggregationConfig())

        self.assertEqual(len(result.clusters), 2)
        self.assertEqual([item.action for item in result.assignments], ["create", "create"])
        self.assertIn("LOCATION_CONFLICT", result.assignments[1].reasons)

    def test_document_without_any_evidence_is_deferred(self):
        document = self._document(
            1,
            "",
            0,
            None,
            location="",
            keywords=frozenset(),
        )
        document.bge_vector = None

        result = cluster_documents([document], AggregationConfig())

        self.assertEqual(len(result.clusters), 0)
        self.assertEqual(result.assignments[0].action, "deferred")
        self.assertIn("INSUFFICIENT_EVIDENCE", result.assignments[0].reasons)

    def test_legacy_assignment_adapter_uses_real_similarity(self):
        result = assign_event_cluster(
            {"vector": [1.0, 0.0]},
            [
                {"event_id": 10, "vector": [0.0, 1.0]},
                {"event_id": 20, "vector": [0.99, 0.01]},
            ],
        )

        self.assertEqual(result["event_id"], 20)
        self.assertEqual(result["action"], "attach")
        self.assertGreater(result["similarity"], 0.9)


if __name__ == "__main__":
    unittest.main()
