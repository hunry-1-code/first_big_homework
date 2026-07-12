import math
import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.analysis.feature_config import FeatureConfig
from app.analysis.feature_matrix import build_feature_matrices
from app.analysis.keyword_extractor import (
    aggregate_event_keywords,
    extract_article_keywords,
)
from app.analysis.result import AnalysisDocument, NoValidDocumentError
from app.core.config import Config


def _documents(count=5):
    base = [
        ("重庆 暴雨 官方 通报", "重庆 暴雨 导致 城市 内涝 应急 响应", "weibo"),
        ("重庆 启动 应急 响应", "强降雨 导致 道路 积水 救援", "news"),
        ("暴雨 影响 交通", "重庆 多地 交通 受阻 官方 提醒", "bilibili"),
        ("城市 内涝 引发 关注", "居民 讨论 排水 救援 进展", "zhihu"),
        ("气象台 发布 预警", "重庆 强降雨 气象 预警 持续", "news"),
    ]
    documents = []
    for index, (title, body, platform) in enumerate(base[:count], start=1):
        documents.append(
            AnalysisDocument(
                article_id=index,
                snapshot_id=index * 10,
                content_version=1,
                title=title.replace(" ", ""),
                title_tokens=title.split(),
                body_tokens=body.split(),
                platform=platform,
                entities={"重庆": "location"},
                topics=["重庆暴雨"],
                nlp_weight=1.0,
            )
        )
    return documents


class FeatureConfigTest(unittest.TestCase):
    def test_defaults_match_approved_design_and_hash_is_stable(self):
        first = FeatureConfig()
        second = FeatureConfig()

        self.assertEqual(first.max_features, 5000)
        self.assertEqual(first.ngram_range, (1, 2))
        self.assertEqual(first.title_weight, 1.0)
        self.assertEqual(first.body_weight, 1.0)
        self.assertEqual(first.article_keyword_limit, 10)
        self.assertEqual(first.event_keyword_limit, 20)
        self.assertEqual(first.config_hash(), second.config_hash())
        self.assertNotEqual(
            first.config_hash(), FeatureConfig(title_weight=2.0).config_hash()
        )

    def test_application_config_exposes_content_analysis_settings(self):
        self.assertEqual(Config.TFIDF_MAX_FEATURES, 5000)
        self.assertEqual(Config.TFIDF_TITLE_WEIGHT, 1.0)
        self.assertEqual(Config.ARTICLE_KEYWORD_LIMIT, 10)
        self.assertEqual(Config.EVENT_KEYWORD_LIMIT, 20)
        self.assertEqual(Config.BGE_MODEL, "BAAI/bge-small-zh-v1.5")


class FeatureMatrixTest(unittest.TestCase):
    def test_builds_pre_tokenized_unigrams_bigrams_and_l2_tfidf(self):
        documents = _documents()

        result = build_feature_matrices(documents, FeatureConfig())

        self.assertEqual(result.document_ids, [1, 2, 3, 4, 5])
        self.assertIn("官方 通报", result.feature_names)
        self.assertIn("重庆", result.feature_names)
        self.assertEqual(result.count_matrix.shape[0], 5)
        self.assertEqual(result.tfidf_matrix.shape, result.count_matrix.shape)
        for row in range(result.tfidf_matrix.shape[0]):
            norm = math.sqrt(result.tfidf_matrix.getrow(row).power(2).sum())
            self.assertAlmostEqual(norm, 1.0, places=6)

    def test_title_weight_changes_weighted_counts_but_not_lda_counts(self):
        documents = _documents()
        normal = build_feature_matrices(documents, FeatureConfig(title_weight=1.0))
        boosted = build_feature_matrices(documents, FeatureConfig(title_weight=2.0))
        term_index = normal.feature_names.index("官方")

        self.assertEqual(
            normal.count_matrix[0, term_index], boosted.count_matrix[0, term_index]
        )
        self.assertGreater(
            boosted.weighted_count_matrix[0, term_index],
            normal.weighted_count_matrix[0, term_index],
        )

    def test_two_to_four_documents_use_small_corpus_degradation(self):
        result = build_feature_matrices(_documents(3), FeatureConfig())

        self.assertIn("SMALL_CORPUS", result.warnings)
        self.assertIsNotNone(result.tfidf_matrix)
        self.assertEqual(result.stats["effective_max_df"], 1.0)

    def test_one_document_skips_corpus_tfidf(self):
        result = build_feature_matrices(_documents(1), FeatureConfig())

        self.assertIn("SINGLE_DOCUMENT_FALLBACK", result.warnings)
        self.assertIsNone(result.tfidf_matrix)
        self.assertEqual(result.stats["document_count"], 1)

    def test_zero_documents_raise_explicit_error(self):
        with self.assertRaises(NoValidDocumentError):
            build_feature_matrices([], FeatureConfig())


