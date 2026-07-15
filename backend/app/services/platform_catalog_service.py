from __future__ import annotations


PLATFORM_CATALOG = [
    {"code": "bilibili", "platform": "B站", "type": "social", "official_url": "https://www.bilibili.com", "search_url": "https://search.bilibili.com/all?keyword={keyword}", "crawler_supported": True, "comment_supported": True, "requires_key": False},
    {"code": "weibo", "platform": "微博", "type": "social", "official_url": "https://weibo.com", "search_url": "https://s.weibo.com/weibo?q={keyword}", "crawler_supported": True, "comment_supported": True, "requires_key": True},
    {"code": "zhihu", "platform": "知乎", "type": "social", "official_url": "https://www.zhihu.com", "search_url": "https://www.zhihu.com/search?q={keyword}", "crawler_supported": True, "comment_supported": True, "requires_key": True},
    {"code": "xiaohongshu", "platform": "小红书", "type": "social", "official_url": "https://www.xiaohongshu.com", "search_url": "https://www.xiaohongshu.com/search_result?keyword={keyword}", "crawler_supported": True, "comment_supported": True, "requires_key": True},
    {"code": "douyin", "platform": "抖音", "type": "social", "official_url": "https://www.douyin.com", "search_url": "https://www.douyin.com/search/{keyword}", "crawler_supported": True, "comment_supported": True, "requires_key": True},
    {"code": "baidu", "platform": "百度搜索", "type": "search", "official_url": "https://www.baidu.com", "search_url": "https://www.baidu.com/s?wd={keyword}", "crawler_supported": True, "comment_supported": False, "requires_key": True},
    {"code": "mainstream_news", "platform": "主流新闻网站", "type": "news_group", "official_url": "https://www.people.com.cn", "search_url": "https://search.people.cn/s?keyword={keyword}", "crawler_supported": True, "comment_supported": True, "requires_key": False},
    {"code": "news_people", "platform": "人民网", "type": "news", "official_url": "https://www.people.com.cn", "search_url": "https://search.people.cn/s?keyword={keyword}", "crawler_supported": True, "comment_supported": False, "requires_key": False},
    {"code": "news_36kr", "platform": "36氪", "type": "news", "official_url": "https://36kr.com", "search_url": "https://36kr.com/search/articles/{keyword}", "crawler_supported": True, "comment_supported": False, "requires_key": False},
    {"code": "news_thepaper", "platform": "澎湃新闻", "type": "news", "official_url": "https://www.thepaper.cn", "search_url": "https://www.thepaper.cn/searchResult?id={keyword}", "crawler_supported": True, "comment_supported": True, "requires_key": False},
    {"code": "news_infoq", "platform": "InfoQ", "type": "news", "official_url": "https://www.infoq.cn", "search_url": "https://www.infoq.cn/search.action?queryString={keyword}", "crawler_supported": True, "comment_supported": False, "requires_key": False},
    {"code": "news_sspai", "platform": "少数派", "type": "news", "official_url": "https://sspai.com", "search_url": "https://sspai.com/search/post/{keyword}", "crawler_supported": True, "comment_supported": True, "requires_key": False},
]


def list_platform_catalog() -> list[dict]:
    return [dict(item) for item in PLATFORM_CATALOG]


def platform_codes() -> set[str]:
    return {item["code"] for item in PLATFORM_CATALOG}


__all__ = ["list_platform_catalog", "platform_codes"]
