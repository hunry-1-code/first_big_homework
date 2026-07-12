import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.crawler.base import RawDocument
from app.preprocessing.pipeline import preprocess_document


class PreprocessingPipelineTest(unittest.TestCase):
    def test_pipeline_preserves_raw_and_produces_features(self):
        raw_text = "这是足够长的测试正文，包含公共事件信息和市民讨论。" * 20
        raw = RawDocument(
            platform="sample",
            source_url="sample://event/1",
            source_article_id="1",
            title="公共事件测试",
            raw_content=raw_text,
            source_type="sample",
            content_type="text",
            author="样例媒体",
            publish_time="2026-07-10T08:00:00+08:00",
        )

        output = preprocess_document(raw)

        self.assertEqual(output.raw_content, raw_text)
        self.assertEqual(output.clean_status, "success")
        self.assertTrue(output.clean_content)
        self.assertTrue(output.features["tfidf_tokens"])
        self.assertEqual(output.normalized_data["raw_content"], raw_text)
        self.assertIn("normalize", [item.stage for item in output.logs])
        self.assertIn("segment", [item.stage for item in output.logs])

    def test_pipeline_attributes_blocked_page_failure_to_crawl(self):
        raw = RawDocument(
            platform="baidu",
            source_url="https://example.com/blocked",
            title="访问页面",
            raw_content="<html>访问异常，请完成安全验证和验证码</html>",
            source_type="news",
            content_type="html",
        )

        output = preprocess_document(raw)

        self.assertEqual(output.clean_status, "failed")
        self.assertEqual(output.clean_error, "CRAWL_CAPTCHA")
        failed = [item for item in output.logs if item.status == "failed"]
        self.assertEqual(failed[-1].stage, "crawl")

    def test_pipeline_marks_duplicate_without_deleting_content(self):
        text = "某地发布公共交通调整方案，市民可通过官方渠道查询详细安排。" * 8
        raw = RawDocument(
            platform="baidu",
            source_url="https://example.com/new",
            title="某地发布公共交通调整方案",
            raw_content=text,
            source_type="news",
            content_type="text",
        )
        candidates = [
            {
                "id": 9,
                "title": "某地发布公共交通调整方案",
                "clean_content": text,
                "duplicate_group_id": "group-9",
            }
        ]

        output = preprocess_document(raw, duplicate_candidates=candidates)

        self.assertTrue(output.duplicate["is_duplicate"])
        self.assertEqual(output.duplicate["duplicate_of_id"], 9)
        self.assertEqual(output.raw_content, text)
        self.assertEqual(output.clean_content, text.replace("，", ","))

    def test_normal_news_that_mentions_verification_code_is_not_blocked(self):
        text = "警方提醒市民不要向陌生人泄露短信验证码，并介绍了常见诈骗案例。" * 20
        raw = RawDocument(
            platform="baidu",
            source_url="https://example.com/security-news",
            title="警方发布防诈骗提醒",
            raw_content=text,
            source_type="news",
            content_type="text",
        )

        output = preprocess_document(raw)

        self.assertEqual(output.clean_status, "success")


if __name__ == "__main__":
    unittest.main()
