"""通用新闻爬虫 — 百度新闻搜索 + trafilatura 正文提取

实现项目需求规格说明书的"网络爬虫实现对主流新闻网站、社交平台中的新闻事件及舆论采集"。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote

from app.crawler.base import CrawlRequest, RawDocument


class NewsCrawler:
    """百度新闻搜索 + trafilatura 提取正文。

    两步：① 百度新闻搜索获取 URL 列表 → ② trafilatura 从每个 URL 提取正文。
    无 API Key 依赖，走公开网页抓取。
    """
    platform = "baidu_news"

    def __init__(self, client, user_agent: str | None = None):
        self.client = client
        self._ua = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "Chrome/126.0.0.0 Safari/537.36"
        )

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        keyword = request.keyword or ""
        limit = min(20, max(1, request.limit))
        html = self._search(keyword)
        if not html:
            return []

        urls = self._extract_urls(html)
        if not urls:
            return []

        documents = []
        for url in urls[:limit]:
            try:
                doc = self._fetch_article(url)
                if doc and len(doc.raw_content or "") > 50:
                    documents.append(doc)
            except Exception:
                continue
        return documents

    def _search(self, keyword: str) -> str | None:
        """用 Playwright 渲染百度新闻搜索结果页，获取完整 HTML。"""
        try:
            from playwright.sync_api import sync_playwright
            search_url = f"https://www.baidu.com/s?wd={quote(keyword)}&tn=news&rtt=1"
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                page = browser.new_page()
                page.goto(search_url, timeout=15000, wait_until="networkidle")
                html = page.content()
                browser.close()
                return html
        except Exception:
            return None

    def _extract_urls(self, html: str) -> list[str]:
        """从百度新闻搜索结果中提取文章 URL。"""
        urls = []
        seen = set()
        for pattern in [
            r'href="(https?://(?!www\.baidu\.com|.*\.baidu\.com|.*\.bdimg\.com|.*\.bcebos\.com)[^"]+)"',
            r'href="(https?://(?!.*baidu)[^"]+)"',
        ]:
            for match in re.finditer(pattern, html):
                url = match.group(1)
                if any(s in url.lower() for s in (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".ttf", ".ico", "javascript:", "mailto:")):
                    continue
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
        return urls[:20]

    def _fetch_article(self, url: str) -> RawDocument | None:
        """用 trafilatura 从 URL 提取正文、标题、时间、作者。"""
        try:
            import trafilatura
            downloaded = trafilatura.fetch_url(url, timeout=15)
            if not downloaded:
                return None

            result = trafilatura.extract(
                downloaded,
                output_format="json",
                with_metadata=True,
                include_title=True,
                include_author=True,
                include_date=True,
                url=url,
            )
            if not result:
                return None

            import json
            data = json.loads(result)
            # trafilatura JSON 格式: {"title": ..., "text": ..., "author": ..., "date": ...}
            title = data.get("title") or ""
            text = data.get("text") or ""
            author = data.get("author") or ""
            pub_date = data.get("date") or ""

            if len(text) < 100:
                return None

            # 生成 source_article_id
            import hashlib
            aid = hashlib.md5(url.encode()).hexdigest()[:16]

            return RawDocument(
                platform=self.platform,
                source_url=url,
                source_article_id=aid,
                title=_clean_title(title),
                raw_content=text[:5000],
                source_type="news",
                author=author or "新闻来源",
                publish_time=pub_date or None,
                content_type="text",
            )
        except Exception:
            return None


def _clean_title(title: str) -> str:
    """清洗标题中的特殊字符和来源标记。"""
    title = title.strip()
    # 去掉末尾的来源标记 " - 新华网" " _ 光明网"
    title = re.sub(r'\s*[-_]\s*(新华网|人民网|央视网|中国新闻网|澎湃新闻|环球网|'
                   r'新浪新闻|网易新闻|腾讯新闻|搜狐新闻|凤凰网|光明网|'
                   r'经济日报|每日经济新闻|第一财经|证券时报|'
                   r'BBC|CNN|Reuters|Bloomberg).*$', '', title)
    # 截断过长标题
    if len(title) > 200:
        title = title[:197] + "..."
    return title
