from typing import Any
import re, html
from urllib.parse import urlsplit
from app.crawler.comments import RawComment
from app.crawler.http import HttpClient

COMMENT_ENDPOINTS = {
    "weibo": ("GET", "/api/v1/weibo/web/fetch_post_comments"),
    "douyin": ("GET", "/api/v1/douyin/web/fetch_video_comments"),
    "zhihu": ("GET", "/api/v1/zhihu/web/fetch_comment_v5"),
    "xiaohongshu": ("GET", "/api/v1/xiaohongshu/app_v2/get_note_comments"),
}
REPLY_ENDPOINTS = {
    "weibo": "/api/v1/weibo/web/fetch_comment_replies",
    "zhihu": "/api/v1/zhihu/web/fetch_sub_comment_v5",
    "douyin": "/api/v1/douyin/web/fetch_video_comment_replies",
    "xiaohongshu": "/api/v1/xiaohongshu/app_v2/get_note_sub_comments",
}

def _first_list(value: Any) -> list[dict]:
    if isinstance(value, list): return [x for x in value if isinstance(x, dict)]
    if not isinstance(value, dict): return []
    for key in ("comments", "data", "items", "replies", "comment_list"):
        rows = _first_list(value.get(key))
        if rows: return rows
    return []

class TikHubCommentAdapter:
    def __init__(self, platform, api_key, base_url="https://api.tikhub.io", timeout=30, client=None):
        if platform not in COMMENT_ENDPOINTS: raise ValueError(f"unsupported comment platform: {platform}")
        self.platform, self.api_key, self.base_url, self.timeout = platform, api_key, base_url.rstrip('/'), timeout
        host = urlsplit(self.base_url).hostname or "api.tikhub.io"
        self.client = client or HttpClient(allowed_hosts={host}, timeout=timeout, max_attempts=3, platform=f"{platform}_comments")

    def _request(self, source_id, cursor):
        _, path = COMMENT_ENDPOINTS[self.platform]
        if self.platform == "weibo":
            params = {"post_id": source_id, "mid": source_id, "max_id": "" if cursor == 0 else cursor, "max_id_type": 0}
        elif self.platform == "zhihu":
            params = {"answer_id": source_id, "limit": "20", "offset": "" if cursor == 0 else str(cursor), "order_by": "score"}
        elif self.platform == "xiaohongshu":
            params = {"note_id": source_id, "share_text": "", "cursor": "" if cursor == 0 else str(cursor), "index": 0, "pageArea": "UNFOLDED", "sort_strategy": "latest_v2"}
        else:
            params = {"aweme_id": source_id, "cursor": cursor, "count": 20}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        return self.client.get_json(f"{self.base_url}{path}", params=params, headers=headers)

    def fetch(self, source_id, limit=50, reply_limit=20):
        if not self.api_key or not source_id: return []
        output, cursor = [], 0
        while len(output) < limit:
            payload = self._request(source_id, cursor)
            rows = _first_list(payload.get("data", payload))
            if not rows: break
            for item in rows:
                raw = self._map(item)
                if raw.content and raw.source_comment_id:
                    output.append(raw)
                    if raw.replies_count and reply_limit:
                        output.extend(self.fetch_replies(source_id, raw.source_comment_id, min(reply_limit, limit - len(output))))
                if len(output) >= limit: break
            data = payload.get("data") or {}
            next_cursor = data.get("cursor") or data.get("next_cursor") or data.get("max_id")
            has_more = data.get("has_more", data.get("has_more_comments", bool(next_cursor)))
            if not has_more or next_cursor in (None, cursor): break
            cursor = next_cursor
        return output[:limit]

    def fetch_replies(self, source_id, comment_id, limit=20):
        if limit <= 0: return []
        path = REPLY_ENDPOINTS[self.platform]
        if self.platform == "weibo": params = {"cid": comment_id, "max_id": 0}
        elif self.platform == "zhihu": params = {"comment_id": comment_id, "limit": str(min(limit, 20)), "offset": "", "order_by": "score"}
        elif self.platform == "douyin": params = {"item_id": source_id, "comment_id": comment_id, "cursor": 0, "count": min(limit, 20)}
        else: params = {"note_id": source_id, "share_text": "", "comment_id": comment_id, "cursor": "", "index": 1}
        payload = self.client.get_json(f"{self.base_url}{path}", params=params, headers={"Authorization": f"Bearer {self.api_key}"})
        rows = _first_list(payload.get("data", payload))
        output = []
        for item in rows[:limit]:
            raw = self._map(item)
            raw.parent_source_comment_id = str(comment_id)
            if raw.content and raw.source_comment_id: output.append(raw)
        return output

    def _map(self, item):
        user = item.get("user") or item.get("member") or item.get("author") or {}
        content = item.get("text") or item.get("content") or item.get("message") or item.get("content_text") or ""
        if isinstance(content, dict): content = content.get("message") or content.get("text") or ""
        content = re.sub(r"<[^>]+>", "", html.unescape(str(content))).strip()
        return RawComment(platform=self.platform, source_comment_id=str(item.get("id") or item.get("comment_id") or item.get("cid") or item.get("rpid") or ""), parent_source_comment_id=str(item.get("parent_id")) if item.get("parent_id") else None, content=content, author=user.get("name") or user.get("nickname") or user.get("screen_name") or user.get("uname"), likes_count=int(item.get("likes") or item.get("like_count") or item.get("digg_count") or item.get("like") or 0), replies_count=int(item.get("reply_count") or item.get("sub_comment_count") or 0), raw_json=item)
