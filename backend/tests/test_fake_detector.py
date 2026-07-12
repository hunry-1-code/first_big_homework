"""虚假/可疑信息风险评估单元测试。

覆盖：6因子规则评分、分数区间clamp、method标记、边界条件
"""
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.analysis.fake_detector import (
    _build_context,
    _estimate_anomaly_speed,
    _load_official_media,
    _match_official_media,
    _sensational_keywords,
    assess_suspicious_risk,
    batch_assess_articles,
)


class OfficialMediaTest(unittest.TestCase):
    """官方媒体白名单与匹配测试"""

    def test_load_returns_set(self):
        media = _load_official_media()
        self.assertIsInstance(media, set)
        self.assertGreater(len(media), 0)

    def test_match_exact(self):
        self.assertTrue(_match_official_media("人民日报"))
        self.assertTrue(_match_official_media("新华社"))
        self.assertTrue(_match_official_media("央视新闻"))

    def test_match_pattern(self):
        self.assertTrue(_match_official_media("某某日报"))
        self.assertTrue(_match_official_media("某某新闻网"))
        self.assertTrue(_match_official_media("某某晚报"))
        self.assertTrue(_match_official_media("某某政府"))

    def test_match_non_official(self):
        self.assertFalse(_match_official_media("普通网友"))
        self.assertFalse(_match_official_media(""))
        self.assertFalse(_match_official_media("吃瓜群众"))


class SensationalKeywordsTest(unittest.TestCase):
    """煽动性关键词测试"""

    def test_keywords_defined(self):
        self.assertIsInstance(_sensational_keywords, list)
        self.assertIn("震惊", _sensational_keywords)
        self.assertIn("炸裂", _sensational_keywords)
        self.assertIn("突发", _sensational_keywords)


class AssessSuspiciousRiskTest(unittest.TestCase):
    """核心评分函数测试"""

    def _make_article(self, **overrides):
        defaults = {
            "id": 1,
            "platform": "weibo",
            "title": "正常标题",
            "clean_content": "正常内容",
            "author": "普通网友",
            "author_type": None,
            "sentiment_score": 0.0,
            "publish_time": None,
            "comments_count": 0,
            "reposts_count": 0,
            "likes_count": 0,
            "event_id": 1,
        }
        defaults.update(overrides)
        # 用简单的属性访问对象
        class ArticleStub:
            def __init__(self, d):
                self.__dict__.update(d)

        return ArticleStub(defaults)

    def _make_event_context(self, **overrides):
        defaults = {
            "event_id": 1,
            "article_count": 10,
            "platforms": {"weibo", "zhihu"},
            "has_official_media": False,
            "first_publish_time": None,
            "avg_interactions": 100,
        }
        defaults.update(overrides)
        return defaults

    def test_normal_article_low_risk(self):
        article = self._make_article()
        ctx = self._make_event_context()
        result = assess_suspicious_risk(article, ctx)
        self.assertFalse(result["is_suspicious"])
        self.assertLess(result["score"], 40)
        self.assertEqual(result["method"], "rule")

    def test_no_cross_validation_adds_score(self):
        article = self._make_article()
        ctx = self._make_event_context(platforms={"weibo"})  # 单一平台
        result = assess_suspicious_risk(article, ctx)
        self.assertGreaterEqual(result["score"], 40)

    def test_sensational_title_adds_score(self):
        article = self._make_article(title="突发！某地发生惊天大事震惊全网")
        ctx = self._make_event_context()
        result = assess_suspicious_risk(article, ctx)
        self.assertGreater(result["score"], 30)
        self.assertIn("标题", result["reason"])

    def test_negative_sentiment_adds_score(self):
        article = self._make_article(sentiment_score=-0.8)
        ctx = self._make_event_context()
        result = assess_suspicious_risk(article, ctx)
        self.assertGreater(result["score"], 30)

    def test_official_media_response_reduces_score(self):
        article = self._make_article(author="人民日报")
        ctx = self._make_event_context(has_official_media=True)
        result = assess_suspicious_risk(article, ctx)
        # 官媒来源本身不触发低可信度 + 有官方回应 → 分数应降低
        self.assertLess(result["score"], 60)

    def test_score_clamped_0_100(self):
        article = self._make_article()
        ctx = self._make_event_context()
        result = assess_suspicious_risk(article, ctx)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_high_risk_detected(self):
        article = self._make_article(
            title="震惊！炸裂！突发重大事件",
        )
        ctx = self._make_event_context(
            platforms={"weibo"},  # 单平台
            has_official_media=False,
        )
        result = assess_suspicious_risk(article, ctx)
        self.assertTrue(result["is_suspicious"] or result["score"] >= 40)

    def test_advertising_call_to_action_adds_low_weight_risk(self):
        article = self._make_article(clean_content="点击链接扫码领取福利，并添加微信咨询")
        result = assess_suspicious_risk(article, self._make_event_context())
        self.assertEqual(result["score"], 33.0)
        self.assertIn("广告引流", result["reason"])

    def test_external_link_adds_low_weight_risk(self):
        article = self._make_article(clean_content="更多内容请查看 http://unknown.example/path")
        result = assess_suspicious_risk(article, self._make_event_context())
        self.assertEqual(result["score"], 28.0)
        self.assertIn("外部链接", result["reason"])

    def test_title_content_low_consistency_adds_low_weight_risk(self):
        article = self._make_article(title="城市暴雨应急救援进展", clean_content="明星演唱会门票正式开售，现场座位已经公布。")
        result = assess_suspicious_risk(article, self._make_event_context())
        self.assertEqual(result["score"], 30.0)
        self.assertIn("标题与正文一致性较低", result["reason"])

    def test_short_or_missing_text_does_not_trigger_consistency_rule(self):
        article = self._make_article(title="通知", clean_content="内容")
        result = assess_suspicious_risk(article, self._make_event_context())
        self.assertEqual(result["score"], 25.0)


