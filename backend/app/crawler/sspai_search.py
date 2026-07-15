"""少数派站内搜索爬虫 -- 文章列表API + 详情页提取 + 关键词过滤"""
from __future__ import annotations

import hashlib
import re

from app.crawler.base import CrawlRequest, RawDocument
from app.crawler.rss import _matches_keyword


class SspaiSearchCrawler:
    platform = "news_sspai"

    def __init__(self, client, min_content_length: int = 50):
        self.client = client
        self._min = min_content_length

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        keyword = request.keyword or ""
        limit = min(20, max(1, request.limit))

        # 1. 从文章列表API获取近期文章
        articles = self._list_articles(limit * 2)
        if not articles:
            return []

        # 2. 获取详情页正文，过滤关键词
        documents = []
        for a in articles:
            if len(documents) >= limit:
                break
            # 标题预过滤：有搜索词时跳过不相关文章
            title = a.get("title") or ""
            if keyword and not _matches_keyword(title, keyword):
                continue
            try:
                doc = self._fetch_detail(a, keyword)
                if doc:
                    documents.append(doc)
            except Exception:
                continue
        return documents

    def _list_articles(self, limit: int = 30) -> list[dict]:
        try:
            resp = self.client.get_json(
                f"https://sspai.com/api/v1/articles?offset=0&limit={limit}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            return resp.get("list") or []
        except Exception:
            return []

    def _fetch_detail(self, article: dict, keyword: str) -> RawDocument | None:
        aid = article.get("id")
        if not aid:
            return None
        try:
            resp = self.client.get_json(
                f"https://sspai.com/api/v1/articles/{aid}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            data = resp.get("article") or resp
            title = data.get("title") or article.get("title") or ""
            html_body = data.get("content") or data.get("body") or ""
            text = re.sub(r"<[^>]+>", "", html_body).strip()

            if len(text) < self._min:
                return None

            url = f"https://sspai.com/post/{aid}"
            return RawDocument(
                platform=self.platform,
                source_url=url,
                source_article_id=str(aid),
                title=title,
                raw_content=text[:5000],
                source_type="news",
                author=str(data.get("author") or ""),
                publish_time=str(data.get("released_at") or article.get("released_at") or ""),
                content_type="html",
                raw_json={"discovery_source": "site_api", "content_quality": "full_text"},
            )
        except Exception:
            return None
