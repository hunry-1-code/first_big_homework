import sys
import unittest
import json
from datetime import datetime, timedelta
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.analysis.feature_config import FeatureConfig
from app.analysis.feature_matrix import build_feature_matrices
from app.analysis.hotspot_config import HotspotConfig
from app.analysis.heat_calculator import HeatArticle, EventHeatInput, calculate_event_heats
from app.analysis.hot_seed import HotSeedSnapshot, merge_hot_seeds, normalize_hot_seed_title
from app.analysis.result import AnalysisDocument
from app.analysis.topic_classifier import classify_topic
from app.analysis.topic_model import candidate_topic_counts, discover_topics
from app.llm.client import LLMClient, LLMUnavailableError


def _documents(count=12):
    weather = [
        ("重庆暴雨预警", ["重庆", "暴雨", "预警", "气象", "降雨"]),
        ("暴雨导致积水", ["暴雨", "积水", "道路", "救援", "重庆"]),
        ("救援力量集结", ["救援", "应急", "暴雨", "居民", "转移"]),
        ("气象台发布预警", ["气象", "预警", "强降雨", "重庆", "天气"]),
        ("城市排水抢险", ["排水", "抢险", "积水", "道路", "救援"]),
        ("强降雨持续", ["强降雨", "天气", "暴雨", "预警", "重庆"]),
    ]
    entertainment = [
        ("新电影上映", ["电影", "上映", "演员", "票房", "观众"]),
        ("电影票房增长", ["电影", "票房", "影院", "观众", "上映"]),
        ("演员参加首映", ["演员", "首映", "电影", "观众", "导演"]),
        ("观众讨论剧情", ["观众", "剧情", "电影", "口碑", "票房"]),
        ("导演回应争议", ["导演", "电影", "争议", "演员", "剧情"]),
        ("影院排片增加", ["影院", "排片", "电影", "票房", "上映"]),
    ]
    rows = (weather + entertainment)[:count]
    return [
        AnalysisDocument(
            article_id=index,
            snapshot_id=index * 10,
            content_version=1,
            title=title,
            title_tokens=tokens[:2],
            body_tokens=tokens,
            platform="news" if index % 2 else "weibo",
        )
        for index, (title, tokens) in enumerate(rows, start=1)
    ]


def _matrix(documents):
    return build_feature_matrices(documents, FeatureConfig(max_df=1.0))


class HotspotConfigTest(unittest.TestCase):
    def test_defaults_and_hash_are_stable(self):
        first = HotspotConfig()
        second = HotspotConfig()

        self.assertEqual(first.window_days, 7)
        self.assertEqual(first.max_topics, 12)
        self.assertEqual(first.core_weight, 0.7)
        self.assertEqual(first.spread_weight, 0.3)
        self.assertEqual(first.config_hash(), second.config_hash())
        self.assertNotEqual(
            first.config_hash(),
            HotspotConfig(core_weight=0.8, spread_weight=0.2).config_hash(),
        )

    def test_weights_must_sum_to_one(self):
        with self.assertRaises(ValueError):
            HotspotConfig(core_weight=0.8, spread_weight=0.3)

    def test_candidate_topic_ranges_follow_document_count(self):
        self.assertEqual(candidate_topic_counts(7, 12), [2])
        self.assertEqual(candidate_topic_counts(10, 12), [2, 3, 4])
        self.assertEqual(candidate_topic_counts(30, 12), [3, 4, 5, 6, 7, 8])
        self.assertEqual(candidate_topic_counts(100, 12), [5, 6, 7, 8, 9, 10])


class TopicDiscoveryTest(unittest.TestCase):
    def test_one_to_four_documents_use_keyword_fallback(self):
        documents = _documents(3)

        result = discover_topics(
            documents,
            feature_names=[],
            count_matrix=None,
            config=HotspotConfig(),
        )

        self.assertEqual(result.method, "keyword_topic_fallback")
        self.assertEqual(result.selected_k, 1)
        self.assertIn("KEYWORD_TOPIC_FALLBACK", result.warnings)
        self.assertEqual(len(result.topics), 1)
        self.assertEqual(len(result.assignments), 3)
        self.assertTrue(all(item.probability == 1.0 for item in result.assignments))
        self.assertTrue(result.topics[0].keywords)

    def test_five_to_nine_documents_use_fixed_two_topics(self):
        documents = _documents(7)
        matrices = _matrix(documents)

        result = discover_topics(
            documents,
            feature_names=matrices.feature_names,
            count_matrix=matrices.count_matrix,
            config=HotspotConfig(),
        )

        self.assertEqual(result.selected_k, 2)
        self.assertIn("SMALL_CORPUS", result.warnings)
        self.assertEqual(len(result.assignments), 7)
        self.assertTrue(all(0.0 <= item.probability <= 1.0 for item in result.assignments))

    def test_normal_corpus_is_reproducible_and_returns_metrics(self):
        documents = _documents(12)
        matrices = _matrix(documents)

        first = discover_topics(
            documents,
            feature_names=matrices.feature_names,
            count_matrix=matrices.count_matrix,
            config=HotspotConfig(),
        )
        second = discover_topics(
            documents,
            feature_names=matrices.feature_names,
            count_matrix=matrices.count_matrix,
            config=HotspotConfig(),
        )

        self.assertIn(first.selected_k, {2, 3, 4})
        self.assertEqual(first.selected_k, second.selected_k)
        self.assertEqual(
            [(item.article_id, item.topic_index) for item in first.assignments],
            [(item.article_id, item.topic_index) for item in second.assignments],
        )
        self.assertEqual(len(first.candidates), 3)
        self.assertTrue(all(item.perplexity > 0 for item in first.candidates))
        self.assertTrue(all(topic.keywords for topic in first.topics))