class KeywordExtractorTest(unittest.TestCase):
    def test_article_keywords_are_structured_limited_and_normalized(self):
        documents = _documents()
        result = build_feature_matrices(documents, FeatureConfig(article_keyword_limit=5))

        keywords = extract_article_keywords(
            result,
            documents,
            FeatureConfig(article_keyword_limit=5),
            query_terms=["重庆暴雨"],
            textrank_provider=lambda _text, _limit: ["备用关键词"],
        )

        self.assertEqual(set(keywords), {1, 2, 3, 4, 5})
        self.assertLessEqual(len(keywords[1]), 5)
        self.assertEqual([item.rank for item in keywords[1]], list(range(1, len(keywords[1]) + 1)))
        self.assertTrue(all(0.0 <= item.score <= 1.0 for item in keywords[1]))
        self.assertTrue(all(item.term for item in keywords[1]))
        self.assertIn("重庆暴雨", {item.term for item in keywords[1]})

    def test_textrank_only_fills_missing_slots(self):
        document = _documents(1)
        result = build_feature_matrices(document, FeatureConfig(article_keyword_limit=3))

        keywords = extract_article_keywords(
            result,
            document,
            FeatureConfig(article_keyword_limit=3),
            textrank_provider=lambda _text, _limit: ["重庆", "救援", "新增词"],
        )[1]

        self.assertLessEqual(len(keywords), 3)
        self.assertTrue(any(item.source in {"textrank", "entity", "topic"} for item in keywords))

    def test_stronger_bigram_suppresses_low_information_unigram(self):
        documents = _documents()
        result = build_feature_matrices(documents, FeatureConfig(article_keyword_limit=10))

        keywords = extract_article_keywords(
            result,
            documents,
            FeatureConfig(article_keyword_limit=10),
        )[1]
        terms = {item.term for item in keywords}

        if "官方通报" in terms:
            self.assertNotIn("官方", terms)

    def test_event_keywords_track_weighted_document_and_platform_coverage(self):
        documents = _documents()
        documents[1].nlp_weight = 0.5
        result = build_feature_matrices(documents, FeatureConfig())

        event_keywords = aggregate_event_keywords(
            result,
            {"event-a": [0, 1, 2, 3, 4]},
            documents,
            FeatureConfig(event_keyword_limit=6),
        )["event-a"]

        self.assertLessEqual(len(event_keywords), 6)
        self.assertTrue(all(item.document_count >= 2 or item.type != "word" for item in event_keywords))
        self.assertTrue(all(item.platform_count >= 1 for item in event_keywords))
        self.assertTrue(all(0.0 <= item.score <= 1.0 for item in event_keywords))

    def test_event_keywords_fall_back_to_entities_and_topics_without_tfidf(self):
        documents = _documents(1)
        result = build_feature_matrices(documents, FeatureConfig())

        event_keywords = aggregate_event_keywords(
            result,
            {"event-a": [0]},
            documents,
            FeatureConfig(event_keyword_limit=5),
        )["event-a"]

        terms = {item.term for item in event_keywords}
        self.assertIn("重庆", terms)
        self.assertIn("重庆暴雨", terms)


if __name__ == "__main__":
    unittest.main()
