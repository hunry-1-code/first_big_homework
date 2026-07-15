import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.crawler.base import CrawlRequest, RawDocument
from app.crawler.mainstream_news import MainstreamNewsCrawler
from app.crawler.news_comments import NewsCommentDispatcher
from app.crawler.people_news import PeopleNewsCrawler


class StubClient:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = []

    def post_json(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if self.error:
            raise self.error
        return self.payload

    def get_json(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if self.error:
            raise self.error
        return self.payload


class FakeSource:
    def __init__(self, platform, count=5, fail=None, shared_url=None):
        self.platform = platform
        self.count = count
        self.fail = fail
        self.shared_url = shared_url
        self.requests = []

    def crawl(self, request):
        self.requests.append(request)
        if self.fail:
            raise self.fail
        return [
            RawDocument(
                platform=self.platform,
                source_url=self.shared_url or f"https://{self.platform}.example.com/{index}",
                source_article_id=f"{self.platform}-{index}",
                title=f"{self.platform} 标题 {index}",
                raw_content="人工智能新闻正文" * 20,
            )
            for index in range(min(self.count, request.limit))
        ]


class MainstreamNewsCrawlerTest(unittest.TestCase):
    def test_people_search_uses_official_payload_and_maps_records(self):
        client = StubClient(
            {
                "code": "0",
                "data": {
                    "records": [
                        {
                            "id": "1000040756993",
                            "title": "剑桥中英<em>人工智能</em>商业论坛",
                            "url": "http://world.people.com.cn/n1/2026/0709/c1002-40756993.html",
                            "inputTime": 1783582110000,
                            "originName": "人民网-国际频道",
                            "content": "<p>人工智能论坛正文内容，足够长用于保存。</p>",
                        }
                    ],
                    "total": 1,
                },
            }
        )
        crawler = PeopleNewsCrawler(
            client,
            rss_fallback=None,
            article_extractor=lambda _: None,
            minimum_content_length=10,
        )

        rows = crawler.crawl(CrawlRequest("news_people", keyword="人工智能", limit=5))

        method, url, kwargs = client.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "http://search.people.cn/search-platform/front/search")
        self.assertEqual(kwargs["json"]["key"], "人工智能")
        self.assertEqual(kwargs["json"]["page"], 1)
        self.assertEqual(kwargs["json"]["limit"], 5)
        self.assertIn("Mozilla", kwargs["headers"]["User-Agent"])
        self.assertEqual(rows[0].platform, "news_people")
        self.assertEqual(rows[0].source_article_id, "1000040756993")
        self.assertEqual(rows[0].title, "剑桥中英人工智能商业论坛")
        self.assertNotIn("<p>", rows[0].raw_content)
        self.assertTrue(rows[0].publish_time.startswith("2026-07"))

    def test_people_search_falls_back_and_filters_stale_rss_documents(self):
        class Fallback:
            def crawl(self, request):
                return [
                    RawDocument(
                        platform="news_people",
                        source_url="https://people.com.cn/old",
                        source_article_id="old",
                        title="旧闻",
                        raw_content="旧闻正文" * 20,
                        publish_time="2025-06-01T08:00:00+08:00",
                    ),
                    RawDocument(
                        platform="news_people",
                        source_url="https://people.com.cn/new",
                        source_article_id="new",
                        title="新稿",
                        raw_content="新稿正文" * 20,
                        publish_time="2026-07-10T08:00:00+08:00",
                    ),
                ]

        crawler = PeopleNewsCrawler(
            StubClient({"code": "0", "data": {"records": []}}),
            rss_fallback=Fallback(),
            now=lambda: datetime(2026, 7, 15, tzinfo=timezone.utc),
            freshness_days=45,
        )

        rows = crawler.crawl(CrawlRequest("news_people", keyword="人工智能", limit=5))

        self.assertEqual([row.source_article_id for row in rows], ["new"])

    def test_aggregate_allocates_fixed_quotas_and_isolates_one_failure(self):
        sources = [
            FakeSource("news_people"),
            FakeSource("news_36kr", fail=RuntimeError("down")),
            FakeSource("news_thepaper"),
            FakeSource("news_infoq"),
            FakeSource("news_sspai"),
        ]
        crawler = MainstreamNewsCrawler(sources)

        rows = crawler.crawl(CrawlRequest("mainstream_news", keyword="人工智能", limit=20))

        self.assertEqual([source.requests[0].limit for source in sources], [4, 4, 4, 4, 4])
        self.assertEqual(len(rows), 16)
        self.assertEqual(
            crawler.last_source_counts,
            {
                "news_people": 4,
                "news_36kr": 0,
                "news_thepaper": 4,
                "news_infoq": 4,
                "news_sspai": 4,
            },
        )
        self.assertEqual(crawler.last_errors[0]["platform"], "news_36kr")

    def test_aggregate_caps_each_source_at_five_and_deduplicates_urls(self):
        shared = "https://example.com/shared"
        sources = [
            FakeSource("news_people", shared_url=shared),
            FakeSource("news_36kr", shared_url=shared),
            FakeSource("news_thepaper"),
            FakeSource("news_infoq"),
            FakeSource("news_sspai"),
        ]
        crawler = MainstreamNewsCrawler(sources)

        rows = crawler.crawl(CrawlRequest("mainstream_news", keyword="人工智能", limit=50))

        self.assertTrue(all(source.requests[0].limit == 5 for source in sources))
        self.assertLessEqual(len(rows), 25)
        self.assertEqual(sum(row.source_url == shared for row in rows), 1)
        self.assertNotIn("mainstream_news", {row.platform for row in rows})

    def test_sspai_comments_map_public_response_and_limit_ten(self):
        payload = {
            "error": 0,
            "data": [
                {
                    "id": 428733 + index,
                    "comment": f"评论 {index}",
                    "likes_count": index,
                    "user": {"nickname": f"用户 {index}"},
                    "reply": [{"id": index}],
                }
                for index in range(12)
            ],
        }
        dispatcher = NewsCommentDispatcher(sspai_client=StubClient(payload))
        document = RawDocument(
            platform="news_sspai",
            source_url="https://sspai.com/post/112320",
            source_article_id="112320",
            title="少数派文章",
            raw_content="正文",
        )

        result = dispatcher.fetch(document, limit=50)

        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.comments), 10)
        self.assertEqual(result.comments[0].platform, "news_sspai")
        self.assertEqual(result.comments[0].source_comment_id, "428733")
        self.assertEqual(result.comments[0].author, "用户 0")
        self.assertEqual(result.comments[0].replies_count, 1)

    def test_thepaper_comments_map_public_response(self):
        payload = {
            "code": 200,
            "data": {
                "list": [
                    {
                        "commentId": 45031126,
                        "content": "积木变纸，这波极简风反而高级。",
                        "originPraiseTimes": 1,
                        "userInfo": {"sname": "草茗"},
                        "commentReply": [{"commentId": 2}],
                    }
                ]
            },
        }
        dispatcher = NewsCommentDispatcher(thepaper_client=StubClient(payload))
        document = RawDocument(
            platform="news_thepaper",
            source_url="https://m.thepaper.cn/newsDetail_forward_33586320?from=rss",
            source_article_id="33586320",
            title="澎湃文章",
            raw_content="正文",
        )

        result = dispatcher.fetch(document, limit=10)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.comments[0].source_comment_id, "45031126")
        self.assertEqual(result.comments[0].author, "草茗")
        self.assertEqual(result.comments[0].likes_count, 1)

    def test_comment_status_distinguishes_empty_unsupported_and_failed(self):
        empty = NewsCommentDispatcher(
            thepaper_client=StubClient({"code": 200, "data": {"list": []}})
        ).fetch(
            RawDocument("news_thepaper", "https://m.thepaper.cn/newsDetail_forward_33585997", "标题", "正文", source_article_id="33585997"),
            limit=10,
        )
        unsupported = NewsCommentDispatcher().fetch(
            RawDocument("news_people", "https://people.com.cn/1", "标题", "正文"),
            limit=10,
        )
        failed = NewsCommentDispatcher(
            sspai_client=StubClient(error=RuntimeError("timeout"))
        ).fetch(
            RawDocument("news_sspai", "https://sspai.com/post/112320", "标题", "正文", source_article_id="112320"),
            limit=10,
        )

        self.assertEqual(empty.status, "empty")
        self.assertEqual(unsupported.status, "unsupported")
        self.assertEqual(failed.status, "failed")
        self.assertIn("timeout", failed.error)


if __name__ == "__main__":
    unittest.main()
