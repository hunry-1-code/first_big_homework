from __future__ import annotations

import time
from typing import Any

from app.crawler.base import CrawlRequest, RawDocument
from app.crawler.errors import raise_for_api_error


def _find_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    current: Any = payload
    for key in ("data", "data"):
        if isinstance(current, dict) and key in current:
            current = current[key]
    if isinstance(current, list):
        return [item for item in current if isinstance(item, dict)]
    if isinstance(payload.get("data"), list):
        return [item for item in payload["data"] if isinstance(item, dict)]
    return []


class ZhihuSearchCrawler:
    platform = "zhihu"

    def __init__(self, client, access_secret: str, base_url: str = "https://developer.zhihu.com"):
        self.client = client
        self.access_secret = access_secret
        self.base_url = base_url.rstrip("/")

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        payload = self.client.get_json(
            f"{self.base_url}/api/v1/content/zhihu_search",
            headers=self._headers(),
            params={"Query": request.keyword or "", "Count": min(10, request.limit)},
        )
        raise_for_api_error(payload, self.platform)
        return [self._map_item(item, "social") for item in _find_items(payload)[: request.limit]]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_secret}",
            "X-Request-Timestamp": str(int(time.time())),
            "Content-Type": "application/json",
        }

    def _map_item(self, item: dict[str, Any], source_type: str) -> RawDocument:
        url = item.get("url") or item.get("link") or ""
        return RawDocument(
            platform=self.platform,
            source_url=url,
            source_article_id=str(item.get("id") or item.get("content_id") or url),
            title=item.get("title") or item.get("question_title") or "",
            raw_content=item.get("summary") or item.get("excerpt") or item.get("content") or "",
            source_type=source_type,
            author=item.get("author_name") or (item.get("author") or {}).get("name") if isinstance(item.get("author"), dict) else item.get("author_name"),
            publish_time=item.get("edit_time") or item.get("updated_time") or item.get("created_time"),
            likes_count=item.get("vote_up_count"),
            comments_count=item.get("comment_count"),
            content_type="text",
            raw_json=item,
        )


class ZhihuHotCrawler(ZhihuSearchCrawler):
    platform = "zhihu_hot"

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        payload = self.client.get_json(
            f"{self.base_url}/api/v1/content/hot_list",
            headers=self._headers(),
            params={"Limit": min(30, request.limit)},
        )
        raise_for_api_error(payload, self.platform)
        return [self._map_item(item, "hotlist") for item in _find_items(payload)[: request.limit]]