class BatchAssessTest(unittest.TestCase):
    """批量评估测试"""

    def test_empty_list_returns_empty(self):
        result = batch_assess_articles([], {})
        self.assertEqual(result, [])

    def test_batch_returns_same_count(self):
        articles = [
            self._make_stub(i) for i in range(3)
        ]
        ctx = {"event_id": 1, "article_count": 3, "platforms": {"weibo", "zhihu"}, "has_official_media": True,
               "first_publish_time": None, "avg_interactions": 50}
        result = batch_assess_articles(articles, ctx)
        self.assertEqual(len(result), 3)

    @staticmethod
    def _make_stub(idx):
        class Stub:
            id = idx
            platform = "weibo"
            title = f"正常标题{idx}"
            clean_content = "正常内容"
            author = "网友"
            author_type = None
            sentiment_score = 0.0
            publish_time = None
            comments_count = 0
            reposts_count = 0
            likes_count = 0
            event_id = 1
        return Stub()


class EdgeCaseTest(unittest.TestCase):
    """边界条件测试"""

    def test_empty_author(self):
        from app.analysis.fake_detector import assess_suspicious_risk
        result = assess_suspicious_risk(
            self._stub(author=""), {"event_id": 1, "platforms": {"weibo"}, "has_official_media": False,
                                    "article_count": 1, "first_publish_time": None, "avg_interactions": 0}
        )
        self.assertIsInstance(result["score"], (int, float))

    def test_empty_title(self):
        from app.analysis.fake_detector import assess_suspicious_risk
        result = assess_suspicious_risk(
            self._stub(title=""), {"event_id": 1, "platforms": {"weibo"}, "has_official_media": False,
                                   "article_count": 1, "first_publish_time": None, "avg_interactions": 0}
        )
        self.assertIsInstance(result["score"], (int, float))

    @staticmethod
    def _stub(**kw):
        class Stub:
            id = 1; platform = "weibo"; title = "标题"; clean_content = "内容"
            author = "网友"; author_type = None; sentiment_score = 0.0
            publish_time = None; comments_count = 0; reposts_count = 0
            likes_count = 0; event_id = 1
        s = Stub()
        for k, v in kw.items():
            setattr(s, k, v)
        return s


if __name__ == "__main__":
    unittest.main()