class FakeTopicClient:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.error:
            raise self.error
        return {"content": self.content, "model": "fake", "raw": {}}


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class TopicNamingTest(unittest.TestCase):
    def test_classify_topic_accepts_structured_llm_output(self):
        client = FakeTopicClient(
            json.dumps(
                {
                    "category": "自然灾害",
                    "topic_name": "重庆暴雨救援",
                    "confidence": 0.91,
                },
                ensure_ascii=False,
            )
        )

        result = classify_topic(
            ["重庆", "暴雨", "救援"],
            ["重庆暴雨救援持续进行"],
            client=client,
        )

        self.assertEqual(result["category"], "自然灾害")
        self.assertEqual(result["topic_name"], "重庆暴雨救援")
        self.assertEqual(result["method"], "lda_llm")
        self.assertEqual(client.calls[0][1]["temperature"], 0)

    def test_classify_topic_parses_markdown_json_fence(self):
        client = FakeTopicClient(
            '```json\n{"category":"娱乐事件","topic_name":"暑期电影票房","confidence":0.8}\n```'
        )

        result = classify_topic(["电影", "票房"], ["暑期电影上映"], client=client)

        self.assertEqual(result["category"], "娱乐事件")
        self.assertEqual(result["method"], "lda_llm")

    def test_classify_topic_falls_back_on_invalid_output(self):
        result = classify_topic(
            ["重庆", "暴雨", "救援", "积水"],
            [],
            client=FakeTopicClient("not-json"),
        )

        self.assertEqual(result["category"], "其他")
        self.assertEqual(result["topic_name"], "重庆·暴雨·救援·积水")
        self.assertEqual(result["method"], "lda_keyword_fallback")
        self.assertIn("LLM_TOPIC_NAMING_DEGRADED", result["warnings"])

    def test_llm_client_posts_openai_compatible_payload(self):
        session = FakeSession(
            FakeResponse(
                payload={
                    "model": "deepseek-chat",
                    "choices": [{"message": {"content": "ok"}}],
                }
            )
        )
        client = LLMClient(
            api_key="secret",
            base_url="https://api.deepseek.com",
            model_name="deepseek-chat",
            timeout=12,
            session=session,
        )

        result = client.chat([{"role": "user", "content": "hello"}], temperature=0)

        self.assertEqual(result["content"], "ok")
        url, kwargs = session.calls[0]
        self.assertEqual(url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(kwargs["timeout"], 12)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(kwargs["json"]["model"], "deepseek-chat")

    def test_llm_client_rejects_missing_key(self):
        with self.assertRaises(LLMUnavailableError):
            LLMClient(api_key="").chat([{"role": "user", "content": "hello"}])


class HeatCalculatorTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 11, 12, 0, 0)

    def _article(
        self,
        article_id,
        platform="news",
        hours_ago=2,
        *,
        representative=True,
        publish=True,
        likes=None,
        comments=None,
        reposts=None,
        views=None,
    ):
        effective = self.now - timedelta(hours=hours_ago)
        return HeatArticle(
            article_id=article_id,
            platform=platform,
            publish_time=effective if publish else None,
            observed_at=effective,
            is_representative=representative,
            likes_count=likes,
            comments_count=comments,
            reposts_count=reposts,
            views_count=views,
        )

    def test_duplicate_articles_do_not_increase_independent_reports(self):
        event = EventHeatInput(
            event_id=1,
            articles=[
                self._article(1, "news"),
                self._article(2, "weibo"),
                self._article(3, "zhihu"),
                self._article(4, "weibo", representative=False, likes=1000),
            ],
        )

        result = calculate_event_heats(
            [event], calculated_at=self.now, config=HotspotConfig()
        )[0]

        self.assertEqual(result.raw_statistics["independent_report_count_7d"], 3)
        self.assertEqual(result.raw_statistics["platform_count"], 3)
        self.assertTrue(result.eligible_as_hot)

    def test_missing_publish_time_uses_observed_time_and_lowers_confidence(self):
        event = EventHeatInput(
            event_id=1,
            articles=[
                self._article(1, publish=False),
                self._article(2, "weibo", publish=False),
                self._article(3, "zhihu", publish=True),
            ],
        )

        result = calculate_event_heats(
            [event], calculated_at=self.now, config=HotspotConfig()
        )[0]

        self.assertEqual(result.time_confidence, "low")
        self.assertEqual(result.raw_statistics["observed_time_count"], 2)

    def test_missing_spread_data_uses_core_heat_only(self):
        event = EventHeatInput(
            event_id=1,
            articles=[
                self._article(1),
                self._article(2, "weibo"),
                self._article(3, "zhihu"),
            ],
        )

        result = calculate_event_heats(
            [event], calculated_at=self.now, config=HotspotConfig()
        )[0]

        self.assertIsNone(result.spread_heat)
        self.assertEqual(result.final_heat, result.core_heat)
        self.assertIn("SPREAD_DATA_UNAVAILABLE", result.warnings)

    def test_available_spread_uses_seventy_thirty_formula(self):
        events = [
            EventHeatInput(
                event_id=1,
                articles=[
                    self._article(1, "weibo", likes=500, comments=50, reposts=100),
                    self._article(2, "news", views=10000),
                    self._article(3, "zhihu", likes=200, comments=30),
                ],
            ),
            EventHeatInput(
                event_id=2,
                articles=[
                    self._article(4, "weibo", likes=5, comments=1, reposts=0),
                    self._article(5, "news", views=100),
                    self._article(6, "zhihu", likes=2, comments=1),
                ],
            ),
        ]

        results = calculate_event_heats(
            events, calculated_at=self.now, config=HotspotConfig()
        )
        first = next(item for item in results if item.event_id == 1)

        self.assertIsNotNone(first.spread_heat)
        self.assertAlmostEqual(
            first.final_heat,
            round(0.7 * first.core_heat + 0.3 * first.spread_heat, 6),
            places=6,
        )
        self.assertGreater(first.spread_heat, next(item for item in results if item.event_id == 2).spread_heat)

    def test_hotlist_evidence_can_replace_two_platform_gate_but_not_report_gate(self):
        eligible = EventHeatInput(
            event_id=1,
            articles=[self._article(1), self._article(2), self._article(3)],
            hotlist_ranks=[1],
        )
        insufficient = EventHeatInput(
            event_id=2,
            articles=[self._article(4), self._article(5)],
            hotlist_ranks=[1],
        )

        results = calculate_event_heats(
            [eligible, insufficient], calculated_at=self.now, config=HotspotConfig()
        )

        self.assertTrue(next(item for item in results if item.event_id == 1).eligible_as_hot)
        self.assertFalse(next(item for item in results if item.event_id == 2).eligible_as_hot)

    def test_inactive_event_is_not_hot_and_ranking_is_limited(self):
        old = EventHeatInput(
            event_id=1,
            articles=[
                self._article(1, hours_ago=30),
                self._article(2, "weibo", hours_ago=30),
                self._article(3, "zhihu", hours_ago=30),
            ],
        )
        recent_a = EventHeatInput(
            event_id=2,
            articles=[self._article(4), self._article(5, "weibo"), self._article(6, "zhihu")],
        )
        recent_b = EventHeatInput(
            event_id=3,
            articles=[self._article(7), self._article(8, "weibo"), self._article(9, "zhihu")],
        )

        results = calculate_event_heats(
            [old, recent_a, recent_b],
            calculated_at=self.now,
            config=HotspotConfig(ranking_limit=1),
        )

        self.assertFalse(next(item for item in results if item.event_id == 1).eligible_as_hot)
        self.assertEqual(len([item for item in results if item.rank is not None]), 1)


