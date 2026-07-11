import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.crawler.base import RawDocument
from app.preprocessing.cleaner import clean_document
from app.preprocessing.deduplicator import (
    compare_documents,
    compute_content_hash,
    hamming_distance,
    simhash_text,
    title_jaccard,
)
from app.preprocessing.extractor import extract_content
from app.preprocessing.normalizer import normalize_document
from app.preprocessing.quality import evaluate_quality
from app.preprocessing.segmenter import segment_document


class NormalizerTest(unittest.TestCase):
    def test_normalizer_canonicalizes_url_metrics_and_timezone(self):
        result = normalize_document(
            {
                "platform": "B站",
                "source_type": "social",
                "url": " HTTPS://EXAMPLE.COM/a?utm_source=x&keep=1#part ",
                "title": "  测试\u200b 标题  ",
                "raw_content": "正文",
                "likes_count": "1.2万",
                "comments_count": "2.5k",
                "views_count": 0,
                "publish_time": "2026-07-10 08:00:00",
            }
        )

        self.assertEqual(result.status, "degraded")
        self.assertEqual(result.data["platform"], "bilibili")
        self.assertEqual(result.data["url"], "https://example.com/a?keep=1")
        self.assertEqual(result.data["likes_count"], 12000)
        self.assertEqual(result.data["comments_count"], 2500)
        self.assertEqual(result.data["views_count"], 0)
        self.assertIn("timezone_assumed", result.warnings)
        self.assertEqual(len(result.data["url_hash"]), 64)

    def test_normalizer_fails_when_identity_and_content_are_missing(self):
        result = normalize_document({"platform": "weibo", "title": ""})

        self.assertEqual(result.status, "failed")
        self.assertIn("NORMALIZE_MISSING_REQUIRED_FIELD", result.errors)


class ExtractorCleanerTest(unittest.TestCase):
    def test_plain_social_text_bypasses_html_extractors(self):
        result = extract_content(
            "这是一个用于测试的社交平台短文本，包含足够信息。",
            content_type="text",
            source_type="social",
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["extraction_method"], "plain_text")

    def test_html_extracts_visible_article_content(self):
        paragraph = "这是新闻正文，用于验证正文抽取链能够保留有效内容并过滤菜单。" * 8
        html = f"<html><nav>首页 登录</nav><article><p>{paragraph}</p></article><script>bad()</script></html>"

        result = extract_content(html, content_type="html", source_type="news")

        self.assertIn(result.status, {"success", "degraded"})
        self.assertIn("这是新闻正文", result.data["text"])
        self.assertNotIn("bad()", result.data["text"])

    def test_extractor_marks_verification_page_as_failed(self):
        html = "<html><body>访问异常，请完成安全验证和验证码后继续访问</body></html>"

        result = extract_content(html, content_type="html", source_type="news")

        self.assertEqual(result.status, "failed")
        self.assertIn("EXTRACT_ALL_METHODS_FAILED", result.errors)

    def test_cleaner_preserves_semantic_features_and_paragraphs(self):
        text = "第一段 @用户 讨论 #公共事件# https://example.com/a\n\n打开APP阅读全文\n第二段：情绪很好🙂"

        result = clean_document(text, platform="weibo")

        self.assertEqual(result.status, "success")
        self.assertIn("@用户", result.data["mentions"])
        self.assertIn("#公共事件#", result.data["topics"])
        self.assertIn("https://example.com/a", result.data["urls"])
        self.assertIn("\n", result.data["clean_content"])
        self.assertNotIn("打开APP阅读全文", result.data["clean_content"])


class QualityDedupSegmentTest(unittest.TestCase):
    def test_quality_score_and_weight_are_separate_from_heat(self):
        text = "这是一篇字段完整、正文清晰且没有明显模板噪声的新闻报道。" * 12
        result = evaluate_quality(
            text,
            source_type="news",
            metadata={"title": "新闻", "author": "媒体", "publish_time": "2026-07-10"},
            extraction_method="trafilatura",
            extraction_degraded=False,
            cleaning_statistics={"original_length": len(text), "removed_length": 0},
        )

        self.assertGreaterEqual(result.data["quality_score"], 0.75)
        self.assertEqual(result.data["quality_level"], "good")
        self.assertEqual(result.data["nlp_weight"], 1.0)
        self.assertNotIn("heat_contribution", result.data)

    def test_low_quality_text_is_marked_not_deleted(self):
        result = evaluate_quality(
            "广告 加微信 购买",
            source_type="news",
            metadata={"title": "广告"},
            extraction_method="fallback",
            extraction_degraded=True,
            cleaning_statistics={"original_length": 100, "removed_length": 80},
        )

        self.assertIn(result.data["quality_level"], {"low", "very_low"})
        self.assertTrue(result.data["is_advertisement"])
        self.assertIn("too_short", result.data["quality_flags"])

    def test_hash_jaccard_and_simhash_detect_near_duplicate(self):
        first = "某地发布公共交通调整方案，市民可通过官方渠道查询详细安排。"
        second = "某地发布公共交通调整方案，市民可以通过官方渠道查询详细安排。"

        self.assertEqual(len(compute_content_hash(first)), 64)
        self.assertGreaterEqual(title_jaccard(first, second), 0.85)
        self.assertLessEqual(hamming_distance(simhash_text(first), simhash_text(second)), 3)
        result = compare_documents(first, first * 8, second, second * 8)
        self.assertTrue(result.is_duplicate)
        self.assertEqual(result.method, "simhash")

    def test_short_titles_cannot_trigger_jaccard_only_duplicate(self):
        result = compare_documents("火灾", "正文甲" * 30, "火灾", "完全不同正文乙" * 30)

        self.assertFalse(result.is_duplicate)

    def test_short_title_simhash_match_is_kept_as_bge_boundary_candidate(self):
        content = "同一篇短标题报道的正文内容，用于边界候选判断。" * 20
        result = compare_documents("火灾", content, "火灾", content + "补充")

        self.assertFalse(result.is_duplicate)
        self.assertTrue(result.dedup_pending)

    def test_segmenter_outputs_multiple_token_sets(self):
        result = segment_document(
            "我非常不支持这个公共交通方案 #城市治理# @市民热线",
            topics=["#城市治理#"],
            mentions=["@市民热线"],
            stopwords={"这个", "我"},
        )

        self.assertTrue(result.data["tokens"])
        self.assertNotIn("这个", result.data["tfidf_tokens"])
        self.assertIn("不", result.data["sentiment_tokens"])
        self.assertEqual(result.data["topics"], ["#城市治理#"])


if __name__ == "__main__":
    unittest.main()
