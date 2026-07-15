"""通用新闻爬虫 -- 千帆搜索发现 + trafilatura 正文提取

发现策略（优先级）:
1. 千帆 Web Search API (已配置, 首选)
2. Playwright 渲染百度新闻页 (降级)

正文提取: trafilatura 通用提取
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import quote

from app.crawler.base import CrawlRequest, RawDocument


class NewsCrawler:
    """千帆搜索 + trafilatura 正文提取。"""
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

        urls = self._discover_qianfan(keyword, limit)
        if not urls:
            urls = self._discover_playwright(keyword)
        if not urls:
            return []

        documents = []
        for url in urls[:limit]:
            try:
                doc = self._fetch_article(url, keyword)
                if doc and len(doc.raw_content or "") > 50:
                    documents.append(doc)
            except Exception:
                continue
        return documents

    def _discover_qianfan(self, keyword: str, limit: int) -> list[str]:
        """千帆 Web Search 发现 URL。"""
        try:
            from flask import current_app
            from app.crawler.qianfan import QianfanSearchCrawler

            key = current_app.config.get("QIANFAN_API_KEY", "")
            if not key:
                return []
            base = current_app.config.get("QIANFAN_API_BASE_URL", "")
            path = current_app.config.get("QIANFAN_WEB_SEARCH_PATH", "")
            top_k = current_app.config.get("QIANFAN_WEB_SEARCH_TOP_K", 50)

            crawler = QianfanSearchCrawler(self.client, key, base, path, top_k)
            docs = crawler.crawl(CrawlRequest(
                platform="baidu", keyword=keyword, limit=limit, mode="search"
            ))
            return [d.source_url for d in docs if d.source_url] if docs else []
        except Exception:
            return []

    def _discover_playwright(self, keyword: str) -> list[str]:
        """Playwright 渲染百度新闻页（降级方案）。"""
        try:
            from playwright.sync_api import sync_playwright
            url = f"https://www.baidu.com/s?wd={quote(keyword)}&tn=news&rtt=1"
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                page = browser.new_page()
                page.goto(url, timeout=15000, wait_until="networkidle")
                html = page.content()
                browser.close()
                return self._extract_urls(html)
        except Exception:
            return []

    def _extract_urls(self, html: str) -> list[str]:
        urls = []
        seen = set()
        for pattern in [
            r'href="(https?://(?!www\.baidu\.com|.*\.baidu\.com|.*\.bdimg\.com|.*\.bcebos\.com)[^"]+)"',
            r'href="(https?://(?!.*baidu)[^"]+)"',
        ]:
            for m in re.finditer(pattern, html):
                u = m.group(1)
                if any(s in u.lower() for s in (".css",".js",".png",".jpg",".jpeg",".gif",".svg",".woff",".ttf",".ico","javascript:","mailto:")):
                    continue
                if u not in seen:
                    seen.add(u)
                    urls.append(u)
        return urls[:20]

    def _fetch_article(self, url: str, keyword: str = "") -> RawDocument | None:
        """trafilatura 从 URL 提取正文。"""
        try:
            import trafilatura, json
            downloaded = trafilatura.fetch_url(url, timeout=15)
            if not downloaded:
                return None
            result = trafilatura.extract(downloaded, output_format="json",
                with_metadata=True, include_title=True, include_author=True,
                include_date=True, url=url)
            if not result:
                return None
            data = json.loads(result)
            title = data.get("title") or ""
            text = data.get("text") or ""
            author = data.get("author") or ""
            pub_date = data.get("date") or ""
            aid = hashlib.md5(url.encode()).hexdigest()[:16]

            quality = "full_text" if len(text) >= 200 else "summary_only" if len(text) >= 50 else "empty_description"
            return RawDocument(
                platform=self.platform, source_url=url, source_article_id=aid,
                title=_clean_title(title), raw_content=text[:5000],
                source_type="news", author=author or "新闻来源",
                publish_time=pub_date or None, content_type="text",
                raw_json={"discovery_source": "qianfan" if self._discover_qianfan else "playwright",
                          "content_quality": quality},
            )
        except Exception:
            return None


def _clean_title(title: str) -> str:
    title = title.strip()
    title = re.sub(r'\s*[-_]\s*(新华网|人民网|央视网|中国新闻网|澎湃新闻|环球网|'
                   r'新浪新闻|网易新闻|腾讯新闻|搜狐新闻|凤凰网|光明网|'
                   r'经济日报|每日经济新闻|第一财经|证券时报|'
                   r'BBC|CNN|Reuters|Bloomberg).*$', '', title)
    if len(title) > 200:
        title = title[:197] + "..."
    return title
