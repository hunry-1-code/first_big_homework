from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.crawler.base import CrawlRequest, RawDocument
from app.crawler.errors import raise_for_api_error


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities from text."""
    import html
    text = re.sub(r"<[^>]+>", "", text or "")
    text = html.unescape(text)
    return text.strip()


ENDPOINTS = {
    "weibo": ("GET", "/api/v1/weibo/web/fetch_search"),
    "xiaohongshu": ("GET", "/api/v1/xiaohongshu/app_v2/search_notes"),
    "douyin": ("POST", "/api/v1/douyin/search/fetch_general_search_v1"),
}


def _nested(data: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _first_list(payload: dict[str, Any], paths: list[tuple[str, ...]]) -> list[dict[str, Any]]:
    for path in paths:
        value = _nested(payload, *path)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


class TikHubCrawler:
    def __init__(
        self,
        client,
        api_key: str,
        platform: str,
        base_url: str = "https://api.tikhub.io",
    ) -> None:
        if platform not in ENDPOINTS:
            raise ValueError(f"unsupported TikHub platform: {platform}")
        self.client = client
        self.api_key = api_key
        self.platform = platform
        self.base_url = base_url.rstrip("/")

    def crawl(self, request: CrawlRequest) -> list[RawDocument]:
        method, path = ENDPOINTS[self.platform]
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if method == "GET":
            params={"keyword": request.keyword or "", "page": request.extra.get("page", 1)}
            if self.platform == "xiaohongshu":
                params.update(
                    sort_type=request.extra.get("sort_type", "general"),
                    note_type=request.extra.get("note_type", "不限"),
                    time_filter=request.extra.get("time_filter", "不限"),
                    search_id=request.extra.get("search_id", ""),
                    search_session_id=request.extra.get("search_session_id", ""),
                    source=request.extra.get("source", "explore_feed"),
                    ai_mode=request.extra.get("ai_mode", 0),
                )
            payload = self.client.get_json(
                f"{self.base_url}{path}",
                headers=headers,
                params=params,
            )
        else:
            payload = self.client.post_json(
                f"{self.base_url}{path}",
                headers={**headers, "Content-Type": "application/json"},
                json={
                    "keyword": request.keyword or "",
                    "cursor": request.extra.get("cursor", 0),
                    "sort_type": "0",
                    "publish_time": "0",
                    "filter_duration": "0",
                    "content_type": "0",
                    "search_id": request.extra.get("search_id", ""),
                    "backtrace": request.extra.get("backtrace", ""),
                },
            )
        raise_for_api_error(payload, self.platform)
        items = self._items(payload)
        documents = [self._map_item(item) for item in items[: request.limit]]
        return [document for document in documents if document is not None]

    def _items(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if self.platform == "weibo":
            items = _first_list(
                payload,
                [("data", "data", "statuses"), ("data", "statuses"), ("data", "data", "cards")],
            )
            flattened = []
            for item in items:
                if isinstance(item.get("mblog"), dict):
                    flattened.append(item["mblog"])
                    continue
                card_group = item.get("card_group")
                if isinstance(card_group, list):
                    flattened.extend(
                        entry["mblog"]
                        for entry in card_group
                        if isinstance(entry, dict) and isinstance(entry.get("mblog"), dict)
                    )
                    continue
                flattened.append(item)
            return flattened
        if self.platform == "xiaohongshu":
            return _first_list(
                payload,
                [("data", "data", "items"), ("data", "items"), ("data", "data", "notes")],
            )
        return _first_list(
            payload,
            [("data", "data"), ("data", "data", "data"), ("data", "aweme_list")],
        )

    def _map_item(self, item: dict[str, Any]) -> RawDocument | None:
        if self.platform == "weibo":
            user = item.get("user") or {}
            item_id = str(item.get("id") or item.get("mid") or "")
            return RawDocument(
                platform="weibo",
                source_url=item.get("url") or f"https://weibo.com/{user.get('id', 'u')}/{item_id}",
                source_article_id=item_id,
                title=_strip_html(item.get("text_raw") or item.get("text") or "微博内容"),
                raw_content=_strip_html(item.get("text_raw") or item.get("text") or ""),
                source_type="social",
                author=user.get("screen_name"),
                author_id=str(user.get("id")) if user.get("id") is not None else None,
                author_followers=user.get("followers_count"),
                author_verified=user.get("verified"),
                publish_time=item.get("created_at"),
                likes_count=item.get("attitudes_count"),
                comments_count=item.get("comments_count"),
                reposts_count=item.get("reposts_count"),
                raw_json=item,
            )
        if self.platform == "xiaohongshu":
            card = item.get("note_card") or item
            user = card.get("user") or item.get("user") or {}
            item_id = str(item.get("id") or card.get("note_id") or card.get("id") or "")
            interact = card.get("interact_info") or {}
            title = _strip_html(card.get("display_title") or card.get("title") or "")
            content = _strip_html(card.get("desc") or title)
            if not item_id and not content:
                return None
            return RawDocument(
                platform="xiaohongshu",
                source_url=item.get("url") or f"https://www.xiaohongshu.com/explore/{item_id}",
                source_article_id=item_id,
                title=title or "小红书笔记",
                raw_content=content,
                source_type="social",
                author=user.get("nickname"),
                author_id=str(user.get("user_id")) if user.get("user_id") is not None else None,
                likes_count=interact.get("liked_count") or card.get("liked_count"),
                comments_count=interact.get("comment_count") or card.get("comment_count"),
                raw_json=item,
            )
        aweme = item.get("aweme_info") or item
        author = aweme.get("author") or {}
        stats = aweme.get("statistics") or {}
        item_id = str(aweme.get("aweme_id") or aweme.get("id") or "")
        publish_time = aweme.get("create_time")
        if isinstance(publish_time, (int, float)):
            publish_time = datetime.fromtimestamp(publish_time, timezone.utc).isoformat()
        return RawDocument(
            platform="douyin",
            source_url=aweme.get("share_url") or f"https://www.douyin.com/video/{item_id}",
            source_article_id=item_id,
            title=_strip_html(aweme.get("desc") or "抖音内容"),
            raw_content=_strip_html(aweme.get("desc") or ""),
            source_type="social",
            author=author.get("nickname"),
            author_id=str(author.get("uid")) if author.get("uid") is not None else None,
            author_followers=author.get("follower_count"),
            publish_time=publish_time,
            likes_count=stats.get("digg_count"),
            comments_count=stats.get("comment_count"),
            reposts_count=stats.get("share_count"),
            views_count=stats.get("play_count"),
            raw_json=item,
        )
