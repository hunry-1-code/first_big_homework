import json
import unittest

from tools.validate_live_crawlers import (
    classify_error,
    result_payload,
    validate_document_contract,
)


class FakeError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class LiveCrawlerValidatorTest(unittest.TestCase):
    def test_result_serialization_never_contains_secret_values(self):
        payload = result_payload(
            "weibo",
            "AUTH_ERROR",
            message="Bearer secret-token authentication failed",
            secrets=["secret-token"],
        )

        self.assertNotIn("secret-token", json.dumps(payload, ensure_ascii=False))

    def test_empty_success_is_distinct_from_success_with_documents(self):
        empty = result_payload("zhihu", "EMPTY_SUCCESS", document_count=0)
        success = result_payload("zhihu", "SUCCESS", document_count=1)

        self.assertNotEqual(empty["status"], success["status"])

    def test_auth_and_quota_errors_are_classified_without_body_dump(self):
        self.assertEqual(classify_error(FakeError("CRAWL_API_401", "unauthorized")), "AUTH_ERROR")
        self.assertEqual(classify_error(FakeError("CRAWL_API_429", "quota exceeded")), "QUOTA_ERROR")

    def test_document_contract_requires_core_fields(self):
        valid = type(
            "Document",
            (),
            {
                "platform": "bilibili",
                "title": "测试视频",
                "source_type": "video",
                "source_url": "https://www.bilibili.com/video/BV1",
                "raw_json": {"bvid": "BV1"},
            },
        )()
        invalid = type(
            "Document",
            (),
            {
                "platform": "",
                "title": "",
                "source_type": "video",
                "source_url": "",
                "raw_json": {},
            },
        )()

        self.assertEqual(validate_document_contract(valid), [])
        self.assertGreater(len(validate_document_contract(invalid)), 0)


if __name__ == "__main__":
    unittest.main()
