import json
import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.crawler.base import CrawlRequest, RawDocument
from app.crawler.errors import CrawlerError
from app.crawler.http import HttpClient


class FakeResponse:
    def __init__(self, status_code, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = headers or {}
        self.encoding = "utf-8"
        if payload is not None:
            self.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        else:
            self.content = text.encode("utf-8")

    def iter_content(self, chunk_size=8192):
        for index in range(0, len(self.content), chunk_size):
            yield self.content[index : index + chunk_size]

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


class CrawlerCoreTest(unittest.TestCase):
    def test_raw_document_preserves_platform_fields(self):
        document = RawDocument(
            platform="baidu",
            source_url="https://example.com/1",
            title="标题",
            raw_content="正文",
        )

        self.assertEqual(document.clean_status, "pending")
        self.assertEqual(document.raw_json, {})
        self.assertEqual(document.source_type, "news")

    def test_crawl_request_clamps_limit_to_positive_value(self):
        request = CrawlRequest(platform="baidu", keyword="测试", limit=0)

        self.assertEqual(request.limit, 1)

    def test_http_client_retries_server_error_then_returns_json(self):
        session = FakeSession(
            [FakeResponse(500, {"message": "busy"}), FakeResponse(200, {"ok": True})]
        )
        delays = []
        client = HttpClient(
            session=session,
            allowed_hosts={"example.com"},
            max_attempts=3,
            sleep=delays.append,
            resolver=lambda _: ["93.184.216.34"],
        )

        payload = client.get_json("https://example.com/data")

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(delays, [1])

    def test_http_client_rejects_host_outside_allowlist(self):
        client = HttpClient(
            session=FakeSession([]),
            allowed_hosts={"example.com"},
            resolver=lambda _: ["93.184.216.34"],
        )

        with self.assertRaises(CrawlerError) as context:
            client.get_json("https://evil.example.net/data")

        self.assertEqual(context.exception.code, "CRAWL_URL_NOT_ALLOWED")
        self.assertFalse(context.exception.retryable)

    def test_http_client_does_not_retry_authentication_failure(self):
        session = FakeSession([FakeResponse(403, {"message": "forbidden"})])
        client = HttpClient(
            session=session,
            allowed_hosts={"example.com"},
            sleep=lambda _: None,
            resolver=lambda _: ["93.184.216.34"],
        )

        with self.assertRaises(CrawlerError) as context:
            client.get_json("https://example.com/data")

        self.assertEqual(context.exception.code, "CRAWL_HTTP_403")
        self.assertEqual(len(session.calls), 1)

    def test_http_client_rejects_private_dns_target(self):
        client = HttpClient(
            session=FakeSession([]),
            allowed_hosts={"example.com"},
            resolver=lambda _: ["127.0.0.1"],
        )

        with self.assertRaises(CrawlerError) as context:
            client.get_json("https://example.com/data")

        self.assertEqual(context.exception.code, "CRAWL_PRIVATE_ADDRESS")

    def test_http_client_disables_redirects(self):
        session = FakeSession([FakeResponse(302, headers={"Location": "http://127.0.0.1"})])
        client = HttpClient(
            session=session,
            allowed_hosts={"example.com"},
            resolver=lambda _: ["93.184.216.34"],
        )

        with self.assertRaises(CrawlerError) as context:
            client.get_json("https://example.com/data")

        self.assertEqual(context.exception.code, "CRAWL_REDIRECT_BLOCKED")
        self.assertFalse(session.calls[0][2]["allow_redirects"])

    def test_http_client_rejects_oversized_response(self):
        session = FakeSession([FakeResponse(200, text="x" * 20)])
        client = HttpClient(
            session=session,
            allowed_hosts={"example.com"},
            resolver=lambda _: ["93.184.216.34"],
            max_response_bytes=10,
        )

        with self.assertRaises(CrawlerError) as context:
            client.get_text("https://example.com/data")

        self.assertEqual(context.exception.code, "CRAWL_RESPONSE_TOO_LARGE")


if __name__ == "__main__":
    unittest.main()
