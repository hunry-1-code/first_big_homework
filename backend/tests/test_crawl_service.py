import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.crawler.base import CrawlRequest, CrawlerRegistry, RawDocument
from app.crawler.errors import CrawlerError
from app.services.crawl_service import CrawlService


class FixedCrawler:
    def __init__(self, platform, count, fail=False):
        self.platform = platform
        self.count = count
        self.fail = fail
        self.requests = []

    def crawl(self, request: CrawlRequest):
        self.requests.append(request)
        if self.fail:
            raise CrawlerError(self.platform, "CRAWL_TIMEOUT", "timeout", True)
        return [
            RawDocument(
                platform=self.platform,
                source_url=f"https://{self.platform}.example.com/{index}",
                source_article_id=str(index),
                title=f"{self.platform}-{index}",
                raw_content=f"正文-{index}",
            )
            for index in range(min(self.count, request.limit))
        ]


class CrawlServiceTest(unittest.TestCase):
    def test_collect_caps_target_and_preferred_platform_limit(self):
        registry = CrawlerRegistry()
        first = FixedCrawler("first", 100)
        second = FixedCrawler("second", 100)
        registry.register(first)
        registry.register(second)

        batch = CrawlService(registry).collect(
            keyword="事件", platforms=["first", "second"], target_count=500
        )

        self.assertEqual(batch.target_count, 200)
        self.assertLessEqual(first.requests[0].limit, 50)
        self.assertLessEqual(second.requests[0].limit, 50)
        self.assertEqual(batch.platform_counts, {"first": 50, "second": 50})

    def test_one_platform_failure_does_not_discard_successful_results(self):
        registry = CrawlerRegistry()
        registry.register(FixedCrawler("ok", 10))
        registry.register(FixedCrawler("bad", 10, fail=True))

        batch = CrawlService(registry).collect("事件", ["ok", "bad"], 20)

        self.assertEqual(len(batch.documents), 10)
        self.assertEqual(batch.errors[0].platform, "bad")
        self.assertEqual(batch.errors[0].code, "CRAWL_TIMEOUT")

    def test_collect_removes_duplicate_urls_across_platforms(self):
        registry = CrawlerRegistry()

        class DuplicateCrawler(FixedCrawler):
            def crawl(self, request):
                return [
                    RawDocument(
                        platform=self.platform,
                        source_url="https://example.com/same",
                        title="same",
                        raw_content="same",
                    )
                ]

        registry.register(DuplicateCrawler("a", 1))
        registry.register(DuplicateCrawler("b", 1))

        batch = CrawlService(registry).collect("事件", ["a", "b"], 20)

        self.assertEqual(len(batch.documents), 1)

    def test_empty_platform_response_is_reported_as_error(self):
        registry = CrawlerRegistry()
        registry.register(FixedCrawler("empty", 0))

        batch = CrawlService(registry).collect("事件", ["empty"], 20)

        self.assertEqual(batch.documents, [])
        self.assertEqual(batch.errors[0].code, "CRAWL_EMPTY_RESPONSE")

    def test_default_keyword_search_excludes_sample_hotlist_and_rss(self):
        registry = CrawlerRegistry()
        search = FixedCrawler("search", 1)
        registry.register(search)
        registry.register(FixedCrawler("sample", 1))
        registry.register(FixedCrawler("weibo_hot", 1))
        registry.register(FixedCrawler("rss", 1))

        batch = CrawlService(registry).collect("事件", platforms=None, target_count=10)

        self.assertEqual(batch.platform_counts, {"search": 1})

    def test_url_and_source_id_are_both_used_for_batch_deduplication(self):
        registry = CrawlerRegistry()

        class SameUrlCrawler(FixedCrawler):
            def crawl(self, request):
                return [
                    RawDocument(
                        platform=self.platform,
                        source_url="https://example.com/same-url",
                        source_article_id=f"{self.platform}-id",
                        title="same",
                        raw_content="same",
                    )
                ]

        registry.register(SameUrlCrawler("a", 1))
        registry.register(SameUrlCrawler("b", 1))

        batch = CrawlService(registry).collect("事件", ["a", "b"], 10)

        self.assertEqual(len(batch.documents), 1)


if __name__ == "__main__":
    unittest.main()
