from __future__ import annotations

from urllib.parse import urlsplit

from app.crawler.base import CrawlerRegistry
from app.crawler.bilibili import BilibiliCrawler
from app.crawler.http import HttpClient
from app.crawler.qianfan import QianfanSearchCrawler, QianfanTrendingCrawler
from app.crawler.rss import RssCrawler
from app.crawler.sample import SampleCrawler
from app.crawler.tikhub import TikHubCrawler
from app.crawler.weibo import WeiboHotCrawler
from app.crawler.zhihu import ZhihuHotCrawler, ZhihuSearchCrawler


def _setting(config, name: str, default=None):
    if isinstance(config, dict):
        return config.get(name, default)
    return getattr(config, name, default)


def _client(host: str, timeout: int, platform: str, max_response_bytes: int) -> HttpClient:
    return HttpClient(
        allowed_hosts={host},
        timeout=timeout,
        max_attempts=3,
        max_response_bytes=max_response_bytes,
        platform=platform,
    )


def build_crawler_registry(config) -> CrawlerRegistry:
    registry = CrawlerRegistry()
    timeout = int(_setting(config, "CRAWL_REQUEST_TIMEOUT", 30))
    max_response_bytes = int(_setting(config, "CRAWL_MAX_RESPONSE_BYTES", 5 * 1024 * 1024))
    registry.register(SampleCrawler())
    registry.register(BilibiliCrawler(_client("bilibili.com", timeout, "bilibili", max_response_bytes)))
    registry.register(WeiboHotCrawler(_client("weibo.com", timeout, "weibo_hot", max_response_bytes)))

    qianfan_key = _setting(config, "QIANFAN_API_KEY", "")
    if qianfan_key:
        qianfan_base = _setting(config, "QIANFAN_API_BASE_URL", "https://qianfan.baidubce.com")
        host = urlsplit(qianfan_base).hostname or "qianfan.baidubce.com"
        qianfan_timeout = int(_setting(config, "QIANFAN_REQUEST_TIMEOUT", timeout))
        registry.register(
            QianfanSearchCrawler(
                _client(host, qianfan_timeout, "baidu", max_response_bytes),
                qianfan_key,
                qianfan_base,
                _setting(config, "QIANFAN_WEB_SEARCH_PATH", "/v2/ai_search/web_search"),
                _setting(config, "QIANFAN_WEB_SEARCH_TOP_K", 50),
            )
        )
        registry.register(
            QianfanTrendingCrawler(
                _client(host, qianfan_timeout, "baidu_hot", max_response_bytes),
                qianfan_key,
                qianfan_base,
                _setting(config, "QIANFAN_TRENDING_PATH", "/v2/tools/baidu_trending"),
            )
        )

    zhihu_secret = _setting(config, "ZHIHU_ACCESS_SECRET", "")
    if zhihu_secret:
        zhihu_base = _setting(config, "ZHIHU_API_BASE_URL", "https://developer.zhihu.com")
        host = urlsplit(zhihu_base).hostname or "developer.zhihu.com"
        registry.register(ZhihuSearchCrawler(_client(host, timeout, "zhihu", max_response_bytes), zhihu_secret, zhihu_base))
        registry.register(ZhihuHotCrawler(_client(host, timeout, "zhihu_hot", max_response_bytes), zhihu_secret, zhihu_base))

    tikhub_key = _setting(config, "TIKHUB_API_KEY", "")
    if tikhub_key:
        tikhub_base = _setting(config, "TIKHUB_BASE_URL", "https://api.tikhub.io")
        host = urlsplit(tikhub_base).hostname or "api.tikhub.io"
        for platform in _setting(config, "TIKHUB_ENABLED_PLATFORMS", []):
            if platform in {"weibo", "xiaohongshu", "douyin"}:
                platform_key = _setting(config, "TIKHUB_PLATFORM_API_KEYS", {}).get(platform) or tikhub_key
                registry.register(
                    TikHubCrawler(
                        _client(host, timeout, platform, max_response_bytes),
                        platform_key,
                        platform,
                        tikhub_base,
                    )
                )

    feed_urls = _setting(config, "RSS_FEED_URL", "")
    if feed_urls:
        for idx, feed_url in enumerate([u.strip() for u in str(feed_urls).split(",") if u.strip()]):
            host = urlsplit(feed_url).hostname
            if host:
                # 每个 RSS 源一个唯一 platform 名
                plat_name = f"rss_{host.split('.')[0]}"
                if idx > 0:
                    plat_name += f"_{idx}"
                registry.register(RssCrawler(
                    _client(host, timeout, plat_name, max_response_bytes),
                    feed_url, platform=plat_name
                ))
    return registry
