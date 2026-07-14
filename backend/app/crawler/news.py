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
        import requests as req
        import time as _time
        keyword = request.keyword or ""
        limit = min(20, max(1, request.limit))
        session = req.Session()
        session.headers.update({
            "User-Agent": self._ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

        # ① 先访问百度首页获取 BAIDUID Cookie（反爬必须）
        try:
            session.get("https://www.baidu.com/", timeout=10)
            _time.sleep(1.5)  # 模拟人类浏览间隔
        except Exception:
            pass

        # ② 搜索百度新闻
        search_url = f"https://www.baidu.com/s?wd={quote(keyword)}&tn=news&rtt=1"
        try:
            resp = session.get(search_url, timeout=15, allow_redirects=True)
            html = resp.text
        except Exception:
            return []

        # 提取新闻 URL
        urls = self._extract_urls(html, keyword)
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

    def _extract_urls(self, html: str, keyword: str) -> list[str]:
        """从百度新闻搜索结果中提取文章 URL。"""
        urls = []
        seen = set()
        # 百度新闻页面中的真实链接：匹配 href 中的非百度域名 URL
        for pattern in [
            r'href="(https?://(?!www\.baidu\.com|.*\.baidu\.com|.*\.bdimg\.com|.*\.bcebos\.com)[^"]+)"',
            r'href="(https?://(?!.*baidu)[^"]+)"',
        ]:
            for match in re.finditer(pattern, html):
                url = match.group(1)
                # 过滤静态资源和无关链接
                if any(skip in url.lower() for skip in (
                    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg",
                    ".woff", ".ttf", ".ico", "javascript:", "mailto:",
                )):
                    continue
                # 过滤搜索引擎和广告链接
                if any(skip in url for skip in (
                    "bing.com", "google.com", "sogou.com", "so.com",
                    "doubleclick", "advertisement",
                )):
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
