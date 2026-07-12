import json
import math
import sys
import unittest
from datetime import datetime
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.analysis.sentiment_aggregator import (
    SentimentAggregateItem,
    build_daily_sentiment,
    build_platform_sentiment,
    summarize_sentiment,
)
from app.analysis.sentiment_analyzer import (
    SentimentAnalysisError,
    analyze_sentiment,
    analyze_with_snownlp,
)
from app.analysis.sentiment_config import SentimentConfig


class FakeLLMClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self.model_name = "deepseek-chat"

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return {"content": self.payload, "model": self.model_name, "raw": {}}


class SentimentConfigTest(unittest.TestCase):
    def test_defaults_and_hash_are_stable(self):
        first = SentimentConfig()
        second = SentimentConfig()

        self.assertEqual(first.text_limit, 500)
        self.assertEqual(first.neutral_score_min, -0.20)
        self.assertEqual(first.neutral_score_max, 0.20)
        self.assertEqual(first.platform_min_articles, 3)
        self.assertEqual(first.platform_min_representatives, 2)
        self.assertEqual(first.config_hash(), second.config_hash())
        self.assertNotEqual(
            first.config_hash(), SentimentConfig(text_limit=600).config_hash()
        )

    def test_invalid_thresholds_are_rejected(self):
        with self.assertRaises(ValueError):
            SentimentConfig(
                snownlp_negative_threshold=0.70,
                snownlp_positive_threshold=0.60,
            )


class SentimentAnalyzerTest(unittest.TestCase):
    def test_llm_json_is_validated_and_normalized(self):
        client = FakeLLMClient(
            json.dumps(
                {
                    "label": "negative",
                    "score": -0.82,
                    "confidence": 0.91,
                    "dimension": "impact",
                    "target": "暴雨造成的损失",
                    "reason": "报道强调伤亡和损失扩大",
                },
                ensure_ascii=False,
            )
        )

        result = analyze_sentiment(
            "暴雨造成严重损失",
            context={"topic_category": "自然灾害", "article_title": "暴雨通报"},
            client=client,
        )

        self.assertEqual(result["label"], "negative")
        self.assertEqual(result["dimension"], "impact")
        self.assertEqual(result["method"], "llm")
        self.assertEqual(result["model_name"], "deepseek-chat")
        self.assertEqual(len(client.calls), 1)

    def test_fenced_json_is_accepted(self):
        client = FakeLLMClient(
            '```json\n{"label":"neutral","score":0.05,"confidence":0.8,'
            '"dimension":"factual","target":"事件进展","reason":"客观通报"}\n```'
        )

        result = analyze_sentiment("事件进展通报", client=client)

        self.assertEqual(result["label"], "neutral")

    def test_invalid_label_score_combination_is_rejected(self):
        client = FakeLLMClient(
            '{"label":"positive","score":-0.8,"confidence":0.9,'
            '"dimension":"stance","target":"处置","reason":"错误组合"}'
        )

        with self.assertRaises(SentimentAnalysisError):
            analyze_sentiment("测试文本", client=client)

    def test_snownlp_probability_maps_to_three_labels(self):
        positive = analyze_with_snownlp("积极进展", probability_fn=lambda _: 0.8)
        neutral = analyze_with_snownlp("普通通报", probability_fn=lambda _: 0.5)
        negative = analyze_with_snownlp("严重损失", probability_fn=lambda _: 0.2)

        self.assertEqual((positive["label"], positive["score"]), ("positive", 0.6))
        self.assertEqual((neutral["label"], neutral["score"]), ("neutral", 0.0))
        self.assertEqual((negative["label"], negative["score"]), ("negative", -0.6))
        self.assertLessEqual(positive["confidence"], SentimentConfig().snownlp_confidence_cap)
        self.assertIn("SNOWNLP_FALLBACK", positive["warnings"])


class SentimentAggregatorTest(unittest.TestCase):
    def _item(
        self,
        article_id,
        label,
        score,
        *,
        platform="weibo",
        publish_time=None,
        observed_time=None,
        representative=True,
        nlp_weight=1.0,
        spam_weight=1.0,
        duplicate_weight=1.0,
        heat_contribution=None,
    ):
        return SentimentAggregateItem(
            article_id=article_id,
            label=label,
            score=score,
            platform=platform,
            publish_time=publish_time,
            observed_time=observed_time,
            is_representative=representative,
            nlp_weight=nlp_weight,
            spam_weight=spam_weight,
            duplicate_weight=duplicate_weight,
            heat_contribution=heat_contribution,
        )

    def test_summary_keeps_raw_counts_and_uses_bounded_weights(self):
        items = [
            self._item(1, "positive", 0.8, heat_contribution=99),
            self._item(2, "negative", -0.7, heat_contribution=0),
            self._item(
                3,
                "negative",
                -0.7,
                representative=False,
                duplicate_weight=0.2,
                heat_contribution=0,
            ),
        ]

        result = summarize_sentiment(items, SentimentConfig())

        self.assertEqual(result["raw_counts"], {"positive": 1, "negative": 2, "neutral": 0})
        self.assertAlmostEqual(sum(result["weighted_ratios"].values()), 1.0)
        self.assertLess(result["weighted_ratios"]["negative"], 0.5)
        self.assertGreaterEqual(result["average_score"], -1.0)
        self.assertLessEqual(result["average_score"], 1.0)

    def test_daily_trend_prefers_publish_time_and_marks_observed_fallback(self):
        items = [
            self._item(1, "positive", 0.5, publish_time=datetime(2026, 7, 10, 8)),
            self._item(2, "negative", -0.5, observed_time=datetime(2026, 7, 11, 9)),
        ]

        daily = build_daily_sentiment(items, SentimentConfig())

        self.assertEqual([row["date"] for row in daily], ["2026-07-10", "2026-07-11"])
        self.assertEqual(daily[1]["time_source_counts"]["observed_at"], 1)
        self.assertIn("TIME_SOURCE_DEGRADED", daily[1]["warnings"])

    def test_platform_distribution_marks_small_samples(self):
        items = [
            self._item(1, "positive", 0.7, platform="weibo"),
            self._item(2, "negative", -0.7, platform="news"),
            self._item(3, "neutral", 0.0, platform="news"),
            self._item(4, "positive", 0.4, platform="news"),
        ]

        rows = build_platform_sentiment(items, SentimentConfig())
        by_platform = {row["platform"]: row for row in rows}

        self.assertTrue(by_platform["weibo"]["sample_insufficient"])
        self.assertFalse(by_platform["news"]["sample_insufficient"])
        self.assertTrue(math.isclose(sum(by_platform["news"]["weighted_ratios"].values()), 1.0))


if __name__ == "__main__":
    unittest.main()
