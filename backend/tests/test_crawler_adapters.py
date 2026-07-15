import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.crawler.base import CrawlRequest
from app.crawler.errors import CrawlerError
from app.crawler.bilibili import BilibiliCrawler
from app.crawler.qianfan import QianfanSearchCrawler, QianfanTrendingCrawler
from app.crawler.rss import RssCrawler, extract_article_text
from app.crawler.tikhub import TikHubCrawler
from app.crawler.weibo import WeiboHotCrawler
from app.crawler.zhihu import ZhihuHotCrawler, ZhihuSearchCrawler


class StubClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.payload

    def post_json(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.payload

    def get_text(self, url, **kwargs):
        self.calls.append(("GET_TEXT", url, kwargs))
        return self.payload


class CrawlerAdapterTest(unittest.TestCase):
    def test_qianfan_api_level_error_is_not_treated_as_empty_success(self):
        crawler = QianfanSearchCrawler(
            StubClient({"code": 216003, "message": "authentication error"}), "bad"
        )

        with self.assertRaises(CrawlerError) as context:
            crawler.crawl(CrawlRequest("baidu", "测试", 1))

        self.assertEqual(context.exception.code, "CRAWL_API_216003")

    def test_qianfan_search_maps_reference(self):
        payload = {
            "references": [
                {
                    "url": "https://news.example.com/1",
                    "title": "测试新闻",
                    "content": "测试新闻正文",
                    "date": "2026-07-10 08:00:00",
                    "website": "示例媒体",
                    "type": "web",
                }
            ]
        }
        crawler = QianfanSearchCrawler(StubClient(payload), "key")

        result = crawler.crawl(CrawlRequest("baidu", "测试", 1))

        self.assertEqual(result[0].source_url, "https://news.example.com/1")
        self.assertEqual(result[0].author, "示例媒体")
        self.assertEqual(result[0].source_type, "news")

    def test_qianfan_trending_maps_hot_item(self):
        payload = {
            "code": "0",
            "data": [
                {
                    "word": "热点词",
                    "desc": "热点描述",
                    "url": "https://www.baidu.com/s?wd=x",
                    "index": 1,
                    "hotScore": "12345",
                }
            ],
        }
        crawler = QianfanTrendingCrawler(StubClient(payload), "key")

        result = crawler.crawl(CrawlRequest("baidu_hot", limit=1, mode="hot"))

        self.assertEqual(result[0].title, "热点词")
        self.assertEqual(result[0].source_type, "hotlist")
        self.assertEqual(result[0].raw_json["hotScore"], "12345")

    def test_zhihu_search_maps_content(self):
        payload = {
            "data": {
                "data": [
                    {
                        "id": "answer-1",
                        "title": "知乎回答",
                        "summary": "回答摘要",
                        "url": "https://www.zhihu.com/question/1/answer/1",
                        "author_name": "作者",
                        "edit_time": "2026-07-10T08:00:00+08:00",
                    }
                ]
            }
        }
        result = ZhihuSearchCrawler(StubClient(payload), "secret").crawl(
            CrawlRequest("zhihu", "测试", 1)
        )

        self.assertEqual(result[0].source_article_id, "answer-1")
        self.assertEqual(result[0].author, "作者")

    def test_zhihu_search_maps_official_uppercase_response(self):
        payload = {
            "Code": 0,
            "Message": "Success",
            "Data": {
                "Items": [
                    {
                        "Title": "知乎回答",
                        "ContentID": "answer-2",
                        "ContentText": "回答正文",
                        "Url": "https://www.zhihu.com/question/2/answer/2",
                        "AuthorName": "作者",
                        "EditTime": 1720579200,
                        "VoteUpCount": 12,
                        "CommentCount": 3,
                    }
                ]
            },
        }

        result = ZhihuSearchCrawler(StubClient(payload), "secret").crawl(
            CrawlRequest("zhihu", "测试", 1)
        )

        self.assertEqual(result[0].source_article_id, "answer-2")
        self.assertEqual(result[0].title, "知乎回答")
        self.assertEqual(result[0].author, "作者")

    def test_zhihu_hot_maps_list(self):
        payload = {
            "data": [
                {
                    "id": 7,
                    "title": "知乎热榜",
                    "excerpt": "热榜摘要",
                    "url": "https://www.zhihu.com/question/7",
                }
            ]
        }
        result = ZhihuHotCrawler(StubClient(payload), "secret").crawl(
            CrawlRequest("zhihu_hot", limit=1, mode="hot")
        )

        self.assertEqual(result[0].source_type, "hotlist")
        self.assertEqual(result[0].source_article_id, "7")

    def test_zhihu_hot_maps_official_uppercase_response(self):
        payload = {
            "Code": 0,
            "Message": "Success",
            "Data": {
                "Items": [
                    {
                        "Title": "知乎热榜",
                        "Url": "https://www.zhihu.com/question/8",
                        "Summary": "热榜摘要",
                    }
                ]
            },
        }

        result = ZhihuHotCrawler(StubClient(payload), "secret").crawl(
            CrawlRequest("zhihu_hot", limit=1, mode="hot")
        )

        self.assertEqual(result[0].title, "知乎热榜")
        self.assertEqual(result[0].raw_content, "热榜摘要")
        self.assertEqual(result[0].source_article_id, "https://www.zhihu.com/question/8")

    def test_bilibili_maps_video_result(self):
        payload = {
            "data": {
                "result": [
                    {
                        "bvid": "BV1TEST",
                        "title": "<em class=\"keyword\">测试</em>视频",
                        "description": "视频简介",
                        "pubdate": 1,
                        "author": "UP主",
                        "play": 100,
                        "favorites": 4,
                        "review": 3,
                    }
                ]
            }
        }
        result = BilibiliCrawler(StubClient(payload)).crawl(
            CrawlRequest("bilibili", "测试", 1)
        )

        self.assertEqual(result[0].source_article_id, "BV1TEST")
        self.assertEqual(result[0].title, "测试视频")
        self.assertEqual(result[0].views_count, 100)

    def test_bilibili_initializes_public_device_cookie_before_search(self):
        class Cookies:
            def __init__(self):
                self.values = {}

            def set(self, name, value, domain=None):
                self.values[name] = (value, domain)

        class Session:
            def __init__(self):
                self.cookies = Cookies()

        class Client:
            def __init__(self):
                self.session = Session()
                self.calls = []

            def get_json(self, url, **kwargs):
                self.calls.append((url, kwargs))
                if url.endswith("/x/frontend/finger/spi"):
                    return {"code": 0, "data": {"b_3": "buvid-3", "b_4": "buvid-4"}}
                return {
                    "code": 0,
                    "data": {
                        "result": [
                            {
                                "bvid": "BVCOOKIE",
                                "title": "设备初始化测试",
                                "description": "简介",
                            }
                        ]
                    },
                }

        client = Client()

        result = BilibiliCrawler(client).crawl(CrawlRequest("bilibili", "测试", 1))

        self.assertEqual(result[0].source_article_id, "BVCOOKIE")
        self.assertIn("buvid3", client.session.cookies.values)
        self.assertIn("buvid4", client.session.cookies.values)
        self.assertEqual(client.session.cookies.values["buvid3"], ("buvid-3", ".bilibili.com"))
        self.assertEqual(client.session.cookies.values["buvid4"], ("buvid-4", ".bilibili.com"))
        self.assertEqual(client.calls[1][1]["headers"]["Referer"], "https://search.bilibili.com/")
        self.assertIn("buvid3=buvid-3", client.calls[1][1]["headers"]["Cookie"])

    def test_bilibili_fetch_comments_converts_bvid_and_maps_replies(self):
        class Cookies:
            def set(self, *args, **kwargs):
                pass

        class Session:
            cookies = Cookies()

        class Client:
            def __init__(self):
                self.session = Session()
                self.calls = []

            def get_json(self, url, **kwargs):
                self.calls.append((url, kwargs))
                if url.endswith("/x/frontend/finger/spi"):
                    return {"code": 0, "data": {"b_3": "buvid-3", "b_4": "buvid-4"}}
                if url.endswith("/x/web-interface/view"):
                    return {"code": 0, "data": {"aid": 12345}}
                return {
                    "code": 0,
                    "data": {
                        "replies": [
                            {
                                "rpid": 10,
                                "content": {"message": "一级评论"},
                                "member": {"uname": "用户A"},
                                "like": 8,
                                "rcount": 1,
                                "replies": [
                                    {
                                        "rpid": 11,
                                        "content": {"message": "回复内容"},
                                        "member": {"uname": "用户B"},
                                        "like": 2,
                                    }
                                ],
                            }
                        ]
                    },
                }

        client = Client()
        rows = BilibiliCrawler(client).fetch_comments("BV1TEST", limit=5)

        self.assertEqual([item.source_comment_id for item in rows], ["10", "11"])
        self.assertEqual(rows[1].parent_source_comment_id, "10")
        reply_call = client.calls[-1]
        self.assertTrue(reply_call[0].endswith("/x/v2/reply"))
        self.assertEqual(reply_call[1]["params"]["oid"], 12345)
        self.assertEqual(reply_call[1]["headers"]["Referer"], "https://search.bilibili.com/")

    def test_bilibili_fetch_comments_rejects_invalid_id_without_reply_request(self):
        class Client:
            def __init__(self):
                self.calls = []

            def get_json(self, url, **kwargs):
                self.calls.append(url)
                return {"code": 0, "data": {}}

        client = Client()
        rows = BilibiliCrawler(client).fetch_comments("not-an-id", limit=5)

        self.assertEqual(rows, [])
        self.assertFalse(any(url.endswith("/x/v2/reply") for url in client.calls))

    def test_weibo_hot_maps_realtime_list(self):
        payload = {
            "data": {
                "realtime": [
                    {"word": "微博热点", "note": "微博热点", "num": 999, "rank": 2}
                ]
            }
        }
        result = WeiboHotCrawler(StubClient(payload)).crawl(
            CrawlRequest("weibo_hot", limit=1, mode="hot")
        )

        self.assertEqual(result[0].title, "微博热点")
        self.assertIn("weibo.com", result[0].source_url)

    def test_tikhub_weibo_maps_nested_status(self):
        payload = {
            "data": {
                "data": {
                    "statuses": [
                        {
                            "id": "123",
                            "text_raw": "微博正文",
                            "created_at": "Fri Jul 10 08:00:00 +0800 2026",
                            "user": {"screen_name": "用户", "id": "9"},
                            "attitudes_count": 10,
                            "comments_count": 2,
                            "reposts_count": 1,
                        }
                    ]
                }
            }
        }
        crawler = TikHubCrawler(StubClient(payload), "key", platform="weibo")

        result = crawler.crawl(CrawlRequest("weibo", "微博", 1))

        self.assertEqual(result[0].source_article_id, "123")
        self.assertEqual(result[0].author, "用户")
        self.assertEqual(result[0].likes_count, 10)

    def test_tikhub_weibo_flattens_web_search_card_groups(self):
        payload = {
            "code": 200,
            "data": {
                "data": {
                    "cards": [
                        {
                            "card_type": 11,
                            "card_group": [
                                {
                                    "mblog": {
                                        "id": "456",
                                        "text_raw": "人工智能微博正文",
                                        "created_at": "Fri Jul 10 08:00:00 +0800 2026",
                                        "user": {"screen_name": "用户", "id": "10"},
                                    }
                                }
                            ],
                        }
                    ]
                }
            },
        }
        crawler = TikHubCrawler(StubClient(payload), "key", platform="weibo")

        result = crawler.crawl(CrawlRequest("weibo", "人工智能", 1))

        self.assertEqual(result[0].source_article_id, "456")
        self.assertEqual(result[0].raw_content, "人工智能微博正文")

    def test_tikhub_xiaohongshu_skips_placeholder_items(self):
        payload = {
            "code": 200,
            "data": {"data": {"items": [{"model_type": "hot_query"}]}},
        }
        crawler = TikHubCrawler(StubClient(payload), "key", platform="xiaohongshu")

        result = crawler.crawl(CrawlRequest("xiaohongshu", "人工智能", 1))

        self.assertEqual(result, [])

    def test_tikhub_xiaohongshu_uses_official_search_parameters(self):
        client=StubClient({'code':200,'data':{'data':{'items':[]}}})
        crawler=TikHubCrawler(client,'key',platform='xiaohongshu')
        crawler.crawl(CrawlRequest('xiaohongshu','人工智能',1,extra={'search_id':'s1','search_session_id':'ss1'}))
        params=client.calls[0][2]['params']
        self.assertEqual(params['sort_type'],'general')
        self.assertEqual(params['note_type'],'不限')
        self.assertEqual(params['search_id'],'s1')
        self.assertEqual(params['search_session_id'],'ss1')

    def test_rss_maps_atom_entry(self):
        xml = """<?xml version='1.0' encoding='utf-8'?>
        <feed xmlns='http://www.w3.org/2005/Atom'>
          <entry><id>item-1</id><title>RSS 标题</title><summary>RSS 正文</summary>
          <link href='https://example.com/rss/1'/><updated>2026-07-10T08:00:00+08:00</updated></entry>
        </feed>"""
        result = RssCrawler(StubClient(xml), "https://example.com/feed.xml").crawl(
            CrawlRequest("rss", limit=1)
        )

        self.assertEqual(result[0].source_article_id, "item-1")
        self.assertEqual(result[0].title, "RSS 标题")

    def test_rss_matches_summary_sets_headers_and_strictly_limits_results(self):
        xml = """<?xml version='1.0' encoding='utf-8'?>
        <rss><channel>
          <item><guid>1</guid><title>行业观察一</title><description>人工智能正在改变产业结构，正文摘要足够长用于降级保存。</description><link>https://example.com/1</link></item>
          <item><guid>2</guid><title>行业观察二</title><description>人工智能应用进入新阶段，这是一段足够长的文章摘要内容。</description><link>https://example.com/2</link></item>
          <item><guid>3</guid><title>行业观察三</title><description>人工智能治理受到关注，这也是一段足够长的摘要文本。</description><link>https://example.com/3</link></item>
        </channel></rss>"""
        client = StubClient(xml)
        crawler = RssCrawler(
            client,
            "https://example.com/feed.xml",
            article_extractor=lambda _: None,
            minimum_content_length=10,
        )

        result = crawler.crawl(CrawlRequest("rss", keyword="人工智能", limit=2))

        self.assertEqual(len(result), 2)
        self.assertTrue(all("人工智能" in item.raw_content for item in result))
        headers = client.calls[0][2]["headers"]
        self.assertIn("Mozilla", headers["User-Agent"])
        self.assertEqual(
            headers["Accept"],
            "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        )
        self.assertTrue(client.calls[0][2]["prefer_xml"])

    def test_rss_expands_artificial_intelligence_keyword_to_common_news_terms(self):
        xml = """<?xml version='1.0' encoding='utf-8'?>
        <rss><channel><item><guid>ai-1</guid>
          <title>AI 基础设施投资持续升温</title>
          <description>大模型产业进入新的发展阶段，这是一段足够长的摘要。</description>
          <link>https://example.com/ai-1</link>
        </item></channel></rss>"""
        crawler = RssCrawler(
            StubClient(xml),
            "https://example.com/feed.xml",
            article_extractor=lambda _: None,
            minimum_content_length=10,
        )

        rows = crawler.crawl(CrawlRequest("rss", keyword="人工智能", limit=1))

        self.assertEqual([row.source_article_id for row in rows], ["ai-1"])

    def test_rss_keyword_matching_ignores_html_attributes_and_maps_cont_id(self):
        xml = """<?xml version='1.0' encoding='utf-8'?>
        <rss><channel>
          <item><contId>33500001</contId><title>普通文化新闻</title>
            <description><![CDATA[<div data-ai="" x-webkit-airplay="allow">这是一段普通文化报道摘要。</div>]]></description>
            <link>https://m.thepaper.cn/newsDetail_forward_33500001</link>
          </item>
          <item><contId>33500002</contId><title>AI 基建新闻</title>
            <description><![CDATA[<p>人工智能基础设施相关报道摘要。</p>]]></description>
            <link>https://m.thepaper.cn/newsDetail_forward_33500002</link>
          </item>
        </channel></rss>"""
        crawler = RssCrawler(
            StubClient(xml),
            "https://m.thepaper.cn/rss_news",
            platform="news_thepaper",
            article_extractor=lambda _: None,
            minimum_content_length=10,
        )

        rows = crawler.crawl(
            CrawlRequest("news_thepaper", keyword="人工智能", limit=2)
        )

        self.assertEqual([row.source_article_id for row in rows], ["33500002"])

    def test_article_extractor_uses_browser_headers_and_txt_output(self):
        response = Mock()
        response.content = b"<html><body>article</body></html>"
        response.headers = {"Content-Length": str(len(response.content))}
        response.raise_for_status.return_value = None

        with patch("app.crawler.rss.requests.get", return_value=response) as get, patch(
            "app.crawler.rss.trafilatura.extract", return_value="正文" * 120
        ) as extract:
            text = extract_article_text("https://www.infoq.cn/article/1")

        self.assertGreater(len(text), 200)
        self.assertIn("Mozilla", get.call_args.kwargs["headers"]["User-Agent"])
        self.assertEqual(extract.call_args.kwargs["output_format"], "txt")

    def test_rss_does_not_match_keyword_only_in_distant_related_links(self):
        unrelated = "普通活动信息" * 260 + " AI 相关阅读"
        xml = f"""<?xml version='1.0' encoding='utf-8'?>
        <rss><channel><item><guid>promo</guid><title>抽奖活动</title>
          <description>{unrelated}</description>
          <link>https://example.com/promo</link>
        </item></channel></rss>"""
        crawler = RssCrawler(
            StubClient(xml),
            "https://example.com/feed.xml",
            article_extractor=lambda _: None,
            minimum_content_length=10,
        )

        rows = crawler.crawl(CrawlRequest("rss", keyword="人工智能", limit=1))

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
