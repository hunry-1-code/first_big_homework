from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from app.crawler.base import CrawlRequest, RawDocument
from app.crawler.errors import CrawlerError, raise_for_api_error


def _plain(value: str | None) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(value or "")).strip()


class BilibiliCrawler:
    platform = "bilibili"

    def __init__(self, client, base_url: str = "https://api.bilibili.com"):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self._device_initialized = False
        self._device_cookie = ""

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
            ),
            "Referer": "https://search.bilibili.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

    def _initialize_public_device(self) -> None:
        if self._device_initialized:
            return
        try:
            payload = self.client.get_json(
                f"{self.base_url}/x/frontend/finger/spi",
                headers=self._headers(),
            )
            raise_for_api_error(payload, self.platform)
        except CrawlerError:
            return
        data = payload.get("data") or {}
        buvid3 = data.get("b_3")
        buvid4 = data.get("b_4")
        cookies = []
        session = getattr(self.client, "session", None)
        cookie_jar = getattr(session, "cookies", None)
        for name, value in (("buvid3", buvid3), ("buvid4", buvid4)):
            if not value:
                continue
            cookies.append(f"{name}={value}")
            if cookie_jar is not None:
                cookie_jar.set(name, value, domain=".bilibili.com")
        self._device_cookie = "; ".join(cookies)
        self._device_initialized = True

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        self._initialize_public_device()
        headers = self._headers()
        if self._device_cookie:
            headers["Cookie"] = self._device_cookie
        payload = self.client.get_json(
            f"{self.base_url}/x/web-interface/search/type",
            headers=headers,
            params={
                "search_type": "article",
                "keyword": request.keyword or "",
                "page": request.extra.get("page", 1),
                "page_size": min(50, request.limit),
            },
        )
        raise_for_api_error(payload, self.platform)
        items = (payload.get("data") or {}).get("result") or []
        documents = []
        for item in items[: request.limit]:
            art_id = str(item.get("id") or item.get("cvid") or item.get("bvid") or item.get("aid") or "")
            if not art_id:
                continue
            publish_time = item.get("pubdate") or item.get("ctime")
            if isinstance(publish_time, (int, float)):
                publish_time = datetime.fromtimestamp(publish_time, timezone.utc).isoformat()
            documents.append(
                RawDocument(
                    platform=self.platform,
                    source_url=f"https://www.bilibili.com/read/cv{art_id}" if str(item.get('id')).isdigit() else f"https://www.bilibili.com/video/{art_id}",
                    source_article_id=art_id,
                    title=_plain(item.get("title")),
                    raw_content=_plain(item.get("description")),
                    source_type="social",
                    author=item.get("author"),
                    author_id=str(item.get("mid")) if item.get("mid") is not None else None,
                    publish_time=publish_time,
                    likes_count=item.get("favorites"),
                    comments_count=item.get("review"),
                    views_count=item.get("play"),
                    content_type="text",
                    raw_json=item,
                )
            )
        return documents