class HotSeedTest(unittest.TestCase):
    def test_normalize_hot_seed_title_removes_topic_markers_and_spaces(self):
        self.assertEqual(normalize_hot_seed_title("  #重庆暴雨#  "), "重庆暴雨")

    def test_merge_hot_seeds_preserves_sources_and_never_counts_as_report(self):
        snapshots = [
            HotSeedSnapshot(
                seed_id=1,
                platform="weibo_hot",
                title="#重庆暴雨#",
                rank=3,
                snapshot_time=datetime(2026, 7, 11, 9, 0, 0),
            ),
            HotSeedSnapshot(
                seed_id=2,
                platform="zhihu_hot",
                title="重庆暴雨",
                rank=5,
                snapshot_time=datetime(2026, 7, 11, 9, 5, 0),
            ),
        ]

        seeds = merge_hot_seeds(snapshots)

        self.assertEqual(len(seeds), 1)
        self.assertEqual(seeds[0].query, "重庆暴雨")
        self.assertEqual(seeds[0].platforms, ["weibo_hot", "zhihu_hot"])
        self.assertEqual(seeds[0].best_rank, 3)
        self.assertEqual(seeds[0].source_seed_ids, [1, 2])
        self.assertEqual(seeds[0].report_count_contribution, 0)


if __name__ == "__main__":
    unittest.main()
